import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import sys
import json
from datetime import datetime, date, timedelta
from pathlib import Path
import logging

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui_app import app as flask_app 
import main as main_module # Import main to access its config instance
from config import Config # To reset the singleton for config

# Store original module constants that might be globally patched by config.load()
ORIGINAL_DATE_FORMAT = main_module.DATE_FORMAT

class TestGUIApp(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        flask_app.testing = True
        self.client = flask_app.test_client()
        
        flask_app.secret_key = 'test_secret_key_for_session'

        self.original_environ = dict(os.environ)
        os.environ.clear()
        
        # Critical: Reset the shared config object for each test
        # This ensures that config loaded in one test doesn't affect another.
        # Both main_module and flask_app.config_module might hold references to the config singleton.
        new_config_instance = Config()
        main_module.config.config = new_config_instance
        if hasattr(flask_app, 'config_module') and hasattr(flask_app.config_module, 'config'):
             flask_app.config_module.config = new_config_instance
        else: # If gui_app directly imports config.config
             flask_app.config = new_config_instance


        # Common mocks
        self.patch_main_main = patch('gui_app.main.main')
        self.patch_main_get_last_7_days = patch('gui_app.main.get_last_7_days_status')
        self.patch_main_get_past_papers = patch('gui_app.main.get_past_papers_from_storage')

        self.patch_storage_list = patch('gui_app.storage.list_storage_files')
        self.patch_storage_download = patch('gui_app.storage.download_to_temp')
        self.patch_storage_delete = patch('gui_app.storage.delete_from_storage')
        self.patch_storage_get_url = patch('gui_app.storage.get_file_url')

        self.patch_email_send = patch('gui_app.email_sender.send_email')
        self.patch_email_alert = patch('gui_app.email_sender.send_alert_email')
        
        # Patch the load method on the *specific instance* that will be used by the app
        self.patch_config_load = patch.object(new_config_instance, 'load', return_value=True)
        self.patch_config_get = patch.object(new_config_instance, 'get')
        
        self.patch_threading_thread = patch('threading.Thread')
        
        self.patch_os_path_exists = patch('os.path.exists')
        self.patch_os_makedirs = patch('os.makedirs')
        self.patch_open = patch('builtins.open', new_callable=mock_open)

        # Start patches
        self.mock_main_main = self.patch_main_main.start()
        self.mock_main_get_last_7_days = self.patch_main_get_last_7_days.start()
        self.mock_main_get_past_papers = self.patch_main_get_past_papers.start()
        self.mock_storage_list = self.patch_storage_list.start()
        self.mock_storage_download = self.patch_storage_download.start()
        self.mock_storage_delete = self.patch_storage_delete.start()
        self.mock_storage_get_url = self.patch_storage_get_url.start()
        self.mock_email_send = self.patch_email_send.start()
        self.mock_email_alert = self.patch_email_alert.start()
        self.mock_config_load = self.patch_config_load.start()
        self.mock_config_get = self.patch_config_get.start()
        self.mock_threading_thread = self.patch_threading_thread.start()
        self.mock_os_path_exists = self.patch_os_path_exists.start()
        self.mock_os_makedirs = self.patch_os_makedirs.start()
        self.mock_open = self.patch_open.start()
        
        def default_config_get_side_effect(key_tuple, default=None):
            if key_tuple == ('general', 'date_format'): return '%Y-%m-%d'
            if key_tuple == ('paths', 'download_dir'): return 'test_downloads'
            return default
        self.mock_config_get.side_effect = default_config_get_side_effect
        
        # Restore main module's global DATE_FORMAT which might be set by config.load()
        main_module.DATE_FORMAT = ORIGINAL_DATE_FORMAT

        logging.disable(logging.CRITICAL)

    def tearDown(self):
        patch.stopall()
        os.environ.clear()
        os.environ.update(self.original_environ)
        logging.disable(logging.NOTSET)
        with flask_app.email_preview_lock: # Use the lock imported with the app
            flask_app.email_preview_data = {"status": "idle", "html": None, "error": None}
            flask_app.email_preview_thread = None


    def test_dashboard_route(self):
        self.mock_os_path_exists.return_value = True
        self.mock_open.return_value.readlines.return_value = ["INFO - Test log 1", "ERROR - Test error 1"]
        self.mock_main_get_last_7_days.return_value = [{'date': '2023-01-01', 'status': 'ready'}]
        
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dashboard", response.data)
        self.assertIn(b"Test log 1", response.data)
        self.assertIn(b"Test error 1", response.data)
        self.assertIn(b"2023-01-01", response.data)
        self.mock_main_get_last_7_days.assert_called_once()

    def test_dashboard_route_log_file_not_exists(self):
        self.mock_os_path_exists.return_value = False # Log file does not exist
        self.mock_main_get_last_7_days.return_value = []

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dashboard", response.data)
        # Should not contain log data, but check for a generic part of the template
        self.assertNotIn(b"Recent Logs", response.data) # Assuming "Recent Logs" title is removed or conditional
        self.mock_main_get_last_7_days.assert_called_once()

    def test_dashboard_route_get_status_exception(self):
        self.mock_os_path_exists.return_value = True # Log file exists
        self.mock_open.return_value.readlines.return_value = ["INFO - Test log 1"]
        self.mock_main_get_last_7_days.side_effect = Exception("Failed to get status")

        with self.client:
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Dashboard", response.data)
            self.assertIn(b"Could not retrieve status for the last 7 days.", response.data) # Check for flash message
        self.mock_main_get_last_7_days.assert_called_once()


    def test_manual_run_post_success(self):
        mock_thread_instance = MagicMock()
        self.mock_threading_thread.return_value = mock_thread_instance
        
        test_date = datetime.today().strftime('%Y-%m-%d')
        response = self.client.post('/run', data={
            'date': test_date, 'dry_run': 'true', 'force_download': 'true'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, url_for('dashboard', _external=False))
        
        self.mock_threading_thread.assert_called_once()
        args_tuple, _ = self.mock_threading_thread.call_args
        # args_tuple[0] is target, args_tuple[1] is args for target
        self.assertEqual(args_tuple[1][1], test_date) # target_date_str
        self.assertTrue(args_tuple[1][2]) # dry_run
        self.assertTrue(args_tuple[1][3]) # force_download
        mock_thread_instance.start.assert_called_once()

    def test_manual_run_post_invalid_date(self):
        response = self.client.post('/run', data={'date': 'invalid-date'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid date format.", response.data)

    def test_email_preview_post(self):
        mock_thread_instance = MagicMock()
        self.mock_threading_thread.return_value = mock_thread_instance

        response = self.client.post('/preview', data={
            'target_date': '2023-01-01',
            'today_paper_url': 'http://example.com/paper.pdf',
            'thumbnail_url': 'http://example.com/thumb.jpg'
        })
        self.assertEqual(response.status_code, 302) # Redirects to GET /preview
        
        with flask_app.email_preview_lock:
            self.assertEqual(flask_app.email_preview_data['status'], "generating")
        
        self.mock_threading_thread.assert_called_once()
        args_tuple, _ = self.mock_threading_thread.call_args
        # args_tuple[0] is target (_generate_email_preview_async)
        # args_tuple[1][0] is app_context
        # args_tuple[1][1] is form_data
        form_data_arg = args_tuple[1][1]
        self.assertEqual(form_data_arg['target_date'], '2023-01-01')
        mock_thread_instance.start.assert_called_once()

    def test_email_preview_data_route(self):
        with flask_app.email_preview_lock:
            flask_app.email_preview_data = {"status": "ready", "html": "<p>Test HTML</p>", "error": None}
        
        response = self.client.get('/preview_data')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], "ready")
        self.assertEqual(data['html'], "<p>Test HTML</p>")

    @patch('gui_app.calculate_next_run_datetime') # Patch within gui_app's scope
    @patch('gui_app.threading.Thread') # Patch Thread where it's used in gui_app
    def test_schedule_post_daily_starts_thread(self, mock_thread_constructor, mock_calc_next_run):
        mock_thread_instance = MagicMock()
        mock_thread_constructor.return_value = mock_thread_instance
        mock_calc_next_run.return_value = datetime(2023, 1, 1, 7, 0, 0) # Dummy next run time
        
        flask_app.schedule_thread_obj = None # Ensure thread is not "running"

        response = self.client.post('/schedule', data={'mode': 'daily', 'time': '07:00'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['schedule_state']['active'])
        self.assertEqual(data['schedule_state']['mode'], 'daily')
        mock_thread_constructor.assert_called_once()
        mock_thread_instance.start.assert_called_once()

    def test_schedule_post_invalid_time(self):
        response = self.client.post('/schedule', data={'mode': 'daily', 'time': 'invalid'})
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn("Invalid time format", data['message'])

    def test_progress_route_file_exists(self):
        status_data = {'step': 'test', 'status': 'success', 'message': 'Test progress'}
        self.mock_os_path_exists.return_value = True # Status file exists
        # Configure mock_open for the specific read call to STATUS_FILE
        self.mock_open.side_effect = lambda path, *args, **kwargs: mock_open(read_data=json.dumps(status_data)).return_value if path == main_module.STATUS_FILE else mock_open().return_value

        response = self.client.get('/progress')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data, status_data)
        self.mock_open.assert_called_with(main_module.STATUS_FILE, 'r', encoding='utf-8')


    def test_progress_route_file_not_found(self):
        self.mock_os_path_exists.return_value = False # Status file does NOT exist
        response = self.client.get('/progress')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['step'], 'idle') # Default status when file not found

    # --- Archive Routes ---
    def test_archive_route_success(self):
        self.mock_storage_list.return_value = [
            {'name': 'file1.pdf', 'size': 1024, 'last_modified': '2023-01-01'},
            {'name': 'file2.html', 'size': 2048, 'last_modified': '2023-01-02'}
        ]
        response = self.client.get('/archive')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"file1.pdf", response.data)
        self.assertIn(b"file2.html", response.data)
        self.mock_storage_list.assert_called_once()

    def test_archive_route_storage_error(self):
        self.mock_storage_list.side_effect = Exception("Storage connection failed")
        with self.client:
            response = self.client.get('/archive')
            self.assertEqual(response.status_code, 200) # Page still loads
            self.assertIn(b"Could not retrieve file list from storage.", response.data) # Flash message
        self.mock_storage_list.assert_called_once()

    def test_download_archive_file_success(self):
        self.mock_storage_download.return_value = "/tmp/safe_storage/file1.pdf"
        # Patch os.path.exists specifically for send_file if it does internal checks, though usually not needed for BytesIO
        with patch('gui_app.send_file') as mock_send_file:
            mock_send_file.return_value = "File content sent" # Dummy response from send_file
            response = self.client.get('/archive/download/file1.pdf')
            # self.assertEqual(response.status_code, 200) # send_file will return 200
            mock_send_file.assert_called_once_with("/tmp/safe_storage/file1.pdf", as_attachment=True)
        self.mock_storage_download.assert_called_once_with("/tmp/safe_storage/file1.pdf")


    def test_download_archive_file_not_found(self):
        self.mock_storage_download.return_value = None # Simulate file not found in storage
        with self.client:
            response = self.client.get('/archive/download/nonexistent.pdf')
            self.assertEqual(response.status_code, 302) # Redirect
            self.assertEqual(response.location, url_for('archive', _external=False))
            # Check for flash message after redirect
            # For this, we need to follow the redirect and check the response data of the target page
            response_redirect = self.client.get(response.location)
            self.assertIn(b"Could not download nonexistent.pdf. File not found or error.", response_redirect.data)
        self.mock_storage_download.assert_called_once_with("/tmp/safe_storage/nonexistent.pdf")


    def test_download_archive_file_invalid_path(self):
        # This tests the ../../etc/passwd scenario
        with self.client:
            response = self.client.get('/archive/download/../../etc/passwd')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, url_for('archive', _external=False))
            response_redirect = self.client.get(response.location)
            self.assertIn(b"Invalid file path: ../../etc/passwd", response_redirect.data)
        self.mock_storage_download.assert_not_called() # Should not be called due to path validation


    def test_delete_archive_file_success(self):
        with self.client:
            response = self.client.post('/archive/delete/file_to_delete.pdf')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, url_for('archive', _external=False))
            self.mock_storage_delete.assert_called_once_with("file_to_delete.pdf")
            # Check flash message
            response_redirect = self.client.get(response.location)
            self.assertIn(b"Deleted file_to_delete.pdf from storage.", response_redirect.data)

    def test_delete_archive_file_storage_error(self):
        self.mock_storage_delete.side_effect = Exception("Deletion failed")
        with self.client:
            response = self.client.post('/archive/delete/file_to_delete.pdf')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, url_for('archive', _external=False))
            self.mock_storage_delete.assert_called_once_with("file_to_delete.pdf")
            # Check flash message
            response_redirect = self.client.get(response.location)
            self.assertIn(b"Error deleting file_to_delete.pdf: Deletion failed", response_redirect.data)

    # --- Config Editor Routes ---
    def test_config_editor_get_success(self):
        self.mock_os_path_exists.side_effect = lambda p: True if p in ['config.yaml', '.env'] else False
        self.mock_open.side_effect = [
            mock_open(read_data="key: value").return_value, # config.yaml
            mock_open(read_data="SECRET=KEY").return_value  # .env
        ]
        response = self.client.get('/config')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"key: value", response.data)
        self.assertIn(b"SECRET=KEY", response.data)

    def test_config_editor_get_files_not_found(self):
        self.mock_os_path_exists.return_value = False # Both files don't exist
        with self.client:
            response = self.client.get('/config')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Config file (config.yaml) not found.", response.data)
            self.assertIn(b".env file (.env) not found.", response.data)

    def test_config_editor_post_save_success(self):
        # Mock reading existing files (empty for simplicity)
        self.mock_os_path_exists.return_value = True
        mock_config_content_initial = ""
        mock_env_content_initial = ""

        # Mock open for reading then for writing
        # Read config.yaml, read .env, write config.yaml, write .env
        self.mock_open.side_effect = [
            mock_open(read_data=mock_config_content_initial).return_value,
            mock_open(read_data=mock_env_content_initial).return_value,
            mock_open().return_value, # For writing config.yaml
            mock_open().return_value  # For writing .env
        ]

        with self.client:
            response = self.client.post('/config', data={
                'config_content': 'new_key: new_value',
                'env_content': 'NEW_SECRET=NEW_KEY'
            })
            self.assertEqual(response.status_code, 302) # Redirect to config_editor
            self.assertEqual(response.location, url_for('config_editor', _external=False))

        # Check that open was called for writing with the new content
        write_calls = [c for c in self.mock_open.mock_calls if c[0] == '().write']
        self.assertIn(call('new_key: new_value'), write_calls)
        self.assertIn(call('NEW_SECRET=NEW_KEY'), write_calls)

        self.mock_config_load.assert_called_once() # Config reloaded

    def test_config_editor_post_save_invalid_yaml(self):
        self.mock_os_path_exists.return_value = True # Files exist for initial load
        self.mock_open.side_effect = [ # For initial GET
            mock_open(read_data="").return_value,
            mock_open(read_data="").return_value
        ]

        with self.client:
            response = self.client.post('/config', data={
                'config_content': 'invalid_yaml: [', # Invalid YAML
                'env_content': 'SECRET=KEY'
            })
            self.assertEqual(response.status_code, 200) # Re-renders template
            self.assertIn(b"Invalid YAML syntax", response.data)
            self.assertIn(b"invalid_yaml: [", response.data) # Shows content back
        self.mock_config_load.assert_not_called() # Should not reload if save fails

    def test_config_editor_post_save_io_error(self):
        self.mock_os_path_exists.return_value = True
        # Initial GET
        mock_initial_config_read = mock_open(read_data="key: val").return_value
        mock_initial_env_read = mock_open(read_data="S=K").return_value
        # Write attempt raises IOError
        mock_config_write_error = mock_open()
        mock_config_write_error.side_effect = IOError("Disk full")

        self.mock_open.side_effect = [
            mock_initial_config_read,
            mock_initial_env_read,
            mock_config_write_error # Attempt to write config.yaml
        ]

        with self.client:
            response = self.client.post('/config', data={
                'config_content': 'new_key: new_value',
                'env_content': 'NEW_SECRET=NEW_KEY'
            })
            self.assertEqual(response.status_code, 302) # Still redirects
            response_redirect = self.client.get(response.location)
            self.assertIn(b"Error saving configuration files: Disk full", response_redirect.data)
        self.mock_config_load.assert_not_called()


    # --- Health Routes ---
    def test_health_route(self):
        self.mock_os_path_exists.return_value = True # Log file exists
        self.mock_open.return_value.readlines.return_value = ["CRITICAL - System down"]
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"CRITICAL - System down", response.data)

    def test_health_test_alert_post_success(self):
        with self.client:
            response = self.client.post('/health/test_alert')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, url_for('health', _external=False))
            self.mock_email_alert.assert_called_once_with(
                'Test Alert from GUI',
                'This is a test alert message sent from the Newspaper Emailer application GUI.'
            )
            response_redirect = self.client.get(response.location)
            self.assertIn(b"Test alert email sent successfully.", response_redirect.data)

    def test_health_test_alert_post_email_error(self):
        self.mock_email_alert.side_effect = Exception("SMTP connection failed")
        with self.client:
            response = self.client.post('/health/test_alert')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, url_for('health', _external=False))
            response_redirect = self.client.get(response.location)
            self.assertIn(b"Failed to send test alert: SMTP connection failed", response_redirect.data)

    # --- Scheduler Routes ---
    def test_schedule_get_current_state(self):
        # Modify the global schedule_state in flask_app for this test
        with flask_app.schedule_lock:
            flask_app.schedule_state['mode'] = 'daily'
            flask_app.schedule_state['time'] = '08:00'
            flask_app.schedule_state['active'] = True

        response = self.client.get('/schedule')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['mode'], 'daily')
        self.assertEqual(data['time'], '08:00')
        self.assertTrue(data['active'])

    @patch('gui_app.calculate_next_run_datetime')
    @patch('gui_app.threading.Thread')
    def test_schedule_post_update_daily_starts_thread_if_not_alive(self, mock_thread_constructor, mock_calc_next_run):
        flask_app.schedule_thread_obj = None # Ensure thread object is None initially
        mock_thread_instance = MagicMock()
        mock_thread_instance.is_alive.return_value = False # Simulate thread not alive
        mock_thread_constructor.return_value = mock_thread_instance
        mock_calc_next_run.return_value = datetime(2023,1,1,9,0,0)

        response = self.client.post('/schedule', json={'mode': 'daily', 'time': '09:00'}) # Send as JSON
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['schedule_state']['active'])
        mock_thread_constructor.assert_called_once_with(target=flask_app.schedule_runner, daemon=True)
        mock_thread_instance.start.assert_called_once()

    def test_schedule_post_update_manual_stops_activity(self):
        with flask_app.schedule_lock: # Set initial state to active
            flask_app.schedule_state['active'] = True
            flask_app.schedule_state['next_run_iso'] = datetime.now().isoformat()

        response = self.client.post('/schedule', json={'mode': 'manual', 'time': '06:00'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertFalse(data['schedule_state']['active'])
        self.assertIsNone(data['schedule_state']['next_run_iso'])

    def test_stop_schedule_route_active(self):
        with flask_app.schedule_lock:
            flask_app.schedule_state['active'] = True

        response = self.client.post('/schedule/stop')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'stopping_or_inactive')
        self.assertIn("Scheduler stopping...", data['message'])
        with flask_app.schedule_lock:
            self.assertFalse(flask_app.schedule_state['active'])

    def test_stop_schedule_route_inactive(self):
        with flask_app.schedule_lock:
            flask_app.schedule_state['active'] = False

        response = self.client.post('/schedule/stop')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'stopping_or_inactive')
        self.assertIn("Scheduler was not active", data['message'])


if __name__ == "__main__":
    logging.disable(logging.NOTSET) 
    unittest.main()
