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
def run_main_asynchronously(app_context, target_date_str, dry_run, force_download):
    with app_context:
        logger.info(f"Background thread: Starting manual run for date: {target_date_str}, dry_run: {dry_run}, force: {force_download}")
        main.main(target_date_str=target_date_str, dry_run=dry_run, force_download=force_download)
        logger.info(f"Background thread: Manual run finished for date: {target_date_str}")

# --- Global state for email preview generation ---
email_preview_thread = None
email_preview_data = {"status": "idle", "html": None, "error": None} # idle, generating, ready, error
email_preview_lock = threading.Lock()

def _generate_email_preview_async(app_context, form_data):
    global email_preview_data, email_preview_lock # Required to modify global variable
    with app_context:
        logger.info("Background thread: Starting email preview generation.")
        try:
            with email_preview_lock: # Ensure thread-safe update to global dict
                email_preview_data["status"] = "generating"
                email_preview_data["html"] = None
                email_preview_data["error"] = None
            
            # Ensure config is loaded for these calls if not already by main app startup
            if not config.config._loaded: # Access internal flag, or add a public property
                config.config.load()

            target_date_str = form_data.get('target_date', datetime.today().strftime(config.config.get(('general', 'date_format'), '%Y-%m-%d')))
            today_paper_url = form_data.get('today_paper_url', '#example-today-paper-url') 
            thumbnail_url = form_data.get('thumbnail_url', None) 
            
            target_date_obj = datetime.strptime(target_date_str, config.config.get(('general', 'date_format'), '%Y-%m-%d')).date()
            
            retention_days = config.config.get(('general', 'retention_days_for_email_links'), 7)
            past_papers = main.get_past_papers_from_storage(target_date_obj, days=retention_days) # Use main's helper
            
            html_content = email_sender.send_email(
                target_date=target_date_obj,
                today_paper_url=today_paper_url,
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
    # Log reading logic
    log_path = 'newspaper_emailer.log' # Consider making this configurable
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
                           logs=logs[-50:], # Display last 50 of the read 200
                           recent_errors=recent_errors[-10:], # Display last 10 errors
                           last_7_days_glance=last_7_days_glance)

@app.route('/run', methods=['GET', 'POST'])
def manual_run():
    # DATE_FORMAT should be loaded from config by now if main() or config.load() was called.
    # Fallback if accessed directly before config load.
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
    try:
        files = storage.list_storage_files()
    except Exception as e:
        logger.exception("Failed to list storage files for archive: %s", e)
        files = []
        flash("Could not retrieve file list from storage.", "danger")
    return render_template('archive.html', files=files)

@app.route('/archive/download/<path:filename>') # Use path converter for filenames with slashes
def download_archive_file(filename): # Renamed to avoid conflict
    try:
        # Define a safe root directory for temporary files
        safe_root = '/tmp/safe_storage'
        # Normalize the filename and construct the full path
        normalized_path = os.path.normpath(os.path.join(safe_root, filename))
        # Ensure the normalized path is within the safe root directory
        if not normalized_path.startswith(safe_root):
            flash(f'Invalid file path: {filename}.', 'danger')
            return redirect(url_for('archive'))
        
        local_path = storage.download_to_temp(normalized_path)
        if local_path:
            return send_file(local_path, as_attachment=True)
        else:
            flash(f'Could not download {filename}. File not found or error.', 'danger')
            return redirect(url_for('archive'))
    except Exception as e:
        logger.exception("Error downloading file '%s' from archive: %s", filename, e)
        flash(f'Error downloading {filename}: {str(e)}', 'danger')
        return redirect(url_for('archive'))

@app.route('/archive/delete/<path:filename>', methods=['POST']) # Use path converter
def delete_archive_file(filename): # Renamed
    try:
        storage.delete_from_storage(filename)
        flash(f'Deleted {filename} from storage.', 'success')
    except Exception as e:
        logger.exception("Error deleting file '%s' from archive: %s", filename, e)
        flash(f'Error deleting {filename}: {str(e)}', 'danger')
    return redirect(url_for('archive'))

@app.route('/config', methods=['GET', 'POST'])
def config_editor():
    # These paths should ideally come from a more robust source or be absolute
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
    global email_preview_thread, email_preview_data, email_preview_lock
    
    if request.method == 'POST':
        with email_preview_lock:
            if email_preview_data["status"] == "generating":
                flash("Preview generation is already in progress. Please wait.", "info")
                return redirect(url_for('email_preview'))

            email_preview_data["status"] = "generating"
            email_preview_data["html"] = None # Clear previous preview
            email_preview_data["error"] = None
        
        # These should ideally be URLs to *already uploaded* items for a true preview
        form_data = {
            'target_date': request.form.get('target_date', datetime.today().strftime(config.config.get(('general', 'date_format'), '%Y-%m-%d'))),
            'today_paper_url': request.form.get('today_paper_url', 'https://example.com/dummy_paper.pdf'), 
            'thumbnail_url': request.form.get('thumbnail_url', None) 
        }
        
        logger.info(f"Starting email preview generation with data: {form_data}")
        email_preview_thread = threading.Thread(target=_generate_email_preview_async, 
                                                args=(app.app_context(), form_data))
        email_preview_thread.start()
        flash("Email preview generation started. Results will appear below shortly.", "info")
        return redirect(url_for('email_preview')) # Redirect to GET to show status

    # For GET request, render the page. JS will poll /preview_data.
    # Pass current state to template for initial rendering
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
    global email_preview_data, email_preview_lock
    with email_preview_lock:
        return jsonify(email_preview_data)


