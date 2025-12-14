import os
import unittest
from unittest.mock import patch
import base64
import sys

# Import the Config class
# Assuming the file is named config.py and in the same or parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import Config  # noqa: E402

# Conditional import for cryptography
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


@unittest.skipUnless(CRYPTO_AVAILABLE, "Cryptography library not installed")
class TestConfigDecryption(unittest.TestCase):

    def setUp(self):
        if not CRYPTO_AVAILABLE:
            self.skipTest("Cryptography library not installed")

        self.passphrase = "mysecretpassphrase"
        self.salt = os.urandom(16)

        # Manually derive key to generate valid encrypted values
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=390000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.passphrase.encode()))
        self.fernet = Fernet(key)

        self.plaintext_secret = "super_secret_api_key"
        self.encrypted_secret = self.fernet.encrypt(
            self.plaintext_secret.encode()
        ).decode()
        self.salt_b64 = base64.urlsafe_b64encode(self.salt).decode()

    def test_decryption_success(self):
        """Test that get() decrypts value when _ENC var and credentials are present."""
        env_vars = {
            "TEST_SECRET_ENC": self.encrypted_secret,
            "SECRETS_PASSPHRASE": self.passphrase,
            "SECRETS_ENC_SALT": self.salt_b64,
        }

        with patch.dict(os.environ, env_vars):
            config = Config()
            # We mock the internal _config to be empty so it falls back to env vars
            val = config.get(("test", "secret"))
            self.assertEqual(val, self.plaintext_secret)

    def test_plaintext_priority(self):
        """Test that plaintext env var takes precedence over encrypted one."""
        env_vars = {
            "TEST_SECRET": "plaintext_override",
            "TEST_SECRET_ENC": self.encrypted_secret,
            "SECRETS_PASSPHRASE": self.passphrase,
            "SECRETS_ENC_SALT": self.salt_b64,
        }

        with patch.dict(os.environ, env_vars):
            config = Config()
            val = config.get(("test", "secret"))
            self.assertEqual(val, "plaintext_override")

    def test_missing_credentials(self):
        """Test that missing passphrase results in None (or failure to decrypt)."""
        env_vars = {
            "TEST_SECRET_ENC": self.encrypted_secret,
            # Missing PASSPHRASE
            "SECRETS_ENC_SALT": self.salt_b64,
        }

        with patch.dict(os.environ, env_vars):
            config = Config()
            # Should log error and return None
            val = config.get(("test", "secret"))
            self.assertIsNone(val)

    def test_wrong_passphrase(self):
        """Test that wrong passphrase fails to decrypt."""
        env_vars = {
            "TEST_SECRET_ENC": self.encrypted_secret,
            "SECRETS_PASSPHRASE": "wrong_passphrase",
            "SECRETS_ENC_SALT": self.salt_b64,
        }

        with patch.dict(os.environ, env_vars):
            config = Config()
            val = config.get(("test", "secret"))
            self.assertIsNone(val)


if __name__ == "__main__":
    unittest.main()
