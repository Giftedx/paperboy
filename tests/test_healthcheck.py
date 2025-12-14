import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import healthcheck


class TestHealthCheck(unittest.TestCase):

    @patch("healthcheck.subprocess.Popen")
    def test_run_cmd_success(self, mock_popen):
        """Test successful command execution."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"output", b"")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        code, output = healthcheck.run_cmd(["echo", "hello"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "output")

    @patch("healthcheck.subprocess.Popen")
    def test_run_cmd_failure(self, mock_popen):
        """Test failed command execution."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"error output", b"")
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        code, output = healthcheck.run_cmd(["false"])

        self.assertEqual(code, 1)
        self.assertEqual(output, "error output")

    @patch("healthcheck.subprocess.Popen")
    def test_run_cmd_file_not_found(self, mock_popen):
        """Test command not found."""
        mock_popen.side_effect = FileNotFoundError("No such file")

        code, output = healthcheck.run_cmd(["missing_cmd"])

        self.assertEqual(code, 127)
        self.assertIn("Command not found", output)

    @patch("healthcheck.run_cmd")
    def test_main_success(self, mock_run_cmd):
        """Test main healthcheck success."""
        mock_run_cmd.return_value = (0, "Success")

        # We need to mock print or console to avoid cluttering output
        with patch("healthcheck.console"):
            ret = healthcheck.main()

        self.assertEqual(ret, 0)

    @patch("healthcheck.run_cmd")
    def test_main_failure(self, mock_run_cmd):
        """Test main healthcheck failure."""
        # Fail the first check
        mock_run_cmd.return_value = (1, "Failed")

        with patch("healthcheck.console"):
            ret = healthcheck.main()

        self.assertEqual(ret, 1)

if __name__ == "__main__":
    unittest.main()
