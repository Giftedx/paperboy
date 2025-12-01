#!/usr/bin/env python3
"""
Simplified website interaction module.

Single implementation: constructs a download URL and fetches via requests.
Includes conditional resilience (retries) if the real 'requests' library is available.
"""

import os
import logging
import datetime
from urllib.parse import urljoin

import config

logger = logging.getLogger(__name__)

# Default timeouts (connect, read)
DEFAULT_TIMEOUT = (10, 60)
DEFAULT_USER_AGENT = "NewspaperDownloader/1.0"


def _get_session(requests_lib):
    """
    Creates a requests Session with retry logic if available.
    If the requests library provided is the fallback one (which might not support Session/Adapters),
    returns None or a simple object, signaling to use a plain get().
    """
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except ImportError:
        # Fallback implementation or partial install; cannot use advanced retry logic
        logger.debug("Advanced requests features (HTTPAdapter, Retry) not available. Using simple requests.")
        return None

    session = requests_lib.Session()

    # Define retry strategy
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Set default headers
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    return session


def download_file(base_url: str, save_path: str, target_date: str | None = None, dry_run: bool = False, force_download: bool = False):
    """Download the newspaper for the given date.

    Returns:
        tuple: (success (bool), result_path_or_error (str))
    """
    # Resolve date
    if target_date is None:
        target_date_obj = datetime.date.today()
    else:
        try:
            target_date_obj = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid target_date format. Please use YYYY-MM-DD.")
            return False, "Invalid date format"

    target_date_str = target_date_obj.strftime("%Y-%m-%d")

    abs_save_path = os.path.abspath(save_path)
    parent_dir = os.path.dirname(abs_save_path)
    os.makedirs(parent_dir, exist_ok=True)

    # Respect existing file if not forcing
    if not force_download:
        existing_pdf = f"{abs_save_path}.pdf"
        if os.path.exists(existing_pdf):
            logger.info("File already exists locally: %s", existing_pdf)
            return True, existing_pdf

    # Use configurable download path pattern, with a sensible default
    download_path_pattern = config.config.get(("newspaper", "download_path_pattern"), "newspaper/download/{date}")
    download_path = download_path_pattern.format(date=target_date_str)
    download_url = urljoin(base_url.rstrip("/") + "/", download_path)
    logger.info("Downloading from: %s", download_url)

    # In dry-run mode, avoid network calls and simply simulate a saved PDF path
    if dry_run:
        logger.info("[Dry Run] Would GET %s and save to %s", download_url, abs_save_path)
        return True, f"{abs_save_path}.pdf"

    # Import requests only when needed to avoid hard dependency during dry-run
    try:
        import requests  # pylint: disable=import-outside-toplevel
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except Exception as exc:
        logger.error("'requests' is required for live downloads but is not available: %s", exc)
        return False, "Missing dependency: requests"

    try:
        session = _get_session(requests)

        if session:
            logger.debug("Using requests.Session with retry logic.")
            response = session.get(download_url, timeout=DEFAULT_TIMEOUT)
        else:
            logger.debug("Using simple requests.get (no retries).")
            response = requests.get(download_url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=DEFAULT_TIMEOUT)

        response.raise_for_status()

        # Determine format (default to pdf)
        content_type = response.headers.get("Content-Type", "").lower()
        file_ext = "pdf" if "pdf" in content_type or not content_type else "bin"
        # If content-type suggests html, use html extension (useful for error pages that return 200 or html papers)
        if "html" in content_type:
            file_ext = "html"

        save_path_with_ext = f"{abs_save_path}.{file_ext}"

        with open(save_path_with_ext, "wb") as fh:
            fh.write(response.content)

        logger.info("Saved newspaper to: %s", save_path_with_ext)
        return True, save_path_with_ext
    except Exception as e:  # requests.RequestException | OSError
        logger.error("Download failed for %s: %s", download_url, e)
        return False, f"Download error: {e}"


# Backwards compatibility alias
login_and_download = download_file

if __name__ == '__main__':
    from dotenv import load_dotenv
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    load_dotenv()

    test_date_str = '2023-10-26' 
    logger.info("--- Running website.py standalone test for date: %s ---", test_date_str)

    WEBSITE_URL_TEST = os.environ.get('WEBSITE_URL', 'https://localhost:8000') # Placeholder, replace with actual URL
    SAVE_PATH_BASE_TEST = os.path.join(os.environ.get('DOWNLOAD_DIR', 'downloads'), f"{test_date_str}_test_download")

    if not WEBSITE_URL_TEST:
        logger.error("Required environment variable (WEBSITE_URL) or config value not set for standalone test.")
    else:
        logger.info("Initiating test download for URL: %s, Save Path Base: %s", WEBSITE_URL_TEST, SAVE_PATH_BASE_TEST)
        success, file_info = download_file(
            base_url=WEBSITE_URL_TEST,
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
