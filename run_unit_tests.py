#!/usr/bin/env python3
"""
Simple test runner for unit tests
Runs unit tests without external dependencies
"""

import sys
import os
import subprocess

def run_unit_tests():
    """Run unit tests only"""
    print("🧪 Running unit tests...")
    
    # Add src to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
    
    try:
        # Run pytest with unit tests only
        cmd = [
            sys.executable, '-m', 'pytest', 
            'tests/test_unit.py',
            'tests/test_flask_unit.py',
            '-v',
            '--tb=short',
            '-m', 'unit'
        ]
        
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=False)
        
        if result.returncode == 0:
            print("\n✅ All unit tests passed!")
        else:
            print("\n❌ Some unit tests failed!")
        
        return result.returncode
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(run_unit_tests())
