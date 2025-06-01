#!/usr/bin/env python3
"""
Main pipeline orchestrator for the newspaper downloader and emailer system.
"""

import os
import json
from datetime import date, timedelta, datetime
import time

import website
import storage
import email_sender
import config # Assuming config.py has been enhanced
import thumbnail # Assuming thumbnail.py has been enhanced

# Logging setup
logger = config.get_logger(__name__) # Use standardized logger
DATE_FORMAT = '%Y-%m-%d' 
FILENAME_TEMPLATE = "{date}_newspaper.{format}" 
THUMBNAIL_FILENAME_TEMPLATE = "{date}_thumbnail.{format}"
RETENTION_DAYS = 7 
STATUS_FILE = 'pipeline_status.json'

# --- Status Update Function (Consolidated) ---
def update_status(step, status, message=None, percent=None, eta=None, explainer=None):
    """Enhanced status update for UI polling."""
    status_obj = {
        'step': step,
        'status': status, # 'pending', 'in_progress', 'success', 'error', 'skipped'
        'message': message or '',
        'timestamp': datetime.now().isoformat(),
        'percent': percent,
        'eta': eta,
        'explainer': explainer
    }
    try:
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status_obj, f)
    except IOError as e: 
        logger.warning("Could not write status file '%s': %s", STATUS_FILE, e)
    except Exception as e:
        logger.exception("Unexpected error writing status file '%s': %s", STATUS_FILE, e)


# --- Helper Functions ---
def get_last_7_days_status():
    """Checks local download directory for papers to determine recent readiness."""
    logger.info("Checking status of downloads for the last 7 days.")
    today = datetime.now().date() # Use datetime.now().date() for consistency
    days_to_check = 7
    statuses = []
    
    # These will use defaults if config hasn't been loaded yet, or actual values if it has.
    # This function is primarily for UI/prompting, so slight initial inaccuracy is acceptable.
    current_date_format = config.config.get(('general', 'date_format'), DATE_FORMAT)
    download_dir = config.config.get(('paths', 'download_dir'), 'downloads')

    for i in range(days_to_check):
        current_date = today - timedelta(days=i)
        date_str = current_date.strftime(current_date_format)
        
        # Check for either PDF or HTML format for the given date
        # Using the global FILENAME_TEMPLATE which might be updated by config later
        pdf_expected_name = FILENAME_TEMPLATE.format(date=date_str, format="pdf")
        html_expected_name = FILENAME_TEMPLATE.format(date=date_str, format="html")
        
        pdf_path = os.path.join(download_dir, pdf_expected_name)
        html_path = os.path.join(download_dir, html_expected_name)

        if os.path.exists(pdf_path) or os.path.exists(html_path):
            statuses.append({'date': date_str, 'status': 'ready'})
        else:
            statuses.append({'date': date_str, 'status': 'missing'})
            
    statuses.reverse() 
    logger.debug("Last 7 days status: %s", statuses)
    return statuses

def get_past_papers_from_storage(target_date: date, days: int):
    """Gets links to newspapers from cloud storage for the specified number of past days."""
    logger.info("Retrieving links for past %d paper(s) from cloud storage, up to %s.", days, target_date.strftime(DATE_FORMAT))
    past_papers_links = []
    current_date_format = config.config.get(('general', 'date_format'), DATE_FORMAT)

    try:
        all_files = storage.list_storage_files()
        if not all_files:
            logger.warning("No files found in cloud storage.")
            return []

        dated_files = []
        for filename in all_files:
            try:
                date_str = filename.split('_')[0]
                file_date = datetime.strptime(date_str, current_date_format).date()
                if "newspaper" in filename and (filename.endswith(".pdf") or filename.endswith(".html")):
                    dated_files.append((file_date, filename))
            except (ValueError, IndexError):
                logger.debug("Could not parse date from filename: '%s'. Skipping.", filename)
        
        dated_files.sort(key=lambda x: x[0], reverse=True)

        unique_dates_found = {}
        for file_date, filename in dated_files:
            if file_date <= target_date: 
                if file_date not in unique_dates_found: 
                     if len(unique_dates_found) < days: 
                        try:
                            url = storage.get_file_url(filename)
                            if url:
                                unique_dates_found[file_date] = (file_date.strftime(current_date_format), url)
                            else:
                                logger.warning("Could not get URL for stored file: '%s'", filename)
                        except Exception as url_e:
                            logger.exception("Error getting URL for stored file '%s': %s", filename, url_e)
                if len(unique_dates_found) >= days:
                    break 
        
        past_papers_links = sorted(list(unique_dates_found.values()), key=lambda x: x[0], reverse=True)
        logger.info("Collected %d past paper links from storage.", len(past_papers_links))
        return past_papers_links
    except Exception as e:
        logger.exception("Error retrieving past papers from storage: %s", e)
        return []

