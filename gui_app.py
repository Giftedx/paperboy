#!/usr/bin/env python3
"""
Flask-based GUI for the Newspaper Emailer System
Allows admin to monitor, trigger, and configure the newspaper delivery pipeline.
"""

import os
import logging
import json
import yaml
from datetime import date, timedelta, datetime
import time
import threading

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify

# Import project modules
import main # main.main and main.update_status will be used
import storage
import email_sender
import config

app = Flask(__name__)
# It's crucial to set a strong, unpredictable secret key in a real environment
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-for-flask')

# Logging setup - Use Flask's logger
if not app.debug: # In production, you might want more sophisticated logging
    # Basic setup if not already configured by Flask/Gunicorn
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

logger = app.logger # Use Flask's app.logger

STATUS_FILE = main.STATUS_FILE # Use status file defined in main.py

# --- Helper for Async Manual Run ---
def run_main_asynchronously(app_context, target_date_str: str, dry_run: bool, force_download: bool):
    """
    Run the main newspaper processing pipeline in a background thread.

    Args:
        app_context: The Flask application context.
        target_date_str: The target date for processing, in 'YYYY-MM-DD' format.
        dry_run: Boolean indicating if it's a dry run.
        force_download: Boolean indicating if download should be forced.
    """
    with app_context: # Use the app context for operations that require it (e.g., logging, config)
        logger.info(f"Background thread: Starting manual run for date: {target_date_str}, dry_run: {dry_run}, force: {force_download}")
        main.main(target_date_str=target_date_str, dry_run=dry_run, force_download=force_download)
        logger.info(f"Background thread: Manual run finished for date: {target_date_str}")

# --- Global state for email preview generation ---
email_preview_thread = None # Holds the thread object for asynchronous preview generation
email_preview_data = {"status": "idle", "html": None, "error": None} # Shared data structure: idle, generating, ready, error
email_preview_lock = threading.Lock() # Lock to protect concurrent access to email_preview_data

def _generate_email_preview_async(app_context, form_data: dict):
    """
    Generate the HTML email preview asynchronously.

    Updates the global `email_preview_data` with the status and result.

    Args:
        app_context: The Flask application context.
        form_data: A dictionary containing data from the preview form,
                   including 'target_date', 'today_paper_url', and 'thumbnail_url'.
    """
    global email_preview_data, email_preview_lock # Required to modify global variables

    with app_context: # Ensure operations run within Flask's application context
        logger.info("Background thread: Starting email preview generation.")
        try:
            # Set status to generating
            with email_preview_lock:
                email_preview_data["status"] = "generating"
                email_preview_data["html"] = None
                email_preview_data["error"] = None
            
            # Ensure config is loaded, as this function might be called standalone or early
            if not config.config._loaded: # Check internal flag; consider a public property in Config class
                config.config.load()

            # Extract data from form, providing defaults
            date_format = config.config.get(('general', 'date_format'), '%Y-%m-%d')
            target_date_str = form_data.get('target_date', datetime.today().strftime(date_format))
            today_paper_url = form_data.get('today_paper_url', '#example-today-paper-url') # Default placeholder
            thumbnail_url = form_data.get('thumbnail_url', None) 
            
            target_date_obj = datetime.strptime(target_date_str, date_format).date()
            
            # Get past papers data for the email template
            retention_days_for_links = config.config.get(('general', 'retention_days_for_email_links'), 7)
            past_papers = main.get_past_papers_from_storage(target_date_obj, days=retention_days_for_links)
            
            # Generate email HTML content (dry_run=True ensures no actual email is sent)
            html_content = email_sender.send_email(
                target_date=target_date_obj,
                today_paper_url=today_paper_url, # URL for the main paper of the target date
                past_papers=past_papers,
                thumbnail_url=thumbnail_url, 
                dry_run=True 
            )
            with email_preview_lock:
                if html_content:
                    email_preview_data["status"] = "ready"
                    email_preview_data["html"] = html_content
                else:
                    email_preview_data["status"] = "error"
                    email_preview_data["error"] = "Email template generation returned no content."
            logger.info("Background thread: Email preview generation finished.")
        except Exception as e:
            logger.exception("Background thread: Error generating email preview.")
            with email_preview_lock:
                email_preview_data["status"] = "error"
                email_preview_data["error"] = str(e)

