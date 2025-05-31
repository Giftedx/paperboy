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

    def test_login_and_download_direct_requests_success_html(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/html; charset=utf-8'}
        mock_response.content = b"<html>Fake HTML data</html>"
        self.mock_requests_session_get.return_value = mock_response

        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_path = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertTrue(success)
        expected_path = save_path_base + ".html"
        self.assertEqual(result_path, expected_path)
        self.mock_requests_session_get.assert_called_once()
        self.mock_open.assert_called_once_with(expected_path, 'wb')

    @patch('website.time.sleep', return_value=None) # Mock time.sleep to avoid actual delays
    def test_login_and_download_requests_timeout_with_retries(self, mock_sleep):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        # Simulate timeout for all requests.get attempts
        self.mock_requests_session_get.side_effect = requests.exceptions.Timeout("Timeout")

        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        # As requests attempts fail, it will try scraping, which also uses requests.get
        # Then it will try Playwright fallback.
        self.mock_beautifulsoup.return_value.select_one.return_value = None # Scraping finds no link
        self.mock_playwright_download.return_value = (False, "Playwright failed too") # Playwright also fails

        success, result_msg = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )

        self.assertFalse(success)
        self.assertEqual(result_msg, "Playwright failed too") # Last error after all fallbacks
        # requests.Session().get is called:
        # 3 times for direct download (retries)
        # 1 time for scraping the page
        self.assertEqual(self.mock_requests_session_get.call_count, 3 + 1) # 3 for initial attempts, 1 for scraping page
        self.assertEqual(mock_sleep.call_count, 2) # Should sleep twice before giving up on direct download
        self.mock_beautifulsoup.assert_called_once() # Scraping was attempted
        self.mock_playwright_download.assert_called_once() # Playwright fallback was attempted

    def test_login_and_download_requests_http_error(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        mock_response = MagicMock()
        mock_response.status_code = 404 # HTTP Not Found
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
        self.mock_requests_session_get.return_value = mock_response

        # Assume scraping also fails or finds no link, and Playwright also fails
        self.mock_beautifulsoup.return_value.select_one.return_value = None
        self.mock_playwright_download.return_value = (False, "Playwright failed")

        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_msg = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertFalse(success)
        self.assertEqual(result_msg, "Playwright failed") # Error from the last fallback
        # requests.Session().get is called for direct download, then for scraping page
        # The first call raises HTTPError, so it won't retry for direct download.
        # It then tries to GET the same URL for scraping.
        self.assertEqual(self.mock_requests_session_get.call_count, 2)
        self.mock_beautifulsoup.assert_called_once()
        self.mock_playwright_download.assert_called_once()

    def test_login_and_download_scrape_link_download_fails(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        mock_response_page = MagicMock() # For scraping
        mock_response_page.status_code = 200
        mock_response_page.content = b"<html><a class='direct_download_link' href='download.pdf'>link</a></html>"

        # Initial direct download fails, page for scraping is fetched successfully, then download from scraped link fails
        self.mock_requests_session_get.side_effect = [
            RequestException("Direct download failed"), # Initial attempt
            mock_response_page,                     # Fetching page for scraping
            RequestException("Scraped link download failed") # Downloading scraped link
        ]

        mock_link_element = MagicMock()
        mock_link_element.get.return_value = 'download.pdf'
        self.mock_beautifulsoup.return_value.select_one.return_value = mock_link_element

        # Assume Playwright also fails if requests scraping fails
        self.mock_playwright_download.return_value = (False, "Playwright failed after scrape fail")

        target_date_str = '2023-01-02'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_msg = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertFalse(success)
        self.assertEqual(result_msg, "Playwright failed after scrape fail")
        self.assertEqual(self.mock_requests_session_get.call_count, 3) # Direct (fail), scrape page (ok), scrape download (fail)
        self.mock_beautifulsoup.assert_called_once()
        self.mock_playwright_download.assert_called_once() # Playwright fallback attempted

    def test_login_and_download_playwright_fallback_fails(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]
        self.mock_requests_session_get.side_effect = RequestException("Requests totally failed") # All requests attempts fail
        self.mock_beautifulsoup.return_value.select_one.return_value = None # No link found
        self.mock_playwright_download.return_value = (False, "Simulated Playwright Failure") # Playwright download fails

        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_msg = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertFalse(success)
        self.assertEqual(result_msg, "Simulated Playwright Failure")
        self.mock_playwright_download.assert_called_once()

    @patch('website.PLAYWRIGHT_AVAILABLE', False)
    def test_login_and_download_playwright_fallback_not_available(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]
        # All requests attempts fail
        self.mock_requests_session_get.side_effect = RequestException("Requests failed, Playwright N/A")
        self.mock_beautifulsoup.return_value.select_one.return_value = None # Scraping finds no link

        # _download_with_playwright should not be called.
        # The function should return the error from the requests/scraping phase.

        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_msg = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertFalse(success)
        # The error message comes from the except block for RequestException in login_and_download
        # after requests and scraping fail, and Playwright is found to be unavailable.
        self.assertIn("Request error: Requests failed, Playwright N/A", result_msg)
        self.assertIn("Playwright fallback unavailable", result_msg)
        self.mock_playwright_download.assert_not_called()

    def test_login_and_download_file_saving_error(self):
        self.mock_os_path_exists.return_value = False
        self.mock_get_session_cookies.return_value = [{'name': 'session', 'value': 'dummy'}]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/pdf'}
        mock_response.content = b"PDF data"
        self.mock_requests_session_get.return_value = mock_response

        self.mock_open.side_effect = OSError("Failed to write file") # Simulate file saving error

        target_date_str = '2023-01-01'
        save_path_base = os.path.join(MOCK_CONFIG_DATA['paths']['download_dir'], f"{target_date_str}_newspaper")

        success, result_msg = website.login_and_download(
            base_url='http://testnews.com', username='u', password='p',
            save_path=save_path_base, target_date=target_date_str
        )
        self.assertFalse(success)
        self.assertEqual(result_msg, "Failed to save file: Failed to write file")
        self.mock_open.assert_called_once_with(save_path_base + ".pdf", 'wb')


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
    @patch('website.PlaywrightTimeoutError', Exception) # Mock PlaywrightTimeoutError
    def test_get_session_cookies_login_error_message_detected(self, mock_sync_playwright_func):
        mock_page = MagicMock()

        mock_field_locator = MagicMock() # For username, password, submit
        mock_field_locator.count.return_value = 1

        mock_error_locator = MagicMock()
        mock_error_locator.count.return_value = 1 # Error message found
        mock_error_locator.text_content.return_value = "Invalid credentials"

        def locator_side_effect(selector_str):
            if selector_str == MOCK_CONFIG_DATA['newspaper']['selectors']['username'] or \
               selector_str == MOCK_CONFIG_DATA['newspaper']['selectors']['password'] or \
               selector_str == MOCK_CONFIG_DATA['newspaper']['selectors']['submit']:
                return mock_field_locator
            elif selector_str == '.login-error, .error-message, .alert-danger':
                return mock_error_locator
            return MagicMock()
        mock_page.locator.side_effect = locator_side_effect

        mock_page.wait_for_selector.side_effect = website.PlaywrightTimeoutError("Timeout on success selector")
        mock_page.wait_for_url.side_effect = website.PlaywrightTimeoutError("Timeout on success URL")

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        mock_sync_playwright_cm = MagicMock()
        mock_sync_playwright_cm.__enter__.return_value = mock_playwright_instance
        mock_sync_playwright_func.return_value = mock_sync_playwright_cm

        cookies = website._get_session_cookies("http://dummy/login", "user", "pass")
        self.assertIsNone(cookies)
        self.mock_logger_error.assert_any_call("Login error detected: %s", "Invalid credentials")
        mock_browser.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
