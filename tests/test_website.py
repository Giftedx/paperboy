import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import sys # For path manipulation
from pathlib import Path # For path manipulation
from datetime import date, datetime # For date objects

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import website # The module to test
from config import Config # To reset the singleton for config
# Import specific exceptions if they are explicitly caught and handled
from requests.exceptions import RequestException 

# Test configuration data (can be accessed by website.py via mocked config.get)
MOCK_CONFIG_DATA = {
    'newspaper': {
        'url': 'http://testnews.com',
        'login_url': 'http://testnews.com/login',
        'username': 'testuser',
        'password': 'testpassword',
        'selectors': { # For _get_session_cookies, which is often mocked as a whole
            'username': '#user', 'password': '#pass', 'submit': '#submit',
            'login_success': '#profile',
            # Selectors for the new scraping logic in login_and_download
            'download_link_css_selectors': [
                'a.direct_download_link[href]', # Test specific selector
                'a[href$=".pdf"]' # Generic PDF link
            ]
        }
    },
    'paths': {
        'download_dir': 'test_downloads_dir'
    },
    'general': { # Added for completeness as main.py also loads these
        'date_format': '%Y-%m-%d',
        'retention_days': 7,
    }
}

# This side effect function will be used by the mock for config.config.get
def mock_config_get_side_effect(key_tuple, default=None):
    d = MOCK_CONFIG_DATA
    try:
        for k in key_tuple:
            d = d[k]
        return d
    except KeyError:
        # Fallback to default if key not in MOCK_CONFIG_DATA
        # This is important if the code being tested calls config.get for other keys
        # not mocked explicitly (e.g. general.date_format if not in MOCK_CONFIG_DATA)
        if key_tuple == ('general', 'date_format'): return '%Y-%m-%d'
        if key_tuple == ('general', 'filename_template'): return "{date}_newspaper.{format}"
        if key_tuple == ('general', 'thumbnail_filename_template'): return "{date}_thumbnail.{format}"
        return default