# --- Routes ---

@app.route('/')
def dashboard():
    """
    Serve the main dashboard page.

    Displays recent logs, error messages, and a 7-day status glance of newspaper downloads.
    Methods: GET
    """
    # Log reading logic: Display recent lines from the application log.
    log_path = 'newspaper_emailer.log' # TODO: Consider making this path configurable via main config.
    logs = []
    recent_errors = []
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                # Read last N lines for performance
                # This simple approach might be slow for huge files.
                # For production, consider log rotation or more advanced log viewers.
                lines = f.readlines() 
                for line in lines[-200:]: # Get last 200 lines
                    logs.append(line.strip())
                    if 'ERROR' in line or 'CRITICAL' in line:
                        recent_errors.append(line.strip())
        except Exception as e:
            logger.error(f"Error reading log file for dashboard: {e}")
            flash("Could not read log file.", "warning")

    # Last 7 days status
    try:
        last_7_days_glance = main.get_last_7_days_status()
    except Exception as e:
        logger.error(f"Error getting last 7 days status: {e}")
        last_7_days_glance = []
        flash("Could not retrieve status for the last 7 days.", "warning")
        
    return render_template('dashboard.html', 
                           logs=logs[-50:], # Display last 50 lines from the last 200 read
                           recent_errors=recent_errors[-10:], # Display last 10 errors from the last 200 read
                           last_7_days_glance=last_7_days_glance)

@app.route('/run', methods=['GET', 'POST'])
def manual_run():
    """
    Handle manual triggering of the newspaper processing pipeline.

    GET: Displays the manual run form with date selection.
    POST: Validates form data (date) and starts the main pipeline in a background thread.
          Flashes messages for success or failure.
    """
    # DATE_FORMAT is used for validating input and displaying today's date.
    # It should be loaded from config; provide a fallback if config isn't loaded yet.
    current_date_format = config.config.get(('general', 'date_format'), '%Y-%m-%d')
    today_str = datetime.today().strftime(current_date_format)

    if request.method == 'POST':
        date_str = request.form.get('date')
        dry_run = 'dry_run' in request.form 
        force_download = 'force_download' in request.form

        if not date_str:
            flash('Date is required.', 'danger')
            return render_template('manual_run.html', today=today_str, submitted_date=date_str)
        
        try:
            datetime.strptime(date_str, current_date_format) # Validate date format
        except ValueError:
            flash(f'Invalid date format. Please use {current_date_format}.', 'danger')
            return render_template('manual_run.html', today=today_str, submitted_date=date_str)

        logger.info(f"Initiating manual run via GUI for date: {date_str}, dry_run: {dry_run}, force: {force_download}")
        thread = threading.Thread(target=run_main_asynchronously, 
                                   args=(app.app_context(), date_str, dry_run, force_download))
        thread.start()
        
        flash(f'Manual run started for {date_str}. Check dashboard for progress.', 'info')
        return redirect(url_for('dashboard'))

    return render_template('manual_run.html', today=today_str)

@app.route('/archive')
def archive():
    """
    Display the list of archived newspaper files from cloud storage.

    Methods: GET
    """
    try:
        # Retrieve list of files from the configured storage provider
        files = storage.list_storage_files()
    except Exception as e:
        logger.exception("Failed to list storage files for archive: %s", e)
        files = [] # Ensure files is an empty list on error to prevent template errors
        flash("Could not retrieve file list from storage.", "danger")
    return render_template('archive.html', files=files)

