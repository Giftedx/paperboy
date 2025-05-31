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

    @patch('thumbnail.fitz.open', side_effect=Exception("Fitz Error"))
    def test_pymupdf_fitz_open_error(self, mock_fitz_open):
        """Test PyMuPDF error during fitz.open()."""
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE: # Though PYMUPDF_AVAILABLE would be false if fitz isn't there
            self.skipTest("PyMuPDF or Pillow not available.")
        
        result = thumbnail._create_thumbnail_pymupdf("dummy.pdf", "out.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)

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
        with patch('thumbnail.PYMUPDF_AVAILABLE', False), \
             patch('thumbnail.PDF2IMAGE_AVAILABLE', False), \
             patch('thumbnail.PIL_AVAILABLE', True): # PIL alone is not enough
            result = thumbnail.generate_thumbnail("d.pdf", "o.jpg", "pdf")
            self.assertFalse(result)

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

    # --- More PyMuPDF Path Failures ---
    @patch('thumbnail.fitz.open')
    def test_pymupdf_get_pixmap_fails(self, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.side_effect = Exception("Pixmap error")

        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    @patch('thumbnail.Image.frombytes', side_effect=Exception("PIL frombytes error"))
    def test_pymupdf_pil_frombytes_fails(self, mock_frombytes, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pixmap = MagicMock()
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap

        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.fitz.open')
    @patch('thumbnail.Image.frombytes')
    def test_pymupdf_pil_save_fails(self, mock_frombytes, mock_fitz_open):
        if not thumbnail.PYMUPDF_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("PyMuPDF or Pillow not available.")
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pixmap = MagicMock()
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap
        mock_frombytes.return_value = self.mock_pil_image
        self.mock_pil_image.save.side_effect = Exception("PIL save error")

        result = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        mock_doc.close.assert_called_once()

    @patch('thumbnail.PYMUPDF_AVAILABLE', True)
    @patch('thumbnail.PIL_AVAILABLE', False)
    @patch('thumbnail.fitz.open') # Mock to prevent actual file access
    def test_generate_pdf_pymupdf_selected_pil_unavailable(self, mock_fitz_open):
        # This tests the _create_thumbnail_pymupdf path specifically when PIL is False
        # The main generate_thumbnail orchestrator might have a slightly different check order
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pixmap = MagicMock() # Define mock_pixmap
        mock_fitz_open.return_value = mock_doc
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap # Ensure get_pixmap returns the mock

        # Test the helper directly
        result_helper = thumbnail._create_thumbnail_pymupdf("d.pdf", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result_helper)

        # Test the main orchestrator to ensure it also fails as expected
        with patch('os.path.exists', return_value=True):
             result_main = thumbnail.generate_thumbnail("d.pdf", "o.jpg", "pdf")
             self.assertFalse(result_main)


    # --- More pdf2image Path Failures ---
    @patch('thumbnail.convert_from_path', side_effect=thumbnail.PDFPageCountError("Page count error"))
    def test_pdf2image_page_count_error(self, mock_convert_from_path):
        if not thumbnail.PDF2IMAGE_AVAILABLE or not thumbnail.PIL_AVAILABLE:
            self.skipTest("pdf2image or Pillow not available.")
        result = thumbnail._create_thumbnail_pdf2image("d.pdf", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)

    @patch('thumbnail.PDF2IMAGE_AVAILABLE', True)
    @patch('thumbnail.PIL_AVAILABLE', False)
    @patch('thumbnail.shutil.which', return_value=True) # Poppler available
    @patch('thumbnail.convert_from_path') # Mock to prevent actual call
    def test_generate_pdf_pdf2image_selected_pil_unavailable(self, mock_convert, mock_shutil):
        # This tests the _create_thumbnail_pdf2image path specifically when PIL is False
        # Assumes PYMUPDF_AVAILABLE is False for this path to be chosen by generate_thumbnail
        with patch('thumbnail.PYMUPDF_AVAILABLE', False):
            # Test the helper directly
            # _create_thumbnail_pdf2image checks PIL_AVAILABLE after calling convert_from_path
            mock_convert.return_value = [self.mock_pil_image] # Simulate images returned
            result_helper = thumbnail._create_thumbnail_pdf2image("d.pdf", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
            self.assertFalse(result_helper)

            # Test the main orchestrator
            with patch('os.path.exists', return_value=True):
                result_main = thumbnail.generate_thumbnail("d.pdf", "o.jpg", "pdf")
                self.assertFalse(result_main)

    # --- More Playwright HTML Path Failures ---
    @patch('thumbnail.sync_playwright')
    def test_html_playwright_page_goto_fails(self, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("PIL not available")
        mock_playwright_cm = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_cm.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.goto.side_effect = Exception("Page load error")

        with patch.dict(sys.modules, {'playwright.sync_api': MagicMock()}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        mock_browser.close.assert_called_once()

    @patch('thumbnail.sync_playwright')
    def test_html_playwright_screenshot_fails(self, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("PIL not available")
        mock_playwright_cm = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_cm.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.side_effect = Exception("Screenshot error")

        with patch.dict(sys.modules, {'playwright.sync_api': MagicMock()}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        mock_browser.close.assert_called_once()

    @patch('thumbnail.sync_playwright')
    @patch('thumbnail.Image.open', side_effect=thumbnail.UnidentifiedImageError("Bad image data"))
    def test_html_playwright_pil_open_fails(self, mock_pil_open, mock_sync_playwright_func):
        if not thumbnail.PIL_AVAILABLE: self.skipTest("PIL not available")
        mock_playwright_cm = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_sync_playwright_func.return_value = mock_playwright_cm
        mock_playwright_cm.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = b"fake_img_bytes"

        with patch.dict(sys.modules, {'playwright.sync_api': MagicMock()}):
            result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        mock_browser.close.assert_called_once()

    @patch('thumbnail.PIL_AVAILABLE', True) # Assume PIL is available for the orchestrator check
    @patch.dict(sys.modules, {'playwright.sync_api': None}) # Simulate Playwright import error locally
    def test_html_playwright_locally_unavailable(self):
        # This test relies on the local import failing inside _create_thumbnail_html_playwright
        # We mock sys.modules to ensure 'playwright.sync_api' is not found by that import
        result = thumbnail._create_thumbnail_html_playwright("d.html", "o.jpg", self.test_width, self.test_height, self.test_format, self.test_quality)
        self.assertFalse(result)
        # Also test the main generate_thumbnail function
        with patch('os.path.exists', return_value=True):
            result_main = thumbnail.generate_thumbnail("d.html", "o.jpg", "html")
            self.assertFalse(result_main)


if __name__ == "__main__":
    logging.disable(logging.NOTSET) # Ensure all logs are enabled for direct test runs
    unittest.main()
