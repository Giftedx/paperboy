#!/usr/bin/env python3
"""
Website interaction module for newspaper downloader
Handles login to newspaper website and downloading the daily newspaper.
"""

import os
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import config

# Playwright imports (optional dependency)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    class PlaywrightTimeoutError(Exception):
        pass
    class PlaywrightError(Exception):
        pass

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration from centralized config module ---
WEBSITE_URL = config.config.get(('newspaper', 'url'))
LOGIN_URL = config.config.get(('newspaper', 'login_url'), WEBSITE_URL) # Often the same as WEBSITE_URL
USERNAME = config.config.get(('newspaper', 'username'))
PASSWORD = config.config.get(('newspaper', 'password'))
DOWNLOAD_DIR = config.config.get(('paths', 'download_dir'), 'downloads') # Local directory to save files
USER_AGENT = config.config.get(('newspaper', 'user_agent'), 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

# --- Website Selectors (Configurable) ---
USERNAME_SELECTOR = config.config.get(('newspaper', 'selectors', 'username'), 'input[name="username"]')
PASSWORD_SELECTOR = config.config.get(('newspaper', 'selectors', 'password'), 'input[name="password"]')
SUBMIT_BUTTON_SELECTOR = config.config.get(('newspaper', 'selectors', 'submit'), 'button[type="submit"]')
LOGIN_SUCCESS_SELECTOR = config.config.get(('newspaper', 'selectors', 'login_success'), '#user-profile-link')
LOGIN_SUCCESS_URL_PATTERN = config.config.get(('newspaper', 'selectors', 'login_success_url'), '')

# --- Helper Functions ---
def _get_session_cookies(login_url, username, password):
    """Uses Playwright to log in and extract session cookies."""
    logger.info("Attempting to log in via Playwright to get session cookies.")
    cookies = None
    browser = None # Initialize browser variable
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # Run headless
            page = browser.new_page()
            logger.debug("Navigating to login page: %s", login_url)
            page.goto(login_url, wait_until='networkidle')

            # --- Configurable Login Logic ---
            # Uses environment variables or defaults for selectors
            logger.debug("Attempting to fill login form using selectors: [Username: %s, Password: %s, Submit: %s]", 
                         USERNAME_SELECTOR, PASSWORD_SELECTOR, SUBMIT_BUTTON_SELECTOR)
            
            # Check if selectors exist before attempting to interact with them
            if page.locator(USERNAME_SELECTOR).count() > 0:
                page.fill(USERNAME_SELECTOR, username)
            else:
                logger.error("Username field not found with selector: %s", USERNAME_SELECTOR)
                return None
                
            if page.locator(PASSWORD_SELECTOR).count() > 0:
                page.fill(PASSWORD_SELECTOR, password)
            else:
                logger.error("Password field not found with selector: %s", PASSWORD_SELECTOR)
                return None
                
            if page.locator(SUBMIT_BUTTON_SELECTOR).count() > 0:
                page.click(SUBMIT_BUTTON_SELECTOR)
            else:
                logger.error("Submit button not found with selector: %s", SUBMIT_BUTTON_SELECTOR)
                return None
            # --- End Configurable Login Logic ---

            # Wait for navigation/login confirmation using configurable methods
            login_success = False
            
            # Method 1: Check for success element if configured
            if LOGIN_SUCCESS_SELECTOR:
                try:
                    logger.debug("Waiting for login success element: %s", LOGIN_SUCCESS_SELECTOR)
                    page.wait_for_selector(LOGIN_SUCCESS_SELECTOR, timeout=30000)
                    login_success = True
                    logger.info("Login successful (based on element presence: %s).", LOGIN_SUCCESS_SELECTOR)
                except PlaywrightTimeoutError:
                    logger.warning("Login success element not found: %s", LOGIN_SUCCESS_SELECTOR)
            
            # Method 2: Check for URL pattern if configured
            if not login_success and LOGIN_SUCCESS_URL_PATTERN:
                try:
                    logger.debug("Waiting for login success URL pattern: %s", LOGIN_SUCCESS_URL_PATTERN)
                    page.wait_for_url(LOGIN_SUCCESS_URL_PATTERN, timeout=30000)
                    login_success = True
                    logger.info("Login successful (based on URL pattern: %s).", LOGIN_SUCCESS_URL_PATTERN)
                except PlaywrightTimeoutError:
                    logger.warning("Login success URL pattern not matched: %s", LOGIN_SUCCESS_URL_PATTERN)
                    
            # Method 3: Wait for network idle as last resort
            if not login_success:
                logger.debug("Using fallback method: waiting for network idle state")
                page.wait_for_load_state('networkidle')
                # Check for login failure indicators (like error messages)
                error_messages = page.locator('.login-error, .error-message, .alert-danger').count()
                if error_messages > 0:
                    error_text = page.locator('.login-error, .error-message, .alert-danger').text_content()
                    logger.error("Login error detected: %s", error_text)
                    return None
                login_success = True
                logger.info("Login appears successful (based on network idle state and no error messages).")
            
            if not login_success:
                logger.error("Login could not be confirmed through any verification method.")
                return None

            # Extract cookies
            cookies = page.context.cookies()
            logger.info("Successfully extracted %d cookies.", len(cookies))
            # browser.close() # Context manager handles closing
    except PlaywrightTimeoutError:
        logger.error("Playwright timed out during login process. Check selectors and network conditions.")
    except PlaywrightError as e:
        logger.error("A Playwright error occurred during login: %s", e)
    except Exception as e: # Catch unexpected errors
        # Using logger.exception to include traceback
        logger.exception("An unexpected error occurred during Playwright login: %s", e)
    # finally:
        # Ensure browser is closed even if errors occur before context manager exit
        # This finally block might be redundant due to the 'with' statement,
        # but kept for explicit safety, especially if errors happen during launch.
        # if browser and browser.is_connected():
        #     logger.debug("Ensuring browser is closed in finally block.")
        #     browser.close()
        # The 'with sync_playwright() as p:' handles browser cleanup.
        # The 'browser' variable might not be assigned if launch fails.
    return cookies

def _download_with_playwright(download_url, save_path, cookies, dry_run=False):
    """
    Fallback method to download using Playwright when the requests method fails.
    
    Args:
        download_url: URL to download the newspaper from
        save_path: Path where the downloaded file should be saved
        cookies: Session cookies for authentication
        dry_run: If True, simulate the operation without actually downloading
        
    Returns:
        tuple: (success_flag, file_format_or_error_message)
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not available for fallback download. Install with: pip install playwright")
        return False, "Playwright not available"
    
    if dry_run:
        logger.info("[Dry Run] Would attempt fallback download using Playwright from: %s", download_url)
        return True, "pdf"  # Assume PDF format in dry run
        
    logger.info("Attempting fallback download using Playwright from: %s", download_url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Set cookies if available
            if cookies:
                for cookie in cookies:
                    # Convert to Playwright format
                    playwright_cookie = {
                        'name': cookie['name'],
                        'value': cookie['value'],
                        'domain': cookie['domain'],
                        'path': cookie['path'],
                    }
                    # Add optional fields if present
                    for field in ['httpOnly', 'secure', 'expires']:
                        if field in cookie:
                            playwright_cookie[field] = cookie[field]
                            
                    context.add_cookies([playwright_cookie])
                    
            # Create a page and navigate to the URL
            page = context.new_page()
            
            # Setup download handling
            download_folder = os.path.dirname(save_path)
            os.makedirs(download_folder, exist_ok=True)
            page.context.set_default_timeout(60000)  # 60 seconds timeout
            
            # Enable file downloads
            download_promise = page.wait_for_download()
            
            # Navigate to the download URL
            logger.debug("Navigating to download URL: %s", download_url)
            response = page.goto(download_url, wait_until='networkidle')
            
            if not response:
                logger.error("Failed to navigate to download URL")
                return False, "Navigation failed"
                
            if response.status >= 400:
                logger.error("Received error status code: %d", response.status)
                return False, f"Error status: {response.status}"
                
            # Method 1: Try to find and click a download button if the URL didn't trigger download
            try:
                download = download_promise.wait_for(timeout=5000)
            except PlaywrightTimeoutError:
                # No automatic download, look for download buttons
                download_selectors = [
                    'a[download]', 
                    'button:has-text("Download")', 
                    'a:has-text("Download")', 
                    '.download-button', 
                    '#download-button'
                ]
                
                for selector in download_selectors:
                    if page.locator(selector).count() > 0:
                        logger.info("Found download element with selector: %s", selector)
                        with page.expect_download() as download_promise:
                            page.click(selector)
                        download = download_promise.value
                        break
                else:
                    # If we get here, we didn't find any download buttons
                    logger.warning("No download buttons found. Trying to save page content directly.")
                    # Method 2: Try to save the page content directly
                    content_type = response.headers.get('content-type', '')
                    if 'pdf' in content_type.lower():
                        # Rename inner variable to avoid redefining outer scope variable
                        inner_file_format = 'pdf'
                        save_path_with_ext = f"{save_path}.{inner_file_format}"
                        try:
                            # Using response.body() instead of page.content() for binary content
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.body())
                            logger.info("Saved page content as PDF: %s", save_path_with_ext)
                            return True, inner_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save PDF content: %s", e)
                            return False, f"Failed to save PDF: {str(e)}"
                    elif 'html' in content_type.lower():
                        # Rename inner variable
                        inner_file_format = 'html'
                        save_path_with_ext = f"{save_path}.{inner_file_format}"
                        try:
                            # For HTML, page.content() is appropriate
                            with open(save_path_with_ext, 'w', encoding='utf-8') as file:
                                file.write(page.content())
                            logger.info("Saved page content as HTML: %s", save_path_with_ext)
                            return True, inner_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save HTML content: %s", e)
                            return False, f"Failed to save HTML: {str(e)}"
                    else:
                        logger.error("Unknown content type: %s", content_type)
                        return False, "Unknown content type"
            
            # Handle the download if we got one
            if download:
                # Rename inner variable
                downloaded_file_format = download.suggested_filename.split('.')[-1].lower()
                if downloaded_file_format not in ['pdf', 'html']:
                    downloaded_file_format = 'pdf'  # Default to PDF
                
                save_path_with_ext = f"{save_path}.{downloaded_file_format}"
                download.save_as(save_path_with_ext)
                logger.info("Playwright successfully downloaded file to: %s", save_path_with_ext)
                return True, downloaded_file_format
                
            return False, "No download occurred"
            
    except PlaywrightTimeoutError as e:
        logger.error("Playwright timeout during download: %s", e)
        return False, f"Playwright timeout: {str(e)}"
    except PlaywrightError as e:
        logger.error("Playwright error during download: %s", e)
        return False, f"Playwright error: {str(e)}"
    except requests.exceptions.RequestException as e: # Catch specific requests errors
        logger.error("Request error during download attempt: %s", e)
        return False, f"Request error: {str(e)}" # Fail fast on request errors
    except OSError as e: # Catch specific OS errors
        logger.error("OS error during download attempt: %s", e)
        return False, f"OS error: {str(e)}" # Fail fast on OS errors
    except Exception as e: # General fallback
        # Using logger.exception to include traceback
        logger.exception("Unexpected error during Playwright download: %s", e)
        return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except requests.exceptions.RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        return None
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        return None

# --- Main Orchestration Function ---

if __name__ == '__main__':
    from dotenv import load_dotenv
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    load_dotenv()

    test_date = '2023-10-26'
    logger.info("--- Running website.py standalone test ---")

    WEBSITE_URL_TEST = os.environ.get('WEBSITE_URL')
    USERNAME_TEST = os.environ.get('WEBSITE_USERNAME')
    PASSWORD_TEST = os.environ.get('WEBSITE_PASSWORD')
    SAVE_PATH_BASE = os.path.join(os.environ.get('DOWNLOAD_DIR', 'downloads'), f"{test_date}_test_download")

    if not all([WEBSITE_URL_TEST, USERNAME_TEST, PASSWORD_TEST]):
        logger.error("Required environment variables (WEBSITE_URL, WEBSITE_USERNAME, WEBSITE_PASSWORD) not set for standalone test.")
    else:
        success, file_format = login_and_download(
            base_url=WEBSITE_URL_TEST,
            username=USERNAME_TEST,
            password=PASSWORD_TEST,
            save_path=SAVE_PATH_BASE,
            target_date=test_date,
            dry_run=False,
            force_download=False
        )

        if success:
            logger.info("Standalone test successful. File format: %s", file_format)
            final_path = f"{SAVE_PATH_BASE}.{file_format}"
            logger.info("Expected file path: %s (check if exists)", final_path)
        else:
            logger.error("Standalone test failed.")
    logger.info("--- End website.py standalone test ---")
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return```python
True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target```python
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...",
                            response.status_code, retry_after, attempt + 1, max_retries
                        )
                        time.sleep(retry_after)
                        continue
                
                # For other HTTP errors, fail immediately
                logger.error("Failed to download newspaper. Status code: %d", response.status_code)
                return False, f"Error {response.status_code}: {response.text}"
                
            except requests.exceptions.Timeout:
                # Handle request timeouts
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    logger.warning(
                        "Request timed out. Retrying in %d seconds (attempt %d of %d)...",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error("Download failed after %d attempts due to timeout", max_retries)
                    return False, "Request timed out repeatedly"
                    
            except requests.exceptions.RequestException as e: # Catch specific requests errors
                logger.error("Request error during download attempt: %s", e)
                return False, f"Request error: {str(e)}" # Fail fast on request errors
            except OSError as e: # Catch specific OS errors
                logger.error("OS error during download attempt: %s", e)
                return False, f"OS error: {str(e)}" # Fail fast on OS errors
            except Exception as e: # General fallback
                # Using logger.exception to include traceback
                logger.exception("Unexpected error during Playwright download: %s", e)
                return False, f"Unexpected error: {str(e)}"

def download_newspaper(url, session):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully downloaded newspaper from %s", url)
        return response.content
    except RequestException as e:
        logger.error("Failed to download newspaper from %s: %s", url, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during newspaper download from %s: %s", url, e)
        raise

# --- Main Orchestration Function ---
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date.

    Args:
        base_url (str): The base URL of the newspaper website.
        username (str): The username for logging in.
        password (str): The password for logging in.
        save_path (str): The local path where the downloaded newspaper should be saved.
        target_date (str, optional): The date for which the newspaper should be downloaded, in 'YYYY-MM-DD' format. Defaults to today.
        dry_run (bool, optional): If True, performs a trial run without downloading. Defaults to False.
        force_download (bool, optional): If True, forces download even if file seems to exist. Defaults to False.

    Returns:
        tuple: A tuple containing a success flag (bool) and the file format (str) or error message (str).
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Ensure the download directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)    # Step 1: Get session cookies by logging in
    logger.info("Step 1: Logging in to get session cookies.")
    cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not cookies:
        return False, "Failed to obtain cookies."
        
    # Step 2: Check if newspaper already exists (if not force_download)
    file_exists = False
    if not force_download:
        # Check if any common file extensions exist for this save_path
        for ext in ['pdf', 'html']:
            potential_file = f"{save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists = True
                logger.info("Newspaper file already exists: %s", potential_file)
                return True, ext  # Return success and the existing file extension
                
    if force_download or not file_exists:
        # Proceed with download
        logger.info("Step 2: Downloading the newspaper for date: %s%s", 
                   target_date, 
                   " (force download)" if force_download and file_exists else "")
        download_url = urljoin(base_url, f"newspaper/download/{target_date}")  # Example endpoint
        
        # Add retry mechanism for transient errors
        max_retries = 3
        retry_delays = [5, 15, 30]  # Increasing delays between retries (in seconds)
        
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                response = requests.get(
                    download_url, 
                    cookies=cookies, 
                    headers={'User-Agent': USER_AGENT},
                    timeout=(10, 30)  # (connect timeout, read timeout) in seconds
                )
                
                # Handle successful response
                if response.status_code == 200:
                    if dry_run:
                        logger.info("Dry run enabled. File would be saved to: %s", save_path)
                        return True, response.headers.get('Content-Type', '').split('/')[-1]  # Return the file format
                    else:
                        # Determine file format from Content-Type header
                        content_type = response.headers.get('Content-Type', '')
                        # Rename inner variable
                        response_file_format = 'pdf' if 'pdf' in content_type.lower() else 'html'
                        
                        # Ensure the save path has the correct extension
                        save_path_with_ext = f"{save_path}.{response_file_format}"
                        
                        try:
                            with open(save_path_with_ext, 'wb') as file:
                                file.write(response.content)
                            logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                            return True, response_file_format
                        except OSError as e: # More specific exception for file I/O
                            logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                            return False, f"Failed to save file: {str(e)}"
                
                # Handle common HTTP errors with potentially different retry strategies
                elif response.status_code in (429, 503, 502, 504):
                    # Too Many Requests or Service Unavailable - worth retrying
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get('Retry-After', retry_delays[attempt]))
                        logger.warning(
                            "Received status code %d. Retrying in %d seconds (attempt %d of %d)...