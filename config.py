#!/usr/bin/env python3
"""
Centralized configuration module for the newspaper emailer system.
Handles loading configuration from environment variables and YAML files,
and provides a unified interface for accessing configuration values.
"""

import os
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        self._config = {}
        self._loaded = False

    def load(self):
        """
        Load configuration from config.yaml and .env (if present).
        Returns True if successful, False otherwise.
        """
        config_path = os.environ.get('NEWSPAPER_CONFIG', 'config.yaml')
        env_path = os.environ.get('NEWSPAPER_ENV', '.env')
        # Load .env first for environment variable overrides
        if os.path.exists(env_path):
            load_dotenv(env_path)
            logger.info("Loaded environment variables from %s", env_path)
        # Load YAML config
        if not os.path.exists(config_path):
            logger.critical("Configuration file %s not found.", config_path)
            return False
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
            self._loaded = True
            logger.info("Loaded configuration from %s", config_path)
            return True
        except Exception as e:
            logger.critical("Failed to load configuration: %s", e)
            return False

    def get(self, key_tuple, default=None):
        """
        Retrieve a value from the config using a tuple of keys, e.g. ('email', 'sender').
        Falls back to environment variable if not found in config.
        """
        d = self._config
        try:
            for k in key_tuple:
                d = d[k]
            return d
        except (KeyError, TypeError):
            # Fallback to environment variable (joined by _)
            env_key = '_'.join(str(k).upper() for k in key_tuple)
            return os.environ.get(env_key, default)

# Singleton config instance
config = Config()
