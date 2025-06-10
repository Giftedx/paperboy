#!/usr/bin/env python3
"""
Tests for the thumbnail generation functionality in thumbnail.py.
"""

import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys
from pathlib import Path
import logging # Import logging to control it during tests

# Add parent directory to path to import thumbnail module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import the module to be tested and its components
import thumbnail # This now imports the refactored thumbnail.py

class TestThumbnailGeneration(unittest.TestCase):
    """Test cases for thumbnail generation."""

    def setUp(self):
        # Default config for thumbnail dimensions for tests
        self.test_width = thumbnail.THUMBNAIL_WIDTH
        self.test_height = thumbnail.THUMBNAIL_HEIGHT
        self.test_format = thumbnail.THUMBNAIL_FORMAT
        self.test_quality = thumbnail.THUMBNAIL_QUALITY
        
        self.mock_pil_image = MagicMock(spec=thumbnail.Image) 
        self.mock_pil_image.mode = 'RGB' 

        # Suppress most logging during tests, enable per test if needed
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET) # Re-enable logging

    # --- Tests for _create_thumbnail_pymupdf ---
    @patch('thumbnail.fitz.open')
    @patch('thumbnail.Image.frombytes') # Mocking PIL.Image.frombytes
    @patch('thumbnail.os.makedirs')
    def test_pymupdf_success(self, mock_makedirs, mock_image_frombytes, mock_fitz_open):
        """Test successful PDF thumbnail creation with PyMuPDF."""
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("PyMuPDF or Pillow not available for this test.")

        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pixmap = MagicMock()
        mock_pixmap.width = 100
        mock_pixmap.height = 150
        mock_pixmap.samples = b"rgb_data"

        mock_fitz_open.return_value = mock_doc 
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap
        mock_image_frombytes.return_value = self.mock_pil_image

        result = thumbnail._create_thumbnail_pymupdf("dummy.pdf", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        
        self.assertTrue(result)
        mock_fitz_open.assert_called_once_with("dummy.pdf")
        mock_doc.load_page.assert_called_once_with(0)
        mock_page.get_pixmap.assert_called_once()
        mock_image_frombytes.assert_called_once_with("RGB", [100, 150], b"rgb_data")
        self.mock_pil_image.thumbnail.assert_called_once_with((self.test_width, self.test_height))
        mock_makedirs.assert_called_once_with(os.path.dirname("out.jpg"), exist_ok=True)
        self.mock_pil_image.save.assert_called_once_with("out.jpg", self.test_format, quality=self.test_quality)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    def test_pymupdf_no_pages(self, mock_fitz_open):
        """Test PyMuPDF handling of PDF with no pages."""
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("PyMuPDF or Pillow not available.")

        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 0
        
        result = thumbnail._create_thumbnail_pymupdf("dummy.pdf", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    def test_pymupdf_load_page_error(self, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE: self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.side_effect = Exception("Load page failed")
        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    def test_pymupdf_get_pixmap_error(self, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE: self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc, mock_page = MagicMock(), MagicMock()
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.side_effect = Exception("Pixmap failed")
        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    @patch('thumbnail.Image.frombytes', side_effect=ValueError("Bad data"))
    def test_pymupdf_image_frombytes_error(self, mock_frombytes, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE: self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc, mock_page, mock_pixmap = MagicMock(), MagicMock(), MagicMock()
        mock_pixmap.width, mock_pixmap.height, mock_pixmap.samples = 10, 10, b"dummy"
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap
        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    @patch('thumbnail.Image.frombytes')
    def test_pymupdf_image_save_oserror(self, mock_frombytes, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE: self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc, mock_page, mock_pixmap = MagicMock(), MagicMock(), MagicMock()
        mock_pil_image_instance = MagicMock() # Instance returned by frombytes
        mock_pil_image_instance.save.side_effect = OSError("Cannot save")

        mock_pixmap.width, mock_pixmap.height, mock_pixmap.samples = 10, 10, b"dummy"
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap
        mock_frombytes.return_value = mock_pil_image_instance # mock_pil_image is class, need instance

        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    @patch('thumbnail.Image.frombytes')
    @patch('thumbnail.os.makedirs') # Ensure makedirs is also mocked
    def test_pymupdf_rgba_to_rgb_conversion(self, mock_makedirs, mock_frombytes, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE: self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc, mock_page, mock_pixmap = MagicMock(), MagicMock(), MagicMock()

        # Simulate RGBA image from PyMuPDF/Pillow interaction
        mock_rgba_image = MagicMock()
        mock_rgba_image.mode = 'RGBA' # Critical for this test
        mock_rgb_image = MagicMock()
        mock_rgb_image.mode = 'RGB'
        mock_rgba_image.convert.return_value = mock_rgb_image

        mock_pixmap.width, mock_pixmap.height, mock_pixmap.samples = 10, 10, b"rgba_data" # Data itself doesn't matter for mode
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap
        mock_frombytes.return_value = mock_rgba_image # Pillow interprets data as RGBA

        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", 100, 100, "JPEG", 80)

        self.assertTrue(result)
        mock_rgba_image.convert.assert_called_once_with('RGB')
        mock_rgb_image.save.assert_called_once_with("o.jpg", "JPEG", quality=80)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    def test_pymupdf_doc_close_error_does_not_mask_original(self, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE: self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.side_effect = Exception("Initial error") # Original error
        mock_doc.close.side_effect = Exception("Close error") # Error in finally

        with self.assertLogs(thumbnail.logger, level='ERROR') as log_watcher:
            result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", 100, 100, "JPEG", 80)

        self.assertFalse(result)
        # Check that both errors were logged, or at least the initial one wasn't lost
        initial_error_logged = any("Initial error" in record.getMessage() for record in log_watcher.records)
        close_error_logged = any("Error closing PDF document" in record.getMessage() and "Close error" in record.getMessage() for record in log_watcher.records)
        self.assertTrue(initial_error_logged, "The initial error was not logged.")
        self.assertTrue(close_error_logged, "The doc.close() error was not logged.")


    @patch('thumbnail.PIL_AVAILABLE', False) # Mock PIL_AVAILABLE at the module level for this test
    @patch('thumbnail.fitz.open') # Still need to mock fitz so it doesn't try to run
    def test_pymupdf_pil_not_available(self, mock_fitz_open_pil_false):
        # This test checks the PIL_AVAILABLE check *inside* _create_thumbnail_pymupdf
        if not thumbnail.PYMUPDF_AVAILABLE: self.skipTest("PyMuPDF not available.") # Pre-condition for this specific test path

        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pixmap = MagicMock()
        mock_pixmap.width = 100; mock_pixmap.height = 150; mock_pixmap.samples = b"rgb_data"
        mock_fitz_open_pil_false.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap

        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_fitz_open_pil_false.assert_called_once() # Ensure fitz part ran up to PIL check
        # mock_doc.close should still be called in finally
        mock_doc.close.assert_called_once()


    @patch('thumbnail.fitz.open', side_effect=Exception("Fitz Error"))
    def test_pymupdf_fitz_open_error(self, mock_fitz_open):
        """Test PyMuPDF error during fitz.open()."""
        # This test is slightly redundant if PYMUPDF_AVAILABLE is false due to fitz not importing,
        # but good to have if fitz imports but open() fails for other reasons.
        if not thumbnail.PYMUPDF_AVAILABLE: # Check if fitz itself is mocked away by unavailability
             # If fitz cannot be imported, PYMUPDF_AVAILABLE will be False,
             # and _create_thumbnail_pymupdf might not even be called by the orchestrator.
             # However, this test targets _create_thumbnail_pymupdf directly.
             # We assume for this unit test that PYMUPDF_AVAILABLE was True for it to be called.
             pass # Allow test to run if fitz is notionally "available" but open fails

        # If PIL is also unavailable, the orchestrator might not call this.
        # But we are unit testing _create_thumbnail_pymupdf.
        if not thumbnail.PIL_AVAILABLE:
            self.skipTest("Pillow not available, though test focuses on fitz.open error.")

        result = thumbnail._create_thumbnail_pymupdf("dummy.pdf", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        # mock_fitz_open was called and raised an error. No doc.close() to assert.

    # --- Tests for _create_thumbnail_pdf2image ---

    def _test_pdf2image_specific_errors(self, error_to_raise, error_message_snippet):
        if not thumbnail.PDF2IMAGE_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("pdf2image or Pillow not available.")

        with patch('thumbnail.convert_from_path', side_effect=error_to_raise(error_message_snippet)) as mock_convert:
            result = thumbnail._create_thumbnail_pdf2image("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
            self.assertFalse(result)
            mock_convert.assert_called_once()
            # Check log for specific error message if needed, e.g.
            # self.mock_logger_error.assert_any_call(unittest.mock.ANY, "d.pdf", error_message_snippet)

    def test_pdf2image_pdf_page_count_error(self):
        self._test_pdf2image_specific_errors(thumbnail.PDFPageCountError, "Page count error")

    def test_pdf2image_pdf_syntax_error(self):
        self._test_pdf2image_specific_errors(thumbnail.PDFSyntaxError, "Syntax error")

    @patch('thumbnail.convert_from_path')
    def test_pdf2image_unidentified_image_error(self, mock_convert_from_path):
        if not thumbnail.PDF2IMAGE_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("pdf2image or Pillow not available.")

        mock_pil_image_instance = MagicMock()
        mock_pil_image_instance.thumbnail.side_effect = thumbnail.UnidentifiedImageError("Cannot identify")
        mock_convert_from_path.return_value = [mock_pil_image_instance] # convert_from_path returns a list of images

        result = thumbnail._create_thumbnail_pdf2image("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_pil_image_instance.thumbnail.assert_called_once() # Error happens during thumbnail
        # Or if error is on save:
        # mock_pil_image_instance.save.side_effect = thumbnail.UnidentifiedImageError("Cannot identify")
        # ... then assert save was called. For now, testing on thumbnail call.

    @patch('thumbnail.convert_from_path')
    def test_pdf2image_ioerror_on_save(self, mock_convert_from_path):
        if not thumbnail.PDF2IMAGE_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("pdf2image or Pillow not available.")

        mock_pil_image_instance = MagicMock()
        mock_pil_image_instance.save.side_effect = IOError("Disk full")
        mock_convert_from_path.return_value = [mock_pil_image_instance]

        result = thumbnail._create_thumbnail_pdf2image("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_pil_image_instance.save.assert_called_once()

    @patch('thumbnail.convert_from_path')
    @patch('thumbnail.os.makedirs')
    def test_pdf2image_rgba_to_rgb_conversion(self, mock_makedirs, mock_convert_from_path):
        if not thumbnail.PDF2IMAGE_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("pdf2image or Pillow not available.")

        mock_rgba_image = MagicMock()
        mock_rgba_image.mode = 'RGBA'
        mock_rgb_image = MagicMock()
        mock_rgb_image.mode = 'RGB'
        mock_rgba_image.convert.return_value = mock_rgb_image

        mock_convert_from_path.return_value = [mock_rgba_image] # pdf2image returns a list

        result = thumbnail._create_thumbnail_pdf2image("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertTrue(result)
        mock_rgba_image.convert.assert_called_once_with('RGB')
        mock_rgb_image.save.assert_called_once_with("o.jpg", "JPEG", quality=80)

    @patch('thumbnail.PIL_AVAILABLE', False)
    @patch('thumbnail.convert_from_path') # Mock to avoid running it
    def test_pdf2image_pil_not_available(self, mock_convert_pil_false):
        if not thumbnail.PDF2IMAGE_AVAILABLE: self.skipTest("pdf2image not available.")

        # Simulate convert_from_path returning something, to reach the PIL_AVAILABLE check
        mock_pil_image_dummy = MagicMock()
        mock_convert_pil_false.return_value = [mock_pil_image_dummy]

        result = thumbnail._create_thumbnail_pdf2image("d.pdf", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_convert_pil_false.assert_called_once() # Ensure pdf2image part ran up to PIL check


    # --- Tests for _create_thumbnail_pdf2image ---
    @patch('thumbnail.convert_from_path')
    # @patch('thumbnail.Image') # Already using self.mock_pil_image effectively
    @patch('thumbnail.os.makedirs')
    def test_pdf2image_success(self, mock_makedirs, mock_convert_from_path):
        """Test successful PDF thumbnail creation with pdf2image."""
        if not thumbnail.PDF2IMAGE_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("pdf2image or Pillow not available.")

        mock_convert_from_path.return_value = [self.mock_pil_image]

        result = thumbnail._create_thumbnail_pdf2image("dummy.pdf", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        
        self.assertTrue(result)
        mock_convert_from_path.assert_called_once_with("dummy.pdf", first_page=1, last_page=1, dpi=72)
        self.mock_pil_image.thumbnail.assert_called_once_with((self.test_width, self.test_height))
        mock_makedirs.assert_called_once_with(os.path.dirname("out.jpg"), exist_ok=True)
        self.mock_pil_image.save.assert_called_once_with("out.jpg", self.test_format, quality=self.test_quality)

    @patch('thumbnail.convert_from_path', return_value=[]) 
    def test_pdf2image_no_images_returned(self, mock_convert_from_path):
        """Test pdf2image returning no images."""
        if not thumbnail.PDF2IMAGE_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("pdf2image or Pillow not available.")
            
        result = thumbnail._create_thumbnail_pdf2image("dummy.pdf", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)

    @patch('thumbnail.convert_from_path', side_effect=thumbnail.PDFInfoNotInstalledError("Poppler not found"))
    def test_pdf2image_poppler_not_found(self, mock_convert_from_path):
        """Test pdf2image when Poppler is not found."""
        if not thumbnail.PDF2IMAGE_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("pdf2image or Pillow not available.")

        result = thumbnail._create_thumbnail_pdf2image("dummy.pdf", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
    
    # --- Tests for _create_thumbnail_html_playwright ---
    @patch('thumbnail.Image.open') 
    @patch('thumbnail.os.makedirs')
    @patch('thumbnail.sync_playwright') # Mock the context manager directly from where it's imported in the function
    def test_html_playwright_success(self, mock_sync_playwright_func, mock_makedirs, mock_pil_image_open):
        """Test successful HTML thumbnail generation with Playwright."""
        if not thumbnail.PIL_AVAILABLE: 
            self.skipTest("Pillow not available for this test.")

        mock_playwright_cm = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_screenshot_bytes = b"png_bytes"
        
        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_cm.__enter__.return_value.chromium.launch.return_value = mock_browser
        
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = mock_screenshot_bytes
        mock_pil_image_open.return_value = self.mock_pil_image

        # Simulate Playwright being importable inside _create_thumbnail_html_playwright
        with patch.dict(sys.modules, {'playwright.sync_api': MagicMock()}):
            result = thumbnail._create_thumbnail_html_playwright("dummy.html", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)

        self.assertTrue(result)
        mock_page.goto.assert_called_once() # Argument can be checked if it's more complex
        mock_page.screenshot.assert_called_once_with(full_page=False)
        mock_pil_image_open.assert_called_once() 
        self.mock_pil_image.thumbnail.assert_called_once_with((self.test_width, self.test_height))
        mock_makedirs.assert_called_once_with(os.path.dirname("out.jpg"), exist_ok=True)
        self.mock_pil_image.save.assert_called_once_with("out.jpg", self.test_format, quality=self.test_quality)
        mock_browser.close.assert_called_once()

    @patch('thumbnail.PIL_AVAILABLE', False)
    @patch('thumbnail.sync_playwright') # Mock to prevent actual playwright import error
    def test_html_playwright_pil_unavailable(self, mock_sync_playwright_func):
        """Test HTML thumbnailing fails if Pillow is unavailable after screenshot."""
        # Simulate Playwright being importable
        mock_playwright_module = MagicMock()
        sys.modules['playwright.sync_api'] = mock_playwright_module
        mock_sync_playwright_func.return_value = MagicMock() # Basic CM mock

        result = thumbnail._create_thumbnail_html_playwright("dummy.html", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        # Restore sys.modules if it was altered for more complex scenarios
        if 'playwright.sync_api' in sys.modules and sys.modules['playwright.sync_api'] == mock_playwright_module:
            del sys.modules['playwright.sync_api']

    @patch('thumbnail.sync_playwright')
    def test_html_playwright_launch_error(self, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("Pillow not available.")
        mock_playwright_cm = MagicMock()
        # Define PlaywrightError_Local for this scope.
        # The function _create_thumbnail_html_playwright defines it locally if playwright.sync_api is not found.
        # For this test, we assume playwright.sync_api *is* imported at the point of the call,
        # so PlaywrightError_Local would be playwright.sync_api.Error.
        # We mock playwright.sync_api.Error to be a distinct local class for assertion.
        class MockPlaywrightError(Exception): pass

        mock_playwright_instance = mock_playwright_cm.__enter__.return_value
        mock_playwright_instance.chromium.launch.side_effect = MockPlaywrightError("Launch failed")
        mock_sync_playwright_func.return_value = mock_playwright_cm

        # Patch sys.modules to simulate playwright.sync_api being available and having the Error attribute
        mock_playwright_api_module = MagicMock()
        mock_playwright_api_module.Error = MockPlaywrightError

        with patch.dict(sys.modules, {'playwright.sync_api': mock_playwright_api_module}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)

    @patch('thumbnail.sync_playwright')
    def test_html_playwright_goto_error(self, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("Pillow not available.")
        mock_playwright_cm, mock_browser, mock_page = MagicMock(), MagicMock(), MagicMock()
        class MockPlaywrightError(Exception): pass

        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_instance = mock_playwright_cm.__enter__.return_value
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.goto.side_effect = MockPlaywrightError("Goto failed")

        mock_playwright_api_module = MagicMock()
        mock_playwright_api_module.Error = MockPlaywrightError
        with patch.dict(sys.modules, {'playwright.sync_api': mock_playwright_api_module}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_browser.close.assert_called_once()


    @patch('thumbnail.sync_playwright')
    def test_html_playwright_screenshot_error(self, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("Pillow not available.")
        mock_playwright_cm, mock_browser, mock_page = MagicMock(), MagicMock(), MagicMock()
        class MockPlaywrightError(Exception): pass

        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_instance = mock_playwright_cm.__enter__.return_value
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.side_effect = MockPlaywrightError("Screenshot failed")

        mock_playwright_api_module = MagicMock()
        mock_playwright_api_module.Error = MockPlaywrightError
        with patch.dict(sys.modules, {'playwright.sync_api': mock_playwright_api_module}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_browser.close.assert_called_once()

    @patch('thumbnail.sync_playwright')
    @patch('thumbnail.Image.open', side_effect=thumbnail.UnidentifiedImageError("Bad image data"))
    def test_html_playwright_image_open_error(self, mock_image_open, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("Pillow not available.")
        mock_playwright_cm, mock_browser, mock_page = MagicMock(), MagicMock(), MagicMock()
        class MockPlaywrightError(Exception): pass

        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_instance = mock_playwright_cm.__enter__.return_value
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = b"dummy_bytes"

        mock_playwright_api_module = MagicMock()
        mock_playwright_api_module.Error = MockPlaywrightError
        with patch.dict(sys.modules, {'playwright.sync_api': mock_playwright_api_module}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_browser.close.assert_called_once()

    @patch('thumbnail.sync_playwright')
    @patch('thumbnail.Image.open')
    def test_html_playwright_image_save_oserror(self, mock_image_open, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("Pillow not available.")
        mock_playwright_cm, mock_browser, mock_page = MagicMock(), MagicMock(), MagicMock()
        mock_pil_image_instance = MagicMock()
        mock_pil_image_instance.save.side_effect = OSError("Cannot save HTML thumb")
        class MockPlaywrightError(Exception): pass

        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_instance = mock_playwright_cm.__enter__.return_value
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = b"dummy_bytes"
        mock_image_open.return_value = mock_pil_image_instance

        mock_playwright_api_module = MagicMock()
        mock_playwright_api_module.Error = MockPlaywrightError
        with patch.dict(sys.modules, {'playwright.sync_api': mock_playwright_api_module}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        mock_browser.close.assert_called_once()

    @patch('thumbnail.sync_playwright')
    @patch('thumbnail.Image.open')
    @patch('thumbnail.os.makedirs')
    def test_html_playwright_rgba_to_rgb_conversion(self, mock_makedirs, mock_image_open, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("Pillow not available.")
        mock_playwright_cm, mock_browser, mock_page = MagicMock(), MagicMock(), MagicMock()
        mock_rgba_image = MagicMock(mode='RGBA')
        mock_rgb_image = MagicMock(mode='RGB')
        mock_rgba_image.convert.return_value = mock_rgb_image
        class MockPlaywrightError(Exception): pass

        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_instance = mock_playwright_cm.__enter__.return_value
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = b"rgba_html_bytes"
        mock_image_open.return_value = mock_rgba_image

        mock_playwright_api_module = MagicMock()
        mock_playwright_api_module.Error = MockPlaywrightError
        with patch.dict(sys.modules, {'playwright.sync_api': mock_playwright_api_module}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", 100, 100, "JPEG", 80)

        self.assertTrue(result)
        mock_rgba_image.convert.assert_called_once_with('RGB')
        mock_rgb_image.save.assert_called_once_with("o.jpg", "JPEG", quality=80)
        mock_browser.close.assert_called_once()

    @patch.dict(sys.modules, {'playwright.sync_api': None}) # Simulate Playwright not importable
    def test_html_playwright_not_really_available(self):
        # This tests the local import check for Playwright inside _create_thumbnail_html_playwright
        # thumbnail.PIL_AVAILABLE is assumed True for this specific check path
        with patch('thumbnail.PIL_AVAILABLE', True): # Ensure PIL is considered available
             result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", 100, 100, "JPEG", 80)
        self.assertFalse(result)
        # Check log: logger.error("Playwright is not available for HTML thumbnail generation...")
        # This log check can be done with self.assertLogs if detailed log validation is needed.

    @patch('thumbnail.sync_playwright')
    def test_html_playwright_browser_close_error(self, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("Pillow not available.")
        mock_playwright_cm, mock_browser, mock_page = MagicMock(), MagicMock(), MagicMock()
        class MockPlaywrightError(Exception): pass

        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_instance = mock_playwright_cm.__enter__.return_value
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = b"ok_bytes" # Success up to this point
        mock_browser.close.side_effect = Exception("Browser close failed") # Error in finally

        # Mock Image.open and save to make the main try block succeed
        mock_pil_image_instance = MagicMock()
        mock_playwright_api_module = MagicMock()
        mock_playwright_api_module.Error = MockPlaywrightError

        with patch('thumbnail.Image.open', return_value=mock_pil_image_instance), \
             patch.dict(sys.modules, {'playwright.sync_api': mock_playwright_api_module}):
            # Ensure logging is enabled to capture the error message from the finally block
            logging.disable(logging.NOTSET)
            with self.assertLogs(thumbnail.logger, level='ERROR') as log_watcher:
                result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", 100, 100, "JPEG", 80)
            logging.disable(logging.CRITICAL) # Re-disable after test

        self.assertTrue(result) # Main operation succeeded
        self.assertTrue(any("Error closing browser" in record.getMessage() for record in log_watcher.records))


    # --- Tests for generate_thumbnail (orchestration logic) ---
    @patch('thumbnail._create_thumbnail_pymupdf')
    @patch('thumbnail.os.path.exists', return_value=True)
    def test_generate_pdf_uses_pymupdf_when_available(self, mock_exists, mock_pymupdf_create):
        with patch('thumbnail.PYMUPDF_AVAILABLE', True), patch('thumbnail.PIL_AVAILABLE', True):
            thumbnail.generate_thumbnail("d.pdf", "o.jpg", "pdf")
            mock_pymupdf_create.assert_called_once()

    @patch('thumbnail._create_thumbnail_pdf2image')
    @patch('thumbnail._create_thumbnail_pymupdf')
    @patch('thumbnail.shutil.which', return_value=True) # Poppler is available
    @patch('os.path.exists', return_value=True)
    def test_generate_pdf_uses_pdf2image_as_fallback(self, mock_exists, mock_shutil_which, mock_pymupdf_create, mock_pdf2image_create):
        with patch('thumbnail.PYMUPDF_AVAILABLE', False), \
             patch('thumbnail.PDF2IMAGE_AVAILABLE', True), \
             patch('thumbnail.PIL_AVAILABLE', True):
            thumbnail.generate_thumbnail("d.pdf", "o.jpg", "pdf")
            mock_pymupdf_create.assert_not_called()
            mock_pdf2image_create.assert_called_once()

    @patch('thumbnail._create_thumbnail_pdf2image')
    @patch('thumbnail.shutil.which', return_value=False) # Poppler is NOT available
    @patch('os.path.exists', return_value=True)
    def test_generate_pdf_fails_if_pdf2image_selected_but_poppler_missing(self, mock_exists, mock_shutil_which, mock_pdf2image_create):
        with patch('thumbnail.PYMUPDF_AVAILABLE', False), \
             patch('thumbnail.PDF2IMAGE_AVAILABLE', True), \
             patch('thumbnail.PIL_AVAILABLE', True):
            result = thumbnail.generate_thumbnail("d.pdf", "o.jpg", "pdf")
            self.assertFalse(result)
            mock_pdf2image_create.assert_not_called()

    @patch('os.path.exists', return_value=True)
    def test_generate_pdf_fails_if_no_pdf_libs_available(self, mock_exists):
        # This test assumes PIL is True, but both PDF libs are False
        with patch('thumbnail.PYMUPDF_AVAILABLE', False), \
             patch('thumbnail.PDF2IMAGE_AVAILABLE', False), \
             patch('thumbnail.PIL_AVAILABLE', True):
            with self.assertLogs(thumbnail.logger, level='ERROR') as log_watcher:
                result = thumbnail.generate_thumbnail("d.pdf", "o.jpg", "pdf")
            self.assertFalse(result)
            self.assertTrue(any("No suitable PDF thumbnailing library" in rec.getMessage() for rec in log_watcher.records))

    @patch('os.path.exists', return_value=True)
    def test_generate_pdf_fails_pil_unavailable(self, mock_exists):
        # Tests that even if PDF libs are (notionally) available, if PIL is False, it fails.
        # The generate_thumbnail function checks PIL_AVAILABLE for both PyMuPDF and pdf2image paths.
        with patch('thumbnail.PYMUPDF_AVAILABLE', True), \
             patch('thumbnail.PDF2IMAGE_AVAILABLE', True), \
             patch('thumbnail.PIL_AVAILABLE', False):
            with self.assertLogs(thumbnail.logger, level='ERROR') as log_watcher:
                result = thumbnail.generate_thumbnail("d.pdf", "o.jpg", "pdf")
            self.assertFalse(result)
            # Check for the generic message or specific PIL messages if logged by sub-functions
            # (though sub-functions might not be called if PIL_AVAILABLE is checked early in generate_thumbnail)
            # The current generate_thumbnail calls the sub-methods which then check PIL_AVAILABLE again.
            # So, the error will likely come from _create_thumbnail_pymupdf or _create_thumbnail_pdf2image
            # or the main orchestrator's own PIL check if it had one (it doesn't currently for PDF path directly).
            # Let's assume the log from the first attempted method (_create_thumbnail_pymupdf)
            self.assertTrue(any("Pillow (PIL) is not available" in rec.getMessage() for rec in log_watcher.records),
                            "Expected log message about PIL not being available was not found.")


    @patch('thumbnail._create_thumbnail_html_playwright')
    @patch('os.path.exists', return_value=True)
    def test_generate_html_uses_playwright(self, mock_exists, mock_playwright_create):
        # Simulate Playwright being importable inside _create_thumbnail_html_playwright
        # and PIL being available for the main generate_thumbnail check
        with patch.dict(sys.modules, {'playwright.sync_api': MagicMock()}), \
             patch('thumbnail.PIL_AVAILABLE', True):
            thumbnail.generate_thumbnail("d.html", "o.jpg", "html")
            mock_playwright_create.assert_called_once()
            
    @patch('os.path.exists', return_value=False) 
    def test_generate_thumbnail_input_not_found(self, mock_exists):
        result = thumbnail.generate_thumbnail("nonexistent.pdf", "out.jpg", file_format="pdf")
        self.assertFalse(result)
        mock_exists.assert_called_once_with("nonexistent.pdf")

    def test_generate_thumbnail_unsupported_format(self):
        with patch('os.path.exists', return_value=True):
            result = thumbnail.generate_thumbnail("dummy.xyz", "out.jpg", file_format="xyz")
            self.assertFalse(result)
            
    def test_generate_thumbnail_dry_run(self):
        with patch('os.path.exists', return_value=True) as mock_exists:
            result = thumbnail.generate_thumbnail("dummy.pdf", "out.jpg", file_format="pdf", dry_run=True)
            self.assertTrue(result)
            mock_exists.assert_called_once_with("dummy.pdf")

if __name__ == "__main__":
    logging.disable(logging.NOTSET) # Ensure all logs are enabled for direct test runs
    unittest.main()
