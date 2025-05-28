import unittest
from unittest.mock import patch, MagicMock 
import os
import config # To allow influencing config for tests
from website import login_and_download, _get_session_cookies # Import functions to test

# Test configuration data
MOCK_CONFIG_DATA = {
    'newspaper': {
        'url': 'http://testnews.com',
        'login_url': 'http://testnews.com/login',
        'username': 'testuser',
        'password': 'testpassword',
        'selectors': {
            'username': '#user',
            'password': '#pass',
            'submit': '#submit',
            'login_success': '#profile',
        }
    },
    'paths': {
        'download_dir': 'test_downloads_dir' # Use a distinct name for clarity
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
        # If a key is not in MOCK_CONFIG_DATA, return the default.
        # This is important if the code being tested calls config.get for other keys.
        return default

class TestWebsite(unittest.TestCase):

    # Patch 'config.config.get' - this is where it's looked up when website.py calls it.
    @patch('config.config.get') 
    @patch('os.makedirs')
    @patch('os.path.exists')
    @patch('website._get_session_cookies') # Patch to check if it's called
    def test_login_and_download_file_exists(self, mock_get_cookies, mock_os_exists, mock_os_makedirs, mock_config_get_method):
        # Setup the mock for config.config.get
        mock_config_get_method.side_effect = mock_config_get_side_effect
        
        # Configure os.path.exists:
        # - Return True for .pdf, False for .html to simulate PDF existing.
        # - The function login_and_download checks for extensions in ['pdf', 'html'].
        def os_exists_side_effect(path):
            if path.endswith('.pdf'):
                return True # Simulate PDF exists
            elif path.endswith('.html'):
                return False # Simulate HTML does not exist
            # Important: os.path.dirname(save_path) is also checked by os.path.exists 
            # in some Python versions when os.makedirs(..., exist_ok=True) is called.
            # So, we need to handle the directory path as well.
            # For this test, assume the directory check part of makedirs is not problematic
            # or that the mock_os_makedirs itself handles it.
            # If tests fail due to this, we might need:
            # if path == MOCK_CONFIG_DATA['paths']['download_dir']: return True 
            return False 
        mock_os_exists.side_effect = os_exists_side_effect

        target_date_str = '2023-01-01'
        
        download_dir = MOCK_CONFIG_DATA['paths']['download_dir']
        file_base_name = f"{target_date_str}_newspaper"
        # This is the 'save_path' argument login_and_download expects (path without extension)
        save_path_argument = os.path.join(download_dir, file_base_name)

        # Call the function under test
        success, file_ext = login_and_download(
            base_url=MOCK_CONFIG_DATA['newspaper']['url'], # Dummy, not used if file exists
            username=MOCK_CONFIG_DATA['newspaper']['username'], # Dummy
            password=MOCK_CONFIG_DATA['newspaper']['password'], # Dummy
            save_path=save_path_argument, 
            target_date=target_date_str,
            dry_run=False,
            force_download=False
        )

        # Assertions
        self.assertTrue(success, "Function should return True when file exists.")
        self.assertEqual(file_ext, 'pdf', "File extension should be 'pdf'.")
        
        # Assert that os.makedirs was called for the directory part of save_path_argument
        # login_and_download has: os.makedirs(os.path.dirname(save_path), exist_ok=True)
        mock_os_makedirs.assert_called_once_with(download_dir, exist_ok=True)

        # Assert that os.path.exists was called with the .pdf path
        pdf_check_path = save_path_argument + ".pdf"
        html_check_path = save_path_argument + ".html"
        
        # It should check for PDF first. Since our mock returns True for PDF,
        # it should find it and not proceed to check for HTML.
        calls_to_os_exists = mock_os_exists.call_args_list
        
        self.assertIn(unittest.mock.call(pdf_check_path), calls_to_os_exists,
                      "os.path.exists should have been called for the .pdf file.")
        
        # Verify that .html was NOT checked because .pdf was found.
        # This depends on the loop: for ext in ['pdf', 'html']
        # If the first iteration (pdf) returns True, the function returns early.
        self.assertNotIn(unittest.mock.call(html_check_path), calls_to_os_exists,
                         "os.path.exists should NOT have been called for .html if .pdf was found first.")

        # Assert that login (_get_session_cookies) was NOT called
        mock_get_cookies.assert_not_called()

    @patch('config.config.get')
    @patch('website.sync_playwright') # Patch where it's used in website.py
    def test_get_session_cookies_success(self, mock_sync_playwright, mock_config_get_method):
        # Setup config mock
        mock_config_get_method.side_effect = mock_config_get_side_effect

        # Configure Playwright mocks
        mock_page = MagicMock()
        # Define the expected cookies that should be returned by page.context.cookies()
        expected_cookies = [{'name': 'sessionid', 'value': 'testsession123', 'domain': 'testnews.com', 'path': '/'}]
        mock_page.context.cookies.return_value = expected_cookies
        
        # Mock for page.locator(SELECTOR).count()
        # page.locator(ANY_SELECTOR) returns mock_locator_object
        mock_locator_object = MagicMock()
        mock_locator_object.count.return_value = 1 # Simulate element is found
        mock_page.locator.return_value = mock_locator_object

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        
        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        
        # Setup the context manager mock for sync_playwright
        # sync_playwright() as p: ... -> p is mock_playwright_instance
        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_instance

        # Call the function under test using values from MOCK_CONFIG_DATA
        login_url = MOCK_CONFIG_DATA['newspaper']['login_url']
        username = MOCK_CONFIG_DATA['newspaper']['username']
        password = MOCK_CONFIG_DATA['newspaper']['password']
        
        # Selectors from MOCK_CONFIG_DATA - used in assertions for fill/click
        username_selector = MOCK_CONFIG_DATA['newspaper']['selectors']['username']
        password_selector = MOCK_CONFIG_DATA['newspaper']['selectors']['password']
        submit_selector = MOCK_CONFIG_DATA['newspaper']['selectors']['submit']
        login_success_selector = MOCK_CONFIG_DATA['newspaper']['selectors']['login_success']

        returned_cookies = _get_session_cookies(login_url, username, password)

        # Assertions
        self.assertEqual(returned_cookies, expected_cookies, "Returned cookies should match the expected cookies.")
        
        # Assert Playwright calls
        mock_sync_playwright.assert_called_once() 
        mock_playwright_instance.chromium.launch.assert_called_once_with(headless=True)
        mock_browser.new_page.assert_called_once()
        
        mock_page.goto.assert_called_once_with(login_url, wait_until='networkidle')
        
        # Check that page.locator(SELECTOR) was called for each specific selector
        # And that mock_locator_object.count() was called thereafter
        mock_page.locator.assert_any_call(username_selector)
        mock_page.locator.assert_any_call(password_selector)
        mock_page.locator.assert_any_call(submit_selector)
        
        # mock_locator_object.count is called after each page.locator call in the actual code
        self.assertGreaterEqual(mock_locator_object.count.call_count, 3, "locator.count should be called for username, password, and submit")

        # Check page.fill(SELECTOR, VALUE) calls - this matches the code in website.py
        mock_page.fill.assert_any_call(username_selector, username)
        mock_page.fill.assert_any_call(password_selector, password)

        # Check page.click(SELECTOR) call - this matches the code in website.py
        mock_page.click.assert_called_once_with(submit_selector)
        
        # Check wait_for_selector for login success
        mock_page.wait_for_selector.assert_called_once_with(login_success_selector, timeout=30000)
        
        # Check cookies call
        mock_page.context.cookies.assert_called_once()
        
        # browser.close() is handled by the context manager (__exit__)
        mock_sync_playwright.return_value.__exit__.assert_called_once()

if __name__ == '__main__':
    unittest.main()
