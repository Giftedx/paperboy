#!/usr/bin/env python3
"""
Thumbnail generation module.
Prioritizes PyMuPDF (fitz) for PDF thumbnails, falls back to pdf2image (requires Poppler),
and uses Playwright for HTML thumbnails.
"""

import logging
import os
import shutil # For Poppler check
import time # For retry delays in dummy file creation, if needed

# PIL (Pillow)
try:
    from PIL import Image, UnidentifiedImageError
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    class UnidentifiedImageError(Exception): # type: ignore
        """Dummy exception if Pillow is not installed."""
        pass
    class Image: # Dummy Image class
        """Dummy Image class if Pillow is not installed."""
        @staticmethod
        def frombytes(mode, size, data): # type: ignore
            pass
        def thumbnail(self, size): # type: ignore
            pass
        def save(self, fp, format=None, **params): # type: ignore
            pass
        @staticmethod
        def open(fp): # type: ignore
             pass


# PyMuPDF (fitz)
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# pdf2image
try:
    from pdf2image import convert_from_path
    from pdf2image.exceptions import (
        PDFInfoNotInstalledError,
        PDFPageCountError,
        PDFSyntaxError
    )
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    class PDFInfoNotInstalledError(Exception): # type: ignore
        pass
    class PDFPageCountError(Exception): # type: ignore
        pass
    class PDFSyntaxError(Exception): # type: ignore
        pass

# Playwright (imported locally in the function that uses it)

# Configure logging
logger = logging.getLogger(__name__)

# Constants
THUMBNAIL_WIDTH = 200
THUMBNAIL_HEIGHT = 200
THUMBNAIL_FORMAT = 'JPEG' # Default output format
THUMBNAIL_QUALITY = 85 # Default JPEG quality

def _create_thumbnail_pymupdf(input_path, output_path, width, height, fmt, quality):
    """Creates a thumbnail from the first page of a PDF file using PyMuPDF."""
    logger.info("Attempting to create thumbnail for '%s' using PyMuPDF.", input_path)
    doc = None
    try:
        doc = fitz.open(input_path)
        if doc.page_count <= 0:
            logger.error("PyMuPDF: No pages in PDF: '%s'.", input_path)
            return False
        
        page = doc.load_page(0)
        
        zoom_x = 2.0 
        zoom_y = 2.0
        mat = fitz.Matrix(zoom_x, zoom_y)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        if not PIL_AVAILABLE:
            logger.error("Pillow (PIL) is not available to process the image from PyMuPDF for '%s'.", input_path)
            return False

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.thumbnail((width, height)) 
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        save_params = {}
        if fmt.upper() == 'JPEG':
            save_params['quality'] = quality
            # To prevent "cannot write mode RGBA as JPEG" if pixmap somehow had alpha despite alpha=False
            if img.mode == 'RGBA':
                img = img.convert('RGB')
        
        img.save(output_path, fmt, **save_params)
            
        logger.info("Successfully created thumbnail using PyMuPDF: '%s'.", output_path)
        return True
    except Exception as e: 
        logger.exception("PyMuPDF: Error during thumbnail creation for '%s': %s", input_path, e)
        return False
    finally:
        if doc:
            try:
                doc.close()
            except Exception as e:
                logger.error("PyMuPDF: Error closing PDF document '%s': %s", input_path, e)

def _create_thumbnail_pdf2image(input_path, output_path, width, height, fmt, quality):
    """Creates a thumbnail from the first page of a PDF using pdf2image."""
    logger.info("Attempting to create thumbnail for '%s' using pdf2image.", input_path)
    try:
        images = convert_from_path(input_path, first_page=1, last_page=1, dpi=72) # dpi=72 is standard for this lib for speed

        if not images:
            logger.error("pdf2image returned no images for '%s'.", input_path)
            return False

        if not PIL_AVAILABLE:
            logger.error("Pillow (PIL) is not available to process the image from pdf2image for '%s'.", input_path)
            return False

        with images[0] as img:
            img.thumbnail((width, height))
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            save_params = {}
            if fmt.upper() == 'JPEG':
                save_params['quality'] = quality
                if img.mode == 'RGBA': # Ensure image is RGB for JPEG
                    img = img.convert('RGB')
            
            img.save(output_path, fmt, **save_params)
            logger.info("Successfully created thumbnail using pdf2image: '%s'.", output_path)
            return True
    except (PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError) as e:
        logger.error("pdf2image error for '%s': %s. Ensure Poppler utilities are installed and PDF is valid.", input_path, e)
        return False
    except UnidentifiedImageError: 
        logger.error("Pillow: Cannot identify image file (from pdf2image output) for '%s'.", input_path)
        return False
    except IOError as e:
        logger.error("File handling error during pdf2image thumbnail creation for '%s': %s", input_path, e)
        return False
    except Exception as e:
        logger.exception("An unexpected error occurred during pdf2image thumbnail creation for '%s': %s", input_path, e)
        return False