@app.route('/archive/download/<path:filename>')
def download_archive_file(filename: str):
    """
    Download a specific archived file from cloud storage.

    Args:
        filename: The name of the file to download (can include path separators).
    Methods: GET
    """
    try:
        # Security: Define a safe root directory for temporary local copies before sending.
        # This helps prevent path traversal issues if `filename` is manipulated.
        safe_root = '/tmp/safe_storage' # TODO: Consider making this configurable or using Flask's instance folder
        # Normalize the path to resolve any '..' components.
        normalized_path = os.path.normpath(os.path.join(safe_root, filename))

        # Security check: Ensure the normalized path is still within the intended safe root.
        if not normalized_path.startswith(safe_root):
            flash(f'Invalid file path: {filename}.', 'danger')
            return redirect(url_for('archive'))
        
        # Download the file from storage to a temporary local path
        local_path = storage.download_to_temp(normalized_path) # `download_to_temp` should handle the actual filename

        if local_path:
            # Send the file to the user for download
            return send_file(local_path, as_attachment=True)
        else:
            flash(f'Could not download {filename}. File not found or error during download.', 'danger')
            return redirect(url_for('archive'))
    except Exception as e:
        logger.exception("Error downloading file '%s' from archive: %s", filename, e)
        flash(f'Error downloading {filename}: {str(e)}', 'danger')
        return redirect(url_for('archive'))

@app.route('/archive/delete/<path:filename>', methods=['POST'])
def delete_archive_file(filename: str):
    """
    Delete a specific archived file from cloud storage.

    Args:
        filename: The name of the file to delete (can include path separators).
    Methods: POST
    """
    try:
        # Attempt to delete the file from storage
        storage.delete_from_storage(filename)
        flash(f'Deleted {filename} from storage.', 'success')
    except Exception as e:
        logger.exception("Error deleting file '%s' from archive: %s", filename, e)
        flash(f'Error deleting {filename}: {str(e)}', 'danger')
    return redirect(url_for('archive')) # Redirect back to the archive page

@app.route('/config', methods=['GET', 'POST'])
def config_editor():
    """
    Display and handle updates to `config.yaml` and `.env` files.

    GET: Reads and displays the content of `config.yaml` and `.env`.
    POST: Validates and saves new content to `config.yaml` and `.env`, then reloads configuration.
    """
    # Determine configuration file paths (from environment or defaults)
    config_path = os.environ.get('NEWSPAPER_CONFIG', 'config.yaml')
    env_path = os.environ.get('NEWSPAPER_ENV', '.env')
    
    config_content = ''
    env_content = ''

    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
        else:
            flash(f"Config file ({config_path}) not found. Create one if needed.", "info")
        
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                env_content = f.read()
        else:
            flash(f".env file ({env_path}) not found. Create one if needed.", "info")
            
    except IOError as e:
        logger.error(f"Error reading config/env files: {e}")
        flash(f"Error reading configuration files: {e}", "danger")

    if request.method == 'POST':
        new_config_content = request.form.get('config_content', '') # Renamed to avoid conflict with module
        new_env_content = request.form.get('env_content', '')   # Renamed

        try:
            # Validate YAML syntax first
            yaml.safe_load(new_config_content)
            
            # YAML is valid, proceed to attempt saving
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(new_config_content)
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.write(new_env_content)

                config.config.load() # Reload config
                flash('Configuration updated and reloaded.', 'success')
            except IOError as e: # Catch IO errors during write
                logger.error(f"Error writing config/env files: {e}")
                flash(f"Error saving configuration files: {e}", "danger")
            # No specific 'else' needed here for the inner try; if no IOError, success flash is shown.

        except yaml.YAMLError as e: # Catch YAML validation errors
            logger.error(f"Invalid YAML syntax in config.yaml: {e}")
            flash(f"Invalid YAML syntax in config.yaml: {e}", "danger")
            # Return to editor, preserving user's input for correction
            return render_template('config_editor.html',
                                   config_content=new_config_content,
                                   env_content=new_env_content) # Pass back the attempted content

        except Exception as e: # Catch other unexpected errors (e.g., during config.config.load())
            logger.exception("Unexpected error updating configuration.")
            flash(f"An unexpected error occurred: {e}", "danger")
            return render_template('config_editor.html',
                                   config_content=new_config_content,
                                   env_content=new_env_content) # Pass back the attempted content

        # Redirect only if no YAML error occurred and re-rendering wasn't done
        return redirect(url_for('config_editor'))
        
    return render_template('config_editor.html', config_content=config_content, env_content=env_content)

