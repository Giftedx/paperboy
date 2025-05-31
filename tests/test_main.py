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
        # Instead of mocking open for status file, we'll mock main_module.update_status directly
        self.patch_update_status = patch('main.update_status')
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
        self.mock_update_status = self.patch_update_status.start() # Start the new mock

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
        self.mock_storage_get_url.side_effect = lambda fn: f"http://cloud/{fn}" # Used by main and get_past_papers
        self.mock_thumbnail_generate.return_value = True
        self.mock_storage_list.return_value = []
        self.mock_email_send.return_value = True

        target_date_obj = date(2023, 1, 1)
        target_date_str = target_date_obj.strftime('%Y-%m-%d')

        # Mock get_past_papers_from_storage directly if it's complex or to isolate
        # For now, relying on mock_storage_list and mock_storage_get_url for its behavior
        with patch('main.get_past_papers_from_storage', return_value=[]) as mock_get_past_papers:
            result = main_module.main(target_date_str=target_date_str)
        
        self.assertTrue(result)
        self.mock_config_load.assert_called_once()
        self.mock_website_login.assert_called_once_with(
            base_url='http://example.com/news',
            username='testuser', password='testpass',
            save_path=os.path.join('test_downloads', '2023-01-01_newspaper'),
            target_date=target_date_str, dry_run=False, force_download=False
        )
        # Upload newspaper and thumbnail
        self.assertEqual(self.mock_storage_upload.call_count, 2)
        self.mock_storage_upload.assert_any_call("test_downloads/2023-01-01_newspaper.pdf", "2023-01-01_newspaper.pdf")
        # Assuming thumbnail format is jpg from default config mock for THUMBNAIL_FILENAME_TEMPLATE
        self.mock_storage_upload.assert_any_call(os.path.join('test_downloads', "2023-01-01_thumbnail.jpg"), "2023-01-01_thumbnail.jpg")

        self.mock_thumbnail_generate.assert_called_once()
        mock_get_past_papers.assert_called_once_with(target_date_obj, days=7)
        self.mock_email_send.assert_called_once_with(
            target_date=target_date_obj,
            today_paper_url='http://cloud/2023-01-01_newspaper.pdf',
            past_papers=[], # from mock_get_past_papers
            thumbnail_url='http://cloud/2023-01-01_thumbnail.jpg',
            dry_run=False
        )
        self.mock_storage_list.assert_any_call() # Called by cleanup_old_files_main

        # Assert update_status calls
        expected_status_calls = [
            call('config_load', 'in_progress', 'Loading configuration...', percent=0),
            call('config_load', 'success', 'Configuration loaded and validated.', percent=5),
            call('date_setup', 'in_progress', 'Determining target date...', percent=10),
            call('date_setup', 'success', f"Target date: {target_date_obj.strftime('%A, %B %d, %Y')}", percent=15),
            call('download', 'in_progress', 'Downloading newspaper...', percent=20, eta='approx. 1-2 min'),
            call('download', 'success', 'Newspaper downloaded: 2023-01-01_newspaper.pdf', percent=40),
            call('upload', 'in_progress', 'Uploading to cloud storage...', percent=45, eta='approx. 30 sec'),
            call('upload', 'success', 'Upload complete!', percent=60),
            call('thumbnail', 'in_progress', 'Generating thumbnail...', percent=65, eta='approx. 20 sec'),
            call('thumbnail', 'success', 'Thumbnail created and uploaded!', percent=75),
            call('email', 'in_progress', 'Preparing email...', percent=80, eta='approx. 30 sec'),
            call('email', 'success', 'Email sent/drafted successfully!', percent=95),
            call('cleanup', 'in_progress', 'Cleaning up old newspapers from cloud storage...', percent=97),
            call('cleanup', 'success', 'Cleanup process complete.', percent=99),
            call('complete', 'success', 'Newspaper processing complete!', percent=100)
        ]
        self.mock_update_status.assert_has_calls(expected_status_calls, any_order=False)


    def test_main_config_load_failure(self):
        # Test when config.load() returns False
        self.mock_config_load.return_value = False
        result = main_module.main()
        self.assertFalse(result)
        # Check that update_status was called appropriately
        expected_status_calls = [
            call('config_load', 'in_progress', 'Loading configuration...', percent=0),
            call('config_load', 'error', 'Configuration failed. Check logs.', percent=0)
        ]
        self.mock_update_status.assert_has_calls(expected_status_calls, any_order=False)
        # self.mock_logger_critical.assert_any_call("Configuration validation failed. Exiting.") # Logger not directly called in main for this


    def test_main_download_failure(self):
        # Test when website.login_and_download returns failure
        self.mock_website_login.return_value = (False, "Simulated download error")
        result = main_module.main(target_date_str="2023-01-01")
        self.assertFalse(result)
        self.mock_logger_critical.assert_any_call("Download failed: Simulated download error")

        expected_status_calls = [
            call('config_load', 'success', unittest.mock.ANY, percent=unittest.mock.ANY), # Skips exact message match
            call('date_setup', 'success', unittest.mock.ANY, percent=unittest.mock.ANY),
            call('download', 'in_progress', unittest.mock.ANY, percent=unittest.mock.ANY, eta=unittest.mock.ANY),
            call('download', 'error', "Download failed: Simulated download error", percent=20)
        ]
        self.mock_update_status.assert_has_calls(expected_status_calls, any_order=True) # True because other calls happen before error

        self.mock_thumbnail_generate.assert_not_called()
        self.mock_storage_upload.assert_not_called()
        self.mock_email_send.assert_not_called()
        self.mock_email_alert.assert_not_called() # As per current main.py, it's commented out


    def test_main_upload_failure(self):
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_upload.side_effect = Exception("S3 Upload Failed") # Simulate upload failure

        result = main_module.main(target_date_str="2023-01-01")
        self.assertFalse(result)
        self.mock_logger_exception.assert_any_call("Cloud storage upload failed for '%s': %s", "2023-01-01_newspaper.pdf", unittest.mock.ANY)

        self.mock_update_status.assert_any_call('upload', 'error', "Upload failed: S3 Upload Failed", percent=45)


    def test_main_thumbnail_failure_is_graceful(self):
        # Ensures pipeline continues and sends email even if thumbnailing fails
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        # Both URLs for paper and (failed) thumbnail needed for email sending attempt
        self.mock_storage_get_url.side_effect = lambda fn: f"http://cloud/{fn}" if "newspaper" in fn else None
        self.mock_thumbnail_generate.return_value = False # Thumbnail generation fails
        self.mock_email_send.return_value = True # Email should still be sent

        result = main_module.main(target_date_str="2023-01-01")
        self.assertTrue(result)
        self.mock_logger_warning.assert_any_call("Thumbnail generation failed for '%s'. Email will be sent without a thumbnail.", "2023-01-01_newspaper.pdf")

        self.mock_update_status.assert_any_call('thumbnail', 'error', 'Thumbnail generation failed.', percent=75)

        self.mock_email_send.assert_called_once()
        args, kwargs = self.mock_email_send.call_args
        self.assertIsNone(kwargs.get('thumbnail_url'))


    def test_main_email_send_returns_false(self):
        # Test when email_sender.send_email explicitly returns False
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.side_effect = lambda fn: f"http://cloud/{fn}"
        self.mock_thumbnail_generate.return_value = True
        self.mock_email_send.return_value = False # Email sending fails by returning False

        result = main_module.main(target_date_str="2023-01-01")
        self.assertFalse(result)
        self.mock_update_status.assert_any_call('email', 'error', 'Failed to send/draft email. Check logs.', percent=80)
        self.mock_email_alert.assert_not_called()

    def test_main_email_send_raises_exception(self):
        # Test when email_sender.send_email raises an unhandled exception
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.side_effect = lambda fn: f"http://cloud/{fn}"
        self.mock_thumbnail_generate.return_value = True
        self.mock_email_send.side_effect = Exception("SMTP Connection Error")

        result = main_module.main(target_date_str="2023-01-01")
        self.assertFalse(result)
        self.mock_logger_exception.assert_any_call("Email preparation/sending failed: %s", unittest.mock.ANY)
        self.mock_update_status.assert_any_call('email', 'error', "Email preparation failed: SMTP Connection Error", percent=80)
        self.mock_email_alert.assert_not_called()


    def test_main_target_date_parsing(self):
        # Tests for how main handles valid, invalid, and None target_date_str
        # Valid date string
        self.mock_website_login.return_value = (True, "test_downloads/2023-10-26_newspaper.pdf")
        self.mock_storage_get_url.side_effect = lambda fn: f"http://cloud/{fn}"
        self.mock_email_send.return_value = True
        self.assertTrue(main_module.main(target_date_str="2023-10-26"))
        self.mock_update_status.assert_any_call('date_setup', 'success', "Target date: Thursday, October 26, 2023", percent=15)

        # Invalid date string format
        self.assertFalse(main_module.main(target_date_str="26-10-2023"))
        self.mock_logger_critical.assert_any_call("Invalid target_date_str format: '%s'. Expected '%s'.", "26-10-2023", "%Y-%m-%d")
        self.mock_update_status.assert_any_call('date_setup', 'error', "Invalid date format: 26-10-2023. Use %Y-%m-%d.", percent=10)

        # None (should default to today)
        with patch('main.date') as mock_date_type: # Patch date.today() within main module context
            mock_date_type.today.return_value = date(2023,1,1) # Mock today's date
            mock_date_type.side_effect = lambda *args, **kwargs: date(*args, **kwargs) # Allow date object creation

            self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
            self.mock_storage_get_url.side_effect = lambda fn: f"http://cloud/{fn}"
            self.assertTrue(main_module.main(target_date_str=None))
            self.mock_website_login.assert_called_with(
                base_url=unittest.mock.ANY, username=unittest.mock.ANY, password=unittest.mock.ANY,
                save_path=os.path.join('test_downloads', '2023-01-01_newspaper'), 
                target_date='2023-01-01', dry_run=False, force_download=False
            )
            self.mock_update_status.assert_any_call('date_setup', 'success', "Target date: Sunday, January 01, 2023", percent=15)


    def test_main_dry_run_mode(self):
        # Test main pipeline in dry_run mode
        self.mock_website_login.return_value = (True, "pdf") # login_and_download returns format in dry_run
        self.mock_thumbnail_generate.return_value = True

        # In dry_run, URLs are placeholders, storage.get_file_url isn't strictly needed for them
        # but might be called by get_past_papers_from_storage.
        self.mock_storage_get_url.side_effect = lambda fn: f"http://dry_run_cloud_storage_url/{fn}"


        with patch('main.get_past_papers_from_storage', return_value=[]) as mock_get_past_papers:
            result = main_module.main(target_date_str="2023-01-01", dry_run=True)

        self.assertTrue(result)
        self.mock_storage_upload.assert_not_called()
        self.mock_thumbnail_generate.assert_called_once() # Called, but internally handles dry_run path

        self.mock_email_send.assert_called_once_with(
            target_date=date(2023,1,1),
            today_paper_url="http://dry_run_cloud_storage_url/2023-01-01_newspaper.pdf",
            past_papers=[],
            thumbnail_url="http://dry_run_cloud_storage_url/2023-01-01_thumbnail.jpg", # Assuming jpg
            dry_run=True
        )
        self.mock_storage_list.assert_any_call() # Called by cleanup
        if self.mock_storage_delete.called:
             self.mock_storage_delete.assert_called_with(unittest.mock.ANY, dry_run=True)

        # Check status updates for dry run indications
        self.mock_update_status.assert_any_call('upload', 'success', 'Upload (simulated) complete.', percent=60)
        self.mock_update_status.assert_any_call('thumbnail', 'success', 'Thumbnail generation (simulated) complete.', percent=75)
        self.mock_update_status.assert_any_call('email', 'success', 'Email simulated sending/drafting successfully!', percent=95)


    @patch('main.storage.list_storage_files')
    @patch('main.storage.delete_from_storage') # Ensure this is the correct path to mock
    def test_cleanup_old_files_main_logic(self, mock_storage_delete_func, mock_storage_list_files_func):
        # Setup config mock for this specific test's needs for DATE_FORMAT and RETENTION_DAYS
        # This is correctly done by self.mock_config_get.side_effect in the test method
        current_config_mock_values = {
            ('general', 'date_format'): '%Y-%m-%d',
            ('general', 'retention_days'): 3 # Keep for 3 days
        }
        self.mock_config_get.side_effect = lambda key, default=None: current_config_mock_values.get(key, default)

        # Update the global RETENTION_DAYS as it's read at the start of main() or relevant function
        # For cleanup_old_files_main, it actually re-gets it from config inside.
        # No, cleanup_old_files_main uses the global RETENTION_DAYS. So we need to set it.
        main_module.RETENTION_DAYS = 3


        mock_storage_list_files_func.return_value = [
            "2023-01-01_newspaper.pdf", # Should be deleted
            "2023-01-02_thumbnail.jpg", # Should be deleted
            "2023-01-03_newspaper.html",# Should be deleted
            "2023-01-04_newspaper.pdf", # Keep
            "2023-01-05_thumbnail.jpg", # Keep
            "invalid_filename.txt"      # Should be skipped
        ]
        target_date_for_cleanup = date(2023, 1, 6) # Cleanup relative to this date

        main_module.cleanup_old_files_main(target_date_for_cleanup, dry_run=False)

        self.assertEqual(mock_storage_delete_func.call_count, 3)
        mock_storage_delete_func.assert_any_call("2023-01-01_newspaper.pdf", dry_run=False)
        mock_storage_delete_func.assert_any_call("2023-01-02_thumbnail.jpg", dry_run=False)
        mock_storage_delete_func.assert_any_call("2023-01-03_newspaper.html", dry_run=False)
    
    @patch('main.storage.list_storage_files')
    @patch('main.storage.get_file_url') # Ensure this is the correct path to mock
    def test_get_past_papers_from_storage_logic(self, mock_storage_get_file_url_func, mock_storage_list_files_func):
        current_config_mock_values = {
            ('general', 'date_format'): '%Y-%m-%d',
        }
        self.mock_config_get.side_effect = lambda key, default=None: current_config_mock_values.get(key, default)

        mock_storage_list_files_func.return_value = [
            "2023-01-05_newspaper.pdf", "2023-01-05_thumbnail.jpg", # Present
            "2023-01-04_newspaper.html", # Present
            # "2023-01-03" is missing
            "2023-01-02_newspaper.pdf", # Present
            "2023-01-01_newspaper.pdf", # Present but beyond 3 days relative to 2023-01-05
            "2022-12-31_newspaper.pdf"  # Present but beyond 3 days
        ]
        mock_storage_get_file_url_func.side_effect = lambda fn: f"http://cloud/{fn}"
        
        target_date = date(2023, 1, 5)
        links = main_module.get_past_papers_from_storage(target_date, days=3) # Get links for 3 days up to target_date
        
        self.assertEqual(len(links), 3)
        # Sorted by date descending
        self.assertEqual(links[0], ("2023-01-05", "http://cloud/2023-01-05_newspaper.pdf"))
        self.assertEqual(links[1], ("2023-01-04", "http://cloud/2023-01-04_newspaper.html"))
        self.assertEqual(links[2], ("2023-01-02", "http://cloud/2023-01-02_newspaper.pdf"))


    @patch('os.path.exists') # Mock os.path.exists used by get_last_7_days_status
    def test_get_last_7_days_status_logic(self, mock_os_path_exists_local):
        current_config_mock_values = {
            ('general', 'date_format'): '%Y-%m-%d',
            ('paths', 'download_dir'): 'test_dl_dir'
        }
        self.mock_config_get.side_effect = lambda key, default=None: current_config_mock_values.get(key, default)
        # Ensure main_module.DATE_FORMAT global is updated if it's used by the function directly before config access
        # get_last_7_days_status gets DATE_FORMAT from config, so this should be fine.

        # Simulate which files "exist" relative to a fixed "today" date for consistent testing
        # Let "today" be date(2023, 1, 7)
        # today-0 (Jan 7): pdf found
        # today-1 (Jan 6): html found
        # today-2 (Jan 5): nothing
        # today-3 (Jan 4): pdf found
        # today-4 (Jan 3): nothing found
        # today-5 (Jan 2): html found
        # today-6 (Jan 1): nothing found

        # FILENAME_TEMPLATE will be fetched from config by the function
        # Example: "{date}_newspaper.{format}"

        def os_path_exists_side_effect(path_str):
            # path_str will be like 'test_dl_dir/YYYY-MM-DD_newspaper.pdf' or .html
            if path_str == os.path.join('test_dl_dir', "2023-01-07_newspaper.pdf"): return True
            if path_str == os.path.join('test_dl_dir', "2023-01-06_newspaper.html"): return True
            # No for 2023-01-05
            if path_str == os.path.join('test_dl_dir', "2023-01-04_newspaper.pdf"): return True
            # No for 2023-01-03
            if path_str == os.path.join('test_dl_dir', "2023-01-02_newspaper.html"): return True
            # No for 2023-01-01
            return False # Default to not found
        mock_os_path_exists_local.side_effect = os_path_exists_side_effect

        with patch('main.date') as mock_main_date_module: # Patch the date object from datetime module where main.py imports it
            mock_main_date_module.today.return_value = date(2023, 1, 7)
            # Allow creation of new date objects using the original date constructor
            mock_main_date_module.side_effect = lambda *args, **kwargs: date(*args, **kwargs)


            statuses = main_module.get_last_7_days_status()
        
        self.assertEqual(len(statuses), 7)
        expected_statuses = [ # Reversed order from loop, so oldest first
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
