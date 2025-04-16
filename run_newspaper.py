#!/usr/bin/env python3
"""
Main execution script for the newspaper emailer.
Parses command-line arguments, sets up logging, loads configuration,
and orchestrates the download, storage, and email process.
"""

import argparse
import logging
import sys
from datetime import date
import config
import main
import os
import storage
import email_sender


def setup_logging(log_path='newspaper_emailer.log'):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def parse_args():
    parser = argparse.ArgumentParser(description='Run the newspaper emailer pipeline.')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD) for the newspaper. Defaults to today.')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the run without downloading, uploading, or emailing.')
    parser.add_argument('--force-download', action='store_true', help='Force re-download even if file exists.')
    parser.add_argument('--health', action='store_true', help='Run a health check for config, storage, and email.')
    parser.add_argument('--onboarding', action='store_true', help='Run interactive onboarding/setup wizard.')
    return parser.parse_args()


def print_colored(msg, color=None):
    # Simple color output for Windows/Unix
    colors = {'green': '\033[92m', 'red': '\033[91m', 'yellow': '\033[93m', 'blue': '\033[94m', 'end': '\033[0m'}
    if color and sys.stdout.isatty():
        print(f"{colors.get(color, '')}{msg}{colors['end']}")
    else:
        print(msg)


def health_check():
    print_colored("\n[Health Check] Newspaper Emailer System\n", 'blue')
    # Config check
    if not config.config.load():
        print_colored("Config: FAILED to load config.yaml", 'red')
        return False
    print_colored("Config: OK", 'green')
    # Storage check
    try:
        files = storage.list_storage_files()
        print_colored(f"Storage: OK ({len(files)} files found)", 'green')
    except Exception as e:
        print_colored(f"Storage: FAILED ({e})", 'red')
        return False
    # Email check
    try:
        result = email_sender.send_alert_email('Health Check', 'This is a test health check email.', dry_run=True)
        if result is not False:
            print_colored("Email: OK (dry-run)", 'green')
        else:
            print_colored("Email: FAILED (see logs)", 'red')
            return False
    except Exception as e:
        print_colored(f"Email: FAILED ({e})", 'red')
        return False
    print_colored("\nAll systems healthy!\n", 'green')
    return True


def onboarding():
    print_colored("\n[Onboarding] Welcome to Newspaper Emailer Setup!\n", 'blue')
    print("This wizard will help you configure your system.\n")
    # Step 1: Config file
    config_path = 'config.yaml'
    if not os.path.exists(config_path):
        print_colored("No config.yaml found. Creating a new one...", 'yellow')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write('# Fill in your configuration here. See README.md for details.\n')
    else:
        print_colored("config.yaml found.", 'green')
    # Step 2: .env file
    env_path = '.env'
    if not os.path.exists(env_path):
        print_colored("No .env file found. Creating a new one...", 'yellow')
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('# Add your secrets here. See README.md for details.\n')
    else:
        print_colored(".env file found.", 'green')
    print("\nPlease edit these files with your credentials and settings.\n")
    print("You can use the web UI config editor or any text editor.\n")
    print_colored("Onboarding complete! Run with --health to check your setup.\n", 'green')


def main_entry():
    args = parse_args()
    setup_logging()
    if args.health:
        health_check()
        return
    if args.onboarding:
        onboarding()
        return
    logging.info('Starting newspaper emailer run...')
    # Load config
    if not config.config.load():
        print_colored('Failed to load configuration. Exiting.', 'red')
        logging.critical('Failed to load configuration. Exiting.')
        sys.exit(1)
    # Determine date
    target_date_str = args.date if args.date else date.today().strftime('%Y-%m-%d')
    logging.info(f"Target date for newspaper: {target_date_str}")
    if args.dry_run:
        print_colored('[DRY RUN] No files will be downloaded, uploaded, or emailed.', 'yellow')
        logging.info('Dry run mode enabled. No files will be downloaded, uploaded, or emailed.')
    if args.force_download:
        print_colored('[FORCE DOWNLOAD] Existing files will be re-downloaded.', 'yellow')
        logging.info('Force download mode enabled. Existing files will be re-downloaded.')
    # Orchestration: Acquisition -> Distribution -> Archive Management
    logging.info('Step 1: Newspaper Acquisition')
    # (Acquisition is handled in main.main)
    logging.info('Step 2: Distribution Process')
    # (Distribution is handled in main.main)
    logging.info('Step 3: Archive Management')
    # (Archive management is handled in main.main)
    # Call main pipeline
    success = main.main(
        target_date_str=target_date_str,
        dry_run=args.dry_run,
        force_download=args.force_download
    )
    if not success:
        print_colored('Newspaper emailer run failed.', 'red')
        logging.error('Newspaper emailer run failed.')
        sys.exit(1)
    print_colored('Newspaper emailer run completed successfully.', 'green')
    logging.info('Newspaper emailer run completed successfully.')


if __name__ == '__main__':
    main_entry()