@app.route('/preview', methods=['GET', 'POST'])
def email_preview():
    """
    Handle generation and display of an email preview.

    GET: Renders the email preview page, which will then use JavaScript to poll `/preview_data`.
    POST: Initiates the asynchronous generation of an email preview based on form data.
          Form data includes 'target_date', 'today_paper_url', and 'thumbnail_url'.
    """
    global email_preview_thread, email_preview_data, email_preview_lock # Global state for async preview
    
    if request.method == 'POST':
        # Prevent multiple preview generations at once
        with email_preview_lock:
            if email_preview_data["status"] == "generating":
                flash("Preview generation is already in progress. Please wait.", "info")
                return redirect(url_for('email_preview'))

            # Reset state for new preview generation
            email_preview_data["status"] = "generating"
            email_preview_data["html"] = None
            email_preview_data["error"] = None
        
        # Collect form data for the preview
        # These URLs should ideally point to already uploaded items for a true preview.
        # Here, they are taken from form input, which might be example URLs.
        form_data = {
            'target_date': request.form.get('target_date', datetime.today().strftime(config.config.get(('general', 'date_format'), '%Y-%m-%d'))),
            'today_paper_url': request.form.get('today_paper_url', 'https://example.com/dummy_paper.pdf'), 
            'thumbnail_url': request.form.get('thumbnail_url', None) 
        }
        
        logger.info(f"Starting email preview generation with data: {form_data}")
        # Start the preview generation in a background thread
        email_preview_thread = threading.Thread(target=_generate_email_preview_async, 
                                                args=(app.app_context(), form_data))
        email_preview_thread.start()
        flash("Email preview generation started. Results will appear below shortly.", "info")
        return redirect(url_for('email_preview')) # Redirect to GET to show status and await results

    # For GET request: render the page. JavaScript will poll /preview_data.
    # Pass current state to template for initial rendering to avoid delay if data is already ready.
    with email_preview_lock:
        current_preview_status = email_preview_data["status"]
        current_html = email_preview_data["html"]
        current_error = email_preview_data["error"]

    return render_template('email_preview.html', 
                           initial_status=current_preview_status, 
                           initial_html=current_html,
                           initial_error=current_error)

@app.route('/preview_data')
def email_preview_data_route():
    """
    Serve the current email preview data (status, HTML, error) as JSON.
    This route is polled by JavaScript on the email preview page.
    Methods: GET
    """
    global email_preview_data, email_preview_lock # Access global state
    with email_preview_lock: # Ensure thread-safe access
        return jsonify(email_preview_data)


@app.route('/health')
def health():
    """
    Display a health check page.

    Currently shows recent errors from the application log.
    Could be expanded to check database connections, storage provider reachability, etc.
    Methods: GET
    """
    # This could be expanded to check DB connections, storage provider status, etc.
    # For now, it primarily shows recent critical/error messages from logs.
    recent_errors = []
    log_path = 'newspaper_emailer.log' # TODO: Make configurable
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines() # Read all lines
                for line in lines[-100:]: # Process last 100 lines for recent errors
                    if 'ERROR' in line or 'CRITICAL' in line:
                        recent_errors.append(line.strip())
        except Exception as e:
            logger.error(f"Error reading log file for health check: {e}")
    return render_template('health.html', recent_errors=recent_errors[-10:]) # Display last 10 found errors

@app.route('/health/test_alert', methods=['POST'])
def test_alert():
    """
    Send a test alert email.

    Used to verify that the email sending configuration is working.
    Methods: POST
    """
    try:
        # Attempt to send a test alert email via the configured email_sender
        email_sender.send_alert_email(
            'Test Alert from GUI',
            'This is a test alert message sent from the Newspaper Emailer application GUI.'
        )
        flash('Test alert email sent successfully.', 'info')
    except Exception as e:
        logger.exception("Failed to send test alert email: %s", e)
        flash(f'Failed to send test alert: {str(e)}', 'danger')
    return redirect(url_for('health')) # Redirect back to the health page

