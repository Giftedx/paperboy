#!/usr/bin/env python3
"""
Tests for the thumbnail generation functionality (new file).
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch, MagicMock
import os
import thumbnail # For accessing constants like thumbnail.THUMBNAIL_WIDTH etc.

from thumbnail import generate_thumbnail

class TestThumbnailGeneration(unittest.TestCase):
    """Test cases for thumbnail generation."""

    @patch('thumbnail.PDF2IMAGE_AVAILABLE', True) # Ensure this path is tested
    @patch('thumbnail.os.makedirs')
    @patch('thumbnail.convert_from_path')
    def test_generate_thumbnail_pdf_success(self, mock_convert_from_path, mock_os_makedirs):
        # Create a mock image object that convert_from_path will return
        mock_image = MagicMock()
        mock_convert_from_path.return_value = [mock_image] # pdf2image returns a list

        # This path assumes 'test_files/dummy.pdf' exists at the root of the repo
        # The test environment should be relative to the repo root typically
        dummy_pdf_path = "test_files/dummy.pdf" 
        output_thumbnail_path = "test_outputs/dummy_thumb.jpg" # Conceptual path

        # Call the function under test
        result = thumbnail.generate_thumbnail(
            input_path=dummy_pdf_path,
            output_path=output_thumbnail_path,
            file_format="pdf"
        )

        # Assertions
        self.assertTrue(result, "generate_thumbnail should return True on successful PDF thumbnail generation.")
        
        mock_os_makedirs.assert_called_once_with(os.path.dirname(output_thumbnail_path), exist_ok=True)
        
        mock_convert_from_path.assert_called_once_with(dummy_pdf_path, first_page=1, last_page=1, dpi=72)
        
        mock_image.thumbnail.assert_called_once_with((thumbnail.THUMBNAIL_WIDTH, thumbnail.THUMBNAIL_HEIGHT))
        mock_image.save.assert_called_once_with(output_thumbnail_path, thumbnail.THUMBNAIL_FORMAT)

    @patch('thumbnail.PLAYWRIGHT_AVAILABLE', True)
    @patch('thumbnail.os.makedirs')
    @patch('thumbnail.sync_playwright')
    def test_generate_thumbnail_html_success(self, mock_sync_playwright, mock_os_makedirs):
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        # Configure the context manager mock
        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_instance

        dummy_html_path = "test_files/dummy.html"
        output_thumbnail_path = "test_outputs/dummy_html_thumb.jpg"

        # Call the function under test
        result = thumbnail.generate_thumbnail(
            input_path=dummy_html_path,
            output_path=output_thumbnail_path,
            file_format="html"
        )

        # Assertions
        self.assertTrue(result, "generate_thumbnail should return True for HTML success.")
        mock_os_makedirs.assert_called_once_with(os.path.dirname(output_thumbnail_path), exist_ok=True)
        
        # Assert Playwright calls
        mock_sync_playwright.assert_called_once()
        mock_playwright_instance.chromium.launch.assert_called_once_with(headless=True)
        # The viewport is set in thumbnail.py, ensure it's part of the assertion
        mock_browser.new_page.assert_called_once_with(viewport={'width': 1280, 'height': 1600}) 
        mock_page.goto.assert_called_once_with(f"file://{os.path.abspath(dummy_html_path)}", wait_until="networkidle")
        mock_page.screenshot.assert_called_once_with(path=output_thumbnail_path, full_page=False)
        mock_browser.close.assert_called_once() # From the finally block
        # Ensure the context manager's __exit__ is also called
        mock_sync_playwright.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
