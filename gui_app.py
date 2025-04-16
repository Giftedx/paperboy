"""
Flask-based GUI for the Newspaper Emailer System
Allows admin to monitor, trigger, and configure the newspaper delivery pipeline.
"""

import os
import main
import storage
import email_sender
import config
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from datetime import datetime
import threading
import time

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'newspaper-emailer-secret')

# --- Dashboard Route ---
@app.route('/')
def dashboard():
    log_path = 'newspaper_emailer.log'
    logs = []
    recent_errors = []
    last_run = {'status': 'N/A', 'time': 'N/A', 'result': 'N/A'}
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f.readlines()[-200:]:
                logs.append(line.strip())
                if 'ERROR' in line or 'CRITICAL' in line:
                    recent_errors.append(line.strip())
                if 'completed successfully' in line:
                    last_run['status'] = 'Success'
                    last_run['time'] = line.split(' - ')[0]
                    last_run['result'] = 'OK'
                elif 'run failed' in line:
                    last_run['status'] = 'Failure'
                    last_run['time'] = line.split(' - ')[0]
                    last_run['result'] = 'Error'
    return render_template('dashboard.html', last_run=last_run, logs=logs[-50:], recent_errors=recent_errors[-10:])

# --- Manual Run Route ---
@app.route('/run', methods=['GET', 'POST'])
def manual_run():
    from datetime import date
    result = None
    today = date.today().strftime('%Y-%m-%d')
    if request.method == 'POST':
        date_str = request.form.get('date')
        dry_run = bool(request.form.get('dry_run'))
        force_download = bool(request.form.get('force_download'))
        success = main.main(target_date_str=date_str, dry_run=dry_run, force_download=force_download)
        result = 'Success' if success else 'Failure'
        flash(f'Manual run for {date_str}: {result}', 'success' if success else 'danger')
        return render_template('manual_run.html', today=today, result=result)
    return render_template('manual_run.html', today=today, result=result)

# --- Archive Browser Route ---
@app.route('/archive')
def archive():
    files = storage.list_storage_files()
    return render_template('archive.html', files=files)

@app.route('/archive/download/<filename>')
def download_file(filename):
    local_path = storage.download_to_temp(filename)
    return send_file(local_path, as_attachment=True)

@app.route('/archive/delete/<filename>', methods=['POST'])
def delete_file(filename):
    storage.delete_from_storage(filename)
    flash(f'Deleted {filename}', 'success')
    return redirect(url_for('archive'))

# --- Config Editor Route ---
@app.route('/config', methods=['GET', 'POST'])
def config_editor():
    config_path = 'config.yaml'
    env_path = '.env'
    config_content = ''
    env_content = ''
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config_content = f.read()
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
    if request.method == 'POST':
        new_config = request.form.get('config_content')
        new_env = request.form.get('env_content')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(new_config)
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(new_env)
        flash('Configuration updated.', 'success')
        return redirect(url_for('config_editor'))
    return render_template('config_editor.html', config_content=config_content, env_content=env_content)

# --- Email Preview Route ---
@app.route('/preview', methods=['GET', 'POST'])
def email_preview():
    preview_html = None
    if request.method == 'POST':
        from datetime import date
        today = date.today()
        today_paper_url = request.form.get('today_paper_url', '#')
        past_papers = []
        thumbnail_path = request.form.get('thumbnail_path', None)
        preview_html = email_sender.send_email(
            target_date=today,
            today_paper_url=today_paper_url,
            past_papers=past_papers,
            thumbnail_path=thumbnail_path,
            dry_run=True
        )
    return render_template('email_preview.html', preview_html=preview_html)

# --- Health/Alert Route ---
@app.route('/health')
def health():
    recent_errors = []
    log_path = 'newspaper_emailer.log'
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f.readlines()[-200:]:
                if 'ERROR' in line or 'CRITICAL' in line:
                    recent_errors.append(line.strip())
    return render_template('health.html', recent_errors=recent_errors[-10:])

@app.route('/health/test_alert', methods=['POST'])
def test_alert():
    email_sender.send_alert_email('Test Alert', 'This is a test alert from the GUI.')
    flash('Test alert sent.', 'info')
    return redirect(url_for('health'))

@app.route('/progress')
def progress():
    import json
    status_file = 'pipeline_status.json'
    if os.path.exists(status_file):
        with open(status_file, 'r', encoding='utf-8') as f:
            try:
                status = json.load(f)
            except Exception:
                status = {'step': 'unknown', 'status': 'unknown', 'message': 'No progress info available.'}
    else:
        status = {'step': 'none', 'status': 'none', 'message': 'No process running.'}
    return jsonify(status)

# --- Scheduling State ---
schedule_state = {
    'mode': 'manual',  # 'manual', 'daily', 'x_days', 'until_stopped'
    'start_date': None,
    'end_date': None,
    'days': None,
    'time': '06:00',
    'active': False,
    'next_run': None
}
schedule_lock = threading.Lock()
schedule_thread = None

def calculate_next_run():
    from datetime import datetime, timedelta
    now = datetime.now()
    run_time = schedule_state.get('time', '06:00')
    hour, minute = map(int, run_time.split(':'))
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run < now:
        next_run += timedelta(days=1)
    return next_run

def schedule_runner():
    global schedule_state
    while True:
        with schedule_lock:
            if not schedule_state['active']:
                break
            next_run = calculate_next_run()
            schedule_state['next_run'] = next_run.strftime('%Y-%m-%d %H:%M')
        now = datetime.now()
        wait_seconds = (next_run - now).total_seconds()
        if wait_seconds > 0:
            time.sleep(min(wait_seconds, 60))  # Check every minute
            continue
        # Time to run
        with schedule_lock:
            if not schedule_state['active']:
                break
        main.main(target_date_str=None, dry_run=False)
        with schedule_lock:
            if schedule_state['mode'] == 'x_days':
                if schedule_state['days'] is not None:
                    schedule_state['days'] -= 1
                    if schedule_state['days'] <= 0:
                        schedule_state['active'] = False
                        break
            elif schedule_state['mode'] == 'manual':
                schedule_state['active'] = False
                break
        time.sleep(60)  # Avoid double-run

@app.route('/schedule', methods=['GET', 'POST'])
def schedule():
    global schedule_thread
    if request.method == 'POST':
        mode = request.form.get('mode', 'manual')
        run_time = request.form.get('time', '06:00')
        days = request.form.get('days', None)
        with schedule_lock:
            schedule_state['mode'] = mode
            schedule_state['time'] = run_time
            schedule_state['active'] = mode != 'manual'
            if mode == 'x_days':
                schedule_state['days'] = int(days) if days else 1
            else:
                schedule_state['days'] = None
            schedule_state['next_run'] = calculate_next_run().strftime('%Y-%m-%d %H:%M') if schedule_state['active'] else None
        if schedule_state['active'] and (schedule_thread is None or not schedule_thread.is_alive()):
            schedule_thread = threading.Thread(target=schedule_runner, daemon=True)
            schedule_thread.start()
        return redirect(url_for('dashboard'))
    with schedule_lock:
        state = dict(schedule_state)
    return jsonify(state)

@app.route('/schedule/stop', methods=['POST'])
def stop_schedule():
    with schedule_lock:
        schedule_state['active'] = False
    return jsonify({'status': 'stopped'})

if __name__ == '__main__':
    app.run(debug=True)
