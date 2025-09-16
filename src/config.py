"""
Configuration file for Flask App
"""

import os

# AWS Configuration
AWS_REGION = os.getenv('AWS_REGION', 'us-east-2')  # Change to your preferred region
SSM_PARAMETER_NAME = 'BLUESKY_PASSWORD_BIKELIFE'

# Bluesky Configuration - supports environment variable fallback for CI
BLUESKY_HANDLE = os.getenv('BLUESKY_HANDLE', 'seattlebike.life')  # Replace with your actual handle

# Environment variable fallbacks for CI/GitHub Actions
BLUESKY_PASSWORD_ENV = os.getenv('BLUESKY_PASSWORD_BIKELIFE')

# Bot Settings
DEFAULT_TIMELINE_LIMIT = 5
IMAGE_DOWNLOAD_TIMEOUT = 10
TEMP_DIR_PREFIX = 'bluesky_images_'

# Flask Web App Settings
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
FLASK_DEBUG = True
