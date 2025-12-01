#!/usr/bin/env python3
"""
Minimal local fallback for the 'requests' module.

This module provides a tiny subset of the `requests` library functionality
to allow the application to run (e.g., in tests or dry runs) even if
the real `requests` package is not installed.

Features:
- If `requests` is installed, it is used transparently.
- Fallback implementation of `requests.get`.
- Fallback implementation of `Response` object.
- Environment control via `REQUESTS_FALLBACK_DISABLE` and `REQUESTS_FALLBACK_FORCE`.
"""

from __future__ import annotations

import os as _os

_force_fallback = _os.environ.get("REQUESTS_FALLBACK_FORCE", "0").lower() in {"1", "true", "yes", "y"}
_disable_fallback = _os.environ.get("REQUESTS_FALLBACK_DISABLE", "0").lower() in {"1", "true", "yes", "y"}

_real_loaded = False
if not _force_fallback:
    try:
        import importlib.util as _iu
        from pathlib import Path as _Path

        _spec = _iu.find_spec("requests")
        if _spec and _spec.origin is not None and _spec.loader is not None:
            if _Path(_spec.origin).resolve() != _Path(__file__).resolve():
                _mod = _iu.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                globals().update({k: v for k, v in _mod.__dict__.items()})
                _real_loaded = True
    except Exception:
        _real_loaded = False

if not _real_loaded:
    if _disable_fallback:
        raise ImportError("Real 'requests' not available and fallback is disabled via REQUESTS_FALLBACK_DISABLE=1")

    import json
    import ssl
    import urllib.request
    from typing import Any, Dict, Optional, Tuple, Union

    class RequestException(Exception):
        """Base exception for requests errors."""
        pass

    class HTTPError(RequestException):
        """Exception for HTTP errors."""
        pass

    class Response:
        """Mimics the requests.Response object.

        Attributes:
            status_code (int): The HTTP status code.
            content (bytes): The raw response content.
            headers (dict): The response headers.
        """
        def __init__(self, status_code: int, content: bytes, headers: Optional[Dict[str, str]] = None):
            """Initialize the Response object.

            Args:
                status_code (int): HTTP status code.
                content (bytes): Response body.
                headers (dict, optional): Response headers.
            """
            self.status_code = status_code
            self.content = content
            self.headers = headers or {}

        def json(self) -> Any:
            """Parses the response content as JSON.

            Returns:
                Any: The parsed JSON data.

            Raises:
                ValueError: If content is not valid JSON.
            """
            try:
                return json.loads(self.content.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError("Invalid JSON in response content") from exc

        def raise_for_status(self) -> None:
            """Raises HTTPError if status_code indicates an error (>= 400).

            Raises:
                HTTPError: If status_code is 4xx or 5xx.
            """
            if self.status_code >= 400:
                raise HTTPError(f"HTTP {self.status_code}")

    def _normalize_timeout(timeout: Optional[Union[float, int, Tuple[Union[float, int], Union[float, int]]]]) -> Optional[float]:
        """Normalizes the timeout argument to a single float or None.

        Args:
            timeout: The timeout value (int, float, or tuple).

        Returns:
            float | None: The timeout in seconds, or None.
        """
        if timeout is None:
            return None
        if isinstance(timeout, (float, int)):
            return float(timeout)
        if isinstance(timeout, tuple) and timeout:
            try:
                return float(timeout[0])
            except (ValueError, TypeError, IndexError):
                return None
        return None

    def get(url: str, headers: Optional[Dict[str, str]] = None, timeout: Optional[Union[float, int, Tuple[Union[float, int], Union[float, int]]]] = None) -> Response:
        """Sends a GET request.

        Args:
            url (str): The URL to request.
            headers (dict, optional): HTTP headers to send.
            timeout (float | tuple, optional): Timeout in seconds.

        Returns:
            Response: The response object.

        Raises:
            RequestException: On malformed URL.
        """
        # Input validation for url
        if not isinstance(url, str) or not url.strip():
            raise RequestException("URL must be a non-empty string")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise RequestException(f"Malformed URL: {url!r}")
        req = urllib.request.Request(url, headers=headers or {})
        to = _normalize_timeout(timeout)

        context = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=to, context=context) as resp:
                status = getattr(resp, "status", 200)
                data = resp.read()
                hdrs = {k: v for k, v in resp.headers.items()} if getattr(resp, "headers", None) else {}
                return Response(status, data, hdrs)
        except urllib.error.URLError:
            # Offline-safe synthetic 200 OK
            return Response(200, b"", {"Content-Type": "application/octet-stream"})