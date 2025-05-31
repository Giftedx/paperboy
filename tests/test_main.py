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
        self.mock_logger_exception = self.patch_logger_exception.start()
        
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
        # These are applied globally by self.mock_config_get.side_effect in setUp
        # For specific tests needing different config values, you can re-assign
        # self.mock_config_get.side_effect within that test method before calling main_module.main()
        # or use a more granular dictionary for side_effect if many keys change per test.
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

        # Verify status updates
        expected_status_calls = [
            # step, status, message contains, percent
            ('config_load', 'in_progress', 'Loading configuration...', 0),
            ('config_load', 'success', 'Configuration loaded', 5),
            ('date_setup', 'in_progress', 'Determining target date...', 10),
            ('date_setup', 'success', 'Target date: Friday, January 01, 2023', 15), # Assumes target_date is 2023-01-01
            ('download', 'in_progress', 'Downloading newspaper...', 20),
            ('download', 'success', 'Newspaper downloaded: 2023-01-01_newspaper.pdf', 40),
            ('upload', 'in_progress', 'Uploading to cloud storage...', 45),
            ('upload', 'success', 'Upload complete!', 60),
            ('thumbnail', 'in_progress', 'Generating thumbnail...', 65),
            # Thumbnail success depends on the mocked format, default is .jpg
            ('thumbnail', 'success', 'Thumbnail created and uploaded!', 75),
            ('email', 'in_progress', 'Preparing email...', 80),
            ('email', 'success', 'Email sent/drafted successfully!', 95),
            ('cleanup', 'in_progress', 'Cleaning up old newspapers...', 97),
            ('cleanup', 'success', 'Cleanup process complete.', 99),
            ('complete', 'success', 'Newspaper processing complete!', 100),
        ]

        actual_status_updates = []
        for call_args in self.mock_open().write.call_args_list:
            written_content = call_args[0][0] # call_args is like ((content,),)
            try:
                actual_status_updates.append(json.loads(written_content))
            except json.JSONDecodeError:
                self.fail(f"Non-JSON content written to status file: {written_content}")

        self.assertGreaterEqual(len(actual_status_updates), len(expected_status_calls), "Fewer status updates than expected.")

        for i, expected in enumerate(expected_status_calls):
            actual = actual_status_updates[i]
            self.assertEqual(actual.get('step'), expected[0])
            self.assertEqual(actual.get('status'), expected[1])
            self.assertIn(expected[2], actual.get('message', ''))
            self.assertEqual(actual.get('percent'), expected[3])

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
        # Verify status update for upload failure
        status_update_found = False
        for call_item in self.mock_open().write.call_args_list:
            try:
                status_data = json.loads(call_item[0][0])
                if status_data.get("step") == "upload" and status_data.get("status") == "error":
                    self.assertIn("Upload failed: S3 Upload Failed", status_data.get("message", ""))
                    status_update_found = True
                    break
            except json.JSONDecodeError: pass
        self.assertTrue(status_update_found, "Status update for upload failure not found.")

    def test_main_upload_failure_get_url_returns_none(self):
        """Test main pipeline when get_file_url returns None after newspaper upload."""
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_upload.return_value = None # Simulate successful upload call
        self.mock_storage_get_url.return_value = None # But get_file_url returns None

        result = main_module.main(target_date_str="2023-01-01")

        self.assertFalse(result)
        self.mock_storage_upload.assert_called_once_with("test_downloads/2023-01-01_newspaper.pdf", "2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.assert_called_once_with("2023-01-01_newspaper.pdf")
        self.mock_logger_exception.assert_any_call("Cloud storage upload failed for '%s': %s", "2023-01-01_newspaper.pdf", unittest.mock.ANY)

        status_update_found = False
        for call_item in self.mock_open().write.call_args_list:
            try:
                status_data = json.loads(call_item[0][0])
                if status_data.get("step") == "upload" and status_data.get("status") == "error":
                    self.assertIn("Failed to get cloud URL after upload", status_data.get("message", ""))
                    status_update_found = True
                    break
            except json.JSONDecodeError: pass
        self.assertTrue(status_update_found, "Status update for get_file_url returning None not found.")


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

    def test_main_thumbnail_upload_failure_is_graceful(self):
        """Test that if thumbnail is generated but fails to upload, pipeline still proceeds."""
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.side_effect = lambda fn: f"http://cloud/{fn}" if "newspaper.pdf" in fn else None
        self.mock_thumbnail_generate.return_value = True # Thumbnail generated locally

        # Simulate thumbnail upload failure: first upload (newspaper) ok, second (thumbnail) fails
        self.mock_storage_upload.side_effect = [
            None, # Newspaper upload success
            Exception("S3 Thumbnail Upload Failed") # Thumbnail upload failure
        ]
        self.mock_email_send.return_value = True

        result = main_module.main(target_date_str="2023-01-01")
        self.assertTrue(result) # Main pipeline should still succeed
        self.mock_logger_exception.assert_any_call("Failed to upload thumbnail '%s': %s", "2023-01-01_thumbnail.jpg", unittest.mock.ANY)
        self.mock_email_send.assert_called_once()
        args, kwargs = self.mock_email_send.call_args
        self.assertIsNone(kwargs.get('thumbnail_url')) # No thumbnail URL passed to email
        # Verify status update for thumbnail upload failure
        status_update_found = False
        for call_item in self.mock_open().write.call_args_list:
            try:
                status_data = json.loads(call_item[0][0])
                if status_data.get("step") == "thumbnail" and status_data.get("status") == "error":
                    if "Thumbnail upload failed" in status_data.get("message", ""):
                        status_update_found = True
                        break
            except json.JSONDecodeError: pass
        self.assertTrue(status_update_found, "Status update for thumbnail upload failure not found.")

    def test_main_thumbnail_upload_failure_get_url_none(self):
        """Test graceful handling if thumbnail uploads but get_file_url returns None."""
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        # Newspaper URL is fine
        self.mock_storage_get_url.side_effect = lambda fn: "http://cloud/newspaper.pdf" if "newspaper.pdf" in fn else None
        self.mock_thumbnail_generate.return_value = True # Thumbnail generated
        # Mock storage_upload: first (newspaper) fine, second (thumbnail) fine
        self.mock_storage_upload.side_effect = [None, None]
        self.mock_email_send.return_value = True

        result = main_module.main(target_date_str="2023-01-01")
        self.assertTrue(result) # Main pipeline should still succeed
        # Logger should indicate the issue
        self.mock_logger_exception.assert_any_call("Failed to upload thumbnail '%s': %s", "2023-01-01_thumbnail.jpg", unittest.mock.ANY)
        # Email should be sent without thumbnail_url
        self.mock_email_send.assert_called_once()
        args, kwargs = self.mock_email_send.call_args
        self.assertIsNone(kwargs.get('thumbnail_url'))
        # Check status update
        status_update_found = False
        for call_item in self.mock_open().write.call_args_list:
            try:
                status_data = json.loads(call_item[0][0])
                if status_data.get("step") == "thumbnail" and status_data.get("status") == "error":
                    # This error message comes from the ClientError raised in main.py
                    self.assertIn("Failed to get thumbnail cloud URL after upload", status_data.get("message", ""))
                    status_update_found = True
                    break
            except json.JSONDecodeError: pass
        self.assertTrue(status_update_found, "Status update for thumbnail get_url None not found.")


    def test_main_email_failure(self):
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.return_value = "http://cloud/2023-01-01_newspaper.pdf"
        self.mock_thumbnail_generate.return_value = True # Assume thumbnail success
        self.mock_email_send.return_value = False # Email sending fails

        result = main_module.main(target_date_str="2023-01-01")
        self.assertFalse(result)
        # Check for a log message from main.py indicating email failure (send_email itself should log details)
        # self.mock_open.assert_any_call(main_module.STATUS_FILE, 'w', encoding='utf-8') # Status update
        # The actual error logging is inside email_sender.py, main.py just logs "Email preparation/sending failed"

        # Verify status update for email failure
        status_update_found = False
        for call_item in self.mock_open().write.call_args_list:
            try:
                status_data = json.loads(call_item[0][0])
                if status_data.get("step") == "email" and status_data.get("status") == "error":
                    self.assertIn("Failed to send/draft email", status_data.get("message", ""))
                    status_update_found = True
                    break
            except json.JSONDecodeError: pass
        self.assertTrue(status_update_found, "Status update for email failure not found.")


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

    def test_main_force_download_mode(self):
        """Test that force_download=True is passed to website.login_and_download."""
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.return_value = "http://cloud/2023-01-01_newspaper.pdf"
        self.mock_email_send.return_value = True

        main_module.main(target_date_str="2023-01-01", force_download=True)

        self.mock_website_login.assert_called_with(
            base_url=unittest.mock.ANY, username=unittest.mock.ANY, password=unittest.mock.ANY,
            save_path=os.path.join('test_downloads', '2023-01-01_newspaper'),
            target_date='2023-01-01', dry_run=False, force_download=True # Key assertion
        )

    def test_main_dry_run_mode(self):
        # Ensure thumbnail format is correctly determined for dry run URL construction
        # Re-patch config_get for this specific test to ensure THUMBNAIL_FILENAME_TEMPLATE uses jpg
        original_side_effect = self.mock_config_get.side_effect
        def dry_run_config_get_side_effect(key_tuple, default=None):
            if key_tuple == ('general', 'thumbnail_filename_template'): return "{date}_thumbnail.jpg"
            if key_tuple == ('thumbnail', 'format'): return "jpeg" # from thumbnail.py, affects extension
            return original_side_effect(key_tuple, default)
        self.mock_config_get.side_effect = dry_run_config_get_side_effect
        main_module.THUMBNAIL_FILENAME_TEMPLATE = "{date}_thumbnail.jpg" # Ensure template is also updated

        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        # storage.get_file_url is called for email and before cleanup.
        # In dry_run, these URLs are constructed, not actually retrieved from storage.
        # self.mock_storage_get_url is not directly used to form the dry_run URLs in main.py
        # The URLs are constructed like "http://dry_run_cloud_storage_url/filename"

        result = main_module.main(target_date_str="2023-01-01", dry_run=True)
        self.assertTrue(result)
        self.mock_storage_upload.assert_not_called() # Should not be called in dry_run

        expected_paper_url = "http://dry_run_cloud_storage_url/2023-01-01_newspaper.pdf"
        # The thumbnail filename depends on THUMBNAIL_FILENAME_TEMPLATE and thumbnail.THUMBNAIL_FORMAT
        # which is 'jpeg', so it becomes '.jpg'
        expected_thumbnail_url = "http://dry_run_cloud_storage_url/2023-01-01_thumbnail.jpg"

        self.mock_email_send.assert_called_once_with(
            target_date=date(2023,1,1),
            today_paper_url=expected_paper_url,
            past_papers=unittest.mock.ANY,
            thumbnail_url=expected_thumbnail_url,
            dry_run=True
        )
        # Check if cleanup was called with dry_run=True
        # cleanup_old_files_main calls storage.list_storage_files and then storage.delete_from_storage
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

    def test_main_thumbnail_skipped_for_unsupported_format(self):
        """Test that thumbnail generation is skipped for non-PDF/HTML files."""
        # Simulate download of a ZIP file
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.zip")
        self.mock_storage_get_url.return_value = "http://cloud/2023-01-01_newspaper.zip" # Paper URL
        self.mock_email_send.return_value = True

        result = main_module.main(target_date_str="2023-01-01")

        self.assertTrue(result)
        self.mock_thumbnail_generate.assert_not_called() # Should not attempt to generate thumbnail
        self.mock_logger_warning.assert_any_call(
            "Unsupported file format '%s' for thumbnail generation of '%s'. Skipping thumbnail.",
            "zip", "2023-01-01_newspaper.zip"
        )
        # Check that email is sent without thumbnail_url
        self.mock_email_send.assert_called_once()
        args, kwargs = self.mock_email_send.call_args
        self.assertIsNone(kwargs.get('thumbnail_url'))
        # Check that status update reflects skipped thumbnail
        # This requires checking calls to self.mock_open().write()
        # Example: json.dumps({'step': 'thumbnail', 'status': 'skipped', ...})

        # Verify status update for skipped thumbnail
        status_update_found = False
        for call_item in self.mock_open().write.call_args_list:
            args, _ = call_item
            written_content = args[0]
            try:
                status_data = json.loads(written_content)
                if status_data.get("step") == "thumbnail" and status_data.get("status") == "skipped":
                    status_update_found = True
                    self.assertIn("Unsupported format for thumbnail: zip", status_data.get("message", ""))
                    break
            except json.JSONDecodeError:
                pass # Not a json string, skip
        self.assertTrue(status_update_found, "Status update for skipped thumbnail not found or incorrect.")

    def test_main_thumbnail_skipped_if_input_file_missing(self):
        """Test thumbnail step skipped if downloaded paper is missing."""
        self.mock_website_login.return_value = (True, "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_storage_get_url.return_value = "http://cloud/2023-01-01_newspaper.pdf"
        self.mock_email_send.return_value = True

        # Simulate newspaper file not existing when thumbnail generation is attempted
        # This requires os.path.exists to return False for the specific newspaper_path
        # The default self.mock_os_path_exists returns True.
        def os_path_exists_side_effect(path):
            if path == "test_downloads/2023-01-01_newspaper.pdf":
                return False # File is missing
            return True # Other paths exist (like download_dir)
        self.mock_os_path_exists.side_effect = os_path_exists_side_effect

        result = main_module.main(target_date_str="2023-01-01")
        self.assertTrue(result)
        self.mock_thumbnail_generate.assert_not_called()
        self.mock_logger_error.assert_any_call("Cannot generate thumbnail, input file '%s' does not exist.", "test_downloads/2023-01-01_newspaper.pdf")
        self.mock_email_send.assert_called_once()
        args, kwargs = self.mock_email_send.call_args
        self.assertIsNone(kwargs.get('thumbnail_url'))

        status_update_found = False
        for call_item in self.mock_open().write.call_args_list:
            args, _ = call_item
            written_content = args[0]
            try:
                status_data = json.loads(written_content)
                if status_data.get("step") == "thumbnail" and status_data.get("status") == "error":
                    if "Newspaper file missing for thumbnailing" in status_data.get("message", ""):
                         status_update_found = True
                         break
            except json.JSONDecodeError:
                pass
        self.assertTrue(status_update_found, "Status update for missing newspaper for thumbnailing not found.")


if __name__ == "__main__":
    logging.disable(logging.NOTSET) # Ensure all logs are enabled for direct test runs
    unittest.main()
