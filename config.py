#!/usr/bin/env python3
"""
Centralized configuration module for the newspaper emailer system.
Handles loading configuration from environment variables and YAML files,
validates critical parameters, and provides a unified interface for
accessing configuration values, logging a summary on startup.
"""
import os
import yaml
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path # Keep Path for potential future use, though not used in current logic
try:
    from dotenv import load_dotenv  # Optional dependency
except Exception:  # ImportError or others
    def load_dotenv(*args, **kwargs):  # type: ignore
        return False
import sys

logger = logging.getLogger(__name__)

def setup_logging(log_level=logging.INFO, log_file="app.log", log_dir="logs"):
    """
    Configures logging for the application.
    Sets up console and rotating file handlers with a standard format.
    Safe to call multiple times; replaces existing root handlers.
    """
    log_directory = Path(log_dir)
    log_directory.mkdir(parents=True, exist_ok=True)
    log_filepath = log_directory / log_file

    # Define the log format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Prepare handlers
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(log_filepath, when="midnight", interval=1, backupCount=7)
    file_handler.setFormatter(formatter)

    # Configure root logger idempotently
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to prevent duplication on reconfiguration
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
        try:
            h.close()
        except Exception as e:
            print(f"Warning: Failed to close log handler {h}: {e}", file=sys.stderr)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logger.info("Logging configured to level '%s', writing to '%s'.", logging.getLevelName(log_level), log_filepath)

# Define critical configuration keys and their expected types/validation rules
# Format: (("tuple", "of", "keys"), 'validation_rule')
# Validation rules: 'str' (non-empty string), 'int', 'bool', 'url' (basic http/https check), 'email_list'
CRITICAL_CONFIG_KEYS = [
    (("newspaper", "url"), 'url'),
    (("email", "recipients"), 'email_list'),
    (("email", "sender"), 'str'),      # Could be enhanced for actual email format
    (("email", "smtp_host"), 'str'),
    (("email", "smtp_port"), 'int'),
    (("email", "smtp_user"), 'str'),
    (("email", "smtp_pass"), 'str'), # Presence checked, value redacted
    (("storage", "endpoint_url"), 'url'),
    (("storage", "access_key_id"), 'str'),
    (("storage", "secret_access_key"), 'str'),
    (("storage", "bucket"), 'str'),
    (("paths", "download_dir"), 'str'), # Default is 'downloads' in other modules
]

# Substrings to identify keys that should have their values redacted in logs
SECRET_KEY_SUBSTRINGS = [
    "password", "token", "secret", "passwd", 
    "smtp_user", "smtp_pass", "api_key", "access_key", "secret_key" # Added common terms
]

