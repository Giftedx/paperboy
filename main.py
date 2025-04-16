import os

import logging
import json
from datetime import date, timedelta, datetime
import time

# Import project modules
import website
import storage
import email_sender
import config

# Logging setup - BasicConfig might be called upstream in run_newspaper.py
# Ensure logger works even if run standalone (though not intended)
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# Get configuration from centralized config module
NEWSPAPER_URL = config.config.get(('newspaper', 'url'))
USERNAME = config.config.get(('newspaper', 'username'))
PASSWORD = config.config.get(('newspaper', 'password'))
EMAIL_SENDER_ADDRESS = config.config.get(('email', 'sender'))
EMAIL_RECIPIENTS = config.config.get(('email', 'recipients'), [])
EMAIL_SUBJECT_TEMPLATE = config.config.get(('email', 'subject_template'))

# Constants from configuration
RETENTION_DAYS = config.config.get(('general', 'retention_days'), 7)
DATE_FORMAT = config.config.get(('general', 'date_format'), '%Y-%m-%d')
FILENAME_TEMPLATE = "{date}_newspaper.{format}" # Use format placeholder
THUMBNAIL_FILENAME_TEMPLATE = "{date}_thumbnail.jpg"

STATUS_FILE = 'pipeline_status.json'

# --- Enhanced Status Update ---
def update_status(step, status, message=None, percent=None, eta=None, explainer=None):
    """
    Enhanced status update for UI polling.
    percent: int (0-100), progress percent
    eta: str, estimated time remaining (e.g. 'about 1 minute')
    explainer: str, optional friendly explanation for slow steps
    """
    status_obj = {
        'step': step,
        'status': status,
        'message': message or '',
        'timestamp': datetime.now().isoformat(),
        'percent': percent,
        'eta': eta,
        'explainer': explainer
    }
    try:
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status_obj, f)
    except Exception as e:
        logger.warning(f"Could not write status file: {e}")

# --- Last 7 Days At A Glance ---
def get_last_7_days_status():
    today = date.today()
    days = [today - timedelta(days=i) for i in range(7)]
    status = []
    for d in reversed(days):
        fname_pdf = f"{d.strftime(DATE_FORMAT)}_newspaper.pdf"
        fname_html = f"{d.strftime(DATE_FORMAT)}_newspaper.html"
        found = False
        for f in storage.list_storage_files():
            if f == fname_pdf or f == fname_html:
                found = True
                break
        status.append({'date': d.strftime(DATE_FORMAT), 'status': 'ready' if found else 'missing'})
    return status

def update_status(step, status, message=None):
    """
    Write the current pipeline step and status to a status file for UI polling.
    step: str, e.g. 'download', 'upload', 'thumbnail', 'email', 'draft'
    status: str, one of 'pending', 'in_progress', 'success', 'error'
    message: str, friendly message for the user
    """
    status_obj = {
        'step': step,
        'status': status,
        'message': message or '',
        'timestamp': datetime.now().isoformat()
    }
    try:
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status_obj, f)
    except Exception as e:
        logger.warning(f"Could not write status file: {e}")

# --- Helper Functions ---

def get_past_papers_from_storage(target_date: date, days=None):
    """
    Get links to newspapers from the past 'days' up to target_date from cloud storage.
    """
    if days is None:
        days = RETENTION_DAYS # Use config value if not provided
    past_papers_links = []
    logger.info("Retrieving past %d paper links from storage up to %s.", days, target_date.strftime(DATE_FORMAT))
    try:
        # Assuming storage.list_storage_files exists despite potential linter error
        all_files = storage.list_storage_files() # pylint: disable=no-member
        if not all_files:
            logger.warning("No files found in cloud storage.")
            return []

        logger.info("Found %d files in storage. Filtering for the last %d days.", len(all_files), days)

        # Filter and sort files based on date in filename
        dated_files = []
        for filename in all_files:
            try:
                # Extract date part assuming format YYYY-MM-DD at the start
                date_str = filename.split('_')[0]
                file_date = datetime.strptime(date_str, DATE_FORMAT).date()
                # Only consider actual newspaper files (ignore thumbnails etc.)
                if "newspaper" in filename and (filename.endswith(".pdf") or filename.endswith(".html")):
                    dated_files.append((file_date, filename))
            except (ValueError, IndexError):
                logger.warning("Could not parse date from filename: %s. Skipping.", filename)
                continue # Skip files that don't match the expected naming convention

        # Sort by date descending (most recent first)
        dated_files.sort(key=lambda x: x[0], reverse=True)

        # Get links for the required number of days up to the target_date
        cutoff_date = target_date - timedelta(days=days -1) # Inclusive date range

        for file_date, filename in dated_files:
            if file_date >= cutoff_date and file_date <= target_date: # Ensure we don't include future dates if running for the past
                try:
                    # Assuming storage.get_file_url exists despite potential linter error
                    url = storage.get_file_url(filename) # pylint: disable=no-member
                    if url:
                        past_papers_links.append((file_date.strftime(DATE_FORMAT), url))
                    else:
                        logger.warning("Could not get URL for file: %s", filename)
                except storage.ClientError as url_ce: # Catch specific storage errors for URL generation
                    logger.error("Storage client error getting URL for %s: %s", filename, url_ce)
                except Exception as url_e: # Catch other unexpected errors during URL generation
                    # Using logger.exception to include traceback
                    logger.exception("Unexpected error getting URL for %s: %s", filename, url_e)
            # Stop adding once we have enough days or go past the cutoff
            if len(past_papers_links) >= days:
                break

        # Ensure the list is sorted chronologically for the email template if needed
        past_papers_links.sort(key=lambda x: x[0], reverse=True) # Keep most recent first for display logic
        logger.info("Collected %d past paper links from storage.", len(past_papers_links))
        return past_papers_links

    except storage.ClientError as ce: # Catch specific storage errors
        logger.error("Storage client error retrieving past papers: %s", ce)
        return []
    except Exception as e: # General fallback for listing/processing
        # Using logger.exception to include traceback
        logger.exception("Error retrieving past papers from storage: %s", e)
        return []


