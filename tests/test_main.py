import unittest
from unittest.mock import patch, MagicMock, mock_open
from datetime import date
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main
import config


class TestMainRefactored(unittest.TestCase):
    def setUp(self):
        # Mock global config to prevent actual config loading or file access
        self.config_patcher = patch("main.config.config")
        self.mock_config = self.config_patcher.start()

        # Mock update_status to prevent file writes
        self.status_patcher = patch("main.update_status")
        self.mock_status = self.status_patcher.start()

    def tearDown(self):
        self.config_patcher.stop()
        self.status_patcher.stop()

    def test_determine_target_date_valid(self):
        """Test valid date parsing."""
        target = main.determine_target_date("2023-10-27")
        self.assertEqual(target, date(2023, 10, 27))

    def test_determine_target_date_invalid(self):
        """Test invalid date parsing."""
        target = main.determine_target_date("invalid-date")
        self.assertIsNone(target)

    def test_determine_target_date_none(self):
        """Test defaulting to today."""
        target = main.determine_target_date(None)
        self.assertEqual(target, date.today())

    @patch("main.website.download_file")
    def test_process_download_success(self, mock_download):
        """Test successful download."""
        mock_download.return_value = (True, "/path/to/downloaded.pdf")

        success, path = main.process_download(
            date(2023, 10, 27), "downloads", False, False
        )

        self.assertTrue(success)
        self.assertEqual(path, "/path/to/downloaded.pdf")
        mock_download.assert_called_once()

    @patch("main.website.download_file")
    def test_process_download_failure(self, mock_download):
        """Test failed download."""
        mock_download.return_value = (False, "Network error")

        success, error = main.process_download(
            date(2023, 10, 27), "downloads", False, False
        )

        self.assertFalse(success)
        self.assertEqual(error, "Download failed: Network error")

    @patch("main.storage.upload_to_storage")
    @patch("main.storage.get_file_url")
    def test_process_upload_success(self, mock_get_url, mock_upload):
        """Test successful upload."""
        mock_get_url.return_value = "http://cloud/file.pdf"

        success, url = main.process_upload(
            "/path/to/file.pdf", "file.pdf", False
        )

        self.assertTrue(success)
        self.assertEqual(url, "http://cloud/file.pdf")
        mock_upload.assert_called_with("/path/to/file.pdf", "file.pdf")

    @patch("main.storage.upload_to_storage")
    def test_process_upload_failure(self, mock_upload):
        """Test upload failure."""
        mock_upload.side_effect = Exception("Upload failed")

        success, url = main.process_upload(
            "/path/to/file.pdf", "file.pdf", False
        )

        self.assertFalse(success)
        self.assertIsNone(url)

    @patch("main.thumbnail.generate_thumbnail")
    @patch("main.storage.upload_to_storage")
    @patch("main.storage.get_file_url")
    @patch("os.path.exists")
    def test_process_thumbnail_success(self, mock_exists, mock_get_url, mock_upload, mock_gen):
        """Test successful thumbnail generation and upload."""
        mock_exists.return_value = True
        mock_gen.return_value = True
        mock_get_url.return_value = "http://cloud/thumb.jpg"

        url = main.process_thumbnail(
            date(2023, 10, 27), "downloads", "/path/to/pdf", "pdf", "file.pdf", False
        )

        self.assertEqual(url, "http://cloud/thumb.jpg")
        mock_gen.assert_called_once()
        mock_upload.assert_called_once()

    @patch("main.email_sender.send_email")
    def test_process_email_success(self, mock_send):
        """Test successful email sending."""
        mock_send.return_value = True

        success = main.process_email(
            date(2023, 10, 27), "http://paper", "http://thumb", False
        )

        self.assertTrue(success)

    @patch("main.setup_configuration")
    @patch("main.determine_target_date")
    @patch("main.process_download")
    @patch("main.process_upload")
    @patch("main.process_thumbnail")
    @patch("main.process_email")
    @patch("main.process_cleanup")
    def test_main_orchestration_success(self, mock_cleanup, mock_email, mock_thumb, mock_upload, mock_download, mock_date, mock_config):
        """Test the main function orchestration (happy path)."""
        mock_config.return_value = True
        mock_date.return_value = date(2023, 10, 27)
        mock_download.return_value = (True, "/path/paper.pdf")
        mock_upload.return_value = (True, "http://paper")
        mock_thumb.return_value = "http://thumb"
        mock_email.return_value = True

        # Configure config.get to return a valid string for date format
        self.mock_config.get.return_value = "%Y-%m-%d"

        success = main.main(None, False, False)

        self.assertTrue(success)
        mock_config.assert_called_once()
        mock_date.assert_called_once()
        mock_download.assert_called_once()
        mock_upload.assert_called_once()
        mock_thumb.assert_called_once()
        mock_email.assert_called_once()
        mock_cleanup.assert_called_once()

if __name__ == "__main__":
    unittest.main()