def cleanup_old_files_main(target_date: date, dry_run: bool):
    """Wrapper for cleanup_old_files to fetch retention_days from config."""
    # Uses global RETENTION_DAYS which is updated after config load
    logger.info("Initiating cleanup of files older than %d days relative to %s.", RETENTION_DAYS, target_date.strftime(DATE_FORMAT))
    current_date_format = config.config.get(('general', 'date_format'), DATE_FORMAT)

    try:
        all_files = storage.list_storage_files()
        if not all_files:
            logger.info("No files found in storage, skipping cleanup.")
            return

        cutoff_date = target_date - timedelta(days=RETENTION_DAYS)
        logger.info("Files older than %s will be %sdeleted.", cutoff_date.strftime(current_date_format), "simulated for " if dry_run else "")

        deleted_count = 0
        for filename in all_files:
            try:
                date_str = filename.split('_')[0]
                file_date = datetime.strptime(date_str, current_date_format).date()
                if file_date < cutoff_date:
                    action_taken = storage.delete_from_storage(filename, dry_run=dry_run)
                    if action_taken: # True if successful or dry_run
                        deleted_count +=1
            except (ValueError, IndexError):
                logger.debug("Could not parse date from filename for cleanup: '%s'. Skipping.", filename)
        
        log_action = "Simulated deleting" if dry_run else "Deleted"
        logger.info("Cleanup complete. %s %d old file(s).", log_action, deleted_count)
    except Exception as e:
        logger.exception("Error during old file cleanup: %s", e)

