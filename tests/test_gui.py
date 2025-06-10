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

    def test_dashboard_log_file_not_exists(self):
        self.mock_os_path_exists.return_value = False # Log file does not exist
        self.mock_main_get_last_7_days.return_value = []

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dashboard", response.data)
        self.assertNotIn(b"Test log 1", response.data) # Logs should be empty
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertEqual(len(flashes), 0) # No flash message if log file is just missing

    def test_dashboard_log_file_empty(self):
        self.mock_os_path_exists.return_value = True
        self.mock_open.return_value.readlines.return_value = [] # Log file is empty
        self.mock_main_get_last_7_days.return_value = []

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dashboard", response.data)
        self.assertNotIn(b"Test log 1", response.data)
        self.mock_open.assert_called_with('newspaper_emailer.log', 'r', encoding='utf-8')

    def test_dashboard_get_last_7_days_status_exception(self):
        self.mock_os_path_exists.return_value = True # Log file exists
        self.mock_open.return_value.readlines.return_value = ["INFO - Log content"]
        self.mock_main_get_last_7_days.side_effect = Exception("DB Error")

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dashboard", response.data)
        self.assertIn(b"Log content", response.data) # Logs should still show
        self.assertNotIn(b"2023-01-01", response.data) # Status data should be empty or not shown
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            self.assertIn(b"Could not retrieve status for the last 7 days.", flashes[0][1])


    def test_manual_run_post_success(self):
        mock_thread_instance = MagicMock()
        self.mock_threading_thread.return_value = mock_thread_instance
        
        # Need to use a fixed date for predictable url_for, if it were used for redirection with date.
        # However, current redirect is just to dashboard.
        # Using current date for the form is fine.
        current_date_format = self.mock_config_get(('general', 'date_format'), '%Y-%m-%d')
        test_date = datetime.today().strftime(current_date_format)

        response = self.client.post('/run', data={
            'date': test_date, 'dry_run': 'true', 'force_download': 'true'
        })
        self.assertEqual(response.status_code, 302)
        # Assuming url_for is imported in test_gui from flask
        from flask import url_for
        self.assertEqual(response.location, url_for('dashboard', _external=False))
        
        self.mock_threading_thread.assert_called_once()
        args_tuple, _ = self.mock_threading_thread.call_args
        # args_tuple[0] is target, args_tuple[1] is args for target
        self.assertEqual(args_tuple[1][1], test_date) # target_date_str
        self.assertTrue(args_tuple[1][2]) # dry_run
        self.assertTrue(args_tuple[1][3]) # force_download
        mock_thread_instance.start.assert_called_once()

    def test_manual_run_get(self):
        current_date_format = self.mock_config_get(('general', 'date_format'), '%Y-%m-%d')
        today_str = datetime.today().strftime(current_date_format)
        response = self.client.get('/run')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Manual Newspaper Run", response.data)
        self.assertIn(bytes(today_str, 'utf-8'), response.data) # Check if today's date is pre-filled

    def test_manual_run_post_missing_date(self):
        response = self.client.post('/run', data={
            'dry_run': 'true', 'force_download': 'true'
            # date is missing
        })
        self.assertEqual(response.status_code, 200) # Should re-render the form with an error
        self.assertIn(b"Date is required.", response.data)
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            self.assertIn(b"Date is required.", flashes[0][1])

    def test_manual_run_post_invalid_date(self):
        response = self.client.post('/run', data={'date': 'invalid-date'})
        self.assertEqual(response.status_code, 200) # Re-renders form
        self.assertIn(b"Invalid date format.", response.data) # Error message in HTML body
        with self.client.session_transaction() as sess: # Check flashed message
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            self.assertTrue(b"Invalid date format." in flashes[0][1])

    # --- Archive Routes Tests ---
    def test_archive_get_success(self):
        self.mock_storage_list.return_value = [
            {'name': '2023-01-01_paper.pdf', 'url': 'http://example.com/2023-01-01_paper.pdf', 'last_modified': 'Mon, 01 Jan 2023 10:00:00 GMT', 'size': 1024},
            {'name': '2023-01-02_paper.pdf', 'url': 'http://example.com/2023-01-02_paper.pdf', 'last_modified': 'Tue, 02 Jan 2023 10:00:00 GMT', 'size': 2048}
        ]
        response = self.client.get('/archive')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"File Archive", response.data)
        self.assertIn(b"2023-01-01_paper.pdf", response.data)
        self.mock_storage_list.assert_called_once()

    def test_archive_get_list_files_exception(self):
        self.mock_storage_list.side_effect = Exception("Storage connection error")
        response = self.client.get('/archive')
        self.assertEqual(response.status_code, 200) # Page should still render
        self.assertIn(b"File Archive", response.data)
        self.assertNotIn(b"2023-01-01_paper.pdf", response.data) # No files listed
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            self.assertIn(b"Could not retrieve file list from storage.", flashes[0][1])

    def test_archive_get_list_files_empty(self):
        self.mock_storage_list.return_value = []
        response = self.client.get('/archive')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"File Archive", response.data)
        self.assertIn(b"No files found in archive.", response.data) # Assuming template shows this

    def test_archive_download_success(self):
        self.mock_storage_download.return_value = "/tmp/safe_storage/2023-01-01_paper.pdf"
        # Need to mock send_file if we were testing its behavior, but here we test if download_to_temp is called
        # and if the response is what send_file would typically produce (or if it's mocked)
        with patch('gui_app.send_file', return_value=MagicMock(status_code=200)) as mock_send_file:
            response = self.client.get('/archive/download/2023-01-01_paper.pdf')
            self.assertEqual(response.status_code, 200)
            self.mock_storage_download.assert_called_once_with('/tmp/safe_storage/2023-01-01_paper.pdf')
            mock_send_file.assert_called_once_with("/tmp/safe_storage/2023-01-01_paper.pdf", as_attachment=True)

    def test_archive_download_download_to_temp_returns_none(self):
        self.mock_storage_download.return_value = None
        response = self.client.get('/archive/download/nonexistent.pdf')
        self.assertEqual(response.status_code, 302) # Redirects to archive
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('archive')))
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            self.assertIn(b"Could not download nonexistent.pdf. File not found or error.", flashes[0][1])

    def test_archive_download_download_to_temp_exception(self):
        self.mock_storage_download.side_effect = Exception("S3 Download Error")
        response = self.client.get('/archive/download/errorfile.pdf')
        self.assertEqual(response.status_code, 302) # Redirects
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('archive')))
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            self.assertIn(b"Error downloading errorfile.pdf: S3 Download Error", flashes[0][1])

    def test_archive_download_path_traversal_attempt(self):
        # The function normalizes paths including the base /tmp/safe_storage.
        # So, a traversal from filename needs to go up enough levels.
        # os.path.normpath(os.path.join('/tmp/safe_storage', '../../../etc/hosts')) would be '/etc/hosts'
        # The check is `if not normalized_path.startswith(safe_root):`
        response = self.client.get('/archive/download/../../../etc/passwd')
        self.assertEqual(response.status_code, 302)
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('archive')))
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            # The message might vary based on how filename is constructed before normpath
            # The current code uses the filename directly in the normpath.
            # So, the check `if not normalized_path.startswith(safe_root)` should catch it.
            # Expected filename in flash message would be the one passed in URL
            self.assertIn(b"Invalid file path: ../../../etc/passwd", flashes[0][1])


    def test_archive_delete_success(self):
        self.mock_storage_delete.return_value = True # Or whatever it returns on success
        response = self.client.post('/archive/delete/2023-01-01_paper.pdf')
        self.assertEqual(response.status_code, 302) # Redirects to archive
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('archive')))
        self.mock_storage_delete.assert_called_once_with('2023-01-01_paper.pdf')
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            self.assertIn(b"Deleted 2023-01-01_paper.pdf from storage.", flashes[0][1])

    def test_archive_delete_exception(self):
        self.mock_storage_delete.side_effect = Exception("S3 Delete Error")
        response = self.client.post('/archive/delete/error_delete.pdf')
        self.assertEqual(response.status_code, 302)
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('archive')))
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertGreater(len(flashes), 0)
            self.assertIn(b"Error deleting error_delete.pdf: S3 Delete Error", flashes[0][1])

    # --- Config Editor Tests ---
    def test_config_editor_get_success(self):
        self.mock_os_path_exists.side_effect = lambda path: True # Both files exist
        self.mock_open.side_effect = [
            mock_open(read_data="key: value").return_value, # config.yaml
            mock_open(read_data="VAR=secret").return_value  # .env
        ]
        response = self.client.get('/config')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"key: value", response.data)
        self.assertIn(b"VAR=secret", response.data)
        self.mock_os_path_exists.assert_any_call('config.yaml')
        self.mock_os_path_exists.assert_any_call('.env')

    def test_config_editor_get_config_yaml_not_exists(self):
        # .env exists, config.yaml does not
        self.mock_os_path_exists.side_effect = lambda path: path == '.env'
        self.mock_open.return_value = mock_open(read_data="VAR=secret").return_value # For .env

        response = self.client.get('/config')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"key: value", response.data) # config_content should be empty
        self.assertIn(b"VAR=secret", response.data)
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Config file (config.yaml) not found." in f[1] for f in flashes))

    def test_config_editor_get_dotenv_not_exists(self):
        # config.yaml exists, .env does not
        self.mock_os_path_exists.side_effect = lambda path: path == 'config.yaml'
        self.mock_open.return_value = mock_open(read_data="key: value").return_value # For config.yaml

        response = self.client.get('/config')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"key: value", response.data)
        self.assertNotIn(b"VAR=secret", response.data) # env_content should be empty
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b".env file (.env) not found." in f[1] for f in flashes))

    def test_config_editor_get_config_yaml_read_ioerror(self):
        self.mock_os_path_exists.return_value = True # Both files notionally exist
        self.mock_open.side_effect = [
            IOError("Cannot read config.yaml"), # Error for config.yaml
            mock_open(read_data="VAR=secret").return_value # .env reads fine
        ]
        response = self.client.get('/config')
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Error reading configuration files: Cannot read config.yaml" in f[1] for f in flashes))

    def test_config_editor_post_success(self):
        # self.mock_config_load is already set up in setUp to return True
        response = self.client.post('/config', data={
            'config_content': 'new_key: new_value',
            'env_content': 'NEW_VAR=new_secret'
        })
        self.assertEqual(response.status_code, 302) # Redirects on success
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('config_editor')))

        self.mock_open.assert_any_call('config.yaml', 'w', encoding='utf-8')
        self.mock_open.assert_any_call('.env', 'w', encoding='utf-8')
        # Get the mock file handle for config.yaml write and assert its content
        # This depends on the order of open calls if side_effect is a list.
        # Assuming config.yaml is written first, then .env
        # For more robustness, could inspect mock_open.mock_calls
        handle_config = self.mock_open.mock_calls[0].return_value
        handle_config.write.assert_called_once_with('new_key: new_value')
        handle_env = self.mock_open.mock_calls[1].return_value
        handle_env.write.assert_called_once_with('NEW_VAR=new_secret')

        self.mock_config_load.assert_called_once() # Ensure config.load() was called
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Configuration updated and reloaded." in f[1] for f in flashes))

    def test_config_editor_post_invalid_yaml(self):
        response = self.client.post('/config', data={
            'config_content': 'invalid_yaml: [ unclosed_bracket',
            'env_content': 'VAR=val'
        })
        self.assertEqual(response.status_code, 200) # Re-renders form
        self.assertIn(b"Invalid YAML syntax", response.data) # Error shown in HTML
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Invalid YAML syntax" in f[1] for f in flashes))
        self.mock_open.assert_not_called() # Should not attempt to write invalid YAML

    def test_config_editor_post_write_config_ioerror(self):
        self.mock_open.side_effect = IOError("Cannot write config.yaml")
        response = self.client.post('/config', data={
            'config_content': 'valid: yaml', 'env_content': 'VAR=val'
        })
        self.assertEqual(response.status_code, 302) # Still redirects, but with error
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Error saving configuration files: Cannot write config.yaml" in f[1] for f in flashes))
        self.mock_config_load.assert_not_called() # Load should not be called if write fails

    def test_config_editor_post_write_env_ioerror(self):
        # First open (config.yaml) succeeds, second ( .env) fails
        mock_config_write_handle = mock_open().return_value
        self.mock_open.side_effect = [
            mock_config_write_handle,
            IOError("Cannot write .env")
        ]
        response = self.client.post('/config', data={
            'config_content': 'valid: yaml', 'env_content': 'VAR=val'
        })
        self.assertEqual(response.status_code, 302) # Redirects
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Error saving configuration files: Cannot write .env" in f[1] for f in flashes))
        mock_config_write_handle.write.assert_called_once_with('valid: yaml') # Config was written
        self.mock_config_load.assert_not_called() # Load should not be called

    def test_config_editor_post_config_load_exception(self):
        self.mock_config_load.side_effect = Exception("Config load failed after write")
        response = self.client.post('/config', data={
            'config_content': 'valid: yaml', 'env_content': 'VAR=val'
        })
        self.assertEqual(response.status_code, 200) # Re-renders with error
        self.assertIn(b"An unexpected error occurred: Config load failed after write", response.data)
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"An unexpected error occurred: Config load failed after write" in f[1] for f in flashes))

    # --- Email Preview Tests ---
    def test_email_preview_get_various_statuses(self):
        test_cases = [
            ("idle", None, None, b"Preview not generated yet or generation in progress."),
            ("ready", "<p>Test HTML</p>", None, b"<p>Test HTML</p>"),
            ("error", None, "Test Error", b"Error generating preview: Test Error")
        ]
        from flask import url_for # Import url_for

        for status, html, error, expected_text in test_cases:
            with self.subTest(status=status):
                with flask_app.email_preview_lock:
                    flask_app.email_preview_data = {"status": status, "html": html, "error": error}

                response = self.client.get(url_for('email_preview'))
                self.assertEqual(response.status_code, 200)
                self.assertIn(expected_text, response.data)

    def test_email_preview_post_already_generating(self):
        with flask_app.email_preview_lock:
            flask_app.email_preview_data['status'] = 'generating'

        response = self.client.post('/preview', data={'target_date': '2023-01-01'})
        self.assertEqual(response.status_code, 302) # Redirect
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('email_preview')))
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Preview generation is already in progress." in f[1] for f in flashes))
        self.mock_threading_thread.assert_not_called() # No new thread should start

    @patch('gui_app._generate_email_preview_async') # To prevent actual thread creation
    def test_email_preview_post_thumbnail_url_handling(self, mock_generate_async_direct_patch):
        # This test focuses on ensuring thumbnail_url is passed, not the thread itself.
        # We mock _generate_email_preview_async directly as patching threading.Thread
        # then its target is more complex for just checking args.

        # Case 1: thumbnail_url is provided
        self.client.post('/preview', data={
            'target_date': '2023-01-01',
            'today_paper_url': 'http://example.com/paper.pdf',
            'thumbnail_url': 'http://example.com/thumb.jpg'
        })
        # mock_generate_async_direct_patch.assert_called_once() # This won't work as it's called in a thread
        # Instead, check the arguments passed to threading.Thread which then calls this.
        # This requires the original self.mock_threading_thread setup.
        # For simplicity, let's assume the thread starts and _generate_email_preview_async is called.
        # We will test the content of form_data passed to it by testing the thread's args.

        # Resetting for the next call, assuming previous test_email_preview_post might have used it.
        self.mock_threading_thread.reset_mock()
        mock_thread_instance = MagicMock()
        self.mock_threading_thread.return_value = mock_thread_instance

        self.client.post('/preview', data={
            'target_date': '2023-01-03',
            'today_paper_url': 'http://example.com/paper3.pdf',
            'thumbnail_url': 'http://example.com/thumb3.jpg'
        })
        args_tuple, _ = self.mock_threading_thread.call_args
        form_data_arg = args_tuple[1][1] # app_context, form_data
        self.assertEqual(form_data_arg['thumbnail_url'], 'http://example.com/thumb3.jpg')

        # Case 2: thumbnail_url is absent (empty string from form)
        self.mock_threading_thread.reset_mock()
        mock_thread_instance_2 = MagicMock()
        self.mock_threading_thread.return_value = mock_thread_instance_2
        self.client.post('/preview', data={
            'target_date': '2023-01-04',
            'today_paper_url': 'http://example.com/paper4.pdf',
            'thumbnail_url': '' # Empty from form
        })
        args_tuple_2, _ = self.mock_threading_thread.call_args
        form_data_arg_2 = args_tuple_2[1][1]
        self.assertEqual(form_data_arg_2['thumbnail_url'], '') # Should be passed as empty or None by form


    def test_generate_email_preview_async_get_past_papers_exception(self):
        self.mock_main_get_past_papers.side_effect = Exception("Storage list error")
        form_data = {'target_date': '2023-01-01', 'today_paper_url': 'url1', 'thumbnail_url': 'thumb1'}

        # Run in app_context as the original function does
        with flask_app.app_context():
            flask_app._generate_email_preview_async(flask_app.app_context(), form_data) # Pass app_context

        with flask_app.email_preview_lock:
            self.assertEqual(flask_app.email_preview_data['status'], 'error')
            self.assertEqual(flask_app.email_preview_data['error'], 'Storage list error')

    def test_generate_email_preview_async_send_email_returns_none(self):
        self.mock_main_get_past_papers.return_value = [] # Success
        self.mock_email_send.return_value = None # send_email returns None (simulating an issue)
        form_data = {'target_date': '2023-01-02', 'today_paper_url': 'url2', 'thumbnail_url': 'thumb2'}

        with flask_app.app_context():
            flask_app._generate_email_preview_async(flask_app.app_context(), form_data)

        with flask_app.email_preview_lock:
            self.assertEqual(flask_app.email_preview_data['status'], 'error')
            self.assertEqual(flask_app.email_preview_data['error'], "Email template generation returned no content.")

    def test_generate_email_preview_async_generic_exception(self):
        self.mock_main_get_past_papers.side_effect = ValueError("Generic value error in preview")
        form_data = {'target_date': '2023-01-03', 'today_paper_url': 'url3', 'thumbnail_url': 'thumb3'}

        with flask_app.app_context():
            flask_app._generate_email_preview_async(flask_app.app_context(), form_data)

        with flask_app.email_preview_lock:
            self.assertEqual(flask_app.email_preview_data['status'], 'error')
            self.assertEqual(flask_app.email_preview_data['error'], 'Generic value error in preview')

    # --- Health Routes Tests ---
    def test_health_get_success(self):
        self.mock_os_path_exists.return_value = True # Log file exists
        self.mock_open.return_value.readlines.return_value = ["ERROR - Test health error"]
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Health Check", response.data)
        self.assertIn(b"Test health error", response.data)

    def test_health_get_log_not_exists(self):
        self.mock_os_path_exists.return_value = False # Log file does not exist
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Health Check", response.data)
        self.assertNotIn(b"Test health error", response.data) # No errors displayed

    def test_health_get_log_read_exception(self):
        self.mock_os_path_exists.return_value = True # Log file exists
        self.mock_open.side_effect = IOError("Cannot read log for health")
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Health Check", response.data)
        # Depending on template, an error message might be shown, or just empty logs
        # The code logs an error via logger.error, but doesn't flash a message for this specific case.
        # So, we just check that the page renders.
        # If a specific message was expected in template: self.assertIn(b"Could not read log", response.data)

    def test_health_test_alert_post_success(self):
        self.mock_email_alert.return_value = True # Assume it returns something on success, or just doesn't raise
        response = self.client.post('/health/test_alert')
        self.assertEqual(response.status_code, 302) # Redirects to health
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('health')))
        self.mock_email_alert.assert_called_once_with('Test Alert from GUI', 'This is a test alert message sent from the Newspaper Emailer application GUI.')
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Test alert email sent successfully." in f[1] for f in flashes))

    def test_health_test_alert_post_exception(self):
        self.mock_email_alert.side_effect = Exception("SMTP Error")
        response = self.client.post('/health/test_alert')
        self.assertEqual(response.status_code, 302) # Redirects to health
        from flask import url_for
        self.assertTrue(response.location.endswith(url_for('health')))
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Failed to send test alert: SMTP Error" in f[1] for f in flashes))


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

    def test_progress_route_io_error(self):
        self.mock_os_path_exists.return_value = True # Status file exists
        self.mock_open.side_effect = IOError("Cannot read status file")

        response = self.client.get('/progress')
        self.assertEqual(response.status_code, 200) # Should still return JSON
        data = json.loads(response.data)
        self.assertEqual(data['step'], 'error')
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'Error reading status file.')
        self.mock_open.assert_called_with(main_module.STATUS_FILE, 'r', encoding='utf-8')

    def test_progress_route_json_decode_error(self):
        self.mock_os_path_exists.return_value = True # Status file exists
        # Configure mock_open to return a handle that simulates invalid JSON
        mock_file_handle = mock_open(read_data="this is not valid json").return_value
        self.mock_open.return_value = mock_file_handle

        response = self.client.get('/progress')
        self.assertEqual(response.status_code, 200) # Should still return JSON
        data = json.loads(response.data)
        self.assertEqual(data['step'], 'error')
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'Error reading status file.')

    # --- Scheduler Routes and Logic Tests ---
    def test_schedule_get(self):
        # Set a known initial state for predictability in the test
        with flask_app.schedule_lock:
            flask_app.schedule_state = {
                'mode': 'manual', 'time': '08:00', 'active': False,
                'next_run_iso': None, 'last_run_log': ['Test log entry']
            }

        response = self.client.get('/schedule')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['mode'], 'manual')
        self.assertEqual(data['time'], '08:00')
        self.assertFalse(data['active'])
        self.assertIsNone(data['next_run_iso'])
        self.assertEqual(data['last_run_log'], ['Test log entry'])

    def test_schedule_post_set_manual_stops_active_schedule(self):
        # Initial state: schedule is active
        with flask_app.schedule_lock:
            flask_app.schedule_state['active'] = True
            flask_app.schedule_state['mode'] = 'daily'
            flask_app.schedule_state['next_run_iso'] = datetime.now().isoformat()

        # Mock the thread object if it's checked (e.g., for is_alive)
        flask_app.schedule_thread_obj = MagicMock()
        flask_app.schedule_thread_obj.is_alive.return_value = True

        response = self.client.post('/schedule', data={'mode': 'manual', 'time': '09:00'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertFalse(data['schedule_state']['active']) # Should become inactive
        self.assertEqual(data['schedule_state']['mode'], 'manual')
        self.assertIsNone(data['schedule_state']['next_run_iso']) # next_run_iso cleared for manual
        self.mock_threading_thread.assert_not_called() # No new thread for manual mode

    @patch('gui_app.calculate_next_run_datetime')
    def test_schedule_post_daily_thread_already_alive(self, mock_calc_next_run):
        mock_calc_next_run.return_value = datetime(2023, 1, 2, 6, 0, 0)

        # Simulate thread being alive
        flask_app.schedule_thread_obj = MagicMock()
        flask_app.schedule_thread_obj.is_alive.return_value = True

        with flask_app.schedule_lock:
            flask_app.schedule_state['mode'] = 'manual' # Start from manual
            flask_app.schedule_state['active'] = False

        response = self.client.post('/schedule', data={'mode': 'daily', 'time': '06:00'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['schedule_state']['active'])
        self.assertEqual(data['schedule_state']['mode'], 'daily')
        # Crucially, threading.Thread() should NOT be called again to start a new thread
        self.mock_threading_thread.assert_not_called()
        mock_calc_next_run.assert_called_once_with('06:00')

    def test_schedule_stop_post_when_active(self):
        with flask_app.schedule_lock:
            flask_app.schedule_state['active'] = True
            flask_app.schedule_state['mode'] = 'daily'
            flask_app.schedule_state['next_run_iso'] = datetime.now().isoformat()

        flask_app.schedule_thread_obj = MagicMock() # Simulate a thread object
        flask_app.schedule_thread_obj.is_alive.return_value = True

        response = self.client.post('/schedule/stop')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'stopping_or_inactive')
        self.assertIn('Scheduler stopping...', data['message'])
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Scheduler stopped." in f[1] for f in flashes))
        with flask_app.schedule_lock:
            self.assertFalse(flask_app.schedule_state['active']) # Should be set to inactive

    def test_schedule_stop_post_when_not_active(self):
        with flask_app.schedule_lock:
            flask_app.schedule_state['active'] = False

        response = self.client.post('/schedule/stop')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'stopping_or_inactive')
        self.assertIn('Scheduler was not active.', data['message'])
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any(b"Scheduler was not active." in f[1] for f in flashes))

    @patch('gui_app.time.sleep', return_value=None) # Mock time.sleep to avoid actual sleep
    @patch('gui_app.datetime') # Mock datetime within gui_app
    @patch('gui_app.main.main') # Mock main.main called by the runner
    @patch('gui_app.calculate_next_run_datetime')
    def test_schedule_runner_logic(self, mock_calculate_next, mock_main_run, mock_datetime, mock_sleep):
        # This is an indirect test of schedule_runner's core logic

        # Setup initial state for a daily run
        run_time_str = "10:00"
        start_time = datetime(2023, 1, 1, 9, 59, 50) # Just before scheduled run
        scheduled_run_dt = datetime(2023, 1, 1, 10, 0, 0)

        mock_datetime.now.return_value = start_time
        mock_datetime.fromisoformat.side_effect = lambda iso_str: datetime.fromisoformat(iso_str) # Pass through

        mock_calculate_next.return_value = scheduled_run_dt # Initial calculation

        with flask_app.schedule_lock:
            flask_app.schedule_state = {
                'mode': 'daily', 'time': run_time_str, 'active': True,
                'next_run_iso': scheduled_run_dt.isoformat(), 'last_run_log': []
            }

        # --- Simulate first iteration of the loop ---
        # Make datetime.now() advance past the scheduled time for the check
        mock_datetime.now.return_value = scheduled_run_dt + timedelta(seconds=1)

        # Run the schedule_runner in the current thread to test its logic for one cycle
        # The thread normally runs indefinitely; we'll control its execution.
        # We need to simulate the app context behavior if main.main relies on it.
        # Since main.main is mocked, we don't strictly need app_context for *its* execution here.

        # To test the loop, we need a way to break it.
        # We'll patch 'active' to become False after main.main is called.
        original_main_run = mock_main_run
        def main_run_side_effect(*args, **kwargs):
            original_main_run(*args, **kwargs) # Call the original mock
            with flask_app.schedule_lock: # Then modify state to stop the loop
                flask_app.schedule_state['active'] = False
        mock_main_run.side_effect = main_run_side_effect

        # Recalculate next run for after the mocked main.main call
        next_day_scheduled_dt = scheduled_run_dt + timedelta(days=1)
        mock_calculate_next.return_value = next_day_scheduled_dt # This will be used for rescheduling

        # Call the runner - it should run once, call main, then stop due to side effect
        flask_app.schedule_runner()

        mock_main_run.assert_called_once()
        current_date_format = self.mock_config_get(('general', 'date_format'), '%Y-%m-%d')
        mock_main_run.assert_called_with(
            target_date_str=scheduled_run_dt.strftime(current_date_format),
            dry_run=False,
            force_download=False
        )

        # Verify that next run time was recalculated and set
        mock_calculate_next.assert_called_with(run_time_str) # Called after main run
        with flask_app.schedule_lock:
            self.assertEqual(flask_app.schedule_state['next_run_iso'], next_day_scheduled_dt.isoformat())
            self.assertFalse(flask_app.schedule_state['active']) # Check if loop termination logic worked

        mock_sleep.assert_called() # Sleep should have been called at least once

if __name__ == "__main__":
    logging.disable(logging.NOTSET) 
    unittest.main()
