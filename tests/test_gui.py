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

if __name__ == "__main__":
    logging.disable(logging.NOTSET) 
    unittest.main()