@app.route('/health')
def health():
    # This could be expanded to check DB connections, etc.
    # For now, just shows recent errors from logs.
    recent_errors = []
    log_path = 'newspaper_emailer.log' 
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[-100:]: # Check last 100 lines
                    if 'ERROR' in line or 'CRITICAL' in line:
                        recent_errors.append(line.strip())
        except Exception as e:
            logger.error(f"Error reading log file for health check: {e}")
    return render_template('health.html', recent_errors=recent_errors[-10:]) # Display last 10

@app.route('/health/test_alert', methods=['POST'])
def test_alert():
    try:
        email_sender.send_alert_email('Test Alert from GUI', 'This is a test alert message sent from the Newspaper Emailer application GUI.')
        flash('Test alert email sent successfully.', 'info')
    except Exception as e:
        logger.exception("Failed to send test alert email: %s", e)
        flash(f'Failed to send test alert: {str(e)}', 'danger')
    return redirect(url_for('health'))

@app.route('/progress')
def progress():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                status = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read or parse status file '{STATUS_FILE}': {e}")
            status = {'step': 'error', 'status': 'error', 'message': 'Error reading status file.'}
    else:
        status = {'step': 'idle', 'status': 'idle', 'message': 'No process running or status not yet updated.'}
    return jsonify(status)

# --- Scheduling ---
# Simplified scheduler state and logic for this example
schedule_state = {
    'mode': 'manual',  # 'manual', 'daily'
    'time': '06:00',
    'active': False,
    'next_run_iso': None, # Store as ISO string
    'last_run_log': [] # Store log of last scheduled run
}
schedule_lock = threading.Lock()
schedule_thread_obj = None # Changed name to avoid conflict

def calculate_next_run_datetime(run_time_str):
    now = datetime.now()
    hour, minute = map(int, run_time_str.split(':'))
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now: # If time has passed for today, schedule for tomorrow
        next_run += timedelta(days=1)
    return next_run

def schedule_runner():
    global schedule_state, schedule_lock # Ensure global state is modified
    logger.info("Scheduler thread started.")
    while True:
        next_run_dt = None
        is_active_local = False
        with schedule_lock:
            is_active_local = schedule_state['active']
            if is_active_local:
                next_run_dt = datetime.fromisoformat(schedule_state['next_run_iso']) if schedule_state['next_run_iso'] else None
        
        if not is_active_local:
            logger.info("Scheduler is not active. Thread exiting.")
            break

        if next_run_dt and datetime.now() >= next_run_dt:
            logger.info(f"Scheduler: Triggering scheduled run for {next_run_dt.strftime('%Y-%m-%d')}")
            # Using app_context for the background thread
            with app.app_context():
                 main.main(target_date_str=next_run_dt.strftime(config.config.get(('general', 'date_format'), '%Y-%m-%d')), dry_run=False, force_download=False)
            
            with schedule_lock:
                if schedule_state['mode'] == 'daily': # Recalculate for next day
                    schedule_state['next_run_iso'] = calculate_next_run_datetime(schedule_state['time']).isoformat()
                    logger.info(f"Scheduler: Next run scheduled for {schedule_state['next_run_iso']}")
                else: # Should not happen if logic is correct, but as safeguard
                    schedule_state['active'] = False
                    schedule_state['next_run_iso'] = None
                    logger.info("Scheduler: Mode not 'daily' after run, stopping.")
        
        time.sleep(30) # Check every 30 seconds

@app.route('/schedule', methods=['GET', 'POST'])
def schedule_settings(): # Renamed to avoid conflict
    global schedule_thread_obj, schedule_state, schedule_lock
    if request.method == 'POST':
        mode = request.form.get('mode', 'manual')
        run_time_str = request.form.get('time', '06:00')

        try:
            datetime.strptime(run_time_str, '%H:%M') # Validate time format
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid time format. Please use HH:MM.'}), 400

        with schedule_lock:
            schedule_state['mode'] = mode
            schedule_state['time'] = run_time_str
            
            if mode == 'daily':
                schedule_state['active'] = True
                schedule_state['next_run_iso'] = calculate_next_run_datetime(run_time_str).isoformat()
                logger.info(f"Daily schedule activated. Next run: {schedule_state['next_run_iso']}")
                if schedule_thread_obj is None or not schedule_thread_obj.is_alive():
                    schedule_thread_obj = threading.Thread(target=schedule_runner, daemon=True)
                    schedule_thread_obj.start()
            else: # manual or other modes imply stopping active schedule
                schedule_state['active'] = False
                schedule_state['next_run_iso'] = None
                logger.info("Scheduler set to manual or inactive.")
            
            current_state_for_json = dict(schedule_state) # Make a copy for sending
        
        flash('Schedule settings updated.', 'success')
        return jsonify({'status': 'success', 'message': 'Schedule updated.', 'schedule_state': current_state_for_json})

    with schedule_lock: # For GET request
        current_state_for_json = dict(schedule_state)
    return jsonify(current_state_for_json)

@app.route('/schedule/stop', methods=['POST'])
def stop_schedule():
    global schedule_state, schedule_lock, schedule_thread_obj
    with schedule_lock:
        if schedule_state['active']:
            schedule_state['active'] = False
            schedule_state['next_run_iso'] = None
            logger.info("Scheduler stop request received. Thread will stop on next check.")
            flash('Scheduler stopped. It may take up to a minute for the process to fully halt if it was about to run.', 'info')
            message = 'Scheduler stopping...'
        else:
            logger.info("Scheduler stop request received, but scheduler was not active.")
            flash('Scheduler was not active.', 'info')
            message = 'Scheduler was not active.'
            
    # schedule_thread_obj is a daemon, so it will exit when app exits or when its loop condition is false.
    # No explicit join here to keep request responsive.
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
