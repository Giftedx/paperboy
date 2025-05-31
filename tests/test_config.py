import unittest
from unittest.mock import patch, mock_open
import os
import yaml # PyYAML for creating dummy yaml content
import logging

# Assuming config.py is in the parent directory or PYTHONPATH is set
from config import Config, CRITICAL_CONFIG_KEYS, SECRET_KEY_SUBSTRINGS 

class TestConfig(unittest.TestCase):

    def setUp(self):
        """Setup method to run before each test."""
        # Store original environment and clear it for tests to avoid interference
        self.original_environ = dict(os.environ)
        os.environ.clear()
        
        # Reset the singleton by creating a new instance
        # This ensures each test starts with a fresh Config object
        self.config_instance = Config()
        
        # Suppress logging output during tests unless specifically testing logs
        # Or redirect it to a test-specific handler
        logging.disable(logging.CRITICAL) # Disable all logging less than CRITICAL for most tests

    def test_critical_config_map_initialization(self):
        """Test that CRITICAL_CONFIG_MAP is correctly initialized on Config instance."""
        self.assertTrue(hasattr(self.config_instance, 'CRITICAL_CONFIG_MAP'))
        self.assertIsInstance(self.config_instance.CRITICAL_CONFIG_MAP, dict)
        for key_path, rule in CRITICAL_CONFIG_KEYS:
            self.assertIn(key_path, self.config_instance.CRITICAL_CONFIG_MAP)
            self.assertEqual(self.config_instance.CRITICAL_CONFIG_MAP[key_path], rule)

    def tearDown(self):
        """Teardown method to run after each test."""
        os.environ.clear()
        os.environ.update(self.original_environ)
        logging.disable(logging.NOTSET) # Re-enable logging

    def test_load_empty_and_defaults(self):
        """Test loading with no files and relying on defaults from get()."""
        with patch('os.path.exists', return_value=False): # No .env, no config.yaml
            # Load should still "succeed" (return True) if critical validation passes due to env vars or defaults
            # However, our current critical keys don't have defaults in get(), so this will fail validation
            # if no env vars are set.
            # Let's test that get() returns default if nothing is set.
            self.assertIsNone(self.config_instance.get(('test', 'nonexistent')))
            self.assertEqual(self.config_instance.get(('test', 'nonexistent'), 'default_val'), 'default_val')

    @patch('config.load_dotenv') # Mock load_dotenv
    @patch('yaml.safe_load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_load_yaml_only_success(self, mock_exists, mock_file_open, mock_yaml_load, mock_load_dotenv):
        """Test loading only YAML configuration successfully with all critical keys."""
        mock_exists.side_effect = lambda path: path == 'config.yaml' # Only config.yaml exists
        
        # Sample critical keys that would be in YAML
        # For this test, we ensure all CRITICAL_CONFIG_KEYS are present and valid
        # to pass validate_critical_config.
        yaml_data = {
            'newspaper': {'url': 'https://example.com', 'username': 'user', 'password': 'pass'},
            'email': {'recipient': 'r@example.com', 'sender': 's@example.com', 
                      'smtp_server': 'smtp.example.com', 'smtp_port': 587, 
                      'smtp_username': 'smtp_user', 'smtp_password': 'smtp_pass'},
            'paths': {'download_dir': '/tmp/downloads'}
        }
        mock_yaml_load.return_value = yaml_data
        
        self.assertTrue(self.config_instance.load())
        self.assertEqual(self.config_instance.get(('newspaper', 'url')), 'https://example.com')
        self.assertEqual(self.config_instance.get(('email', 'smtp_port')), 587)
        mock_load_dotenv.assert_not_called() # .env should not have been loaded

    @patch('config.load_dotenv')
    @patch('yaml.safe_load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_load_env_file_only_success(self, mock_exists, mock_file_open, mock_yaml_load, mock_load_dotenv):
        """Test loading only .env file successfully with critical keys via environment."""
        mock_exists.side_effect = lambda path: path == '.env' # Only .env exists
        mock_yaml_load.return_value = {} # YAML load returns empty

        # Simulate that load_dotenv sets these environment variables
        os.environ['NEWSPAPER_URL'] = 'https://env.example.com'
        os.environ['NEWSPAPER_USERNAME'] = 'env_user'
        os.environ['NEWSPAPER_PASSWORD'] = 'env_pass'
        os.environ['EMAIL_RECIPIENT'] = 'r_env@example.com'
        os.environ['EMAIL_SENDER'] = 's_env@example.com'
        os.environ['EMAIL_SMTP_SERVER'] = 'smtp_env.example.com'
        os.environ['EMAIL_SMTP_PORT'] = "465" # Env vars are strings
        os.environ['EMAIL_SMTP_USERNAME'] = 'smtp_user_env'
        os.environ['EMAIL_SMTP_PASSWORD'] = 'smtp_pass_env'
        os.environ['PATHS_DOWNLOAD_DIR'] = '/tmp/env_downloads'
        
        mock_load_dotenv.return_value = True # Simulate .env was found and loaded

        self.assertTrue(self.config_instance.load())
        self.assertEqual(self.config_instance.get(('newspaper', 'url')), 'https://env.example.com')
        self.assertEqual(self.config_instance.get(('email', 'smtp_port')), 465) # Test type casting
        mock_load_dotenv.assert_called_once_with('.env', verbose=True, override=True)


    @patch('config.load_dotenv', return_value=True) # Assume .env is loaded
    @patch('yaml.safe_load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_yaml_overrides_env_values_via_get(self, mock_exists, mock_file_open, mock_yaml_load, mock_load_dotenv):
        """Test that YAML values take precedence in get() even if env var (from .env or actual env) exists."""
        mock_exists.return_value = True # Both .env and config.yaml exist

        # Simulate environment variable that might have been set by .env or shell
        os.environ['NEWSPAPER_URL'] = 'https://env.example.com' 
        os.environ['EMAIL_SMTP_PORT'] = '123' # Env var (string)
        # Critical keys not in YAML for this test, assume they are set in env for validation to pass
        os.environ['NEWSPAPER_USERNAME'] = 'env_user_val_pass'
        os.environ['NEWSPAPER_PASSWORD'] = 'env_pass_val_pass'
        os.environ['EMAIL_RECIPIENT'] = 'r_env_val_pass@example.com'
        os.environ['EMAIL_SENDER'] = 's_env_val_pass@example.com'
        os.environ['EMAIL_SMTP_SERVER'] = 'smtp_env_val_pass.example.com'
        os.environ['EMAIL_SMTP_USERNAME'] = 'smtp_user_env_val_pass'
        os.environ['EMAIL_SMTP_PASSWORD'] = 'smtp_pass_env_val_pass'
        os.environ['PATHS_DOWNLOAD_DIR'] = '/tmp/downloads_val_pass'


        yaml_data = {
            'newspaper': {'url': 'https://yaml.example.com'}, # Override URL
            'email': {'smtp_port': 587} # Override port (and type)
        }
        mock_yaml_load.return_value = yaml_data
        
        self.assertTrue(self.config_instance.load())
        # get() should prioritize YAML
        self.assertEqual(self.config_instance.get(('newspaper', 'url')), 'https://yaml.example.com')
        self.assertEqual(self.config_instance.get(('email', 'smtp_port')), 587) # YAML int should be preferred
        # Test that a value only in env (due to .env load) is still accessible if not in YAML
        self.assertEqual(self.config_instance.get(('paths', 'download_dir')), '/tmp/downloads_val_pass')


    @patch('logging.Logger.critical') # Patch the logger instance used in config.py
    @patch('config.load_dotenv', return_value=False)
    @patch('yaml.safe_load', return_value={}) # Empty YAML
    @patch('os.path.exists', return_value=True) # Assume files exist but are empty or don't set criticals
    def test_critical_config_validation_missing_key(self, mock_exists, mock_yaml_load, mock_load_dotenv, mock_log_critical):
        """Test load() fails if a critical key is missing entirely."""
        # No environment variables set for critical keys either
        self.assertFalse(self.config_instance.load())
        
        # Check if logging.critical was called for at least one of the missing keys.
        # Example: Check for newspaper.url missing message
        # The exact message might vary, so check for key parts.
        self.assertTrue(any("MISSING critical configuration: 'newspaper.url'" in call.args[0] for call in mock_log_critical.call_args_list))


    @patch('logging.Logger.critical')
    @patch('config.load_dotenv', return_value=False)
    @patch('os.path.exists', return_value=True)
    def test_critical_config_validation_invalid_type(self, mock_exists, mock_load_dotenv, mock_log_critical):
        """Test load() fails if a critical key has an invalid type (e.g., port not int)."""
        # Set critical keys mostly correctly, but make smtp_port a string that cannot be int
        # Simulate these values coming from environment after YAML was empty or didn't define them
        os.environ['NEWSPAPER_URL'] = 'https://example.com'
        os.environ['NEWSPAPER_USERNAME'] = 'user'
        os.environ['NEWSPAPER_PASSWORD'] = 'pass'
        os.environ['EMAIL_RECIPIENT'] = 'r@example.com'
        os.environ['EMAIL_SENDER'] = 's@example.com'
        os.environ['EMAIL_SMTP_SERVER'] = 'smtp.example.com'
        os.environ['EMAIL_SMTP_PORT'] = "not-an-int" # Invalid
        os.environ['EMAIL_SMTP_USERNAME'] = 'smtp_user'
        os.environ['EMAIL_SMTP_PASSWORD'] = 'smtp_pass'
        os.environ['PATHS_DOWNLOAD_DIR'] = '/tmp/downloads'

        with patch('yaml.safe_load', return_value={}): # Empty YAML
             self.assertFalse(self.config_instance.load())

        self.assertTrue(any("INVALID configuration: 'email.smtp_port' must be an integer" in call.args[0] for call in mock_log_critical.call_args_list))

    @patch('logging.Logger.critical')
    @patch('config.load_dotenv', return_value=False)
    @patch('os.path.exists', return_value=True)
    def test_critical_config_validation_invalid_url(self, mock_exists, mock_load_dotenv, mock_log_critical):
        """Test load() fails for invalid URL format."""
        os.environ['NEWSPAPER_URL'] = 'htp://invalid-url' # Invalid scheme
        # Set other criticals to satisfy validation for them
        os.environ['NEWSPAPER_USERNAME'] = 'user'
        os.environ['NEWSPAPER_PASSWORD'] = 'pass'
        # ... (set other critical keys as in previous test) ...
        os.environ['EMAIL_RECIPIENT'] = 'r@example.com'
        os.environ['EMAIL_SENDER'] = 's@example.com'
        os.environ['EMAIL_SMTP_SERVER'] = 'smtp.example.com'
        os.environ['EMAIL_SMTP_PORT'] = "587" 
        os.environ['EMAIL_SMTP_USERNAME'] = 'smtp_user'
        os.environ['EMAIL_SMTP_PASSWORD'] = 'smtp_pass'
        os.environ['PATHS_DOWNLOAD_DIR'] = '/tmp/downloads'

        with patch('yaml.safe_load', return_value={}):
            self.assertFalse(self.config_instance.load())
        self.assertTrue(any("INVALID configuration: 'newspaper.url' must be a valid URL" in call.args[0] for call in mock_log_critical.call_args_list))


    @patch('logging.Logger.log') # Patching the specific logger instance's method
    @patch('config.load_dotenv', return_value=False)
    @patch('yaml.safe_load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_log_config_summary_redaction(self, mock_exists, mock_file_open, mock_yaml_load, mock_log_method, mock_load_dotenv):
        """Test that secrets are redacted in the config summary log."""
        mock_exists.side_effect = lambda path: path == 'config.yaml'
        yaml_data = {
            'newspaper': {'url': 'https://example.com', 'username': 'user', 'password': 'SECRET_PASSWORD'},
            'email': {'smtp_port': 123, 'smtp_password': 'SMTP_SECRET'} # Add another secret
        }
        # Fill in other critical keys to pass validation
        yaml_data['email']['recipient'] = 'r@example.com'
        yaml_data['email']['sender'] = 's@example.com'
        yaml_data['email']['smtp_server'] = 'server'
        yaml_data['email']['smtp_username'] = 'user'
        yaml_data['paths'] = {'download_dir': '/tmp'}
        
        mock_yaml_load.return_value = yaml_data
        
        # Re-enable INFO logging for this specific test to capture summary
        logging.disable(logging.NOTSET) 
        # Create a new config instance that will use the patched logger
        test_config = Config()
        with patch.object(config.logger, 'log', mock_log_method): # Patch logger used by config instance
            self.assertTrue(test_config.load()) # Load should succeed
            test_config.log_config_summary(log_level=logging.INFO) # Explicitly call with INFO

        # Check the log calls for redaction
        found_password_redacted = False
        found_smtp_password_redacted = False
        found_url_clear = False
        
        for call_args in mock_log_method.call_args_list:
            args, _ = call_args
            log_message = args[1] # Actual message string is the second argument to logger.log(level, message, ...)
            if isinstance(log_message, str):
                if "newspaper.password: ********" in log_message:
                    found_password_redacted = True
                if "email.smtp_password: ********" in log_message:
                    found_smtp_password_redacted = True
                if "newspaper.url: https://example.com" in log_message:
                    found_url_clear = True
        
        self.assertTrue(found_password_redacted, "Newspaper password was not redacted in log summary.")
        self.assertTrue(found_smtp_password_redacted, "SMTP password was not redacted in log summary.")
        self.assertTrue(found_url_clear, "Newspaper URL was not clearly logged or was missing.")
        logging.disable(logging.CRITICAL) # Re-disable for other tests


    def test_get_env_var_type_casting(self):
        """Test type casting for environment variables via get()."""
        # For these tests, CRITICAL_CONFIG_KEYS needs to have type info for these keys
        # We assume they are defined like: (('test', 'port'), 'int'), (('test', 'enable_feature'), 'bool')
        
        # Preserve existing integer test
        os.environ['EMAIL_SMTP_PORT'] = "587" # String, but 'int' rule exists in CRITICAL_CONFIG_KEYS

        # Test for plain string (no rule)
        os.environ['GENERAL_TEXT'] = "some text"

        # Comprehensive Boolean Testing
        test_bool_key = ('feature', 'enabled_test_bool')
        # Temporarily add this key to the instance's CRITICAL_CONFIG_MAP for boolean testing
        # This is safe as self.config_instance is fresh for each test method due to setUp.
        self.config_instance.CRITICAL_CONFIG_MAP[test_bool_key] = 'bool'

        true_values = ["true", "1", "yes", "y", "TRUE"]
        for val_str in true_values:
            os.environ['FEATURE_ENABLED_TEST_BOOL'] = val_str
            with patch.object(self.config_instance, '_config', {}): # Ensure fallback to env
                self.assertTrue(self.config_instance.get(test_bool_key), f"Failed for true value: {val_str}")

        false_values = ["false", "0", "no", "n", "FALSE"]
        for val_str in false_values:
            os.environ['FEATURE_ENABLED_TEST_BOOL'] = val_str
            with patch.object(self.config_instance, '_config', {}):
                self.assertFalse(self.config_instance.get(test_bool_key), f"Failed for false value: {val_str}")

        invalid_bool_values = ["random", "maybe", ""]
        for val_str in invalid_bool_values:
            os.environ['FEATURE_ENABLED_TEST_BOOL'] = val_str
            with patch.object(self.config_instance, '_config', {}):
                # get() should return the string itself if casting to bool fails
                self.assertEqual(self.config_instance.get(test_bool_key), val_str, f"Failed for invalid bool value: {val_str}")

        # Clean up env var for boolean test
        del os.environ['FEATURE_ENABLED_TEST_BOOL']

        # Simulate that these keys are not in YAML, so get() falls back to env
        with patch.object(self.config_instance, '_config', {}):
            self.assertEqual(self.config_instance.get(('email', 'smtp_port')), 587) # Should be cast to int
            self.assertEqual(self.config_instance.get(('general', 'text')), "some text") # No rule, so string


    @patch('config.load_dotenv', return_value=True)
    @patch('os.path.exists')
    def test_load_yaml_not_found_but_env_provides_criticals(self, mock_exists, mock_load_dotenv):
        """Test successful load if default YAML is missing but env vars cover criticals."""
        mock_exists.side_effect = lambda path: path == '.env' # Only .env exists, config.yaml does not

        # Simulate environment variables providing all criticals
        os.environ['NEWSPAPER_URL'] = 'https://env.example.com'
        os.environ['NEWSPAPER_USERNAME'] = 'env_user'
        os.environ['NEWSPAPER_PASSWORD'] = 'env_pass'
        os.environ['EMAIL_RECIPIENT'] = 'r_env@example.com'
        os.environ['EMAIL_SENDER'] = 's_env@example.com'
        os.environ['EMAIL_SMTP_SERVER'] = 'smtp_env.example.com'
        os.environ['EMAIL_SMTP_PORT'] = "465" 
        os.environ['EMAIL_SMTP_USERNAME'] = 'smtp_user_env'
        os.environ['EMAIL_SMTP_PASSWORD'] = 'smtp_pass_env'
        os.environ['PATHS_DOWNLOAD_DIR'] = '/tmp/env_downloads'

        # Patch yaml.safe_load to ensure it's not called if file doesn't exist,
        # or to return empty if it were somehow called.
        with patch('yaml.safe_load', return_value={}):
            self.assertTrue(self.config_instance.load())
            self.assertEqual(self.config_instance.get(('newspaper', 'url')), 'https://env.example.com')


    @patch('config.load_dotenv', return_value=False) # .env not found or empty
    @patch('yaml.safe_load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_load_specified_yaml_not_found_critical_failure(self, mock_exists, mock_file_open, mock_yaml_load, mock_load_dotenv):
        """Test load fails if a NEWSPAPER_CONFIG specified YAML is not found."""
        os.environ['NEWSPAPER_CONFIG'] = 'non_default_config.yaml'
        mock_exists.side_effect = lambda path: path == '.env' # .env might exist, but specified YAML does not
        
        self.assertFalse(self.config_instance.load())


if __name__ == "__main__":
    unittest.main()
