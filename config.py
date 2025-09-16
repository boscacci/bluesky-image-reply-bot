"""
Configuration file for Flask App - imports from src/bluesky_bot/config.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import all config from the bluesky_bot config
from bluesky_bot.config import *
