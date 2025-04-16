the #!/usr/bin/env python3
"""
Thumbnail generation module
Uses pdf2image (requires poppler) to create a PNG thumbnail from the first page of a PDF.
"""

import logging
import os
from PIL import UnidentifiedImageError # Import specific error

# Optional dependency handling for pdf2image
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
    # Define dummy exceptions if pdf2image is not installed
    class PDFInfoNotInstalledError(Exception):
        pass
    class PDFPageCountError(Exception):
        pass
    class PDFSyntaxError(Exception):
        pass
    # Define dummy UnidentifiedImageError only if Pillow isn't installed
    # and it hasn't been imported at the top level.
    try:
        # Check if Pillow's version is already imported
        from PIL import UnidentifiedImageError as _PillowUnidentifiedImageError
        # If the above works, UnidentifiedImageError from PIL is available
    except ImportError:
        # Pillow is not installed, define a dummy class if the name isn't already taken
        if 'UnidentifiedImageError' not in globals():
            class UnidentifiedImageError(Exception):
                pass
        # If 'UnidentifiedImageError' is already in globals (e.g., from the top import attempt)
        # we don't need to redefine it.

# Configure logging
logger = logging.getLogger(__name__)

# Constants
THUMBNAIL_WIDTH = 200 # Desired width for the thumbnail
THUMBNAIL_HEIGHT = 200 # Desired height for the thumbnail (adjust aspect ratio as needed)
THUMBNAIL_FORMAT = 'JPEG' # Output format for the thumbnail

def create_thumbnail(input_path, output_path, width=THUMBNAIL_WIDTH, height=THUMBNAIL_HEIGHT, fmt=THUMBNAIL_FORMAT):
    """Creates a thumbnail from the first page of a PDF file."""
    logger.info("Attempting to create thumbnail for: %s", input_path)
    try:
        # Use pdf2image to get the first page
        images = convert_from_path(input_path, first_page=1, last_page=1, dpi=72) # Lower DPI for speed

        if not images:
            logger.error("pdf2image returned no images for %s.", input_path)
            return False

        # Use Pillow to resize and save the thumbnail
        with images[0] as img:
            img.thumbnail((width, height))
            # Ensure the output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path, fmt)
            logger.info("Successfully created thumbnail: %s", output_path)
            return True

    except PDFInfoNotInstalledError:
        logger.error("Poppler 'pdfinfo' not found. Please install poppler-utils.")
        return False
    except PDFPageCountError:
        logger.error("Could not get page count for PDF: %s. Is it a valid PDF?", input_path)
        return False
    except PDFSyntaxError:
        logger.error("Syntax error in PDF file: %s. The file might be corrupted.", input_path)
        return False
    except UnidentifiedImageError:
        logger.error("Cannot identify image file (potentially during processing). Is the PDF valid? Path: %s", input_path)
        return False
    except IOError as e:
        logger.error("File handling error during thumbnail creation for %s: %s", input_path, e)
        return False
    except Exception as e:
        # Catch any other unexpected errors from pdf2image or Pillow
        # Using logger.exception to include traceback
        logger.exception("An unexpected error occurred during thumbnail creation for %s: %s", input_path, e)
        return False

def generate_thumbnail(input_path, output_path, file_format="pdf", dry_run=False):
    """
    Generate a thumbnail for a newspaper file (PDF or HTML).
    
    This is a wrapper function for create_thumbnail that handles different file formats
    and implements dry_run support.
    
    Args:
        input_path: Path to the input file
        output_path: Path where the thumbnail should be saved
        file_format: Format of the input file ('pdf' or 'html')
        dry_run: If True, simulate the operation without actually generating the thumbnail
        
    Returns:
        bool: True if the thumbnail was generated successfully (or simulated in dry_run), False otherwise
    """
    if dry_run:
        logger.info("[Dry Run] Would generate thumbnail from %s to %s", input_path, output_path)
        return True  # Assume success in dry run mode
    
    # Verify dependencies before attempting thumbnail generation
    if file_format.lower() == 'pdf':
        if not PDF2IMAGE_AVAILABLE:
            logger.error(
                "Cannot generate PDF thumbnail: pdf2image library not installed. "
                "Install it using: pip install pdf2image"
            )
            # Check for Poppler dependency on non-Windows systems
            if os.name != 'nt':  # Not Windows
                import shutil
                if not shutil.which('pdftoppm') and not shutil.which('pdftocairo'):
                    logger.error(
                        "Poppler utilities not found. On Linux, install using: "
                        "apt-get install poppler-utils. On macOS: brew install poppler"
                    )
            return False
    
    if not os.path.exists(input_path):
        logger.error("Input file not found: %s", input_path)
        return False
    try:
        if file_format.lower() == 'pdf' and PDF2IMAGE_AVAILABLE:
            # For PDF files, use the create_thumbnail function
            return create_thumbnail(input_path, output_path)
        elif file_format.lower() == 'html':
            # For HTML files, use Playwright to take a screenshot
            try:
                from playwright.sync_api import sync_playwright
                logger.info("Using Playwright to generate thumbnail from HTML file")
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 1600})
                    
                    # Load the HTML file using file:// protocol
                    absolute_path = os.path.abspath(input_path)
                    file_url = f"file://{absolute_path}"
                    logger.debug("Loading HTML file from: %s", file_url)
                    
                    page.goto(file_url, wait_until="networkidle")
                    
                    # Ensure output directory exists
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    
                    # Take screenshot and save as thumbnail
                    page.screenshot(path=output_path, full_page=False)
                    browser.close()
                    
                    logger.info("Successfully created HTML thumbnail: %s", output_path)
                    return True
            except ImportError:
                logger.error("Playwright not available. Install with: pip install playwright")
                return False
            except Exception as e:
                # Using logger.exception to include traceback
                logger.exception("Error generating HTML thumbnail: %s", e)
                return False
        else:
            if file_format.lower() == 'pdf' and not PDF2IMAGE_AVAILABLE:
                logger.error("PDF thumbnail generation requires pdf2image module. Please install it.")
            else:
                logger.error("Unsupported file format for thumbnail generation: %s", file_format)
            return False
    except Exception as e:
        # Using logger.exception to include traceback
        logger.exception("Unexpected error generating thumbnail: %s", e)
        return False