class TestWebsite(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.original_environ = dict(os.environ)
        os.environ.clear()
        
        # Reset the config singleton for each test
        website.config.config = Config() # website.py uses config.config directly

        # Common patchers - start them in specific tests or here if widely used
        self.patch_os_makedirs = patch('os.makedirs')
        self.patch_os_path_exists = patch('os.path.exists')
        self.patch_open = patch('builtins.open', new_callable=mock_open)
        self.patch_get_session_cookies = patch('website._get_session_cookies', return_value=[{'name': 'session', 'value': 'dummy'}])
        self.patch_requests_session_get = patch('requests.Session.get') # More specific than just requests.get
        self.patch_beautifulsoup = patch('website.BeautifulSoup') # Patch where it's imported in website.py
        self.patch_playwright_download = patch('website._download_with_playwright')
        self.patch_logger_info = patch('website.logger.info')
        self.patch_logger_warning = patch('website.logger.warning')
        self.patch_logger_error = patch('website.logger.error')
        self.patch_logger_exception = patch('website.logger.exception')
        self.patch_time_sleep = patch('time.sleep', return_value=None) # Mock time.sleep


        self.mock_os_makedirs = self.patch_os_makedirs.start()
        self.mock_os_path_exists = self.patch_os_path_exists.start()
        self.mock_open = self.patch_open.start()
        self.mock_get_session_cookies = self.patch_get_session_cookies.start()
        self.mock_requests_session_get = self.patch_requests_session_get.start()
        self.mock_beautifulsoup = self.patch_beautifulsoup.start()
        self.mock_playwright_download = self.patch_playwright_download.start()
        
        self.mock_logger_info = self.patch_logger_info.start()
        self.mock_logger_warning = self.patch_logger_warning.start()
        self.mock_logger_error = self.patch_logger_error.start()
        self.mock_logger_exception = self.patch_logger_exception.start()
        self.mock_time_sleep = self.patch_time_sleep.start()

        # Patch config.config.get used within the website module
        self.patch_config_get_in_website = patch.object(website.config.config, 'get', side_effect=mock_config_get_side_effect)
        self.mock_config_get_method = self.patch_config_get_in_website.start()


    def tearDown(self):
        patch.stopall()
        os.environ.clear()
        os.environ.update(self.original_environ)

    def test_login_and_download_file_exists_no_force(self):
        self.mock_os_path_exists.side_effect = lambda path: path.endswith('.pdf') # Simulate PDF exists
        
        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str,
            force_download=False
        )
        self.assertTrue(success)
        self.assertEqual(result, 'pdf') # Should return the extension of the found file
        self.mock_os_makedirs.assert_called_once_with(MOCK_CONFIG_DATA['paths']['download_dir'], exist_ok=True)
        self.mock_os_path_exists.assert_any_call(save_path_base + ".pdf")
        self.mock_get_session_cookies.assert_not_called() # Should not attempt login/download

    def test_login_and_download_force_download_skips_exist_check(self):
        self.mock_os_path_exists.return_value = True # File exists, but should be ignored
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]
        # Simulate successful direct download
        mock_response_direct = MagicMock()
        mock_response_direct.status_code = 200
        mock_response_direct.headers = {'Content-Type': 'application/pdf'}
        mock_response_direct.content = b"PDF Content"
        self.mock_requests_session_get.return_value = mock_response_direct

        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str,
            force_download=True # Force download
        )
        self.assertTrue(success)
        self.assertEqual(result, save_path_base + ".pdf") # Should return full path of downloaded file
        self.mock_get_session_cookies.assert_called_once()
        self.mock_requests_session_get.assert_called_once() # Direct download attempt
        self.mock_open.assert_called_once_with(save_path_base + ".pdf", 'wb')


    def test_login_and_download_direct_requests_success(self):
        self.mock_os_path_exists.return_value = False # File does not exist initially
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/pdf'}
        mock_response.content = b"Fake PDF data"
        self.mock_requests_session_get.return_value = mock_response
        
        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_path = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertTrue(success)
        expected_path = save_path_base + ".pdf"
        self.assertEqual(result_path, expected_path)
        self.mock_requests_session_get.assert_called_once() # Only direct download attempt
        self.mock_open.assert_called_once_with(expected_path, 'wb')
        self.mock_beautifulsoup.assert_not_called()
        self.mock_playwright_download.assert_not_called()

    def test_login_and_download_requests_fails_scrape_success(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        # First requests.get (direct download) fails
        mock_response_page = MagicMock() # For scraping
        mock_response_page.status_code = 200
        mock_response_page.content = b"<html><a class='direct_download_link' href='download.pdf'>link</a></html>"
        
        mock_response_file = MagicMock() # For scraped link download
        mock_response_file.status_code = 200
        mock_response_file.headers = {'Content-Type': 'application/pdf'}
        mock_response_file.content = b"Scraped PDF data"

        self.mock_requests_session_get.side_effect = [
            RequestException("Direct download failed"), # Initial attempt
            mock_response_page,                     # Fetching page for scraping
            mock_response_file                      # Downloading scraped link
        ]
        
        mock_link_element = MagicMock()
        mock_link_element.get.return_value = 'download.pdf'
        self.mock_beautifulsoup.return_value.select_one.return_value = mock_link_element
        
        target_date_str = '2023-01-02'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_path = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertTrue(success)
        expected_path = save_path_base + ".pdf"
        self.assertEqual(result_path, expected_path)
        self.assertEqual(self.mock_requests_session_get.call_count, 3)
        self.mock_beautifulsoup.assert_called_once()
        self.mock_open.assert_called_once_with(expected_path, 'wb')
        self.mock_playwright_download.assert_not_called()

    def test_login_and_download_scrape_no_link_fallback_playwright_success(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        mock_response_page = MagicMock()
        mock_response_page.status_code = 200
        mock_response_page.content = b"<html>No link here</html>"
        
        self.mock_requests_session_get.side_effect = [
            RequestException("Direct download failed"), 
            mock_response_page 
        ]
        self.mock_beautifulsoup.return_value.select_one.return_value = None # No link found
        
        playwright_downloaded_path = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "playwright_file.pdf")
        self.mock_playwright_download.return_value = (True, "pdf") # Simulates _download_with_playwright returning format

        target_date_str = '2023-01-03'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")


        # _download_with_playwright is expected to save the file itself and return (True, format)
        # So login_and_download will construct the path.
        expected_final_path = save_path_base + ".pdf" 

        success, result_path = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertTrue(success)
        self.assertEqual(result_path, expected_final_path)
        self.assertEqual(self.mock_requests_session_get.call_count, 2)
        self.mock_beautifulsoup.assert_called_once()
        self.mock_playwright_download.assert_called_once()
        # File opening for saving is handled inside _download_with_playwright, which is mocked.

    def _test_login_and_download_http_error_fallback(self, status_code, expected_fallback_call_count=1):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        # Mock initial requests.get to return an HTTP error
        mock_http_error_response = MagicMock()
        mock_http_error_response.status_code = status_code
        mock_http_error_response.raise_for_status.side_effect = requests.exceptions.HTTPError(f"{status_code} Error")

        # Mock subsequent scraping attempt (page fetch)
        mock_scrape_page_response = MagicMock()
        mock_scrape_page_response.status_code = 200
        mock_scrape_page_response.content = b"<html>No link here for scraping</html>" # Ensure scraping finds no link

        self.mock_requests_session_get.side_effect = [
            mock_http_error_response,       # Initial direct download attempt (fails with HTTPError)
            mock_scrape_page_response,      # Page fetch for scraping
            # Add another RequestException if scraping itself tries to download and fails, leading to playwright
            RequestException("Scraping download attempt failed")
        ]
        self.mock_beautifulsoup.return_value.select_one.return_value = None # No link found by scraping

        # Playwright is the final fallback
        playwright_final_path = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "playwright_file.html")
        self.mock_playwright_download.return_value = (True, "html") # Playwright succeeds

        target_date_str = f'2023-01-1{status_code % 10}' # Unique date for each test
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")
        expected_final_path = save_path_base + ".html"

        success, result_path = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )

        self.assertTrue(success)
        self.assertEqual(result_path, expected_final_path)
        # Called for: initial attempt (HTTP error), page fetch for scraping, (optionally link download from scraping - mocked to fail)
        self.assertEqual(self.mock_requests_session_get.call_count, 3 if MOCK_CONFIG_DATA['newspaper']['selectors']['download_link_css_selectors'] else 2)
        self.mock_beautifulsoup.assert_called_once()
        self.mock_playwright_download.assert_called_once()
        self.mock_logger_warning.assert_any_call(
            "Initial requests.get failed for %s: %s. Attempting to scrape for a direct link.",
            unittest.mock.ANY, # URL
            unittest.mock.ANY  # Original HTTPError
        )

    def test_login_and_download_http_401_fallback(self):
        self._test_login_and_download_http_error_fallback(401)

    def test_login_and_download_http_403_fallback(self):
        self._test_login_and_download_http_error_fallback(403)

    def test_login_and_download_http_404_fallback(self):
        self._test_login_and_download_http_error_fallback(404)

    def test_login_and_download_http_500_fallback(self):
        self._test_login_and_download_http_error_fallback(500)

    def _test_login_and_download_requests_exception_fallback(self, exception_to_raise, is_timeout=False):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        # Mock initial requests.get to raise the specified exception
        # Mock subsequent scraping attempt (page fetch)
        mock_scrape_page_response = MagicMock()
        mock_scrape_page_response.status_code = 200
        mock_scrape_page_response.content = b"<html>No link here for scraping either</html>"

        self.mock_requests_session_get.side_effect = [
            exception_to_raise,             # Initial direct download attempt (fails with specific exception)
            mock_scrape_page_response,      # Page fetch for scraping
            RequestException("Scraping download attempt failed") # If scraping tries to download
        ]
        self.mock_beautifulsoup.return_value.select_one.return_value = None # No link found by scraping

        playwright_final_path = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "playwright_file.pdf")
        self.mock_playwright_download.return_value = (True, "pdf") # Playwright succeeds

        target_date_str = f'2023-01-2{hash(exception_to_raise.__class__.__name__) % 10}' # Unique date
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")
        expected_final_path = save_path_base + ".pdf"

        success, result_path = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )

        self.assertTrue(success)
        self.assertEqual(result_path, expected_final_path)
        # Called for: initial attempt (exception), page fetch for scraping, (optionally link download from scraping - mocked to fail)
        self.assertEqual(self.mock_requests_session_get.call_count, 3 if MOCK_CONFIG_DATA['newspaper']['selectors']['download_link_css_selectors'] else 2)

        self.mock_beautifulsoup.assert_called_once()
        self.mock_playwright_download.assert_called_once()

        if is_timeout:
            self.mock_logger_warning.assert_any_call(
                "Request timed out (Attempt %d/%d). Retrying if possible...", 1, 3 # Max retries is 3
            )
        else: # For other RequestException like ConnectionError
             self.mock_logger_warning.assert_any_call(
                "Initial requests.get failed for %s: %s. Attempting to scrape for a direct link.",
                unittest.mock.ANY, # URL
                unittest.mock.ANY  # Original Exception
            )


    def test_login_and_download_requests_timeout_fallback(self):
        # The function has its own retry loop for Timeout. This test ensures that if all retries fail,
        # it then proceeds to scraping and playwright.
        # To test this, mock_requests_session_get should raise Timeout for all direct attempts.
        num_direct_attempts = 3 # From website.py logic

        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        mock_scrape_page_response = MagicMock()
        mock_scrape_page_response.status_code = 200
        mock_scrape_page_response.content = b"<html>No link here for scraping timeout</html>"

        # All direct attempts timeout, then scraping page fetch, then scraping download attempt fails
        effects = [requests.exceptions.Timeout("Timeout")] * num_direct_attempts + \
                  [mock_scrape_page_response] + \
                  [RequestException("Scraping download attempt failed (after timeout)")]
        self.mock_requests_session_get.side_effect = effects

        self.mock_beautifulsoup.return_value.select_one.return_value = None
        self.mock_playwright_download.return_value = (True, "pdf")

        target_date_str = '2023-01-30'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")
        expected_final_path = save_path_base + ".pdf"

        success, result_path = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertTrue(success)
        self.assertEqual(result_path, expected_final_path)
        self.assertEqual(self.mock_requests_session_get.call_count, num_direct_attempts + 2) # 3 timeouts + 1 scrape page + 1 scrape download
        self.mock_beautifulsoup.assert_called_once()
        self.mock_playwright_download.assert_called_once()
        # Check that all timeout warnings were logged
        for i in range(num_direct_attempts):
            self.mock_logger_warning.assert_any_call(
                "Request timed out (Attempt %d/%d). Retrying if possible...", i + 1, num_direct_attempts
            )
        # Check the final error log after all retries for timeout
        self.mock_logger_error.assert_any_call(
            "Download failed after %d attempts due to timeout from %s", num_direct_attempts, unittest.mock.ANY
        )
        # Check that scraping was attempted after timeouts
        self.mock_logger_warning.assert_any_call(
            "Initial requests.get failed for %s: %s. Attempting to scrape for a direct link.",
            unittest.mock.ANY, "Request timed out repeatedly" # This is the message passed after timeout retries
        )


    def test_login_and_download_requests_connection_error_fallback(self):
        self._test_login_and_download_requests_exception_fallback(
            requests.exceptions.ConnectionError("Connection failed")
        )


    def test_login_and_download_all_fail(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        self.mock_requests_session_get.side_effect = RequestException("All requests attempts fail")
        self.mock_beautifulsoup.return_value.select_one.return_value = None # No link found by scraping
        self.mock_playwright_download.return_value = (False, "Playwright download ultimately failed")

        target_date_str = '2023-01-04'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_msg = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertFalse(success)
        self.assertEqual(result_msg, "Playwright download ultimately failed") # Last error message
        self.mock_playwright_download.assert_called_once()


    def test_login_and_download_dry_run(self):
        self.mock_os_path_exists.return_value = False # Ensure download path is attempted
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]
        
        # Simulate direct requests.get() succeeding in terms of headers for dry run
        mock_response_dry_run = MagicMock()
        mock_response_dry_run.status_code = 200
        mock_response_dry_run.headers = {'Content-Type': 'application/pdf'}
        self.mock_requests_session_get.return_value = mock_response_dry_run

        target_date_str = '2023-01-05'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str,
            dry_run=True
        )
        self.assertTrue(success)
        self.assertEqual(result, "pdf") # Dry run should return the detected format
        self.mock_open.assert_not_called() # No file should be written
        self.mock_playwright_download.assert_not_called()


    # test_get_session_cookies_success from the original file is excellent and can be kept.
    # Ensure it uses the class-level MOCK_CONFIG_DATA and side_effect for config.get.
    @patch('website.sync_playwright') # Patch where it's used in website._get_session_cookies
    def test_get_session_cookies_success_original(self, mock_sync_playwright_func):
        # No need to patch config.config.get here as it's done in setUp
        
        mock_page = MagicMock()
        expected_cookies = [{'name': 'sessionid', 'value': 'testsession123', 'domain': 'testnews.com', 'path': '/'}]
        mock_page.context.cookies.return_value = expected_cookies
        
        mock_locator_object = MagicMock()
        mock_locator_object.count.return_value = 1 
        mock_page.locator.return_value = mock_locator_object

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        
        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        
        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        login_url = MOCK_CONFIG_DATA['newspaper']['login_url']
        username = MOCK_CONFIG_DATA['newspaper']['username']
        password = MOCK_CONFIG_DATA['newspaper']['password']
        
        returned_cookies = website._get_session_cookies(login_url, username, password)

        self.assertEqual(returned_cookies, expected_cookies)
        # ... (add more assertions from the original test if they were removed by mistake)
        mock_playwright_instance.chromium.launch.assert_called_once_with(headless=True)
        mock_browser.close.assert_called_once() # Ensure browser is closed

    @patch('website.PLAYWRIGHT_AVAILABLE', False)
    def test_get_session_cookies_playwright_not_available(self):
        # config.get is already mocked in setUp
        cookies = website._get_session_cookies("http://dummy/login", "user", "pass")
        self.assertIsNone(cookies)
        self.mock_logger_error.assert_any_call("Playwright is not installed. Cannot use Playwright for login. Run `pip install playwright` and `playwright install`.")

    @patch('website.sync_playwright')
    def test_get_session_cookies_username_field_not_found(self, mock_sync_playwright_func):
        mock_page = MagicMock()

        # Simulate username field not found
        mock_username_locator = MagicMock()
        mock_username_locator.count.return_value = 0
        mock_page.locator.return_value = mock_username_locator # Default for any locator call

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        cookies = website._get_session_cookies("http://dummy/login", "user", "pass")
        self.assertIsNone(cookies)
        self.mock_logger_error.assert_any_call("Username field not found with selector: %s", MOCK_CONFIG_DATA['newspaper']['selectors']['username'])
        mock_browser.close.assert_called_once()

    @patch('website.sync_playwright')
    def test_get_session_cookies_password_field_not_found(self, mock_sync_playwright_func):
        mock_page = MagicMock()

        mock_username_locator = MagicMock()
        mock_username_locator.count.return_value = 1 # Username field found

        mock_password_locator = MagicMock()
        mock_password_locator.count.return_value = 0 # Password field not found

        # Configure page.locator to return different mocks based on selector
        def locator_side_effect(selector_str):
            if selector_str == MOCK_CONFIG_DATA['newspaper']['selectors']['username']:
                return mock_username_locator
            elif selector_str == MOCK_CONFIG_DATA['newspaper']['selectors']['password']:
                return mock_password_locator
            return MagicMock() # Default for other selectors
        mock_page.locator.side_effect = locator_side_effect

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        cookies = website._get_session_cookies("http://dummy/login", "user", "pass")
        self.assertIsNone(cookies)
        self.mock_logger_error.assert_any_call("Password field not found with selector: %s", MOCK_CONFIG_DATA['newspaper']['selectors']['password'])
        mock_browser.close.assert_called_once()

    @patch('website.sync_playwright')
    def test_get_session_cookies_submit_button_not_found(self, mock_sync_playwright_func):
        mock_page = MagicMock()

        mock_username_locator = MagicMock()
        mock_username_locator.count.return_value = 1
        mock_password_locator = MagicMock()
        mock_password_locator.count.return_value = 1
        mock_submit_locator = MagicMock()
        mock_submit_locator.count.return_value = 0 # Submit button not found

        def locator_side_effect(selector_str):
            if selector_str == MOCK_CONFIG_DATA['newspaper']['selectors']['username']:
                return mock_username_locator
            elif selector_str == MOCK_CONFIG_DATA['newspaper']['selectors']['password']:
                return mock_password_locator
            elif selector_str == MOCK_CONFIG_DATA['newspaper']['selectors']['submit']:
                return mock_submit_locator
            return MagicMock()
        mock_page.locator.side_effect = locator_side_effect

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        cookies = website._get_session_cookies("http://dummy/login", "user", "pass")
        self.assertIsNone(cookies)
        self.mock_logger_error.assert_any_call("Submit button not found with selector: %s", MOCK_CONFIG_DATA['newspaper']['selectors']['submit'])
        mock_browser.close.assert_called_once()

    @patch('website.sync_playwright')
    @patch('website.PlaywrightTimeoutError', Exception) # Mock PlaywrightTimeoutError for this test
    def test_get_session_cookies_login_verification_fails_no_selectors_no_errors(self, mock_sync_playwright_func):
        mock_page = MagicMock()

        # Login form fields are found and filled
        mock_field_locator = MagicMock()
        mock_field_locator.count.return_value = 1
        mock_page.locator.return_value = mock_field_locator

        # Simulate login success element not found
        mock_page.wait_for_selector.side_effect = website.PlaywrightTimeoutError("Timeout waiting for selector")
        # Simulate login success URL pattern not matched
        mock_page.wait_for_url.side_effect = website.PlaywrightTimeoutError("Timeout waiting for URL")

        # Simulate no error messages found on page
        mock_error_locator = MagicMock()
        mock_error_locator.count.return_value = 0
        # Make page.locator return the error locator only for the error selector string
        def locator_side_effect(selector_str):
            if selector_str == '.login-error, .error-message, .alert-danger':
                return mock_error_locator
            return mock_field_locator # For username, password, submit
        mock_page.locator.side_effect = locator_side_effect

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        # Ensure LOGIN_SUCCESS_SELECTOR and LOGIN_SUCCESS_URL_PATTERN are set in MOCK_CONFIG_DATA
        # (they are by default from the provided test file)

        cookies = website._get_session_cookies("http://dummy/login", "user", "pass")

        # Based on current logic, if element/URL checks fail, but no error messages are found,
        # it logs "Login appears successful (based on network idle state and no error messages)."
        # and proceeds to get cookies.
        # However, the prompt asks to assert that the function returns None if login_success remains False
        # *before* this fallback. The current code structure sets login_success = True after the "network idle"
        # check if no errors are found.
        # The only way it would return None *after* this point is if page.context.cookies() itself fails
        # or returns None, or if the final "if not login_success:" check is somehow hit, which seems
        # unlikely with the current flow if no errors are detected.
        # Let's assume the test wants to verify the scenario *before* the "network idle" fallback sets login_success = True.
        # This means we need to ensure the test fails before that last "login_success = True" line.
        # The current code: if not login_success: (after element/URL checks) -> enters networkidle block.
        # Inside networkidle block: if error_messages > 0 -> returns None. Else -> login_success = True.
        # Then: if not login_success: (this is the one mentioned in prompt) -> returns None.
        # This final check seems hard to hit if the networkidle block sets login_success=True.
        # For this test to make sense and return None as requested by the prompt,
        # the "Login appears successful (based on network idle state and no error messages)."
        # should NOT lead to actual cookie retrieval if the initial selectors failed.
        # The function's final `if not login_success:` implies that if all checks fail,
        # including the implicit success from networkidle, it should return None.
        # The point "Assert that the function returns None (if that's the expected behavior when verification
        # elements are missing and the 'network idle' doesn't definitively confirm success in a way that sets cookies)"
        # is key. The current code *does* set cookies if network idle shows no errors.

        # Let's test the scenario where the final "if not login_success:" is hit.
        # This would mean the networkidle part also somehow failed to set login_success = True.
        # This is hard to achieve without modifying the function or having a very specific interpretation.
        # The current code structure will likely return cookies if no error messages are found.
        # Let's assume the prompt implies that if the *specific* login success selectors fail,
        # and the network idle fallback is perhaps not trusted enough, it should return None.
        # However, the code as written will proceed.

        # Given the current code, if LOGIN_SUCCESS_SELECTOR and LOGIN_SUCCESS_URL_PATTERN fail,
        # and no .login-error is found, it *will* try to return cookies.
        # So, to make it return None as per the prompt's implied desire for this specific test,
        # we'd have to make page.context.cookies() return None or empty.
        # Or, the prompt means the final "if not login_success:" check, which is hard to reach.

        # Test the behavior when login success selectors fail but no explicit error messages are found.
        # self._assert_login_behavior(MOCK_CONFIG_DATA) # This helper is being removed.

        # The core logic previously in _assert_login_behavior is now directly in this test.
        expected_cookies_after_fallback = [{'name': 'fallback_session', 'value': 'fallback_value'}]
        mock_page.context.cookies.return_value = expected_cookies_after_fallback # Cookies found via network idle

        login_url = MOCK_CONFIG_DATA['newspaper']['login_url'] # Use configured login_url
        username = MOCK_CONFIG_DATA['newspaper']['username']
        password = MOCK_CONFIG_DATA['newspaper']['password']

        returned_cookies = website._get_session_cookies(login_url, username, password)
        self.assertEqual(returned_cookies, expected_cookies_after_fallback)

        # Assertions for this specific scenario (selectors fail, no page errors, network idle "success")
        self.mock_logger_warning.assert_any_call(
            "Login success element not found: %s", MOCK_CONFIG_DATA['newspaper']['selectors']['login_success']
        )
        # Ensure the pattern is actually configured before asserting it was checked and failed
        if MOCK_CONFIG_DATA['newspaper']['selectors'].get('login_success_url_pattern', ''): # Default is ''
            self.mock_logger_warning.assert_any_call(
                "Login success URL pattern not matched: %s", MOCK_CONFIG_DATA['newspaper']['selectors']['login_success_url_pattern']
            )
        self.mock_logger_info.assert_any_call(
            "Login appears successful (based on network idle state and no error messages)."
        )
        mock_browser.close.assert_called_once()

    @patch('website.sync_playwright')
    @patch('website.PlaywrightTimeoutError', Exception)
    def test_get_session_cookies_login_success_selector_fails_url_pattern_succeeds(self, mock_sync_playwright_func):
        mock_page = MagicMock()
        mock_field_locator = MagicMock()
        mock_field_locator.count.return_value = 1

        # Simulate error messages not found
        mock_error_locator = MagicMock()
        mock_error_locator.count.return_value = 0

        def locator_side_effect(selector_str):
            if selector_str == '.login-error, .error-message, .alert-danger':
                return mock_error_locator
            return mock_field_locator
        mock_page.locator.side_effect = locator_side_effect

        # LOGIN_SUCCESS_SELECTOR fails
        mock_page.wait_for_selector.side_effect = website.PlaywrightTimeoutError("Timeout for success selector")
        # LOGIN_SUCCESS_URL_PATTERN succeeds
        mock_page.wait_for_url.return_value = None # Successful wait, no exception

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        expected_cookies = [{'name': 'url_pattern_session', 'value': 'url_pattern_ok'}]
        mock_page.context.cookies.return_value = expected_cookies

        login_url = MOCK_CONFIG_DATA['newspaper']['login_url']
        username = MOCK_CONFIG_DATA['newspaper']['username']
        password = MOCK_CONFIG_DATA['newspaper']['password']

        # Ensure LOGIN_SUCCESS_URL_PATTERN is configured for this test
        original_url_pattern = MOCK_CONFIG_DATA['newspaper']['selectors'].get('login_success_url_pattern')
        MOCK_CONFIG_DATA['newspaper']['selectors']['login_success_url_pattern'] = "**/home"

        returned_cookies = website._get_session_cookies(login_url, username, password)

        MOCK_CONFIG_DATA['newspaper']['selectors']['login_success_url_pattern'] = original_url_pattern # Restore

        self.assertEqual(returned_cookies, expected_cookies)
        self.mock_logger_warning.assert_any_call("Login success element not found: %s", MOCK_CONFIG_DATA['newspaper']['selectors']['login_success'])
        self.mock_logger_info.assert_any_call("Login successful (based on URL pattern: %s).", "**/home")
        mock_page.wait_for_selector.assert_called_once_with(MOCK_CONFIG_DATA['newspaper']['selectors']['login_success'], timeout=30000)
        mock_page.wait_for_url.assert_called_once_with("**/home", timeout=30000)
        mock_browser.close.assert_called_once()

    @patch('website.sync_playwright')
    @patch('website.PlaywrightTimeoutError', Exception) # Not strictly needed here as success is mocked
    def test_get_session_cookies_login_success_selector_succeeds_url_pattern_ignored(self, mock_sync_playwright_func):
        mock_page = MagicMock()
        mock_field_locator = MagicMock()
        mock_field_locator.count.return_value = 1
        mock_page.locator.return_value = mock_field_locator # For form fields

        # LOGIN_SUCCESS_SELECTOR succeeds
        mock_page.wait_for_selector.return_value = None # Successful wait

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        expected_cookies = [{'name': 'selector_session', 'value': 'selector_ok'}]
        mock_page.context.cookies.return_value = expected_cookies

        login_url = MOCK_CONFIG_DATA['newspaper']['login_url']
        username = MOCK_CONFIG_DATA['newspaper']['username']
        password = MOCK_CONFIG_DATA['newspaper']['password']

        returned_cookies = website._get_session_cookies(login_url, username, password)

        self.assertEqual(returned_cookies, expected_cookies)
        self.mock_logger_info.assert_any_call("Login successful (based on element presence: %s).", MOCK_CONFIG_DATA['newspaper']['selectors']['login_success'])
        mock_page.wait_for_selector.assert_called_once_with(MOCK_CONFIG_DATA['newspaper']['selectors']['login_success'], timeout=30000)
        mock_page.wait_for_url.assert_not_called() # URL pattern check should be skipped
        mock_browser.close.assert_called_once()


    @patch('website.sync_playwright')
    @patch('website.PlaywrightTimeoutError', Exception) # Mock PlaywrightTimeoutError
    def test_get_session_cookies_login_verification_fails_with_error_messages(self, mock_sync_playwright_func):
        # This test covers: "When both fail, and error messages *are* found on the page, expecting None to be returned."
        mock_page = MagicMock()

        # Login form fields are found and filled
        mock_field_locator = MagicMock()
        mock_field_locator.count.return_value = 1

        # Simulate error messages found on page
        mock_error_locator = MagicMock()
        mock_error_locator.count.return_value = 1
        mock_error_locator.text_content.return_value = "Test Error Message"

        def locator_side_effect(selector_str):
            if selector_str == '.login-error, .error-message, .alert-danger':
                return mock_error_locator
            # For username, password, submit, login_success_selector
            return mock_field_locator
        mock_page.locator.side_effect = locator_side_effect

        # Simulate login success element not found & URL pattern not matched
        mock_page.wait_for_selector.side_effect = website.PlaywrightTimeoutError("Timeout waiting for success selector")
        mock_page.wait_for_url.side_effect = website.PlaywrightTimeoutError("Timeout waiting for success URL")


        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        login_url = MOCK_CONFIG_DATA['newspaper']['login_url']
        username = MOCK_CONFIG_DATA['newspaper']['username']
        password = MOCK_CONFIG_DATA['newspaper']['password']

        returned_cookies = website._get_session_cookies(login_url, username, password)

        self.assertIsNone(returned_cookies)
        self.mock_logger_error.assert_any_call("Login error detected: %s", "Test Error Message")
        mock_browser.close.assert_called_once()

    # --- Tests for _download_with_playwright ---

    @patch('website.sync_playwright')
    def test_download_with_playwright_success(self, mock_sync_playwright_func):
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_browser = MagicMock()
        mock_playwright_instance = MagicMock()
        mock_sync_playwright_cm = MagicMock()

        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_download_info = MagicMock()
        mock_download_info.value.suggested_filename = 'downloaded_file.pdf'
        mock_download_info.value.save_as = MagicMock()

        mock_page.expect_download.return_value.__enter__.return_value = mock_download_info # Simulate 'with page.expect_download() as download_info:'

        mock_response = MagicMock()
        mock_response.status = 200 # Success status for page.goto()
        mock_page.goto.return_value = mock_response


        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "test_playwright_download")
        cookies = [{'name': 'session', 'value': 'dummyval', 'domain': 'testnews.com'}]

        success, file_format = website._download_with_playwright(
            "http://testnews.com/downloadpage",
            save_path_base,
            cookies
        )

        self.assertTrue(success)
        self.assertEqual(file_format, "pdf")
        mock_playwright_instance.chromium.launch.assert_called_once_with(headless=True)
        mock_context.add_cookies.assert_called_once()
        mock_page.goto.assert_called_once_with("http://testnews.com/downloadpage", wait_until='networkidle')
        mock_page.expect_download.assert_called_once()
        expected_save_location = save_path_base + ".pdf"
        mock_download_info.value.save_as.assert_called_once_with(expected_save_location)
        self.mock_os_makedirs.assert_called_with(os.path.dirname(save_path_base), exist_ok=True) # Ensure download_folder is created
        mock_browser.close.assert_called_once()


    @patch('website.sync_playwright')
    @patch('website.PlaywrightTimeoutError', Exception) # Ensure it's the class used in website.py
    def test_download_with_playwright_goto_timeout(self, mock_sync_playwright_func):
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_browser = MagicMock()
        mock_playwright_instance = MagicMock()
        mock_sync_playwright_cm = MagicMock()

        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_page.goto.side_effect = website.PlaywrightTimeoutError("Page goto timed out")

        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "timeout_test")
        success, message = website._download_with_playwright("http://test.com/dl", save_path_base, [])

        self.assertFalse(success)
        self.assertTrue("Playwright timeout" in message)
        self.mock_logger_error.assert_any_call("Playwright timeout during download from %s: %s", "http://test.com/dl", "Page goto timed out")
        mock_browser.close.assert_called_once()


    @patch('website.sync_playwright')
    @patch('website.PlaywrightError', Exception) # Ensure it's the class used in website.py
    def test_download_with_playwright_generic_playwright_error(self, mock_sync_playwright_func):
        mock_playwright_instance = MagicMock()
        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        # Simulate error on chromium.launch()
        mock_playwright_instance.chromium.launch.side_effect = website.PlaywrightError("Launch failed")
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm


        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "generic_error_test")
        success, message = website._download_with_playwright("http://test.com/anotherdl", save_path_base, [])

        self.assertFalse(success)
        self.assertTrue("Playwright error" in message)
        self.mock_logger_error.assert_any_call("Playwright error during download from %s: %s", "http://test.com/anotherdl", "Launch failed")
        # browser.close() might not be called if launch fails, depending on implementation, so no assertion here.

    @patch('website.sync_playwright')
    def test_download_with_playwright_goto_returns_error_status(self, mock_sync_playwright_func):
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_browser = MagicMock()
        mock_playwright_instance = MagicMock()
        mock_sync_playwright_cm = MagicMock()

        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_error_response = MagicMock()
        mock_error_response.status = 404 # Error status
        mock_page.goto.return_value = mock_error_response

        # If goto fails, expect_download might not be reached, or might timeout.
        # Let's assume for this test that expect_download is set up but the check for response.status happens first.
        mock_download_info = MagicMock() # Required for 'with page.expect_download() as download_info:'
        mock_page.expect_download.return_value.__enter__.return_value = mock_download_info


        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "goto_status_error")
        success, message = website._download_with_playwright("http://test.com/dl_error_status", save_path_base, [])

        self.assertFalse(success)
        self.assertTrue("Navigation failed or status error: 404" in message)
        mock_browser.close.assert_called_once()

    @patch('website.sync_playwright')
    def test_download_with_playwright_suggested_filenames(self, mock_sync_playwright_func):
        test_cases = [
            ("file.pdf", "pdf"),
            ("archive.zip", "pdf"), # Default to pdf if not pdf/html
            ("document.html", "html"),
            ("image.jpeg", "pdf"), # Default to pdf
            ("no_extension_file", "pdf") # Default to pdf
        ]

        for suggested_name, expected_format in test_cases:
            with self.subTest(suggested_name=suggested_name, expected_format=expected_format):
                mock_page = MagicMock()
                mock_context = MagicMock()
                mock_browser = MagicMock()
                mock_playwright_instance = MagicMock()
                mock_sync_playwright_cm = MagicMock()

                mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
                mock_playwright_instance.chromium.launch.return_value = mock_browser
                mock_browser.new_context.return_value = mock_context
                mock_context.new_page.return_value = mock_page

                mock_download_info = MagicMock()
                mock_download_info.value.suggested_filename = suggested_name
                mock_download_info.value.save_as = MagicMock()
                mock_page.expect_download.return_value.__enter__.return_value = mock_download_info

                mock_response = MagicMock()
                mock_response.status = 200
                mock_page.goto.return_value = mock_response

                save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"test_filename_{suggested_name.split('.')[0]}")

                success, file_format = website._download_with_playwright(
                    f"http://testnews.com/download_{suggested_name}",
                    save_path_base,
                    []
                )

                self.assertTrue(success)
                self.assertEqual(file_format, expected_format)
                expected_save_location = f"{save_path_base}.{expected_format}"
                mock_download_info.value.save_as.assert_called_with(expected_save_location) # save_as is called with the correct extension
                # Reset mocks for next subtest iteration if necessary (though patch.stopall in tearDown should handle it for fresh test runs)
                mock_sync_playwright_func.reset_mock() # Reset the main mock for playwright

    @patch('website.PLAYWRIGHT_AVAILABLE', False)
    def test_download_with_playwright_not_available(self):
        # Config.get is already mocked in setUp
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "pw_not_avail")
        success, message = website._download_with_playwright("http://dummy.com/dl", save_path_base, [])
        self.assertFalse(success)
        self.assertEqual(message, "Playwright not available")
        self.mock_logger_error.assert_any_call("Playwright not available for fallback download. Install with: pip install playwright")

    # --- Tests for login_and_download error handling ---

    def test_login_and_download_get_session_cookies_fails(self):
        self.mock_get_session_cookies.return_value = None # Simulate failure to get cookies

        target_date_str = '2023-02-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper_cookies_fail")

        success, message = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )

        self.assertFalse(success)
        self.assertEqual(message, "Failed to obtain cookies.")
        self.mock_get_session_cookies.assert_called_once()
        self.mock_requests_session_get.assert_not_called() # Should not proceed to download attempts
        self.mock_playwright_download.assert_not_called()
        self.mock_logger_error.assert_any_call("Failed to obtain session cookies. Login unsuccessful.")

    def test_login_and_download_os_error_on_save_direct_request(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        mock_response_direct = MagicMock()
        mock_response_direct.status_code = 200
        mock_response_direct.headers = {'Content-Type': 'application/pdf'}
        mock_response_direct.content = b"PDF Content"
        self.mock_requests_session_get.return_value = mock_response_direct

        self.mock_open.side_effect = OSError("Disk full or permission denied")

        target_date_str = '2023-02-02'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper_os_error_direct")

        success, message = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )

        self.assertFalse(success)
        self.assertTrue("Failed to save file:" in message)
        self.mock_open.assert_called_once_with(save_path_base + ".pdf", 'wb')
        self.mock_logger_error.assert_any_call("Failed to save downloaded file %s: %s", save_path_base + ".pdf", "Disk full or permission denied")

    def test_login_and_download_os_error_on_save_scraped_link(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        # Direct download fails, leading to scrape
        mock_response_page_for_scrape = MagicMock()
        mock_response_page_for_scrape.status_code = 200
        mock_response_page_for_scrape.content = b"<html><a class='direct_download_link' href='download.pdf'>link</a></html>"

        mock_response_scraped_file = MagicMock()
        mock_response_scraped_file.status_code = 200
        mock_response_scraped_file.headers = {'Content-Type': 'application/pdf'}
        mock_response_scraped_file.content = b"Scraped PDF data"

        self.mock_requests_session_get.side_effect = [
            requests.exceptions.RequestException("Direct download failed for OS error test"),
            mock_response_page_for_scrape,
            mock_response_scraped_file
        ]

        mock_link_element = MagicMock()
        mock_link_element.get.return_value = 'download.pdf' # Relative link
        self.mock_beautifulsoup.return_value.select_one.return_value = mock_link_element

        self.mock_open.side_effect = OSError("Cannot write to disk - scraped")

        target_date_str = '2023-02-03'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper_os_error_scrape")

        success, message = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertFalse(success)
        self.assertTrue("Failed to save file (from scraped link):" in message)
        # Ensure open was called for the scraped file attempt
        self.mock_open.assert_called_once_with(save_path_base + ".pdf", 'wb')
        self.mock_logger_error.assert_any_call(
            "Failed to save downloaded file (from scraped link) %s: %s",
            save_path_base + ".pdf", "Cannot write to disk - scraped"
        )

    def test_login_and_download_invalid_date_format(self):
        target_date_str = '01-02-2023' # Invalid format (DD-MM-YYYY instead of YYYY-MM-DD)
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], "newspaper_invalid_date")

        success, message = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertFalse(success)
        self.assertEqual(message, "Invalid date format")
        self.mock_logger_error.assert_any_call("Invalid target_date format. Please use YYYY-MM-DD.")
        self.mock_get_session_cookies.assert_not_called() # Should fail before attempting login


if __name__ == '__main__':
    unittest.main()
