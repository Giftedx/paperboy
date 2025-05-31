#!/usr/bin/env python3
"""
Website interaction module for newspaper downloader
Handles login to newspaper website and downloading the daily newspaper.
"""

import os
import logging
import datetime
import requests 
from requests.exceptions import RequestException 
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import config
import time 

# Playwright imports (optional dependency)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    class PlaywrightTimeoutError(Exception): # type: ignore
        pass
    class PlaywrightError(Exception): # type: ignore
        pass

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration from centralized config module ---
WEBSITE_URL = config.config.get(('newspaper', 'url'))
LOGIN_URL = config.config.get(('newspaper', 'login_url'), WEBSITE_URL)
USERNAME = config.config.get(('newspaper', 'username'))
PASSWORD = config.config.get(('newspaper', 'password'))
DOWNLOAD_DIR = config.config.get(('paths', 'download_dir'), 'downloads')
USER_AGENT = config.config.get(('newspaper', 'user_agent'), 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

# --- Website Selectors (Configurable) ---
USERNAME_SELECTOR = config.config.get(('newspaper', 'selectors', 'username'), 'input[name="username"]')
PASSWORD_SELECTOR = config.config.get(('newspaper', 'selectors', 'password'), 'input[name="password"]')
SUBMIT_BUTTON_SELECTOR = config.config.get(('newspaper', 'selectors', 'submit'), 'button[type="submit"]')
LOGIN_SUCCESS_SELECTOR = config.config.get(('newspaper', 'selectors', 'login_success'), '#user-profile-link')
LOGIN_SUCCESS_URL_PATTERN = config.config.get(('newspaper', 'selectors', 'login_success_url'), '')

# --- Helper Functions ---
def _get_session_cookies(login_url: str, username: str, password: str) -> list[dict] | None:
    """
    Log in to a website using Playwright and extract session cookies.

    Navigates to the login page, fills in username and password, clicks submit,
    and waits for login success indicators (CSS selector or URL pattern).
    If login is successful, extracts and returns all browser context cookies.

    Args:
        login_url: The URL of the login page.
        username: The username for login.
        password: The password for login.

    Returns:
        A list of cookie dictionaries if login and cookie extraction are successful,
        otherwise None. Each cookie dictionary typically contains keys like
        'name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite'.
    """
    logger.info("Attempting to log in via Playwright to get session cookies from %s.", login_url)
    cookies: list[dict] | None = None # Explicitly define type for clarity
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright is not installed. Cannot use Playwright for login. Run `pip install playwright` and `playwright install`.")
        return None
        
    browser = None 
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # Consider making headless configurable
            page = browser.new_page()
            logger.debug("Navigating to login page: %s", login_url)
            page.goto(login_url, wait_until='networkidle') # Wait for network to be idle to ensure page is fully loaded

            logger.debug("Attempting to fill login form using selectors: [Username: %s, Password: %s, Submit: %s]", 
                         USERNAME_SELECTOR, PASSWORD_SELECTOR, SUBMIT_BUTTON_SELECTOR)
            
            # Fill username
            if page.locator(USERNAME_SELECTOR).count() > 0:
                page.fill(USERNAME_SELECTOR, username)
            else:
                logger.error("Username field not found with selector: '%s'", USERNAME_SELECTOR)
                if browser: browser.close()
                return None

            # Fill password
            if page.locator(PASSWORD_SELECTOR).count() > 0:
                page.fill(PASSWORD_SELECTOR, password)
            else:
                logger.error("Password field not found with selector: '%s'", PASSWORD_SELECTOR)
                if browser: browser.close()
                return None

            # Click submit button
            if page.locator(SUBMIT_BUTTON_SELECTOR).count() > 0:
                page.click(SUBMIT_BUTTON_SELECTOR)
            else:
                logger.error("Submit button not found with selector: '%s'", SUBMIT_BUTTON_SELECTOR)
                if browser: browser.close()
                return None

            # Verify login success
            login_success = False
            # Method 1: Check for a specific element indicating login success
            if LOGIN_SUCCESS_SELECTOR:
                try:
                    logger.debug("Waiting for login success element: %s", LOGIN_SUCCESS_SELECTOR)
                    page.wait_for_selector(LOGIN_SUCCESS_SELECTOR, timeout=30000) # Wait up to 30s
                    login_success = True
                    logger.info("Login successful (based on element presence: %s).", LOGIN_SUCCESS_SELECTOR)
                except PlaywrightTimeoutError:
                    logger.warning("Login success element ('%s') not found after timeout.", LOGIN_SUCCESS_SELECTOR)
            
            # Method 2 (if Method 1 failed): Check if URL matches a success pattern
            if not login_success and LOGIN_SUCCESS_URL_PATTERN:
                try:
                    logger.debug("Waiting for login success URL pattern: %s", LOGIN_SUCCESS_URL_PATTERN)
                    page.wait_for_url(LOGIN_SUCCESS_URL_PATTERN, timeout=30000) # Wait up to 30s
                    login_success = True
                    logger.info("Login successful (based on URL pattern: %s).", LOGIN_SUCCESS_URL_PATTERN)
                except PlaywrightTimeoutError:
                    logger.warning("Login success URL pattern ('%s') not matched after timeout.", LOGIN_SUCCESS_URL_PATTERN)

            # Method 3 (Fallback if specific selectors/URLs fail):
            # Wait for network to be idle again and check for common error messages.
            if not login_success:
                logger.debug("Login success not confirmed by specific selectors/URL. Using fallback: waiting for network idle and checking for error messages.")
                page.wait_for_load_state('networkidle', timeout=30000) # Wait for page to settle
                # Check for common error message patterns/selectors
                error_message_selectors = '.login-error, .error-message, .alert-danger, [class*="error"], [id*="error"]'
                error_locator = page.locator(error_message_selectors)

                if error_locator.count() > 0:
                    # Try to get text from the first visible error message
                    first_error_text = "Unknown login error (error element present but no text extracted)"
                    for i in range(error_locator.count()):
                        if error_locator.nth(i).is_visible():
                            first_error_text = error_locator.nth(i).text_content(timeout=1000) or first_error_text
                            break
                    logger.error("Login error detected on page: %s", first_error_text.strip())
                    if browser: browser.close()
                    return None
                else:
                    # If no specific success indicators AND no error messages found, assume success.
                    # This can be risky; strong success indicators are preferred.
                    login_success = True
                    logger.info("Login appears successful (based on network idle state and no explicit error messages found).")
            
            # Final check if login was confirmed by any method
            if not login_success:
                logger.error("Login could not be confirmed through any verification method (specific selectors, URL, or fallback error check).")
                if browser: browser.close()
                return None

            cookies = page.context.cookies()
            logger.info("Successfully extracted %d cookies.", len(cookies))
    except PlaywrightTimeoutError:
        logger.error("Playwright timed out during login process. Check selectors and network conditions.")
    except PlaywrightError as e: 
        logger.error("A Playwright error occurred during login: %s", e)
    except Exception as e: 
        logger.exception("An unexpected error occurred during Playwright login: %s", e)
    finally:
        if browser: 
             browser.close()
    return cookies

def _download_with_playwright(download_url, save_path, cookies, dry_run=False):
    """
    Attempt to download a file using Playwright.

    This is typically used as a fallback if `requests`-based download methods fail.
    It navigates to the download URL, handling cookies if provided, and waits
    for a download event to save the file.

    Args:
        download_url: The direct URL to the file to be downloaded.
        save_path: The base local path (without extension) where the file should be saved.
                   The correct extension will be appended based on the downloaded file.
        cookies: A list of cookie dictionaries (from a previous Playwright session)
                 to be added to the Playwright context.
        dry_run: If True, simulates the download attempt without actually saving the file.

    Returns:
        A tuple (bool, str):
        - True if download is successful (or simulated successfully in dry_run),
          False otherwise.
        - A string indicating the determined file format (e.g., 'pdf', 'html') on success,
          or an error message string on failure.
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not available for fallback download. Install with: `pip install playwright` and `playwright install`.")
        return False, "Playwright not available"
    
    if dry_run:
        logger.info("[Dry Run] Would attempt fallback download using Playwright from: %s", download_url)
        return True, "pdf"
        
    logger.info("Attempting fallback download using Playwright from: %s", download_url)
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # Consider making headless configurable
            context = browser.new_context()
            
            # Add cookies to the context if provided
            if cookies:
                formatted_cookies = []
                for cookie_data in cookies:
                    # Ensure cookie structure is valid for Playwright
                    pw_cookie = {
                        'name': cookie_data.get('name'),
                        'value': cookie_data.get('value'),
                        'domain': cookie_item.get('domain'),
                        'path': cookie_item.get('path', '/'), 
                        'expires': cookie_item.get('expires', -1), 
                        'httpOnly': cookie_item.get('httpOnly', False),
                        'secure': cookie_item.get('secure', False),
                        'sameSite': cookie_item.get('sameSite', 'Lax') 
                    }
                    formatted_cookies.append({k:v for k,v in pw_cookie.items() if v is not None})
                context.add_cookies(formatted_cookies)
                    
            page = context.new_page()
            # Ensure download directory exists
            download_folder = os.path.dirname(save_path)
            os.makedirs(download_folder, exist_ok=True)
            
            # Set a reasonable timeout for page operations and download event
            page.context.set_default_timeout(60000) # 60 seconds

            download_event_info = None # Initialize download event info
            # Start waiting for the download event *before* navigating
            with page.expect_download(timeout=60000) as download_info_context:
                logger.debug("Navigating to download URL with Playwright: %s", download_url)
                page_response = page.goto(download_url, wait_until='networkidle', timeout=60000) # wait_until can also be 'domcontentloaded' or 'load'

            download_event_info = download_info_context.value # Actual Download object

            if not page_response:
                logger.error("Playwright: Failed to navigate to download URL (no response): %s", download_url)
                if browser: browser.close()
                return False, "Playwright navigation failed (no response)"
            
            if page_response.status >= 400:
                logger.error("Playwright: Received error status code %d for URL %s", page_response.status, download_url)
                if browser: browser.close()
                return False, f"Playwright navigation error status: {page_response.status}"

            # Determine file format from suggested filename or default to 'pdf'
            suggested_filename = download_event_info.suggested_filename
            logger.info("Playwright: Download initiated, suggested filename: %s", suggested_filename)
            downloaded_file_format = suggested_filename.split('.')[-1].lower() if '.' in suggested_filename else 'pdf'
            if downloaded_file_format not in ['pdf', 'html']: # Ensure it's one of the expected types
                logger.warning("Playwright: Downloaded file format '%s' not standard, defaulting to 'pdf'.", downloaded_file_format)
                downloaded_file_format = 'pdf' 
            
            # Construct final save path with the determined extension
            save_path_with_ext = f"{save_path}.{downloaded_file_format}"
            download_event_info.save_as(save_path_with_ext)
            logger.info("Playwright successfully downloaded and saved file to: %s", save_path_with_ext)
            return True, downloaded_file_format
            
    except PlaywrightTimeoutError as e:
        logger.error("Playwright timeout during download from %s: %s", download_url, e)
        return False, f"Playwright timeout: {str(e)}"
    except PlaywrightError as e:
        logger.error("Playwright error during download from %s: %s", download_url, e)
        return False, f"Playwright error: {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error during Playwright download from %s: %s", download_url, e)
        return False, f"Unexpected error: {str(e)}"
    finally:
        if browser:
            browser.close()
    return False, "Playwright download did not complete" # Fallback if not returned earlier

# --- Main Orchestration Function ---
def login_and_download(base_url: str, username: str, password: str,
                       save_path: str, target_date: str | None = None,
                       dry_run: bool = False, force_download: bool = False) -> tuple[bool, str]:
    """
    Log in to the newspaper website and download the edition for the specified date.

    This function orchestrates the login process (via Playwright to get cookies),
    then attempts to download the newspaper using `requests`. If `requests` fails,
    it tries a scraping method to find a direct download link. If scraping also fails,
    it falls back to downloading directly with Playwright.

    Args:
        base_url: The base URL of the newspaper website.
        username: Username for login.
        password: Password for login.
        save_path: The base local path (without extension) to save the downloaded file.
                   The correct extension (.pdf or .html) will be appended.
        target_date: The target date for the newspaper in 'YYYY-MM-DD' format.
                     Defaults to the current day if None.
        dry_run: If True, simulates actions without actual downloads or file writes.
        force_download: If True, downloads the file even if it already exists locally.

    Returns:
        A tuple (bool, str):
        - True if successful, False otherwise.
        - If successful, the determined file format ('pdf', 'html') or the full path
          to the saved file (if not dry_run and file was downloaded).
        - If failed, an error message string.
    """
    # Date handling
    if target_date is None:
        target_date_obj = datetime.datetime.now().date() # Use .date() for date object
    else:
        try:
            target_date_obj = datetime.datetime.strptime(target_date, '%Y-%m-%d').date()
        except ValueError:
            logger.error("Invalid target_date format '%s'. Please use YYYY-MM-DD.", target_date)
            return False, "Invalid date format"
    
    target_date_str = target_date_obj.strftime('%Y-%m-%d') # Consistent string format for internal use

    # Prepare save path
    abs_save_path = os.path.abspath(save_path) # Ensure path is absolute
    download_parent_dir = os.path.dirname(abs_save_path)
    os.makedirs(download_parent_dir, exist_ok=True) # Create download directory if it doesn't exist

    # Step 1: Login using Playwright to get session cookies
    # -----------------------------------------------------
    logger.info("Step 1: Logging in to get session cookies.")
    session_cookies = _get_session_cookies(LOGIN_URL or base_url, username, password) # Use LOGIN_URL if defined, else base_url
    if not session_cookies:
        logger.error("Failed to obtain session cookies. Login unsuccessful.")
        return False, "Login failed: Could not obtain session cookies."
        
    # Step 2: Check if file already exists locally (unless force_download or dry_run)
    # ------------------------------------------------------------------------------
    if not force_download and not dry_run: # In dry_run, we always simulate the download attempt
        for ext in ['pdf', 'html']:
            potential_file = f"{abs_save_path}.{ext}"
            if os.path.exists(potential_file):
                logger.info("Newspaper file already exists locally: %s. Skipping download.", potential_file)
                return True, ext # Return True and the extension of the existing file
                
    logger.info("Step 2: Preparing to download newspaper for date: %s%s.",
               target_date_str, 
               " (force download)" if force_download else "")
    
    # Construct the primary download URL (this might be site-specific)
    # Example: base_url/newspaper/download/YYYY-MM-DD
    # This part needs to be configured or made more generic if possible.
    # For now, assuming a pattern; this should ideally come from config.
    download_url_path = f"newspaper/download/{target_date_str}" # Example path
    actual_download_url = urljoin(base_url, download_url_path)
    
    # Step 3: Attempt download using Python `requests` with session cookies
    # ---------------------------------------------------------------------
    max_retries = config.config.get(('newspaper', 'download_retries'), 3)
    retry_delays = config.config.get(('newspaper', 'retry_delays_s'), [5, 15, 30]) # In seconds
    
    for attempt in range(max_retries):
        try:
            logger.debug("Attempting download from %s (Attempt %d/%d) using requests.", actual_download_url, attempt + 1, max_retries)
            session = requests.Session()
            # Populate session with cookies obtained from Playwright login
            if session_cookies:
                for cookie_data in session_cookies:
                    session.cookies.set(
                        cookie_data['name'],
                        cookie_data['value'],
                        domain=cookie_data['domain'],
                        path=cookie_data.get('path', '/')
                    )

            response = session.get(
                actual_download_url, 
                headers={'User-Agent': USER_AGENT}, # Use configured User-Agent
                timeout=(10, 30), 
                allow_redirects=True
            )
            response.raise_for_status()

            if dry_run:
                logger.info("[Dry Run] File would be saved to: %s (Content-Type: %s)", 
                            abs_save_path, response.headers.get('Content-Type'))
                content_type = response.headers.get('Content-Type', '').lower()
                if 'pdf' in content_type: file_format = 'pdf'
                elif 'html' in content_type: file_format = 'html'
                else: file_format = 'bin'
                return True, file_format
            
            content_type = response.headers.get('Content-Type', '').lower()
            file_format = 'pdf' 
            if 'pdf' in content_type: file_format = 'pdf'
            elif 'html' in content_type: file_format = 'html'
            else:
                cont_disp = response.headers.get('Content-Disposition')
                if cont_disp:
                    filename_part = next((s for s in cont_disp.split(';') if 'filename=' in s.lower()), None) # case-insensitive
                    if filename_part:
                        filename = filename_part.split('=')[-1].strip('"')
                        if '.' in filename:
                            file_format = filename.split('.')[-1].lower()
            
            save_path_with_ext = f"{abs_save_path}.{file_format}"
            try:
                with open(save_path_with_ext, 'wb') as file_handle: # renamed variable
                    file_handle.write(response.content)
                logger.info("Newspaper downloaded successfully: %s", save_path_with_ext)
                return True, file_format
            except OSError as e:
                logger.error("Failed to save downloaded file %s: %s", save_path_with_ext, e)
                return False, f"Failed to save file: {str(e)}"

        except requests.exceptions.Timeout:
            logger.warning("Request timed out (Attempt %d/%d). Retrying if possible...", attempt + 1, max_retries)
            if attempt >= max_retries - 1:
                logger.error("Download failed after %d attempts due to timeout from %s", max_retries, actual_download_url)
                return False, "Request timed out repeatedly"
            time.sleep(retry_delays[attempt])
        except RequestException as e: # Original exception for initial requests.get failure
            logger.warning("Initial requests.get failed for %s: %s. Attempting to scrape for a direct link.", actual_download_url, e)
            
            try:
                # Use the same session that already has cookies
                page_response = session.get(actual_download_url, headers={'User-Agent': USER_AGENT}, timeout=(10,30), allow_redirects=True)
                page_response.raise_for_status() 
                
                soup = BeautifulSoup(page_response.content, 'html.parser')
                
                download_link_selectors_config = config.config.get(('newspaper', 'selectors', 'download_link_css_selectors'), [
                    'a[href$=".pdf"]', 
                    'a[href$=".html"]',
                    'a.download-button[href]', 
                    'a#downloadLink[href]'    
                ])

                found_download_url = None
                for selector in download_link_selectors_config:
                    link_element = soup.select_one(selector)
                    if link_element and link_element.get('href'):
                        found_download_url = urljoin(actual_download_url, link_element['href'])
                        logger.info("Found potential download link via scraping: %s", found_download_url)
                        break
                
                if found_download_url:
                    logger.info("Attempting download from scraped link: %s", found_download_url)
                    # Re-assign response variable for the new download attempt
                    response = session.get(
                        found_download_url, 
                        headers={'User-Agent': USER_AGENT},
                        timeout=(10, 30),
                        allow_redirects=True
                    )
                    response.raise_for_status()

                    if dry_run:
                        logger.info("[Dry Run] Scraped link: File would be saved to: %s (Content-Type: %s)", 
                                    abs_save_path, response.headers.get('Content-Type'))
                        content_type = response.headers.get('Content-Type', '').lower()
                        if 'pdf' in content_type: file_format = 'pdf'
                        elif 'html' in content_type: file_format = 'html'
                        else: file_format = 'bin'
                        return True, file_format

                    content_type = response.headers.get('Content-Type', '').lower()
                    file_format = 'pdf' 
                    if 'pdf' in content_type: file_format = 'pdf'
                    elif 'html' in content_type: file_format = 'html'
                    else:
                        cont_disp = response.headers.get('Content-Disposition')
                        if cont_disp:
                            filename_part = next((s_part for s_part in cont_disp.split(';') if 'filename=' in s_part.lower()), None)
                            if filename_part:
                                filename = filename_part.split('=')[-1].strip('"')
                                if '.' in filename:
                                    file_format = filename.split('.')[-1].lower()
                    
                    save_path_with_ext = f"{abs_save_path}.{file_format}"
                    try:
                        with open(save_path_with_ext, 'wb') as file_handle:
                            file_handle.write(response.content)
                        logger.info("Newspaper downloaded successfully via scraped link: %s", save_path_with_ext)
                        return True, file_format
                    except OSError as os_err:
                        logger.error("Failed to save downloaded file (from scraped link) %s: %s", save_path_with_ext, os_err)
                        # If saving the scraped file fails, this attempt is over.
                        # Depending on desired behavior, could fall through to Playwright or return failure for this scraped attempt.
                        # For now, returning False as this specific download path (scraping) failed at saving.
                        return False, f"Failed to save file (from scraped link): {str(os_err)}"
                else:
                    logger.warning("No direct download link found via scraping page %s. Proceeding to Playwright fallback if configured and available.", actual_download_url)

            except RequestException as scrape_e: 
                logger.error("Error during scraping/sub-download attempt for %s: %s. Proceeding to Playwright fallback if configured and available.", actual_download_url, scrape_e)
            
            # Fallback to Playwright if scraping failed, no link was found, or any other error occurred during scraping.
            # This is part of the original except RequestException as e block from the initial requests.get()
            if PLAYWRIGHT_AVAILABLE: # Check if Playwright is an option
                logger.info("Falling back to Playwright download for %s (original error: %s).", actual_download_url, e) # Log original error 'e'
                return _download_with_playwright(actual_download_url, abs_save_path, session_cookies, dry_run)
            
            # If Playwright is not available and scraping didn't yield a result (or itself failed)
            return False, f"Request error: {str(e)} (and scraping failed or Playwright fallback unavailable)"
        except OSError as e: 
            logger.error("OS error during download/saving process: %s", e)
            return False, f"OS error: {str(e)}"
        except Exception as e: 
            logger.exception("An unexpected error occurred during download from %s: %s", actual_download_url, e)
            if attempt >= max_retries - 1:
                return False, f"Unexpected error: {str(e)}"
            time.sleep(retry_delays[attempt])
            
    return False, "Download failed after all retries."


if __name__ == '__main__':
    from dotenv import load_dotenv
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    load_dotenv()

    test_date_str = '2023-10-26' 
    logger.info("--- Running website.py standalone test for date: %s ---", test_date_str)

    WEBSITE_URL_TEST = os.environ.get('WEBSITE_URL', WEBSITE_URL) 
    USERNAME_TEST = os.environ.get('WEBSITE_USERNAME', USERNAME)
    PASSWORD_TEST = os.environ.get('WEBSITE_PASSWORD', PASSWORD)
    SAVE_PATH_BASE_TEST = os.path.join(os.environ.get('DOWNLOAD_DIR', DOWNLOAD_DIR), f"{test_date_str}_test_download")

    if not all([WEBSITE_URL_TEST, USERNAME_TEST, PASSWORD_TEST]):
        logger.error("Required environment variables (WEBSITE_URL, WEBSITE_USERNAME, WEBSITE_PASSWORD) or config values not set for standalone test.")
    else:
        logger.info("Initiating test download for URL: %s, User: %s, Save Path Base: %s", WEBSITE_URL_TEST, USERNAME_TEST, SAVE_PATH_BASE_TEST)
        success, file_info = login_and_download(
            base_url=WEBSITE_URL_TEST,
            username=USERNAME_TEST,
            password=PASSWORD_TEST,
            save_path=SAVE_PATH_BASE_TEST, 
            target_date=test_date_str,
            dry_run=False, 
            force_download=True 
        )

        if success:
            logger.info("Standalone test successful. File info/format: %s", file_info)
            final_path = f"{SAVE_PATH_BASE_TEST}.{file_info}" if isinstance(file_info, str) and not os.path.exists(file_info) else file_info
            if os.path.exists(final_path):
                 logger.info("File successfully saved to: %s", final_path)
            else:
                 logger.warning("File path %s does not exist, check file_info and save_path logic.", final_path)
        else:
            logger.error("Standalone test failed. Reason: %s", file_info)
    logger.info("--- End website.py standalone test ---")