@app.route('/progress')
def progress():
    """
    Provide the current status of an ongoing newspaper processing pipeline.

    Reads status from the `STATUS_FILE` (e.g., pipeline_status.json) and returns it as JSON.
    Used by the UI to display real-time progress updates.
    Methods: GET
    """
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                status = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read or parse status file '{STATUS_FILE}': {e}")
            status = {'step': 'error', 'status': 'error', 'message': 'Error reading status file.'}
    else:
        # If status file doesn't exist, assume no process is running or status hasn't been updated yet.
        status = {'step': 'idle', 'status': 'idle', 'message': 'No process running or status not yet updated.'}
    return jsonify(status)

# --- Scheduling ---
# Simplified scheduler state and logic for this example.
# In a more complex application, this might be stored in a database or a more robust cache.
schedule_state = {
    'mode': 'manual',  # 'manual' (no schedule), 'daily' (run at specified time)
    'time': '06:00',
    'active': False,
    'next_run_iso': None, # Store as ISO string
    'last_run_log': [] # TODO: Implement logging for scheduled runs if needed.
}
schedule_lock = threading.Lock() # Protects access to schedule_state and schedule_thread_obj
schedule_thread_obj = None # Holds the scheduler background thread object

def calculate_next_run_datetime(run_time_str: str) -> datetime:
    """
    Calculate the next run datetime based on a 'HH:MM' time string.

    If the calculated time for today has already passed, it schedules for the next day.

    Args:
        run_time_str: The time of day for the schedule, in 'HH:MM' format.

    Returns:
        A datetime object for the next scheduled run.
    """
    now = datetime.now()
    hour, minute = map(int, run_time_str.split(':'))
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now: # If this time has already passed for today
        next_run += timedelta(days=1) # Schedule for tomorrow
    return next_run

def schedule_runner():
    """
    Background thread function to monitor and trigger scheduled tasks.

    Checks every 30 seconds if a scheduled run is due. If so, it executes
    the main newspaper processing pipeline. If the mode is 'daily', it
    recalculates the next run time. The thread exits if the schedule
    is deactivated.
    """
    global schedule_state, schedule_lock # Access global scheduler state
    logger.info("Scheduler thread started.")
    while True:
        next_run_dt = None
        is_active_local = False # Local copy of active status to minimize lock holding

        # Check current schedule status under lock
        with schedule_lock:
            is_active_local = schedule_state['active']
            if is_active_local and schedule_state['next_run_iso']:
                try:
                    next_run_dt = datetime.fromisoformat(schedule_state['next_run_iso'])
                except ValueError:
                    logger.error(f"Scheduler: Invalid ISO format for next_run_iso: {schedule_state['next_run_iso']}. Deactivating schedule.")
                    schedule_state['active'] = False # Deactivate on error
                    is_active_local = False # Ensure thread exits
        
        if not is_active_local:
            logger.info("Scheduler is not active. Thread exiting.")
            break # Exit the loop, terminating the thread

        # If a run is scheduled and due
        if next_run_dt and datetime.now() >= next_run_dt:
            logger.info(f"Scheduler: Triggering scheduled run for {next_run_dt.strftime('%Y-%m-%d %H:%M')}")

            # Run the main pipeline within the app context
            with app.app_context():
                 date_format = config.config.get(('general', 'date_format'), '%Y-%m-%d')
                 main.main(target_date_str=next_run_dt.strftime(date_format),
                           dry_run=False, force_download=False)
            
            # After the run, update schedule state under lock
            with schedule_lock:
                if schedule_state['mode'] == 'daily': # If still in daily mode, recalculate for next day
                    schedule_state['next_run_iso'] = calculate_next_run_datetime(schedule_state['time']).isoformat()
                    logger.info(f"Scheduler: Next run automatically scheduled for {schedule_state['next_run_iso']}")
                else: # If mode changed (e.g., to manual) or something unexpected, deactivate
                    schedule_state['active'] = False
                    schedule_state['next_run_iso'] = None
                    logger.info("Scheduler: Mode no longer 'daily' after run, or schedule was deactivated. Stopping periodic runs.")
        
        time.sleep(30) # Check schedule every 30 seconds

