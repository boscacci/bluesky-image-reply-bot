#!/usr/bin/env python3
"""
Test Runner for Bluesky Bot System
Provides easy commands to run different types of tests
"""

import sys
import subprocess
import argparse


def run_command(cmd):
    """Run a command and return the result"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description='Run integration tests for Bluesky Bot System')
    parser.add_argument('--slow', action='store_true', 
                       help='Include slow tests')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Verbose output')
    
    args = parser.parse_args()
    
    # Base pytest command
    cmd = ['python3', '-m', 'pytest']
    
    if args.verbose:
        cmd.append('-v')
    
    # Add integration test filter
    cmd.extend(['-m', 'integration'])
    
    # Add slow tests if requested
    if args.slow:
        cmd.extend(['-m', 'integration or slow'])
    
    # Add test file
    cmd.append('tests/test_integration.py')
    
    # Run the tests
    exit_code = run_command(cmd)
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
