"""
Configuration file for Bluesky Bot
"""

# AWS Configuration
AWS_REGION = 'us-east-2'  # Change to your preferred region
SSM_PARAMETER_NAME = 'BLUESKY_PASSWORD_BIKELIFE'

# Bluesky Configuration
BLUESKY_HANDLE = 'seattlebike.bsky.social'  # Replace with your actual handle

# Bot Settings
DEFAULT_TIMELINE_LIMIT = 5
IMAGE_DOWNLOAD_TIMEOUT = 10
TEMP_DIR_PREFIX = 'bluesky_images_'

# Flask Web App Settings
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
FLASK_DEBUG = True