def _create_thumbnail_html_playwright(input_path, output_path, width, height, fmt, quality):
    """Creates a thumbnail from an HTML file using Playwright and Pillow."""
    logger.info("Attempting to create thumbnail for HTML '%s' using Playwright.", input_path)
    
    # Playwright availability check (local to this function)
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError_Local
        playwright_is_really_available = True
    except ImportError:
        playwright_is_really_available = False
        class PlaywrightError_Local(Exception): pass # Dummy for except block

    if not playwright_is_really_available:
        logger.error("Playwright is not available for HTML thumbnail generation. Install with: pip install playwright and playwright install")
        return False
    if not PIL_AVAILABLE:
        logger.error("Pillow (PIL) is not available for HTML thumbnail processing for '%s'.", input_path)
        return False

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Use a larger viewport initially for better quality screenshot before thumbnailing
            page = browser.new_page(viewport={"width": 1280, "height": 1024}) 
            
            absolute_path = os.path.abspath(input_path)
            file_url = f"file://{absolute_path}"
            logger.debug("Loading HTML file from: %s", file_url)
            
            page.goto(file_url, wait_until="networkidle")
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            img_bytes = page.screenshot(full_page=False) # Take screenshot of the current viewport
            
            from io import BytesIO
            img = Image.open(BytesIO(img_bytes))
            img.thumbnail((width, height)) # Resize

            save_params = {}
            if fmt.upper() == 'JPEG':
                save_params['quality'] = quality
                if img.mode == 'RGBA': # Ensure image is RGB for JPEG
                    img = img.convert('RGB')
            
            img.save(output_path, fmt, **save_params)
            
            logger.info("Successfully created HTML thumbnail using Playwright: '%s'", output_path)
            return True
    except PlaywrightError_Local as e: 
         logger.exception("Playwright error generating HTML thumbnail for '%s': %s", input_path, e)
         return False
    except UnidentifiedImageError:
        logger.error("Pillow: Cannot identify image from Playwright screenshot for '%s'.", input_path)
        return False
    except Exception as e:
        logger.exception("Unexpected error generating HTML thumbnail for '%s': %s", input_path, e)
        return False
    finally:
        if browser:
            try:
                browser.close()
            except Exception as e:
                logger.error("Playwright: Error closing browser for '%s': %s", input_path, e)


