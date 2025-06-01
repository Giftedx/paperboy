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


def _get_session_cookies(login_url, username, password):
    """Uses Playwright to log in and extract session cookies."""
    logger.info("Attempting to log in via Playwright to get session cookies.")
    cookies = None
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright is not installed. Cannot use Playwright for login. Run `pip install playwright` and `playwright install`.")
        return None
        
    browser = None 
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) 
            page = browser.new_page()
            logger.debug("Navigating to login page: %s", login_url)
            page.goto(login_url, wait_until='networkidle')

            logger.debug("Attempting to fill login form using selectors: [Username: %s, Password: %s, Submit: %s]", 
                         USERNAME_SELECTOR, PASSWORD_SELECTOR, SUBMIT_BUTTON_SELECTOR)
            
            if page.locator(USERNAME_SELECTOR).count() > 0:
                page.fill(USERNAME_SELECTOR, username)
            else:
                logger.error("Login failed: Username field not found with selector: %s", USERNAME_SELECTOR)
                if browser: browser.close()
                return None

            if page.locator(PASSWORD_SELECTOR).count() > 0:
                page.fill(PASSWORD_SELECTOR, password)
            else:
                logger.error("Login failed: Password field not found with selector: %s", PASSWORD_SELECTOR)
                if browser: browser.close()
                return None

            if page.locator(SUBMIT_BUTTON_SELECTOR).count() > 0:
                page.click(SUBMIT_BUTTON_SELECTOR)
            else:
                logger.error("Submit button not found with selector: %s", SUBMIT_BUTTON_SELECTOR)
                if browser: browser.close()
                return None

            login_success = False
            if LOGIN_SUCCESS_SELECTOR:
                try:
                    logger.debug("Waiting for login success element: %s", LOGIN_SUCCESS_SELECTOR)
                    page.wait_for_selector(LOGIN_SUCCESS_SELECTOR, timeout=30000)
                    login_success = True
                    logger.info("Login successful (based on element presence: %s).", LOGIN_SUCCESS_SELECTOR)
                except PlaywrightTimeoutError:
                    logger.warning("Login success element not found: %s", LOGIN_SUCCESS_SELECTOR)

            if not login_success and LOGIN_SUCCESS_URL_PATTERN:
                try:
                    logger.debug("Waiting for login success URL pattern: %s", LOGIN_SUCCESS_URL_PATTERN)
                    page.wait_for_url(LOGIN_SUCCESS_URL_PATTERN, timeout=30000)
                    login_success = True
                    logger.info("Login successful (based on URL pattern: %s).", LOGIN_SUCCESS_URL_PATTERN)
                except PlaywrightTimeoutError:
                    logger.warning("Login success URL pattern not matched: %s", LOGIN_SUCCESS_URL_PATTERN)

            if not login_success:
                logger.debug("Using fallback method: waiting for network idle state")
                page.wait_for_load_state('networkidle')
                error_messages = page.locator('.login-error, .error-message, .alert-danger').count()
                if error_messages > 0:
                    error_text = page.locator('.login-error, .error-message, .alert-danger').text_content() or "Unknown login error"
                    logger.error("Login error detected: %s", error_text)
                    if browser: browser.close()
                    return None
                login_success = True # Assume success if no errors and network is idle
                logger.info("Login appears successful (based on network idle state and no error messages).")
            
            if not login_success:
                logger.error("Login could not be confirmed through any verification method.")
                if browser: browser.close()
                return None

            cookies = page.context.cookies()
            logger.debug("Extracted cookies: %s", cookies)
            logger.info("Successfully extracted %d cookies.", len(cookies))
    except PlaywrightTimeoutError:
        logger.error("Playwright timed out during login process. Check selectors, URL, and network conditions.")
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
    Fallback method to download using Playwright when the requests method fails.
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not available for fallback download. Install with: pip install playwright")
        return False, "Playwright not available"
    
    if dry_run:
        logger.info("[Dry Run] Would attempt fallback download using Playwright from: %s", download_url)
        return True, "pdf" # Assume PDF for dry run format
        
    logger.info("Attempting fallback download using Playwright from: %s", download_url)
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True) # Ensure context accepts downloads
            
            if cookies:
                formatted_cookies = []
                for cookie_item in cookies: # Renamed to avoid conflict with module
                    pw_cookie = {
                        'name': cookie_item.get('name'),
                        'value': cookie_item.get('value'),
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
            download_folder = os.path.dirname(save_path)
            # Playwright handles download path, but ensure parent dir exists for final move/save_as
            os.makedirs(download_folder, exist_ok=True)
            page.context.set_default_timeout(60000)
            
            download = None # Initialize download variable
            with page.expect_download() as download_info:
                logger.debug("Navigating to download URL: %s", download_url)
                response = page.goto(download_url, wait_until='networkidle')
                
            if not response or response.status >= 400:
                status_code = response.status if response else 'N/A'
                logger.error("Failed to navigate to download URL: %s", download_url)
                if browser: browser.close()
                return False, f"Navigation failed or status error: {status_code}"
            
            if download is None:
                if browser: browser.close()
                return False, f"Error status: {response.status}"

            download = download_info.value # type: ignore
            downloaded_file_format = download.suggested_filename.split('.')[-1].lower()
            if downloaded_file_format not in ['pdf', 'html']:
                downloaded_file_format = 'pdf' 

            save_path_with_ext = f"{save_path}.{downloaded_file_format}"
            download.save_as(save_path_with_ext)
            logger.info("Playwright successfully downloaded file to: %s", save_path_with_ext)
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
def login_and_download(base_url, username, password, save_path, target_date=None, dry_run=False, force_download=False):
    """Logs in to the website and downloads the newspaper for the given date."""
    if target_date is None:
        target_date_obj = datetime.datetime.now()
    else:
        try:
            target_date_obj = datetime.datetime.strptime(target_date, '%Y-%m-%d')
        except ValueError:
            logger.error("Invalid target_date format. Please use YYYY-MM-DD.")
            return False, "Invalid date format"
    
    # Ensure target_date is a string for URL construction and file naming
    target_date_str = target_date_obj.strftime('%Y-%m-%d')

    abs_save_path = os.path.abspath(save_path)
    download_parent_dir = os.path.dirname(abs_save_path)
    os.makedirs(download_parent_dir, exist_ok=True)

    logger.info("Step 1: Logging in to get session cookies.")
    session_cookies = _get_session_cookies(LOGIN_URL, username, password)
    if not session_cookies:
        logger.error("Failed to obtain session cookies. Login unsuccessful.")
        return False, "Failed to obtain cookies."
        
    file_exists_locally = False
    determined_file_ext = ""
    if not force_download:
        for ext in ['pdf', 'html']:
            potential_file = f"{abs_save_path}.{ext}"
            if os.path.exists(potential_file):
                file_exists_locally = True
                determined_file_ext = ext
                logger.info("Newspaper file already exists: %s", potential_file)
                break 
        if file_exists_locally:
            return True, determined_file_ext
                
    logger.info("Step 2: Downloading the newspaper for date: %s%s", 
               target_date_str, 
               " (force download)" if force_download and file_exists_locally else "")
    
    year = target_date_obj.strftime('%Y')
    month = target_date_obj.strftime('%m')
    day = target_date_obj.strftime('%d')
    download_url_path = f"newspaper/download/{target_date_str}" 
    actual_download_url = urljoin(base_url, download_url_path)
    
    max_retries = 3
    retry_delays = [5, 15, 30] 
    
    for attempt in range(max_retries):
        try:
            logger.debug("Attempting download from %s (Attempt %d/%d)", actual_download_url, attempt + 1, max_retries)
            session = requests.Session()
            if session_cookies:
                for cookie_item in session_cookies: # renamed variable
                    session.cookies.set(cookie_item['name'], cookie_item['value'], domain=cookie_item['domain'], path=cookie_item.get('path', '/'))

            response = session.get(
                actual_download_url, 
                headers={'User-Agent': USER_AGENT},
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
            logger.error("Standalone test failed. Reason: %s", file_info) # file_info contains the error message
    logger.info("--- End website.py standalone test ---")
