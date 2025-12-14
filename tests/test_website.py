import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import sys

# Add parent directory to path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import website  # noqa: E402


class TestWebsiteDownload(unittest.TestCase):

    def setUp(self):
        self.base_url = "https://example.com"
        self.save_path = "/tmp/test_download"
        self.target_date = "2023-10-26"

    @patch("website.config.config.get")
    def test_download_file_with_real_requests(self, mock_config_get):
        """Test download using real requests (mocked) with Session."""
        # Setup config
        mock_config_get.return_value = "newspaper/download/{date}"

        # Create a mock requests module
        mock_requests = MagicMock()
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        # Setup successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"PDF CONTENT"
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_session.get.return_value = mock_response

        # Since requests is imported inside the function, we must patch sys.modules BEFORE calling the function
        # AND ensuring that the import statement inside the function picks up our mock.
        # This requires that 'requests' is NOT in sys.modules, OR we overwrite it in sys.modules.

        with patch.dict(sys.modules, {"requests": mock_requests}):
            # We also need to ensure that when _get_session tries to import adapters, it succeeds.
            mock_adapters = MagicMock()
            mock_urllib3 = MagicMock()
            with patch.dict(
                sys.modules,
                {
                    "requests.adapters": mock_adapters,
                    "urllib3.util.retry": mock_urllib3,
                },
            ):
                with patch("builtins.open", mock_open()):
                    success, result = website.download_file(
                        self.base_url, self.save_path, self.target_date
                    )

        # Verify
        self.assertTrue(success)
        self.assertTrue(result.endswith(".pdf"))
        mock_requests.Session.assert_called_once()  # Verify Session was created
        mock_session.mount.assert_called()  # Verify adapters were mounted
        mock_session.get.assert_called_once()  # Verify session.get was used

    @patch("website.config.config.get")
    def test_download_file_fallback_no_session(self, mock_config_get):
        """Test download when requests lacks Session/Retry (fallback mode)."""
        mock_config_get.return_value = "newspaper/download/{date}"

        mock_requests = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"PDF CONTENT"
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_requests.get.return_value = mock_response

        # We need _get_session to return None.
        # Easier way: Patch website._get_session directly
        with patch.dict(sys.modules, {"requests": mock_requests}):
            with patch("website._get_session", return_value=None) as mock_get_session:
                with patch("builtins.open", mock_open()):
                    success, result = website.download_file(
                        self.base_url, self.save_path, self.target_date
                    )

        self.assertTrue(success)
        mock_get_session.assert_called_once()
        mock_requests.get.assert_called_once()  # Verify plain get was used

    def test_get_session_logic(self):
        """Test the logic inside _get_session."""
        # Case 1: Real requests with everything
        mock_req = MagicMock()

        # We need to ensure the imports inside _get_session work
        mock_adapters = MagicMock()
        mock_urllib3 = MagicMock()

        with patch.dict(
            sys.modules,
            {"requests.adapters": mock_adapters, "urllib3.util.retry": mock_urllib3},
        ):
            session = website._get_session(mock_req)
            self.assertIsNotNone(session)
            mock_req.Session.assert_called()

        # Case 2: Fallback requests (ImportError for adapters)

        # We need to ensure 'requests.adapters' triggers ImportError.
        # We can do this by patching builtins.__import__ specifically to fail for this module.

        orig_import = __import__

        def import_mock(name, *args, **kwargs):
            if name == "requests.adapters":
                raise ImportError("No module named requests.adapters")
            return orig_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_mock):
            # Depending on how the test runner works, the module might be cached.
            # Ensure we clear cache for this test context if needed, but patch.dict might not be enough if it's already imported.
            if "requests.adapters" in sys.modules:
                del sys.modules["requests.adapters"]

            session = website._get_session(mock_req)
            self.assertIsNone(session)

    @patch("website.config.config.get")
    def test_download_failure(self, mock_config_get):
        """Test download failure handling."""
        mock_config_get.return_value = "newspaper/download/{date}"

        mock_requests = MagicMock()
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session
        mock_session.get.side_effect = Exception("Connection Error")

        with patch.dict(sys.modules, {"requests": mock_requests}):
            with patch("website._get_session", return_value=mock_session):
                success, result = website.download_file(
                    self.base_url, self.save_path, self.target_date
                )

        self.assertFalse(success)
        self.assertIn("Download error", result)


if __name__ == "__main__":
    unittest.main()
