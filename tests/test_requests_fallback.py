import unittest
from unittest.mock import MagicMock, patch
import os
import importlib.util


class TestRequestsFallback(unittest.TestCase):

    def setUp(self):
        # Path to the requests.py file
        self.requests_py_path = os.path.abspath("requests.py")

        # Load the local requests.py as a module named 'local_requests'
        # We force the fallback mode behavior by setting the env var BEFORE loading
        with patch.dict(os.environ, {"REQUESTS_FALLBACK_FORCE": "1"}):
            spec = importlib.util.spec_from_file_location(
                "local_requests", self.requests_py_path
            )
            self.local_requests = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.local_requests)

    def test_get_success(self):
        """Test successful GET request."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b"OK"
            mock_response.headers.items.return_value = [("Content-Type", "text/plain")]

            # Context manager support
            mock_urlopen.return_value.__enter__.return_value = mock_response

            response = self.local_requests.get("http://example.com")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"OK")
            self.assertEqual(response.headers["Content-Type"], "text/plain")

    def test_get_network_error(self):
        """Test that network errors raise RequestException."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            import urllib.error

            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            with self.assertRaisesRegex(
                self.local_requests.RequestException, "Connection refused"
            ):
                self.local_requests.get("http://example.com")

    def test_get_timeout(self):
        """Test that timeouts are passed correctly."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b"OK"
            mock_urlopen.return_value.__enter__.return_value = mock_response

            # Timeout as float
            self.local_requests.get("http://example.com", timeout=5.0)
            args, kwargs = mock_urlopen.call_args
            self.assertEqual(kwargs["timeout"], 5.0)

            # Timeout as tuple
            self.local_requests.get("http://example.com", timeout=(3.0, 10.0))
            args, kwargs = mock_urlopen.call_args
            self.assertEqual(
                kwargs["timeout"], 3.0
            )  # Our simplified implementation takes the first element

    def test_raise_for_status(self):
        """Test raise_for_status behavior."""
        Response = self.local_requests.Response

        # 200 OK
        resp = Response(200, b"")
        resp.raise_for_status()  # Should not raise

        # 404 Not Found
        resp = Response(404, b"")
        with self.assertRaises(self.local_requests.HTTPError):
            resp.raise_for_status()

        # 500 Internal Server Error
        resp = Response(500, b"")
        with self.assertRaises(self.local_requests.HTTPError):
            resp.raise_for_status()

    def test_json_parsing(self):
        """Test .json() method."""
        Response = self.local_requests.Response

        resp = Response(200, b'{"key": "value"}')
        self.assertEqual(resp.json(), {"key": "value"})

        resp = Response(200, b"invalid json")
        with self.assertRaises(ValueError):
            resp.json()


if __name__ == "__main__":
    unittest.main()
