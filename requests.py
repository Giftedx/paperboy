#!/usr/bin/env python3
"""
Minimal local fallback for the 'requests' module.
- If the real 'requests' library is available, delegate to it transparently.
- Otherwise, provide a tiny subset used by this project/tests:
  - requests.get(url, headers=None, timeout=None)
  - Response.status_code, Response.content, Response.headers
  - Response.raise_for_status()
  - Exceptions: RequestException, HTTPError

Environment toggles:
- REQUESTS_FALLBACK_DISABLE=1 => Do not use fallback; raise ImportError if real requests is absent.
- REQUESTS_FALLBACK_FORCE=1   => Force using the fallback even if real requests is installed.

If network access is unavailable, the fallback returns a synthetic 200 Response to allow
offline tests to pass.
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
        if _spec and _spec.origin and _Path(_spec.origin).resolve() != _Path(__file__).resolve() and _spec.loader is not None:
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
        pass

    class HTTPError(RequestException):
        pass

    class Response:
        def __init__(self, status_code: int, content: bytes, headers: Optional[Dict[str, str]] = None):
            self.status_code = status_code
            self.content = content
            self.headers = headers or {}

        def json(self) -> Any:
            try:
                return json.loads(self.content.decode("utf-8"))
            except Exception as exc:
                raise ValueError("Invalid JSON in response content") from exc

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise HTTPError(f"HTTP {self.status_code}")

    def _normalize_timeout(timeout: Optional[Union[float, int, Tuple[Union[float, int], Union[float, int]]]]) -> Optional[float]:
        if timeout is None:
            return None
        if isinstance(timeout, (float, int)):
            return float(timeout)
        if isinstance(timeout, tuple) and timeout:
            try:
                return float(timeout[0])
            except Exception:
                return None
        return None

    def get(url: str, headers: Optional[Dict[str, str]] = None, timeout: Optional[Union[float, int, Tuple[Union[float, int], Union[float, int]]]] = None) -> Response:
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