# --- Main Execution Logic ---
def main(target_date_str: str | None = None, dry_run: bool = False, force_download: bool = False):
    """Main pipeline for downloading, storing, and preparing newspaper for email."""
    global DATE_FORMAT, FILENAME_TEMPLATE, THUMBNAIL_FILENAME_TEMPLATE, RETENTION_DAYS

    try:
        update_status('config_load', 'in_progress', 'Loading configuration...', percent=0)
        if not config.config.load(): 
            update_status('config_load', 'error', 'Configuration failed. Check logs.', percent=0)
            return False
        update_status('config_load', 'success', 'Configuration loaded and validated.', percent=5)

        # Update global constants from loaded config
        DATE_FORMAT = config.config.get(('general', 'date_format'), DATE_FORMAT)
        FILENAME_TEMPLATE = config.config.get(('general', 'filename_template'), FILENAME_TEMPLATE)
        THUMBNAIL_FILENAME_TEMPLATE = config.config.get(('general', 'thumbnail_filename_template'), THUMBNAIL_FILENAME_TEMPLATE)
        RETENTION_DAYS = config.config.get(('general', 'retention_days'), RETENTION_DAYS)

        update_status('date_setup', 'in_progress', 'Determining target date...', percent=10)
        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, DATE_FORMAT).date()
            except ValueError:
                logger.critical("Invalid target_date_str format: '%s'. Expected '%s'.", target_date_str, DATE_FORMAT)
                update_status('date_setup', 'error', f"Invalid date format: {target_date_str}. Use {DATE_FORMAT}.", percent=10)
                return False
        else:
            target_date = datetime.now().date() # Use datetime.now().date()
        logger.info("Processing for target date: %s", target_date.strftime(DATE_FORMAT))
        update_status('date_setup', 'success', f"Target date: {target_date.strftime('%A, %B %d, %Y')}", percent=15)

        download_dir = config.config.get(('paths', 'download_dir'), 'downloads')
        os.makedirs(download_dir, exist_ok=True)
        
        # Base path for download; website.login_and_download should append the correct extension.
        base_save_path = os.path.join(download_dir, FILENAME_TEMPLATE.format(date=target_date.strftime(DATE_FORMAT), format='').rstrip('.'))
        
        update_status('download', 'in_progress', 'Downloading newspaper...', percent=20, eta='approx. 1-2 min')
        
        download_success, download_result = website.login_and_download(
            base_url=config.config.get(('newspaper', 'url')),
            username=config.config.get(('newspaper', 'username')),
            password=config.config.get(('newspaper', 'password')),
            save_path=base_save_path, 
            target_date=target_date.strftime(DATE_FORMAT),
            dry_run=dry_run,
            force_download=force_download
        )
        
        if not download_success:
            error_msg = f"Download failed: {download_result}"
            update_status('download', 'error', error_msg, percent=20)
            logger.critical(error_msg)
            # Consider re-enabling alert email if email_sender is robust
            # email_sender.send_alert_email(subject='Newspaper Download Failed', message=error_msg, dry_run=dry_run)
            return False

        newspaper_path = download_result 
        newspaper_filename = os.path.basename(newspaper_path)
        file_format = newspaper_filename.split('.')[-1].lower() if '.' in newspaper_filename else 'unknown'

        logger.info("Newspaper downloaded successfully: '%s' (format: %s)", newspaper_path, file_format)
        update_status('download', 'success', f"Newspaper downloaded: {newspaper_filename}", percent=40)

        update_status('upload', 'in_progress', 'Uploading to cloud storage...', percent=45, eta='approx. 30 sec')
        cloud_file_url = None
        if dry_run:
            logger.info("[Dry Run] Would upload '%s' to cloud storage as '%s'.", newspaper_path, newspaper_filename)
            cloud_file_url = f"http://dry_run_cloud_storage_url/{newspaper_filename}" # Placeholder
            update_status('upload', 'success', 'Upload (simulated) complete.', percent=60)
        else:
            try:
                storage.upload_to_storage(newspaper_path, newspaper_filename)
                cloud_file_url = storage.get_file_url(newspaper_filename)
                if not cloud_file_url:
                    raise storage.ClientError("Failed to get cloud URL after upload (URL is None or empty).")
                logger.info("Successfully uploaded '%s' to cloud storage. URL: %s", newspaper_filename, cloud_file_url)
                update_status('upload', 'success', 'Upload complete!', percent=60)
            except Exception as e:
                logger.exception("Cloud storage upload failed for '%s': %s", newspaper_filename, e)
                update_status('upload', 'error', f"Upload failed: {e}", percent=45)
                return False

        update_status('thumbnail', 'in_progress', 'Generating thumbnail...', percent=65, eta='approx. 20 sec')
        thumbnail_actual_format = thumbnail.THUMBNAIL_FORMAT.lower() # e.g. 'jpeg' -> 'jpg' if needed
        if thumbnail_actual_format == 'jpeg': thumbnail_actual_format = 'jpg' # common extension
        
        thumbnail_output_filename = THUMBNAIL_FILENAME_TEMPLATE.format(date=target_date.strftime(DATE_FORMAT), format=thumbnail_actual_format)
        thumbnail_output_path = os.path.join(download_dir, thumbnail_output_filename)
        thumbnail_cloud_url = None

        if dry_run:
            logger.info("[Dry Run] Would generate thumbnail for '%s' at '%s'.", newspaper_path, thumbnail_output_path)
            thumbnail_cloud_url = f"http://dry_run_cloud_storage_url/{thumbnail_output_filename}"
            update_status('thumbnail', 'success', 'Thumbnail generation (simulated) complete.', percent=75)
        else:
            if not os.path.exists(newspaper_path):
                 logger.error("Cannot generate thumbnail, input file '%s' does not exist.", newspaper_path)
                 update_status('thumbnail', 'error', "Newspaper file missing for thumbnailing.", percent=65)
            elif file_format not in ["pdf", "html"]:
                logger.warning("Unsupported file format '%s' for thumbnail generation of '%s'. Skipping thumbnail.", file_format, newspaper_filename)
                update_status('thumbnail', 'skipped', f"Unsupported format for thumbnail: {file_format}", percent=75)
            else:
                thumb_success = thumbnail.generate_thumbnail(
                    input_path=newspaper_path, output_path=thumbnail_output_path, file_format=file_format
                )
                if thumb_success and os.path.exists(thumbnail_output_path):
                    logger.info("Thumbnail generated successfully: '%s'", thumbnail_output_path)
                    try:
                        storage.upload_to_storage(thumbnail_output_path, thumbnail_output_filename)
                        thumbnail_cloud_url = storage.get_file_url(thumbnail_output_filename)
                        if not thumbnail_cloud_url:
                             raise storage.ClientError("Failed to get thumbnail cloud URL after upload.")
                        logger.info("Thumbnail uploaded to cloud: %s", thumbnail_cloud_url)
                        update_status('thumbnail', 'success', 'Thumbnail created and uploaded!', percent=75)
                    except Exception as e:
                        logger.exception("Failed to upload thumbnail '%s': %s", thumbnail_output_filename, e)
                        update_status('thumbnail', 'error', 'Thumbnail upload failed.', percent=75)
                else:
                    logger.warning("Thumbnail generation failed for '%s'. Email will be sent without a thumbnail.", newspaper_filename)
                    update_status('thumbnail', 'error', 'Thumbnail generation failed.', percent=75)
        
        update_status('email', 'in_progress', 'Preparing email...', percent=80, eta='approx. 30 sec')
        try:
            retention_days_for_links = config.config.get(('general', 'retention_days_for_email_links'), 7)
            past_papers = get_past_papers_from_storage(target_date, days=retention_days_for_links)
            
            email_sent_or_drafted = email_sender.send_email(
                target_date=target_date,
                today_paper_url=cloud_file_url, 
                past_papers=past_papers,
                thumbnail_url=thumbnail_cloud_url,
                dry_run=dry_run
            )
            if email_sent_or_drafted:
                action_verb = "simulated sending/drafting" if dry_run else "sent/drafted"
                update_status('email', 'success', f'Email {action_verb} successfully!', percent=95)
            else:
                update_status('email', 'error', 'Failed to send/draft email. Check logs.', percent=80)
                return False
        except Exception as e:
            logger.exception("Email preparation/sending failed: %s", e)
            update_status('email', 'error', f"Email preparation failed: {e}", percent=80)
            return False

        update_status('cleanup', 'in_progress', 'Cleaning up old newspapers from cloud storage...', percent=97)
        cleanup_old_files_main(target_date, dry_run=dry_run)
        update_status('cleanup', 'success', 'Cleanup process complete.', percent=99)
        
        update_status('complete', 'success', 'Newspaper processing complete!', percent=100)
        logger.info("Daily newspaper processing for %s completed successfully.", target_date.strftime(DATE_FORMAT))
        
        if not dry_run: 
            if all(status['status'] == 'ready' for status in get_last_7_days_status()):
                logger.info("Consistently successful for the past 7 days. Consider full automation if not already set up.")
        return True

    except Exception as e: 
        final_error_msg = f"Main pipeline failed: {e}"
        logger.exception(final_error_msg)
        try: # Best effort to update status one last time
            with open(STATUS_FILE, 'r', encoding='utf-8') as f_current_status:
                current_status_data = json.load(f_current_status)
            if current_status_data.get('status') != 'error': 
                 update_status('pipeline_error', 'error', final_error_msg, percent=current_status_data.get('percent', 0))
        except Exception: # If status cannot be read or written
             update_status('pipeline_error', 'error', final_error_msg) # Default percent
        return False