@app.route('/schedule', methods=['GET', 'POST'])
def schedule_settings():
    """
    Manage scheduler settings.

    GET: Returns the current scheduler status (mode, time, active, next_run).
    POST: Updates scheduler settings. Expects JSON data with 'mode' ('manual' or 'daily')
          and 'time' ('HH:MM'). Starts or stops the scheduler thread accordingly.
    """
    global schedule_thread_obj, schedule_state, schedule_lock # Access global scheduler objects

    if request.method == 'POST':
        # Expecting JSON data for POST
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'Invalid request. JSON data expected.'}), 400

        mode = data.get('mode', 'manual')
        run_time_str = data.get('time', '06:00')

        # Validate time format
        try:
            datetime.strptime(run_time_str, '%H:%M')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid time format. Please use HH:MM.'}), 400

        with schedule_lock:
            schedule_state['mode'] = mode
            schedule_state['time'] = run_time_str
            
            if mode == 'daily':
                schedule_state['active'] = True
                schedule_state['next_run_iso'] = calculate_next_run_datetime(run_time_str).isoformat()
                logger.info(f"Daily schedule activated. Next run: {schedule_state['next_run_iso']}")
                # Start the scheduler thread if it's not already running
                if schedule_thread_obj is None or not schedule_thread_obj.is_alive():
                    logger.info("Starting scheduler thread.")
                    schedule_thread_obj = threading.Thread(target=schedule_runner, daemon=True)
                    schedule_thread_obj.start()
            else: # 'manual' mode or any other mode implies stopping the active schedule
                schedule_state['active'] = False
                schedule_state['next_run_iso'] = None
                logger.info("Scheduler set to manual or inactive. Active runs stopped.")
            
            current_state_for_json = dict(schedule_state)
        
        flash('Schedule settings updated.', 'success') # Flash for user feedback on next GET
        return jsonify({'status': 'success', 'message': 'Schedule updated.', 'schedule_state': current_state_for_json})

    # For GET request, return current schedule state
    with schedule_lock:
        current_state_for_json = dict(schedule_state)
    return jsonify(current_state_for_json)

@app.route('/schedule/stop', methods=['POST'])
def stop_schedule():
    """
    Explicitly stop the scheduler if it is active.
    Methods: POST
    """
    global schedule_state, schedule_lock, schedule_thread_obj # Access global scheduler objects
    with schedule_lock:
        if schedule_state['active']:
            schedule_state['active'] = False # Signal the scheduler thread to stop
            schedule_state['next_run_iso'] = None
            logger.info("Scheduler stop request received. Thread will stop on its next check cycle.")
            # Note: The thread object `schedule_thread_obj` itself is not joined here to keep the request responsive.
            # As a daemon thread, it will exit when the main app exits or when its loop condition (is_active_local) becomes false.
            flash('Scheduler stopping process initiated. It may take up to 30 seconds for the process to fully halt.', 'info')
            message = 'Scheduler stopping process initiated...'
        else:
            logger.info("Scheduler stop request received, but scheduler was not active.")
            flash('Scheduler was not active.', 'info')
            message = 'Scheduler was not active.'
            
    return jsonify({'status': 'stopping_or_inactive', 'message': message})

if __name__ == '__main__':
    # Load .env for direct Flask run, config.load() will also do this but good for early setup
    env_path = os.environ.get('NEWSPAPER_ENV', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path, verbose=True, override=True)
        logger.info(f"Loaded .env from {env_path} for Flask development server.")

    # Initial config load for the app itself
    if not config.config.load():
        logger.warning("Initial configuration load failed for Flask app. Some parts may not work until config is fixed via UI or file.")
        # Not exiting, as GUI might be used to fix config.

    # Start the scheduler thread if it was active from a previous state (not typical for dev server)
    # This would typically be handled by a more robust startup/init process
    # For now, scheduler is started via UI interaction.

    # Determine if the app should run in debug mode based on the environment
    is_debug = os.environ.get('FLASK_ENV', 'development') != 'production'
    app.run(debug=is_debug, host='0.0.0.0', port=int(os.environ.get('FLASK_PORT', 8080)))
