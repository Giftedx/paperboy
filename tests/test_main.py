import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import sys
from pathlib import Path
from datetime import date, timedelta, datetime
import json # For checking status file content

# Add parent directory to path to import main and other project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as main_module # Rename to avoid conflict with main_module.main function
from config import Config # To reset the singleton

# Store original module constants that might be globally patched by config.load()
ORIGINAL_DATE_FORMAT = main_module.DATE_FORMAT
ORIGINAL_FILENAME_TEMPLATE = main_module.FILENAME_TEMPLATE
ORIGINAL_THUMBNAIL_FILENAME_TEMPLATE = main_module.THUMBNAIL_FILENAME_TEMPLATE
ORIGINAL_RETENTION_DAYS = main_module.RETENTION_DAYS


class TestMainPipeline(unittest.TestCase):
    """Test cases for the main newspaper processing pipeline."""

    def setUp(self):
        self.maxDiff = None # Show full diff on assertion failure
        # Store and clear os.environ for test isolation
        self.original_environ = dict(os.environ)
        os.environ.clear()

        # Reset the global config singleton before each test
        main_module.config.config = Config()

        # Common mocks for external dependencies
        self.patch_config_load = patch.object(main_module.config.config, 'load', return_value=True)
        self.patch_config_get = patch.object(main_module.config.config, 'get')
        
        self.patch_website_login = patch('main.website.login_and_download')
        self.patch_storage_upload = patch('main.storage.upload_to_storage')
        self.patch_storage_get_url = patch('main.storage.get_file_url')
        self.patch_storage_list = patch('main.storage.list_storage_files')
        self.patch_storage_delete = patch('main.storage.delete_from_storage')
        self.patch_thumbnail_generate = patch('main.thumbnail.generate_thumbnail')
        self.patch_email_send = patch('main.email_sender.send_email')
        self.patch_email_alert = patch('main.email_sender.send_alert_email') # For download failure alert
        
        self.patch_os_makedirs = patch('os.makedirs')
        self.patch_os_path_exists = patch('os.path.exists', return_value=True) # Assume files exist by default
        self.patch_open = patch('builtins.open', new_callable=mock_open) # For status file
        self.patch_logger_info = patch('main.logger.info')
        self.patch_logger_error = patch('main.logger.error')
        self.patch_logger_critical = patch('main.logger.critical')
        self.patch_logger_warning = patch('main.logger.warning')
        self.patch_logger_exception = patch('main.logger.exception')
        
        # Start patches
        self.mock_config_load = self.patch_config_load.start()
        self.mock_config_get = self.patch_config_get.start()
        self.mock_website_login = self.patch_website_login.start()
        self.mock_storage_upload = self.patch_storage_upload.start()
        self.mock_storage_get_url = self.patch_storage_get_url.start()
        self.mock_storage_list = self.patch_storage_list.start()
        self.mock_storage_delete = self.patch_storage_delete.start()
        self.mock_thumbnail_generate = self.patch_thumbnail_generate.start()
        self.mock_email_send = self.patch_email_send.start()
        self.mock_email_alert = self.patch_email_alert.start()
        self.mock_os_makedirs = self.patch_os_makedirs.start()
        self.mock_os_path_exists = self.patch_os_path_exists.start()
        self.mock_open = self.patch_open.start()

        self.mock_logger_info = self.patch_logger_info.start()
        self.mock_logger_error = self.patch_logger_error.start()
        self.mock_logger_critical = self.patch_logger_critical.start()
        self.mock_logger_warning = self.patch_logger_warning.start()
        self.mock_logger_exception = self.patch_logger_exception.start()


        # Default return values for config.get to simulate a loaded config
        # This allows testing logic that depends on these values.
        # Specific tests can override these with different side_effect values.
        def config_get_side_effect(key_tuple, default=None):
            if key_tuple == ('general', 'date_format'): return '%Y-%m-%d'
            if key_tuple == ('paths', 'download_dir'): return 'test_downloads'
            if key_tuple == ('newspaper', 'url'): return 'http://example.com/news'
            if key_tuple == ('newspaper', 'username'): return 'testuser'
            if key_tuple == ('newspaper', 'password'): return 'testpass'
            if key_tuple == ('general', 'retention_days'): return 7
            if key_tuple == ('general', 'retention_days_for_email_links'): return 7
            if key_tuple == ('general', 'filename_template'): return "{date}_newspaper.{format}"
            if key_tuple == ('general', 'thumbnail_filename_template'): return "{date}_thumbnail.{format}"
            return default
        self.mock_config_get.side_effect = config_get_side_effect
        
        # Reset main module's global constants that are set from config
        main_module.DATE_FORMAT = ORIGINAL_DATE_FORMAT
        main_module.FILENAME_TEMPLATE = ORIGINAL_FILENAME_TEMPLATE
        main_module.THUMBNAIL_FILENAME_TEMPLATE = ORIGINAL_THUMBNAIL_FILENAME_TEMPLATE
        main_module.RETENTION_DAYS = ORIGINAL_RETENTION_DAYS


    def tearDown(self):
        patch.stopall()
        os.environ.clear()
        os.environ.update(self.original_environ)

    def test_main_success_flow(self):
        """Test the main pipeline success flow with all mocks returning success."""
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.side_effect = lambda fn: f"http://cloud/{fn}"
        self.mock_thumbnail_generate.return_value = True # Thumbnail generation succeeds
        self.mock_storage_list.return_value = [] # No old files to clean for simplicity here
        self.mock_email_send.return_value = True # Email sent/drafted successfully

        target_date = date(2023, 1, 1)
        result = main_module.main(target_date_str=target_date.strftime('%Y-%m-%d'))
        
        self.assertTrue(result)
        self.mock_config_load.assert_called_once()
        self.mock_website_login.assert_called_once()
        self.mock_storage_upload.assert_called_once_with("test_downloads/2023-01-01_newspaper.pdf", "2023-01-01_newspaper.pdf")
        self.mock_thumbnail_generate.assert_called_once()
        self.mock_email_send.assert_called_once()
        # Check that cleanup_old_files_main was effectively called (by checking storage.list_storage_files from it)
        self.mock_storage_list.assert_any_call() # Called by get_past_papers and cleanup


    def test_main_config_load_failure(self):
        self.mock_config_load.return_value = False
        result = main_module.main()
        self.assertFalse(result)
        self.mock_logger_critical.assert_any_call("Configuration validation failed. Exiting.")


    def test_main_download_failure(self):
        self.mock_website_login.return_value = (False, "Simulated download error")
        result = main_module.main()
        self.assertFalse(result)
        self.mock_logger_critical.assert_any_call("Download failed: Simulated download error")
        # self.mock_email_alert.assert_called_once() # If alert email is re-enabled

    def test_main_upload_failure(self):
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_upload.side_effect = Exception("S3 Upload Failed")
        result = main_module.main(target_date_str="2023-01-01")
        self.assertFalse(result)
        self.mock_logger_exception.assert_any_call("Cloud storage upload failed for '%s': %s", "2023-01-01_newspaper.pdf", unittest.mock.ANY)

    def test_main_thumbnail_failure_is_graceful(self):
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.return_value = "http://cloud/2023-01-01_newspaper.pdf"
        self.mock_thumbnail_generate.return_value = False # Thumbnail generation fails
        self.mock_email_send.return_value = True # Email should still be sent

        result = main_module.main(target_date_str="2023-01-01")
        self.assertTrue(result) # Pipeline should still succeed overall
        self.mock_logger_warning.assert_any_call("Thumbnail generation failed for '%s'. Email will be sent without a thumbnail.", "2023-01-01_newspaper.pdf")
        # Check that email_sender.send_email was called with thumbnail_url=None or similar
        self.mock_email_send.assert_called_once()
        args, kwargs = self.mock_email_send.call_args
        self.assertIsNone(kwargs.get('thumbnail_url'))


    def test_main_email_failure(self):
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.return_value = "http://cloud/2023-01-01_newspaper.pdf"
        self.mock_thumbnail_generate.return_value = True # Assume thumbnail success
        self.mock_email_send.return_value = False # Email sending fails

        result = main_module.main(target_date_str="2023-01-01")
        self.assertFalse(result)
        # Check for a log message from main.py indicating email failure (send_email itself should log details)
        self.mock_open.assert_any_call(main_module.STATUS_FILE, 'w', encoding='utf-8') # Status update
        # The actual error logging is inside email_sender.py, main.py just logs "Email preparation/sending failed"


    def test_main_target_date_parsing(self):
        # Valid date string
        self.mock_website_login.return_value = (True, "test_downloads/2023-10-26_newspaper.pdf")
        self.mock_storage_get_url.return_value = "http://cloud/2023-10-26_newspaper.pdf"
        self.mock_email_send.return_value = True
        self.assertTrue(main_module.main(target_date_str="2023-10-26"))

        # Invalid date string format
        self.assertFalse(main_module.main(target_date_str="26-10-2023"))
        self.mock_logger_critical.assert_any_call("Invalid target_date_str format: '%s'. Expected '%s'.", "26-10-2023", "%Y-%m-%d")

        # None (should default to today) - Check if date.today() is used
        with patch('main.datetime') as mock_dt: # Patch datetime within main module
            mock_dt.today.return_value = date(2023,1,1) # Mock today's date
            mock_dt.strptime = datetime.strptime # Keep original strptime
            self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf") # Adjust mock for new date
            self.mock_storage_get_url.return_value = "http://cloud/2023-01-01_newspaper.pdf"
            self.assertTrue(main_module.main(target_date_str=None))
            self.mock_website_login.assert_called_with(
                base_url=unittest.mock.ANY, username=unittest.mock.ANY, password=unittest.mock.ANY,
                save_path=os.path.join('test_downloads', '2023-01-01_newspaper'), 
                target_date='2023-01-01', dry_run=False, force_download=False
            )


    def test_main_dry_run_mode(self):
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        # storage.get_file_url is called for email and before cleanup
        self.mock_storage_get_url.return_value = "http://cloud_dry_run/2023-01-01_newspaper.pdf"
        self.mock_thumbnail_generate.return_value = True # For thumbnail cloud URL

        result = main_module.main(target_date_str="2023-01-01", dry_run=True)
        self.assertTrue(result)
        self.mock_storage_upload.assert_not_called() # Should not be called in dry_run
        self.mock_email_send.assert_called_once_with(
            target_date=date(2023,1,1),
            today_paper_url="http://cloud_dry_run/2023-01-01_newspaper.pdf", # from dry_run logic
            past_papers=unittest.mock.ANY, # Assuming get_past_papers handles dry_run or is mocked
            thumbnail_url="http://cloud_dry_run/2023-01-01_thumbnail.jpg", # from dry_run logic
            dry_run=True
        )
        # Check if cleanup was called with dry_run=True
        # cleanup_old_files_main calls storage.list_storage_files and then storage.delete_from_storage
        self.mock_storage_list.assert_any_call() # Called by cleanup
        # If delete was called, it must have dry_run=True. If not called, that's also fine for dry_run.
        if self.mock_storage_delete.called:
             self.mock_storage_delete.assert_called_with(unittest.mock.ANY, dry_run=True)


    @patch('main.storage.list_storage_files')
    @patch('main.storage.delete_from_storage')
    def test_cleanup_old_files_main_logic(self, mock_delete, mock_list_files):
        # Setup config mock for this specific test's needs for DATE_FORMAT and RETENTION_DAYS
        def side_effect_config_get(key_tuple, default=None):
            if key_tuple == ('general', 'date_format'): return '%Y-%m-%d'
            if key_tuple == ('general', 'retention_days'): return 3 # Keep for 3 days
            return default
        self.mock_config_get.side_effect = side_effect_config_get
        main_module.RETENTION_DAYS = 3 # Update global that cleanup_old_files_main uses

        mock_list_files.return_value = [
            "2023-01-01_newspaper.pdf", # Should be deleted
            "2023-01-02_thumbnail.jpg", # Should be deleted
            "2023-01-03_newspaper.html",# Should be deleted
            "2023-01-04_newspaper.pdf", # Keep
            "2023-01-05_thumbnail.jpg", # Keep
            "invalid_filename.txt"      # Should be skipped
        ]
        target_date_for_cleanup = date(2023, 1, 6) # Cleanup relative to this date

        main_module.cleanup_old_files_main(target_date_for_cleanup, dry_run=False)

        self.assertEqual(mock_delete.call_count, 3)
        mock_delete.assert_any_call("2023-01-01_newspaper.pdf", dry_run=False)
        mock_delete.assert_any_call("2023-01-02_thumbnail.jpg", dry_run=False)
        mock_delete.assert_any_call("2023-01-03_newspaper.html", dry_run=False)
    
    @patch('main.storage.list_storage_files')
    @patch('main.storage.get_file_url')
    def test_get_past_papers_from_storage_logic(self, mock_get_url, mock_list_files):
        def side_effect_config_get(key_tuple, default=None):
            if key_tuple == ('general', 'date_format'): return '%Y-%m-%d'
            return default
        self.mock_config_get.side_effect = side_effect_config_get

        mock_list_files.return_value = [
            "2023-01-05_newspaper.pdf", "2023-01-05_thumbnail.jpg",
            "2023-01-04_newspaper.html",
            "2023-01-02_newspaper.pdf", # Gap here
            "2023-01-01_newspaper.pdf",
            "2022-12-31_newspaper.pdf"
        ]
        mock_get_url.side_effect = lambda fn: f"http://cloud/{fn}"
        
        target_date = date(2023, 1, 5)
        links = main_module.get_past_papers_from_storage(target_date, days=3)
        
        self.assertEqual(len(links), 3)
        self.assertEqual(links[0], ("2023-01-05", "http://cloud/2023-01-05_newspaper.pdf"))
        self.assertEqual(links[1], ("2023-01-04", "http://cloud/2023-01-04_newspaper.html"))
        self.assertEqual(links[2], ("2023-01-02", "http://cloud/2023-01-02_newspaper.pdf"))


    @patch('os.path.exists') # Mock os.path.exists used by get_last_7_days_status
    def test_get_last_7_days_status_logic(self, mock_os_path_exists_local):
        # Setup config mock for this specific test's needs
        def side_effect_config_get(key_tuple, default=None):
            if key_tuple == ('general', 'date_format'): return '%Y-%m-%d'
            if key_tuple == ('paths', 'download_dir'): return 'test_dl_dir'
            return default
        self.mock_config_get.side_effect = side_effect_config_get
        main_module.DATE_FORMAT = '%Y-%m-%d' # Update global

        # Simulate which files "exist"
        # Dates relative to today: date(2023,1,7)
        # today-0 (Jan 7): pdf found
        # today-1 (Jan 6): html found
        # today-2 (Jan 5): nothing
        # today-3 (Jan 4): pdf found
        # today-4 (Jan 3): nothing
        # today-5 (Jan 2): html found
        # today-6 (Jan 1): nothing
        def os_exists_side_effect(path):
            if path == os.path.join('test_dl_dir', '2023-01-07_newspaper.pdf'): return True
            if path == os.path.join('test_dl_dir', '2023-01-06_newspaper.html'): return True
            if path == os.path.join('test_dl_dir', '2023-01-04_newspaper.pdf'): return True
            if path == os.path.join('test_dl_dir', '2023-01-02_newspaper.html'): return True
            return False
        mock_os_path_exists_local.side_effect = os_exists_side_effect

        with patch('main.date') as mock_date_type: # Mock date.today()
            mock_date_type.today.return_value = date(2023, 1, 7)
            mock_date_type.side_effect = lambda *args, **kwargs: date(*args, **kwargs) # Allow date object creation

            statuses = main_module.get_last_7_days_status()
        
        self.assertEqual(len(statuses), 7)
        expected_statuses = [
            {'date': '2023-01-01', 'status': 'missing'},
            {'date': '2023-01-02', 'status': 'ready'},
            {'date': '2023-01-03', 'status': 'missing'},
            {'date': '2023-01-04', 'status': 'ready'},
            {'date': '2023-01-05', 'status': 'missing'},
            {'date': '2023-01-06', 'status': 'ready'},
            {'date': '2023-01-07', 'status': 'ready'},
        ]
        self.assertEqual(statuses, expected_statuses)

if __name__ == "__main__":
    logging.disable(logging.NOTSET) # Ensure all logs are enabled for direct test runs
    unittest.main()