def cleanup_old_files(target_date: date, days_to_keep=None, dry_run: bool = False):
    """
    Remove files older than 'days_to_keep' relative to target_date from cloud storage.
    """
    if days_to_keep is None:
        days_to_keep = RETENTION_DAYS # Use config value if not provided
    try:
        # Assuming storage.list_storage_files exists
        # pylint: disable=no-member ; Pylint struggles with lazy S3 client init in storage module
        all_files = storage.list_storage_files()
        if not all_files:
            logger.info("No files found in storage, skipping cleanup.")
            return # Nothing to clean

        logger.info("Checking %d files for cleanup (older than %d days relative to %s).", len(all_files), days_to_keep, target_date.strftime(DATE_FORMAT))
        cutoff_date = target_date - timedelta(days=days_to_keep) # Files strictly older than this date

        deleted_count = 0
        for filename in all_files:
            try:
                # Extract date part assuming format YYYY-MM-DD at the start
                date_str = filename.split('_')[0]
                file_date = datetime.strptime(date_str, DATE_FORMAT).date()

                if file_date < cutoff_date:
                    logger.info("Attempting to delete old file: %s (Date: %s)", filename, file_date)
                    # Pass dry_run flag to storage.delete_from_storage
                    # Assuming storage.delete_from_storage exists
                    # pylint: disable=no-member ; Pylint struggles with lazy S3 client init in storage module
                    if storage.delete_from_storage(filename, dry_run=dry_run):
                        deleted_count += 1
                        logger.info("Successfully deleted %s%s", filename, (" (Dry Run)" if dry_run else ""))
                    else:
                        # delete_from_storage should log its own errors/warnings
                        pass # Already logged in delete_from_storage
            except (ValueError, IndexError):
                logger.warning("Could not parse date from filename for cleanup: %s. Skipping.", filename)
                continue # Skip files that don't match the expected naming convention

        logger.info("Cleanup complete. %s %d old files.", ('Simulated deleting' if dry_run else 'Deleted'), deleted_count)

    except storage.ClientError as ce: # Catch specific storage errors
        logger.error("Storage client error during cleanup: %s", ce)
    except Exception as e: # General fallback
        # Using logger.exception to include traceback
        logger.exception("Error during old file cleanup: %s", e)


