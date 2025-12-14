import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import configure


class TestConfigure(unittest.TestCase):

    @patch("configure.getpass.getpass")
    @patch("configure.Confirm.ask")
    @patch("configure.Prompt.ask")
    @patch("configure.IntPrompt.ask")
    @patch("configure.save_config_yaml")
    @patch("configure.save_env_file")
    def test_main_wizard_defaults(self, mock_save_env, mock_save_yaml, mock_int, mock_prompt, mock_confirm, mock_getpass):
        """Test wizard with default answers."""
        # Setup mocks to return defaults where possible or specific values
        mock_confirm.return_value = True
        mock_getpass.return_value = "secret_passphrase"

        # We need to align side_effect with the exact sequence of prompts.
        # configure.py sequence:
        # 1. Newspaper Base URL
        # 2. Download Path Pattern
        # 3. Storage Endpoint URL
        # 4. Bucket Name
        # 5. Access Key ID
        # 6. Secret Access Key
        # 7. Sender Email Address
        # 8. Recipient Email Address
        # 9. SMTP Host
        # 10. SMTP Username
        # 11. SMTP Password

        mock_prompt.side_effect = [
            "https://example.com", # 1
            "downloads", # 2
            "http://s3.com", # 3
            "bucket", # 4
            "key", # 5
            "secret", # 6
            "sender@example.com", # 7
            "recipient@example.com", # 8
            "smtp.com", # 9
            "user", # 10
            "pass", # 11
        ]
        mock_int.return_value = 587

        with patch("configure.console"):
            configure.main()

        mock_save_yaml.assert_called()
        mock_save_env.assert_called()

    @patch("configure.Confirm.ask")
    def test_save_config_yaml(self, mock_confirm):
        """Test saving YAML config."""
        config_data = {"key": "value"}
        # Assume overwrite is OK
        mock_confirm.return_value = True

        with patch("builtins.open", mock_open()) as mock_file:
            with patch("configure.yaml.dump") as mock_dump:
                configure.save_config_yaml(config_data)
                mock_dump.assert_called()

    @patch("configure.Confirm.ask")
    def test_save_env_file(self, mock_confirm):
        """Test saving .env file."""
        # Assume overwrite is OK
        mock_confirm.return_value = True

        with patch("builtins.open", mock_open()) as mock_file:
            configure.save_env_file("key", "enc_secret", "enc_pass", "salt")
            # Verify content write - check that it contains expected lines
            handle = mock_file()
            # Get the argument passed to write
            args, _ = handle.write.call_args
            written_content = args[0]
            self.assertIn('STORAGE_ACCESS_KEY_ID="key"', written_content)
            self.assertIn('SECRETS_ENC_SALT="salt"', written_content)

if __name__ == "__main__":
    unittest.main()
