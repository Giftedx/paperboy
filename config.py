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
from pathlib import Path # Keep Path for potential future use, though not used in current logic
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Define critical configuration keys and their expected types/validation rules.
# Format: (('tuple', 'of', 'keys'), 'validation_rule')
# Validation rules: 'str' (non-empty string), 'int', 'bool', 'url' (basic http/https check).
# The 'validation_rule' string is also used by the `get()` method to attempt type-casting
# for values retrieved from environment variables.
CRITICAL_CONFIG_KEYS = [
    (('newspaper', 'url'), 'url'),
    (('newspaper', 'username'), 'str'),
    (('newspaper', 'password'), 'str'),  # Presence checked, value redacted
    (('email', 'recipient'), 'str'),    # Could be enhanced for actual email format
    (('email', 'sender'), 'str'),      # Could be enhanced for actual email format
    (('email', 'smtp_server'), 'str'),
    (('email', 'smtp_port'), 'int'),
    (('email', 'smtp_username'), 'str'),
    (('email', 'smtp_password'), 'str'), # Presence checked, value redacted
    (('paths', 'download_dir'), 'str'), # Default is 'downloads' in other modules
]

# Substrings to identify keys that should have their values redacted in logs
SECRET_KEY_SUBSTRINGS = [
    "password", "token", "secret", "passwd", 
    "smtp_user", "smtp_pass", "api_key" # Added common term
]

