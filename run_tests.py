#!/usr/bin/env python3
"""
Test runner script for JIRA Time Tracker
"""

import subprocess
import sys
import os


def run_tests():
    """Run all tests with coverage reporting"""
    print("🧪 Running JIRA Time Tracker Tests...")
    print("=" * 50)
    
    # Check if pytest is installed
    try:
        import pytest
        import responses
    except ImportError:
        print("❌ Missing test dependencies. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    
    # Run tests
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "test_jira_time_tracker.py",
            "-v",
            "--tb=short"
        ], check=False)
        
        if result.returncode == 0:
            print("\n✅ All tests passed!")
        else:
            print(f"\n❌ Tests failed with return code: {result.returncode}")
            
        return result.returncode
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1


def run_specific_test(test_name):
    """Run a specific test"""
    print(f"🧪 Running specific test: {test_name}")
    print("=" * 50)
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            f"test_jira_time_tracker.py::{test_name}",
            "-v",
            "--tb=short"
        ], check=False)
        
        return result.returncode
        
    except Exception as e:
        print(f"❌ Error running test: {e}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run specific test
        test_name = sys.argv[1]
        exit_code = run_specific_test(test_name)
    else:
        # Run all tests
        exit_code = run_tests()
    
    sys.exit(exit_code)