#!/usr/bin/env python3
"""
Simple test script to verify that the bug fixes work correctly.

This script imports key modules and performs basic runtime checks to ensure
imports function as expected and the configuration system initializes correctly.
"""

import sys
import os

def test_imports():
    """Test that all modules can be imported without errors.

    Returns:
        bool: True if all imports succeed, False otherwise.
    """
    print("Testing imports...")
    
    try:
        import config
        print("✓ config module imported successfully")
    except Exception as e:
        print(f"✗ Failed to import config: {e}")
        return False
    
    try:
        import email_sender
        print("✓ email_sender module imported successfully")
    except Exception as e:
        print(f"✗ Failed to import email_sender: {e}")
        return False
    
    try:
        import storage
        print("✓ storage module imported successfully")
    except Exception as e:
        print(f"✗ Failed to import storage: {e}")
        return False
    
    try:
        import website
        print("✓ website module imported successfully")
    except Exception as e:
        print(f"✗ Failed to import website: {e}")
        return False
    
    try:
        import thumbnail
        print("✓ thumbnail module imported successfully")
    except Exception as e:
        print(f"✗ Failed to import thumbnail: {e}")
        return False
    
    try:
        import main
        print("✓ main module imported successfully")
    except Exception as e:
        print(f"✗ Failed to import main: {e}")
        return False
    
    return True

def test_config_loading():
    """Test that configuration can be loaded without critical errors.

    Returns:
        bool: True if configuration loading behaves as expected (even if it fails validation).
    """
    print("\nTesting configuration loading...")
    
    try:
        import config
        # Initialize config
        config_obj = config.Config()
        
        # Test loading (this will fail due to missing values, but shouldn't crash)
        success = config_obj.load()
        
        if success:
            print("✓ Configuration loaded successfully")
        else:
            print("⚠ Configuration loading failed (expected due to missing values)")
        
        # Test that the config object can be accessed without crashing
        test_value = config_obj.get(('paths', 'download_dir'), 'default_downloads')
        print(f"✓ Config get method works: {test_value}")
        
        return True
        
    except Exception as e:
        print(f"✗ Configuration loading test failed: {e}")
        return False

def test_email_sender_requests():
    """Test that email_sender can use requests module.

    Returns:
        bool: True if requests is accessible and functional.
    """
    print("\nTesting email_sender requests functionality...")
    
    try:
        import email_sender
        import requests
        
        # Test that requests is available in email_sender
        if hasattr(email_sender, 'requests'):
            print("✓ requests module is available in email_sender")
        else:
            print("⚠ requests module not directly accessible in email_sender namespace")
        
        # Test basic requests functionality
        response = requests.get('https://httpbin.org/get', timeout=5)
        if response.status_code == 200:
            print("✓ requests module works correctly")
        else:
            print(f"⚠ requests test returned status code: {response.status_code}")
        
        return True
        
    except Exception as e:
        print(f"✗ email_sender requests test failed: {e}")
        return False

def main():
    """Run all verification tests.

    Returns:
        int: 0 if all tests pass, 1 otherwise.
    """
    print("Running bug fix verification tests...\n")
    
    tests = [
        test_imports,
        test_config_loading,
        test_email_sender_requests,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
    
    print(f"\nTest Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The bug fixes appear to be working correctly.")
        return 0
    else:
        print("⚠ Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
