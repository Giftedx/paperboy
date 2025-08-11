#!/usr/bin/env python3
"""
Report which 'requests' implementation is active.

Usage:
  python which_requests.py [--require-real | --require-fallback]

- Prints a JSON object with keys: implementation, path, env.
- Returns exit code 0 on success.
- If --require-real is provided, exits 1 if fallback is active.
- If --require-fallback is provided, exits 1 if real requests is active.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check which 'requests' implementation is active")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--require-real", action="store_true", help="exit non-zero if fallback is active")
    group.add_argument("--require-fallback", action="store_true", help="exit non-zero if real requests is active")
    args = parser.parse_args()

    try:
        import requests  # type: ignore
    except Exception as exc:
        result = {
            "implementation": "missing",
            "path": None,
            "env": {
                "REQUESTS_FALLBACK_FORCE": os.environ.get("REQUESTS_FALLBACK_FORCE"),
                "REQUESTS_FALLBACK_DISABLE": os.environ.get("REQUESTS_FALLBACK_DISABLE"),
            },
            "error": str(exc),
        }
        print(json.dumps(result, indent=2))
        return 1

    path = getattr(requests, "__file__", None)
    path_str = str(path) if path else None

    # Detect fallback implementation by checking for a unique module attribute
    is_fallback = getattr(requests, "__fallback__", False)
    if path_str:
        try:
            resolved = str(Path(path_str).resolve())
            path_str = resolved
        except Exception:
            # If resolution fails, keep original
            pass

    implementation = "fallback" if is_fallback else "real"

    result = {
        "implementation": implementation,
        "path": path_str,
        "env": {
            "REQUESTS_FALLBACK_FORCE": os.environ.get("REQUESTS_FALLBACK_FORCE"),
            "REQUESTS_FALLBACK_DISABLE": os.environ.get("REQUESTS_FALLBACK_DISABLE"),
        },
    }
    print(json.dumps(result, indent=2))

    if args.require_real and implementation != "real":
        return 1
    if args.require_fallback and implementation != "fallback":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())