def generate_thumbnail(input_path, output_path, file_format="pdf", dry_run=False, 
                       width=THUMBNAIL_WIDTH, height=THUMBNAIL_HEIGHT, 
                       fmt=THUMBNAIL_FORMAT, quality=THUMBNAIL_QUALITY):
    """
    Generate a thumbnail for a newspaper file (PDF or HTML).
    Prioritizes PyMuPDF for PDFs, then pdf2image, then Playwright for HTML.
    """
    logger.info("Generating thumbnail for '%s' (format: %s) -> '%s'", input_path, file_format, output_path)
    if dry_run:
        logger.info("[Dry Run] Thumbnail generation skipped for '%s'.", input_path)
        return True

    if not os.path.exists(input_path):
        logger.error("Input file not found: '%s'.", input_path)
        return False

    file_format_lower = file_format.lower()

    if file_format_lower == 'pdf':
        if PYMUPDF_AVAILABLE and PIL_AVAILABLE:
            return _create_thumbnail_pymupdf(input_path, output_path, width, height, fmt, quality)
        elif PDF2IMAGE_AVAILABLE and PIL_AVAILABLE:
            logger.warning("PyMuPDF (fitz) not available or PIL missing. Falling back to pdf2image for PDF: '%s'.", input_path)
            if os.name != 'nt': 
                if not shutil.which('pdftoppm') and not shutil.which('pdftocairo'):
                    logger.error(
                        "pdf2image requires Poppler utilities, which are not found. "
                        "On Linux, install using: sudo apt-get install poppler-utils. On macOS: brew install poppler"
                    )
                    return False
            return _create_thumbnail_pdf2image(input_path, output_path, width, height, fmt, quality)
        else:
            logger.error("No suitable PDF thumbnailing library (PyMuPDF+PIL or pdf2image+PIL) available for '%s'.", input_path)
            if not PIL_AVAILABLE: logger.info("Pillow (PIL) is required by both methods.")
            if not PYMUPDF_AVAILABLE: logger.info("Consider installing PyMuPDF: pip install PyMuPDF")
            if not PDF2IMAGE_AVAILABLE: logger.info("Consider installing pdf2image: pip install pdf2image (and Poppler utilities)")
            return False
    elif file_format_lower == 'html':
        return _create_thumbnail_html_playwright(input_path, output_path, width, height, fmt, quality)
    else:
        logger.error("Unsupported file format for thumbnail generation: '%s' for input file '%s'.", file_format, input_path)
        return False

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    dummy_pdf_path = "dummy_test.pdf"
    dummy_html_path = "dummy_test.html"
    pdf_thumb_path = "dummy_pdf_thumbnail.jpg"
    html_thumb_path = "dummy_html_thumbnail.jpg"

    # Create dummy PDF if PyMuPDF is available
    if PYMUPDF_AVAILABLE:
        if not os.path.exists(dummy_pdf_path):
            try:
                doc = fitz.open()
                page = doc.new_page()
                page.insert_text((50, 72), "Hello, PyMuPDF Test!")
                doc.save(dummy_pdf_path)
                doc.close()
                logger.info("Created dummy PDF: %s", dummy_pdf_path)
            except Exception as e:
                logger.error("Could not create dummy PDF for testing: %s", e)
    else:
        logger.warning("PyMuPDF not available, cannot create dummy PDF for testing.")

    # Create dummy HTML
    if not os.path.exists(dummy_html_path):
        try:
            with open(dummy_html_path, "w") as f:
                f.write("<html><head><title>Test HTML</title></head><body><h1>Hello, HTML Thumbnail Test!</h1><p>This is a test page content.</p></body></html>")
            logger.info("Created dummy HTML: %s", dummy_html_path)
        except Exception as e:
            logger.error("Could not create dummy HTML for testing: %s", e)

    # Test PDF thumbnail generation
    if os.path.exists(dummy_pdf_path):
        logger.info("--- Testing PDF Thumbnail Generation ---")
        success_pdf = generate_thumbnail(dummy_pdf_path, pdf_thumb_path, file_format="pdf")
        if success_pdf:
            logger.info("PDF thumbnail test successful: %s", pdf_thumb_path)
        else:
            logger.error("PDF thumbnail test failed.")
    else:
        logger.info("Skipping PDF thumbnail test as dummy PDF is not available.")

    # Test HTML thumbnail generation
    if os.path.exists(dummy_html_path):
        logger.info("--- Testing HTML Thumbnail Generation ---")
        # Check for Playwright before attempting HTML test
        try:
            from playwright.sync_api import sync_playwright
            _playwright_installed_for_test = True
        except ImportError:
            _playwright_installed_for_test = False
            logger.warning("Playwright not installed, skipping HTML thumbnail test.")
            
        if _playwright_installed_for_test and PIL_AVAILABLE:
            success_html = generate_thumbnail(dummy_html_path, html_thumb_path, file_format="html")
            if success_html:
                logger.info("HTML thumbnail test successful: %s", html_thumb_path)
            else:
                logger.error("HTML thumbnail test failed.")
        elif not PIL_AVAILABLE:
            logger.warning("Pillow not installed, skipping HTML thumbnail test as it's needed for processing.")
    else:
        logger.info("Skipping HTML thumbnail test as dummy HTML is not available.")

    # Clean up dummy files
    # for f_path in [dummy_pdf_path, dummy_html_path, pdf_thumb_path, html_thumb_path]:
    #     if os.path.exists(f_path):
    #         try:
    #             os.remove(f_path)
    #             logger.info("Cleaned up: %s", f_path)
    #         except Exception as e:
    #             logger.error("Error cleaning up file %s: %s", f_path, e)