if __name__ == "__main__":
    logger.info("Starting main.py directly for testing or manual execution.")
    
    # Attempt to load .env if present, for direct execution convenience
    # Loading .env and basicConfig moved to config.py setup
    # The logger obtained via config.get_logger(__name__) will be correctly configured.

    # --- Configuration for direct execution ---
    # Allow overriding target_date, dry_run, force_download via environment variables for testing
    target_date_override = os.environ.get("MAIN_PY_TARGET_DATE") # e.g., "2023-10-28"
    dry_run_override = os.environ.get("MAIN_PY_DRY_RUN", "False").lower() == "true"
    force_download_override = os.environ.get("MAIN_PY_FORCE_DOWNLOAD", "False").lower() == "true"
    
    # Use global DATE_FORMAT here, which will be updated by config.load() if main() is called.
    # If main() isn't called (e.g. syntax error before), it remains the module default, but config.load() is called first in main().
    effective_target_date_str = target_date_override if target_date_override else date.today().strftime(DATE_FORMAT)
    
    logger.info(f"Running main pipeline with: Target Date='{effective_target_date_str}', Dry Run={dry_run_override}, Force Download={force_download_override}")
    
    main_success = main(target_date_str=effective_target_date_str, 
                        dry_run=dry_run_override, 
                        force_download=force_download_override)

    if main_success:
        logger.info("main.py direct execution completed successfully.")
        exit(0)
    else:
        logger.error("main.py direct execution failed.")
        exit(1)