# --- Main Execution Logic ---
def main(target_date_str: str | None = None, dry_run: bool = False, force_download: bool = False):
    try:
        update_status('start', 'in_progress', 'Starting the daily newspaper process...', percent=0, eta='about 2-3 minutes')
        # Step 1: Validate configuration
        update_status('config', 'in_progress', 'Checking your settings...', percent=5)
        if not config.load():
            update_status('config', 'error', 'Configuration validation failed. Please check your settings.', percent=0)
            logger.critical("Configuration validation failed. Exiting.")
            return False
        update_status('config', 'success', 'Settings look good!', percent=10)

        # Step 2: Determine target date
        target_date = date.today() if not target_date_str else datetime.strptime(target_date_str, '%Y-%m-%d').date()
        update_status('date', 'success', f"Preparing your newspaper for {target_date.strftime('%A, %B %d, %Y')}", percent=15)

        # Step 3: Ensure download directory exists
        download_dir = config.config.get(('paths', 'download_dir'), 'downloads')
        os.makedirs(download_dir, exist_ok=True)

        # Step 4: Download newspaper
        update_status('download', 'in_progress', 'Downloading today\'s newspaper...', percent=20, eta='about 1 minute')
        formats = ['pdf', 'html']
        newspaper_path = None
        newspaper_filename = None
        file_format = None
        download_success = False
        download_start = time.time()
        for fmt in formats:
            candidate_filename = f"{target_date.strftime('%Y-%m-%d')}_newspaper.{fmt}"
            candidate_path = os.path.join(download_dir, candidate_filename)
            success, detected_format = website.login_and_download(
                base_url=config.config.get(('newspaper', 'url')),
                username=config.config.get(('newspaper', 'username')),
                password=config.config.get(('newspaper', 'password')),
                save_path=candidate_path,
                target_date=target_date_str,
                dry_run=dry_run,
                force_download=force_download
            )
            if success:
                newspaper_path = candidate_path
                newspaper_filename = candidate_filename
                file_format = fmt
                download_success = True
                break
            # If download is slow, show explainer
            if time.time() - download_start > 60:
                update_status('download', 'in_progress', 'Still downloading... This can take a few minutes if the newspaper site is busy.', percent=25, eta='a few more minutes', explainer='No action needed. Sometimes the newspaper site is slow. We\'ll keep trying.')
        if not download_success:
            update_status('download', 'error', 'Could not download today\'s newspaper. Please check your subscription or try again later.', percent=0)
            logger.error("Failed to download newspaper for %s. Exiting.", target_date)
            email_sender.send_alert_email(
                subject='Newspaper Download Failed',
                message=f'Could not download newspaper for {target_date}.',
                dry_run=dry_run
            )
            return False
        update_status('download', 'success', 'Downloaded today\'s newspaper!', percent=35)

        # Step 5: Upload to cloud storage
        update_status('upload', 'in_progress', 'Uploading your newspaper to the cloud...', percent=40, eta='about 30 seconds')
        try:
            storage.upload_to_storage(newspaper_path, newspaper_filename, dry_run=dry_run)
            update_status('upload', 'success', 'Upload complete!', percent=55)
        except Exception as e:
            update_status('upload', 'error', 'Upload failed. Please check your cloud storage settings.', percent=0)
            logger.exception('Upload failed: %s', e)
            return False

        # Step 6: Generate thumbnail
        update_status('thumbnail', 'in_progress', 'Creating a preview image of the front page...', percent=60, eta='about 20 seconds')
        try:
            from thumbnail import generate_thumbnail
            thumbnail_path = generate_thumbnail(newspaper_path)
            update_status('thumbnail', 'success', 'Preview image created!', percent=75)
        except Exception as e:
            update_status('thumbnail', 'error', 'Could not create a preview image. The email will not include a thumbnail.', percent=0)
            logger.warning('Thumbnail generation failed: %s', e)
            thumbnail_path = None

        # Step 7: Update email template and prepare draft
        update_status('email', 'in_progress', 'Updating your email with today\'s newspaper and preview...', percent=80, eta='about 30 seconds')
        try:
            past_papers = get_past_papers_from_storage(target_date)
            email_sender.send_email(
                target_date=target_date,
                today_paper_url=storage.get_file_url(newspaper_filename),
                past_papers=past_papers,
                thumbnail_path=thumbnail_path,
                dry_run=dry_run
            )
            update_status('email', 'success', 'Email is ready to send! Check your drafts in Gmail.', percent=95)
        except Exception as e:
            update_status('email', 'error', 'Could not update the email. Please check your email settings.', percent=0)
            logger.exception('Email update failed: %s', e)
            return False

        update_status('done', 'success', 'All done! Your newspaper is ready and your email draft is waiting.', percent=100)

        # After a successful week, prompt for automation
        last_7 = get_last_7_days_status()
        if all(day['status'] == 'ready' for day in last_7):
            logger.info('Prompt: Would you like to automate this process to run every day? You can stop it anytime.')
        return True
    except Exception as e:
        update_status('done', 'error', 'Something went wrong. Please check the logs for details.', percent=0)
        logger.exception('Pipeline failed: %s', e)
        return False

# This block is mostly for testing/standalone runs, main execution is via run_newspaper.py
if __name__ == "__main__":
    logger.warning("main.py should ideally be run via run_newspaper.py to ensure proper configuration.")
    # Example of running for today in non-dry-run mode if executed directly
    today_date_str = date.today().strftime(DATE_FORMAT)
    success = main(target_date_str=today_date_str, dry_run=False) # Corrected: Pass target_date_str
    if not success:
        exit(1)

    # Reminder: Respect website Terms of Service and rate limiting
    logger.info("Reminder: Ensure compliance with the newspaper website's Terms of Service. Avoid excessive requests. Consider adding delays if needed.")