class Config:
    def __init__(self):
        self._config = {}  # Stores configuration loaded from the YAML file.
        self._yaml_loaded_successfully = False # True if YAML file was found and successfully parsed.
        self._yaml_attempted_load = False # True if an attempt was made to load a YAML file.
        self._env_file_processed = False # True if a .env file was found and processed by load_dotenv.
        # self._env_file_loaded is True if load_dotenv successfully loaded variables from the .env file.
        # load_dotenv can return False if the .env file exists but is empty or only contains comments.
        self._env_file_loaded = False
        self.CRITICAL_CONFIG_MAP = {key_path: rule for key_path, rule in CRITICAL_CONFIG_KEYS}

    def _is_secret(self, key_name_parts):
        """
        Checks if any part of a multi-level key name suggests a secret value.
        Example: key_name_parts = ('email', 'smtp_password')
        """
        if not isinstance(key_name_parts, (list, tuple)):
            key_name_parts = [str(key_name_parts)] # Ensure it's iterable

        for part in key_name_parts:
            part_lower = str(part).lower()
            if any(s in part_lower for s in SECRET_KEY_SUBSTRINGS):
                return True
        return False

    def validate_critical_config(self):
        """Validates the presence and basic type of critical configuration keys."""
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
            # Add more rules like 'bool' as needed in the future
        
        if is_valid:
            logger.info("Critical configuration validation successful.")
        else:
            # Specific errors already logged with CRITICAL level
            logger.error("Critical configuration validation FAILED. Some parameters are missing or invalid.")
        return is_valid

    def log_config_summary(self, log_level=logging.INFO):
        """Logs a summary of the loaded configuration, redacting secrets."""
        # Check if any configuration loading (YAML or .env) was attempted or successful.
        if not self._yaml_attempted_load and not self._env_file_processed:
            logger.info("No configuration loading attempted (YAML or .env). Summary not available.")
            return

        logger.log(log_level, "--- Configuration Summary ---")
        
        # Determine the .env path that was used or would have been used.
        env_path_env = os.environ.get('NEWSPAPER_ENV')
        env_path_default = '.env'
        env_path_used = env_path_env or env_path_default

        if self._env_file_processed:
            if self._env_file_loaded:
                logger.log(log_level, f"Source: .env file loaded from '{env_path_used}'.")
            else:
                logger.log(log_level, f"Source: .env file at '{env_path_used}' was processed but set no new environment variables (e.g., file empty, vars already set).")
        else:
            logger.log(log_level, f"Source: .env file not found or not loaded from '{env_path_used}'.")

        # Determine the YAML path that was used or would have been used.
        yaml_config_path_env = os.environ.get('NEWSPAPER_CONFIG')
        yaml_config_path_default = 'config.yaml'
        yaml_config_path_used = yaml_config_path_env or yaml_config_path_default

        if self._yaml_attempted_load:
            if self._yaml_loaded_successfully and self._config: # _config has content from YAML
                logger.log(log_level, f"Source: YAML file loaded from '{yaml_config_path_used}'.")
            elif self._yaml_loaded_successfully and not self._config: # YAML file was found but empty
                 logger.log(log_level, f"Source: YAML file at '{yaml_config_path_used}' was empty or contained no data.")
            elif not self._yaml_loaded_successfully and yaml_config_path_env: # Specified YAML failed to load
                 logger.log(log_level, f"Source: Specified YAML file '{yaml_config_path_used}' failed to load or was not found.")
            else: # Default YAML not found or other non-critical load issue
                 logger.log(log_level, f"Source: Default YAML file not found or not loaded from '{yaml_config_path_used}'.")
        else:
            # This case should ideally not be reached if load() was called, as it always attempts YAML load.
            logger.log(log_level, "Source: YAML file loading was not attempted.")
        
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

    def _load_env_file(self, env_path_default: str, env_path_env: str | None) -> bool:
        """
        Loads environment variables from a .env file.
        Sets internal flags `_env_file_processed` and `_env_file_loaded`.
        Returns True, as .env loading itself is not usually a critical failure.
        """
        # Determine the .env file path. Priority: NEWSPAPER_ENV > default.
        actual_env_path = env_path_env or env_path_default
        self._env_file_processed = False
        self._env_file_loaded = False

        if os.path.exists(actual_env_path):
            self._env_file_processed = True # Mark that we found and attempted to process the .env file.
            # load_dotenv loads variables into the environment.
            # It returns True if the file was found and variables were loaded.
            # It returns False if the file was found but was empty or only contained comments,
            # or if the file was not found (though os.path.exists should prevent this last case).
            # `override=True` ensures .env variables can overwrite existing environment variables.
            self._env_file_loaded = load_dotenv(actual_env_path, verbose=True, override=True)
            if self._env_file_loaded:
                 logger.info("Loaded environment variables from '%s'. These may be overridden by system-set environment variables.", actual_env_path)
            else:
                 logger.info(".env file at '%s' was processed but set no new environment variables (e.g., file empty, vars already set, or only comments).", actual_env_path)
        else:
            logger.info(".env file not found at '%s'. Skipping .env load.", actual_env_path)
        return True # Loading .env itself is not critical; validation will catch missing criticals.

    def _load_yaml_file(self, config_path_default: str, config_path_env: str | None) -> bool:
        """
        Loads configuration from a YAML file.
        Sets `self._config`, `self._yaml_loaded_successfully`, and `self._yaml_attempted_load`.
        Returns True if YAML loading allows proceeding, False for critical YAML errors.
        """
        # Determine the YAML file path. Priority: NEWSPAPER_CONFIG > default.
        actual_config_path = config_path_env or config_path_default
        self._yaml_attempted_load = True
        self._yaml_loaded_successfully = False

        if os.path.exists(actual_config_path):
            try:
                with open(actual_config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {} # Ensure _config is a dict, even if file is empty.
                self._yaml_loaded_successfully = True # YAML file was found and parsed (even if empty).
                logger.info("Loaded YAML configuration from '%s'.", actual_config_path)
            except Exception as e: # Includes YAMLError, File Not Found (though caught by os.path.exists), etc.
                logger.critical("Failed to load or parse YAML configuration from '%s': %s", actual_config_path, e)
                # If a specific config file was requested via env var and it failed to load/parse,
                # this is a critical failure.
                if config_path_env:
                    return False
                # If the default config.yaml failed to load/parse, it's not immediately critical,
                # as environment variables might cover all necessary configurations.
                # We'll proceed, and validate_critical_config will determine if we can run.
        else:
            # If a specific config file path was provided via NEWSPAPER_CONFIG but not found, it's critical.
            if config_path_env:
                 logger.critical("Specified configuration file '%s' not found. This is critical.", actual_config_path)
                 return False
            else:
                 # If the default config.yaml is not found, it's not critical.
                 # The application might rely entirely on environment variables or a .env file.
                 logger.info("Default configuration file '%s' not found. Relying on environment variables and/or .env if present.", actual_config_path)
                 self._config = {}
                 # Considered "successfully processed" in the sense that its absence is handled gracefully.
                 # `_yaml_loaded_successfully` remains False if file not found, but we can proceed.
                 # Or, set self._yaml_loaded_successfully = True to indicate we've handled it?
                 # For clarity, let's keep it False if no YAML data was actually loaded.
                 # The key is that we return True to allow the load process to continue.
        return True # Return True to indicate non-critical YAML issues or successful load.

    def load(self):
        """
        Load configuration from .env and YAML file (e.g., config.yaml).
        Orchestrates loading, validates critical parameters, and logs a summary.
        Returns True if configuration is successfully loaded and validated, False otherwise.
        """
        # Determine paths from environment variables or use defaults.
        config_path_env = os.environ.get('NEWSPAPER_CONFIG')
        config_path_default = 'config.yaml'
        
        env_path_env = os.environ.get('NEWSPAPER_ENV')
        env_path_default = '.env'

        # Load .env file first. It sets environment variables that YAML might depend on,
        # or that might be overridden by YAML (though current get() prioritizes YAML).
        # load_dotenv itself doesn't return critical status.
        self._load_env_file(env_path_default, env_path_env)

        # Load YAML config. This can fail critically if a specified file is missing/unparseable.
        if not self._load_yaml_file(config_path_default, config_path_env):
            return False # Critical YAML loading error occurred.
        
        # After attempting to load all sources, validate critical configuration.
        if not self.validate_critical_config():
            # Validation errors already logged with CRITICAL level
            return False 
            
        # Log summary of loaded configuration (if any part was loaded/processed)
        self.log_config_summary()
        return True

    def get(self, key_tuple, default=None):
        """
        Retrieve a configuration value.
        Resolution order:
        1. YAML configuration (`self._config`).
        2. Environment variables (converted to appropriate types if specified in CRITICAL_CONFIG_MAP).
        3. Provided default value.
        """
        # 1. Try to retrieve the value from YAML configuration.
        # YAML parsing typically handles basic types like int, bool, float, and strings automatically.
        current_level = self._config
        try:
            for key_part in key_tuple:
                current_level = current_level[key_part]
            return current_level # Value found in YAML.
        except (KeyError, TypeError):
            # Value not found in YAML or self._config is not a subscriptable structure (e.g., None or empty).
            # 2. Fallback to environment variables.
            env_key_name = '_'.join(str(k).upper() for k in key_tuple)
            env_value_str = os.environ.get(env_key_name)
            
            if env_value_str is not None:
                # If the key is found in environment variables, attempt type casting
                # based on the validation rule defined in CRITICAL_CONFIG_MAP.
                # This helps ensure that environment variables are treated with the same type expectations
                # as their YAML counterparts where possible.
                expected_type_rule = self.CRITICAL_CONFIG_MAP.get(key_tuple)
                
                if expected_type_rule == 'int':
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
                return env_value # Return as string if no specific type cast or if cast failed warningly
            
            # If not in YAML and not in env, return default
            return default

# Singleton config instance
config = Config()

# Example of how to load config at application startup (e.g., in main.py)
# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     if config.load():
#         logger.info("Configuration loaded and validated successfully.")
#         # Example usage:
#         # SENDER_EMAIL = config.get(('email', 'sender'), 'default_sender@example.com')
#         # logger.info("Sender email: %s", SENDER_EMAIL)
#         # API_KEY = config.get(('some_service', 'api_key')) # Will be redacted in summary
#         # if API_KEY:
#         #    logger.info("Some service API key is set.")
#     else:
#         logger.error("Failed to load or validate configuration. Application might not run correctly.")
