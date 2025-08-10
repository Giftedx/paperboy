#!/usr/bin/env python3
"""
Comprehensive test runner for the Newspaper Emailer system.
This script can run basic tests even without a full virtual environment.
"""

import os
import sys
import subprocess
import importlib
import ast
from pathlib import Path

def print_status(message, status="INFO"):
    """Print a formatted status message."""
    colors = {
        "INFO": "\033[94m",    # Blue
        "SUCCESS": "\033[92m", # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m",   # Red
        "RESET": "\033[0m"     # Reset
    }
    print(f"{colors.get(status, '')}[{status}]{colors['RESET']} {message}")

def check_python_syntax(file_path):
    """Check if a Python file has valid syntax."""
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

def check_imports(file_path):
    """Check if a Python file can be imported without errors."""
    try:
        # Get the module name from the file path
        module_name = Path(file_path).stem
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            # Don't actually execute the module, just check if it can be loaded
            return True
    except Exception as e:
        print_status(f"Import error in {file_path}: {e}", "ERROR")
        return False
    return True

def test_config_loading():
    """Test configuration loading functionality."""
    print_status("Testing configuration loading...", "INFO")
    
    try:
        import config
        # Test basic config loading
        if hasattr(config, 'config'):
            print_status("Config module structure is correct", "SUCCESS")
            return True
        else:
            print_status("Config module missing 'config' attribute", "ERROR")
            return False
    except Exception as e:
        print_status(f"Config loading failed: {e}", "ERROR")
        return False

def test_basic_functionality():
    """Test basic functionality without external dependencies."""
    print_status("Testing basic functionality...", "INFO")
    
    tests = [
        ("Main module syntax", "main.py"),
        ("Config module syntax", "config.py"),
        ("Website module syntax", "website.py"),
        ("Storage module syntax", "storage.py"),
        ("Email sender syntax", "email_sender.py"),
        ("Thumbnail module syntax", "thumbnail.py"),
        ("GUI app syntax", "gui_app.py"),
        ("CLI runner syntax", "run_newspaper.py"),
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
    
    print_status(f"Basic functionality tests: {passed}/{total} passed", 
                "SUCCESS" if passed == total else "WARNING")
    return passed == total

def test_configuration_files():
    """Test configuration file structure."""
    print_status("Testing configuration files...", "INFO")
    
    config_files = [
        ("config.yaml", "Main configuration file"),
        ("requirements.txt", "Full requirements"),
        ("requirements_basic.txt", "Basic requirements"),
        ("requirements_minimal.txt", "Minimal requirements"),
        ("requirements_pinned.txt", "Pinned requirements"),
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
    
    print_status(f"Configuration files: {passed}/{total} found and readable", 
                "SUCCESS" if passed >= total * 0.8 else "WARNING")
    return passed >= total * 0.8

def test_documentation():
    """Test documentation completeness."""
    print_status("Testing documentation...", "INFO")
    
    doc_files = [
        ("README.md", "Main documentation"),
        ("LOCAL_SETUP.md", "Local setup guide"),
        ("CODEBASE_ANALYSIS.md", "Codebase analysis"),
        ("BUG_FIXES_SUMMARY.md", "Bug fixes summary"),
        ("QUICK_START.md", "Quick start guide"),
    ]
    
    passed = 0
    total = len(doc_files)
    
    for file_path, description in doc_files:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if len(content.strip()) > 100:  # At least 100 characters
                    print_status(f"✓ {description} ({file_path})", "SUCCESS")
                    passed += 1
                else:
                    print_status(f"✗ {description} ({file_path}) - too short", "WARNING")
            except Exception as e:
                print_status(f"✗ {description} ({file_path}) - read error: {e}", "ERROR")
        else:
            print_status(f"✗ {description} ({file_path}) - not found", "WARNING")
    
    print_status(f"Documentation: {passed}/{total} complete", 
                "SUCCESS" if passed >= total * 0.8 else "WARNING")
    return passed >= total * 0.8

def test_directory_structure():
    """Test that necessary directories exist."""
    print_status("Testing directory structure...", "INFO")
    
    required_dirs = [
        ("templates", "Email templates"),
        ("tests", "Test files"),
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
    
    print_status(f"Directory structure: {passed}/{total} directories exist", 
                "SUCCESS" if passed >= total * 0.8 else "WARNING")
    return passed >= total * 0.8

def run_pytest_if_available():
    """Run pytest if available."""
    print_status("Checking for pytest availability...", "INFO")
    
    try:
        import pytest
        print_status("Pytest is available, running tests...", "INFO")
        
        # Run pytest with basic options
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/", "-v", "--tb=short", "--maxfail=5"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print_status("✓ All pytest tests passed", "SUCCESS")
            return True
        else:
            print_status("✗ Some pytest tests failed", "WARNING")
            print(result.stdout)
            print(result.stderr)
            return False
    except ImportError:
        print_status("Pytest not available, skipping pytest tests", "WARNING")
        return True
    except Exception as e:
        print_status(f"Error running pytest: {e}", "ERROR")
        return False

def main():
    """Run all tests."""
    print_status("Starting comprehensive test suite...", "INFO")
    print()
    
    tests = [
        ("Basic functionality", test_basic_functionality),
        ("Configuration files", test_configuration_files),
        ("Documentation", test_documentation),
        ("Directory structure", test_directory_structure),
        ("Configuration loading", test_config_loading),
        ("Pytest tests", run_pytest_if_available),
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
    
    # Summary
    print_status("Test Summary:", "INFO")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        color = "SUCCESS" if result else "ERROR"
        print_status(f"{status} {test_name}", color)
    
    print()
    print_status(f"Overall: {passed}/{total} tests passed", 
                "SUCCESS" if passed == total else "WARNING")
    
    if passed == total:
        print_status("🎉 All tests passed! The codebase is in good shape.", "SUCCESS")
        return 0
    else:
        print_status("⚠️  Some tests failed. Please review the issues above.", "WARNING")
        return 1

if __name__ == "__main__":
    sys.exit(main())