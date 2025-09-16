#!/usr/bin/env python3
"""
Main entry point for the Bluesky Timeline Flask App
"""

import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app import app, init_models
from config import FLASK_DEBUG, FLASK_HOST, FLASK_PORT

if __name__ == '__main__':
    print("🚀 Starting Bluesky Timeline Flask App...")
    print("📱 Open your browser and go to: http://localhost:5000")
    print("🔄 Press Ctrl+C to stop the server")
    print("-" * 50)
    
    # Start AI models loading in the background (non-blocking)
    print("🤖 Starting AI models loading in background...")
    try:
        init_models()
        print("✅ AI models loading started in background")
        print("💡 You can use the UI immediately while models load!")
    except Exception as e:
        print(f"⚠️  AI models will be loaded on first use: {e}")
    
    print("🌐 Flask app starting...")
    app.run(debug=FLASK_DEBUG, host=FLASK_HOST, port=FLASK_PORT)
