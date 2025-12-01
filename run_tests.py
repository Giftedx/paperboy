#!/usr/bin/env python3
"""
Comprehensive test runner for the simplified Newspaper Emailer system.

This script runs basic static checks and environment diagnostics
without external dependencies.
"""

import os
import sys
import ast
from pathlib import Path


def print_status(message, status="INFO"):
    """Prints a status message with color coding.

    Args:
        message (str): The message to print.
        status (str): The status level ('INFO', 'SUCCESS', 'WARNING', 'ERROR').
    """
    colors = {
        "INFO": "\033[94m",
        "SUCCESS": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "RESET": "\033[0m",
    }
    print(f"{colors.get(status, '')}[{status}]{colors['RESET']} {message}")


def check_python_syntax(file_path):
    """Checks if a file contains valid Python syntax.

    Args:
        file_path (str): Path to the Python file.

    Returns:
        bool: True if syntax is valid, False otherwise.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        return True
    except SyntaxError as e:
        print_status(f"Syntax error in {file_path}: {e}", "ERROR")
        return False
    except Exception as e:
        print_status(f"Error reading {file_path}: {e}", "ERROR")
        return False


def test_basic_functionality():
    """Runs syntax checks on key source files.

    Returns:
        bool: True if all files pass syntax checks.
    """
    print_status("Testing basic functionality...", "INFO")
    tests = [
        ("Main module syntax", "main.py"),
        ("Config module syntax", "config.py"),
        ("Website module syntax", "website.py"),
        ("Storage module syntax", "storage.py"),
        ("Email sender syntax", "email_sender.py"),
        ("Thumbnail module syntax", "thumbnail.py"),
    ]
    passed = 0
    total = len(tests)
    for test_name, file_path in tests:
        if os.path.exists(file_path):
            if check_python_syntax(file_path):
                print_status(f"✓ {test_name}", "SUCCESS")
                passed += 1
            else:
                print_status(f"✗ {test_name}", "ERROR")
        else:
            print_status(f"✗ {test_name} (file not found)", "ERROR")
    print_status(
        f"Basic functionality tests: {passed}/{total} passed",
        "SUCCESS" if passed == total else "WARNING",
    )
    return passed == total


def test_configuration_files():
    """Checks for the existence and readability of configuration files.

    Returns:
        bool: True if critical config files exist and are readable.
    """
    print_status("Testing configuration files...", "INFO")
    config_files = [
        ("config.yaml", "Main configuration file"),
        ("requirements.txt", "Requirements"),
    ]
    passed = 0
    total = len(config_files)
    for file_path, description in config_files:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content.strip():
                    print_status(f"✓ {description} ({file_path})", "SUCCESS")
                    passed += 1
                else:
                    print_status(f"✗ {description} ({file_path}) - empty file", "WARNING")
            except Exception as e:
                print_status(f"✗ {description} ({file_path}) - read error: {e}", "ERROR")
        else:
            print_status(f"✗ {description} ({file_path}) - not found", "WARNING")
    print_status(
        f"Configuration files: {passed}/{total} found and readable",
        "SUCCESS" if passed >= total * 0.8 else "WARNING",
    )
    return passed >= total * 0.8


def test_directory_structure():
    """Verifies that required directories exist.

    Returns:
        bool: True if required directories exist.
    """
    print_status("Testing directory structure...", "INFO")
    required_dirs = [
        ("templates", "Email templates"),
        ("logs", "Log files"),
    ]
    passed = 0
    total = len(required_dirs)
    for dir_path, description in required_dirs:
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            print_status(f"✓ {description} ({dir_path})", "SUCCESS")
            passed += 1
        else:
            print_status(f"✗ {description} ({dir_path}) - not found", "WARNING")
    print_status(
        f"Directory structure: {passed}/{total} directories exist",
        "SUCCESS" if passed >= total * 0.8 else "WARNING",
    )
    return passed >= total * 0.8


def environment_diagnostics():
    """Checks the environment for dependencies, specifically 'requests'.

    Returns:
        bool: Always True (diagnostic only).
    """
    print_status("Environment diagnostics...", "INFO")
    try:
        import requests  # type: ignore
        path = getattr(requests, '__file__', None)
        path_str = str(path) if path else 'builtin'
        is_fallback = False
        try:
            resolved = str(Path(path_str).resolve()) if path else path_str
            is_fallback = (Path(resolved).name == 'requests.py') and ('site-packages' not in resolved)
            path_str = resolved
        except Exception:
            pass
        impl = 'fallback' if is_fallback else 'real'
        print_status(f"requests implementation: {impl} ({path_str})", "INFO")
    except Exception as e:
        print_status(f"requests import failed: {e}", "WARNING")
    return True


def main():
    """Main entry point for the test runner.

    Returns:
        int: Exit code (0 for pass, 1 for fail).
    """
    print_status("Starting simplified test suite...", "INFO")
    print()

    tests = [
        ("Basic functionality", test_basic_functionality),
        ("Configuration files", test_configuration_files),
        ("Directory structure", test_directory_structure),
        ("Environment diagnostics", environment_diagnostics),
    ]

    results = []
    for test_name, test_func in tests:
        print_status(f"Running {test_name}...", "INFO")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print_status(f"Test {test_name} failed with exception: {e}", "ERROR")
            results.append((test_name, False))
        print()

    print_status("Test Summary:", "INFO")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        color = "SUCCESS" if result else "ERROR"
        print_status(f"{status} {test_name}", color)

    print()
    print_status(
        f"Overall: {passed}/{total} tests passed",
        "SUCCESS" if passed == total else "WARNING",
    )

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())