class Config:
    """Singleton configuration manager.

    Attributes:
        _config (dict): The loaded YAML configuration.
        _loaded (bool): Whether YAML configuration has been loaded.
        _env_file_loaded (bool): Whether a .env file was successfully loaded.
        CRITICAL_CONFIG_MAP (dict): Map of config keys to validation rules.
    """
    def __init__(self):
        """Initializes the Config object."""
        self._config = {}  # Loaded from YAML
        self._loaded = False
        self._env_file_loaded = False # Tracks if a .env file was processed
        self.CRITICAL_CONFIG_MAP = {key_path: rule for key_path, rule in CRITICAL_CONFIG_KEYS}

    def _is_secret(self, key_name_parts):
        """Checks if any part of a multi-level key name suggests a secret value.

        Args:
            key_name_parts (list or tuple): The path of the configuration key.

        Returns:
            bool: True if the key contains a secret keyword, False otherwise.
        """
        if not isinstance(key_name_parts, (list, tuple)):
            key_name_parts = [str(key_name_parts)] # Ensure it's iterable

        for part in key_name_parts:
            part_lower = str(part).lower()
            if any(s in part_lower for s in SECRET_KEY_SUBSTRINGS):
                return True
        return False

    def validate_critical_config(self):
        """Validates the presence and basic type of critical configuration keys.

        Returns:
            bool: True if all critical configurations are valid, False otherwise.
        """
        is_valid = True
        logger.debug("Validating critical configuration parameters...")
        for key_path, validation_rule in CRITICAL_CONFIG_KEYS:
            value = self.get(key_path)  # Uses combined YAML/env/default logic
            key_str = '.'.join(key_path) # For logging

            if value is None:
                # For paths.download_dir, a default is often acceptable, so treat as warning
                if key_path == ('paths', 'download_dir'):
                     logger.warning("Potentially missing configuration: '%s'. Application will use default or behavior might be unexpected. Define in config.yaml or as env var (%s).", 
                                   key_str, '_'.join(k.upper() for k in key_path))
                else:
                    logger.critical("MISSING critical configuration: '%s'. Please define it in config.yaml or as an environment variable (%s).", 
                                   key_str, '_'.join(k.upper() for k in key_path))
                    is_valid = False
                continue

            if validation_rule == 'str':
                if not isinstance(value, str) or not value.strip():
                    logger.critical("INVALID configuration: '%s' must be a non-empty string. Found: '%s' (type: %s)", 
                                    key_str, "********" if self._is_secret(key_path) else value, type(value).__name__)
                    is_valid = False
            elif validation_rule == 'int':
                if not isinstance(value, int):
                    try:
                        int(value) # Check if it can be cast
                    except (ValueError, TypeError):
                        logger.critical("INVALID configuration: '%s' must be an integer. Found: '%s' (type: %s)", 
                                        key_str, "********" if self._is_secret(key_path) else value, type(value).__name__)
                        is_valid = False
            elif validation_rule == 'url':
                if not isinstance(value, str) or not (value.startswith('http://') or value.startswith('https://')):
                    logger.critical("INVALID configuration: '%s' must be a valid URL (starting with http:// or https://). Found: '%s'", 
                                    key_str, "********" if self._is_secret(key_path) else value)
                    is_valid = False
            elif validation_rule == 'email_list':
                # Accept list of strings; also accept a single comma-separated string for convenience
                if isinstance(value, list):
                    if not value or not all(isinstance(v, str) and v.strip() for v in value):
                        logger.critical("INVALID configuration: '%s' must be a non-empty list of email strings.", key_str)
                        is_valid = False
                elif isinstance(value, str):
                    parsed = [v.strip() for v in value.split(',') if v.strip()]
                    if not parsed:
                        logger.critical("INVALID configuration: '%s' must be a non-empty list of email strings.", key_str)
                        is_valid = False
                    else:
                        # Normalize into list for downstream consumers
                        self._set(key_path, parsed)
                else:
                    logger.critical("INVALID configuration: '%s' must be a list of emails or comma-separated string. Found type: %s", key_str, type(value).__name__)
                    is_valid = False
            # Add more rules like 'bool' as needed in the future
        
        if is_valid:
            logger.info("Critical configuration validation successful.")
        else:
            # Specific errors already logged with CRITICAL level
            logger.error("Critical configuration validation FAILED. Some parameters are missing or invalid.")
        return is_valid

    def log_config_summary(self, log_level=logging.INFO):
        """Logs a summary of the loaded configuration, redacting secrets.

        Args:
            log_level: The logging level to use for the summary.
        """
        if not self._loaded and not self._env_file_loaded: # Check if any loading attempt was made
            logger.info("No configuration loaded (YAML not found/empty and .env not processed). Summary not available.")
            return

        logger.log(log_level, "--- Configuration Summary ---")
        
        # Indicate .env loading status
        env_path_used = os.environ.get('NEWSPAPER_ENV', '.env')
        if self._env_file_loaded:
            logger.log(log_level, f"Source: .env file loaded from '{env_path_used}'.")
        else:
            logger.log(log_level, f"Source: .env file not found or not loaded from '{env_path_used}'.")

        # Indicate YAML loading status
        yaml_config_path_used = os.environ.get('NEWSPAPER_CONFIG', 'config.yaml')
        if self._loaded and self._config: # _config has content from YAML
            logger.log(log_level, f"Source: YAML file loaded from '{yaml_config_path_used}'.")
        elif self._loaded and not self._config: # YAML file was found but empty or parsed to None
             logger.log(log_level, f"Source: YAML file at '{yaml_config_path_used}' was empty or contained no data.")
        else: # YAML file not found (and it was the default path)
             logger.log(log_level, f"Source: YAML file not found at '{yaml_config_path_used}'.")
        
        logger.log(log_level, "Effective critical settings (priority: YAML > Environment > Default):")
        for key_path, validation_rule in CRITICAL_CONFIG_KEYS:
            key_str = '.'.join(key_path)
            value = self.get(key_path) # This gets the effective value based on priority
            
            is_secret_key = self._is_secret(key_path) 
            
            if value is not None:
                display_value = "********" if is_secret_key else value
                # For integers, ensure they are displayed as such
                if validation_rule == 'int' and not is_secret_key and isinstance(value, int):
                     display_value = str(value)
                elif isinstance(value, bool) and not is_secret_key: # Handle booleans if added later
                     display_value = str(value)

                logger.log(log_level, f"  {key_str}: {display_value}")
            else:
                logger.log(log_level, f"  {key_str}: Not set (and no default defined in get())")
                        
        logger.log(log_level, "-----------------------------")

    def load(self):
        """Loads configuration from .env and YAML file (e.g., config.yaml).

        Validates critical parameters and logs a summary.

        Returns:
            bool: True if successful and critical configs are valid, False otherwise.
        """
        # Determine paths for .env and config.yaml
        config_path_env = os.environ.get('NEWSPAPER_CONFIG')
        config_path_default = 'config.yaml'
        config_path = config_path_env or config_path_default
        
        env_path_env = os.environ.get('NEWSPAPER_ENV')
        env_path_default = '.env'
        env_path = env_path_env or env_path_default

        # Load .env file first. It sets environment variables.
        if os.path.exists(env_path):
            self._env_file_processed = True  # Tracks whether the .env file was found and processed successfully.
            self._env_file_loaded = load_dotenv(env_path, verbose=True, override=True) # override=True ensures .env can set vars even if they exist
            if self._env_file_loaded:
                 logger.info("Loaded environment variables from '%s'. These may be overridden by environment-set variables.", env_path)
            else: # load_dotenv returns False if file is empty or only comments
                 logger.info(".env file at '%s' was processed but set no new environment variables (they may already exist or file is empty/comments-only).", env_path)
        else:
            logger.info(".env file not found at '%s'. Skipping .env load.", env_path)
            self._env_file_processed = False
            self._env_file_loaded = False

        # Load YAML config
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {} # Ensure _config is a dict
                self._loaded = True # Indicates YAML file was processed
                logger.info("Loaded YAML configuration from '%s'.", config_path)
            except Exception as e:
                logger.critical("Failed to load YAML configuration from '%s': %s", config_path, e)
                self._loaded = False # Explicitly mark YAML as not successfully loaded
                # If a specific config file was requested and failed to load, this is critical.
                if config_path_env: return False 
                # If default config.yaml failed, we might proceed if env vars cover criticals.
        else:
            # If default config.yaml is not found, it's not critical if all settings are from env vars.
            if config_path == config_path_default:
                 logger.info("Default configuration file '%s' not found. Relying on environment variables and .env.", config_path)
                 self._config = {} 
                 self._loaded = True # Considered "processed" for logic flow, even if no file loaded
            else: # If a custom config path was specified but not found
                 logger.critical("Specified configuration file '%s' not found. This is critical.", config_path)
                 return False
        
        # Validate critical configuration (checks effective values from YAML/Env)
        if not self.validate_critical_config():
            # Validation errors already logged with CRITICAL level
            return False 
            
        # Log summary of loaded configuration (if any part was loaded/processed)
        self.log_config_summary()
        return True

    def get(self, key_tuple, default=None):
        """Retrieves a value from the config.

        Priority: 1. YAML config, 2. Environment Variables, 3. Default value.

        Args:
            key_tuple (tuple): The key path in the config dictionary (e.g. ('email', 'smtp_host')).
            default: The default value to return if the key is not found.

        Returns:
            The configuration value, or the default.
        """
        # Try YAML first
        d = self._config
        try:
            for k in key_tuple:
                d = d[k]
            # If value is found in YAML, check its type for common cases (e.g. bool, int)
            # YAML automatically parses basic types like int, bool, float, strings.
            # So, direct return is usually fine.
            return d
        except (KeyError, TypeError):
            # Fallback to environment variable
            env_key = '_'.join(str(k).upper() for k in key_tuple)
            env_value = os.environ.get(env_key)
            
            if env_value is not None:
                # Attempt to cast common types from environment variables
                # This is a simple heuristic; more complex type casting might be needed
                # if specific validation rules were 'int' or 'bool' for CRITICAL_CONFIG_KEYS
                # Use precomputed dictionary for faster lookups
                expected_type = self.CRITICAL_CONFIG_MAP.get(key_tuple)
                
                if expected_type == 'int':
                    try:
                        return int(env_value)
                    except ValueError:
                        logger.warning("Env var '%s' with value '%s' could not be cast to int, returning as string. Validation will occur in validate_critical_config.", env_key, env_value)
                        return env_value # Return string, validation is centralized
                elif expected_type == 'bool':
                    if env_value.lower() in ['true', '1', 'yes', 'y']:
                        return True
                    elif env_value.lower() in ['false', '0', 'no', 'n']:
                        return False
                    else:
                        logger.warning("Env var '%s' with value '%s' could not be cast to bool, returning as string. Validation will assess if this is acceptable.", env_key, env_value)
                        return env_value # Return string, validation is centralized
                elif expected_type == 'email_list':
                    # Allow comma-separated env var
                    parsed = [v.strip() for v in env_value.split(',') if v.strip()]
                    return parsed if parsed else None
                return env_value # Return as string if no specific type cast or if cast failed warningly
            
            # If not in YAML and not in env, return default
            return default

    def _set(self, key_tuple, value):
        """Sets a value deep in the YAML config structure to normalize types.

        Args:
            key_tuple (tuple): The path of keys.
            value: The value to set.
        """
        d = self._config
        for k in key_tuple[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[key_tuple[-1]] = value

# Singleton config instance
config = Config()

# Set up logging immediately when config module is imported
setup_logging()