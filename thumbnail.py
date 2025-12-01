#!/usr/bin/env python3
"""
Thumbnail generation module (simplified).

Single implementation: PDF only using PyMuPDF (fitz) + Pillow.
"""

import logging
import os

logger = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 200
THUMBNAIL_HEIGHT = 200
THUMBNAIL_FORMAT = 'JPEG'
THUMBNAIL_QUALITY = 85


def generate_thumbnail(input_path: str, output_path: str, file_format: str = "pdf", dry_run: bool = False,
                       width: int = THUMBNAIL_WIDTH, height: int = THUMBNAIL_HEIGHT,
                       fmt: str = THUMBNAIL_FORMAT, quality: int = THUMBNAIL_QUALITY) -> bool:
    """Generates a thumbnail image from the first page of a PDF file.

    Requires PyMuPDF (fitz) and Pillow (PIL) libraries.

    Args:
        input_path (str): Path to the source PDF file.
        output_path (str): Path where the thumbnail should be saved.
        file_format (str): The format of the input file. Must be 'pdf'.
        dry_run (bool): If True, skip generation and return success.
        width (int): Target width of the thumbnail.
        height (int): Target height of the thumbnail.
        fmt (str): Output image format (e.g., 'JPEG', 'PNG').
        quality (int): Quality setting for JPEG output (1-100).

    Returns:
        bool: True if generation was successful, False otherwise.
    """
    if dry_run:
        logger.info("[Dry Run] Would generate thumbnail for %s -> %s", input_path, output_path)
        return True

    if file_format.lower() != "pdf":
        logger.error("Unsupported file format for thumbnail: %s (PDF only)", file_format)
        return False

    if not os.path.exists(input_path):
        logger.error("Input file not found: %s", input_path)
        return False

    try:
        try:
            import fitz  # PyMuPDF
        except Exception as exc:
            logger.error("PyMuPDF (fitz) is required for thumbnail generation but is not installed: %s", exc)
            return False
        try:
            from PIL import Image
        except Exception as exc:
            logger.error("Pillow is required for thumbnail generation but is not installed: %s", exc)
            return False

        doc = fitz.open(input_path)
        if doc.page_count <= 0:
            logger.error("No pages in PDF: %s", input_path)
            return False

        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.thumbnail((width, height))

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        save_params = {}
        if fmt.upper() == 'JPEG':
            save_params['quality'] = quality
            if img.mode == 'RGBA':
                img = img.convert('RGB')

        img.save(output_path, fmt, **save_params)
        logger.info("Thumbnail created: %s", output_path)
        return True
    except Exception as e:
        logger.exception("Error creating thumbnail for %s: %s", input_path, e)
        return False
    finally:
        try:
            doc.close()  # type: ignore[name-defined]
        except Exception:
            pass
