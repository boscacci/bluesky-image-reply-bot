#!/usr/bin/env python3
"""
Flask Web App for Bluesky Timeline with Images
"""

import os
import tempfile
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path
import boto3
from atproto import Client, models
from PIL import Image
import json
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, send_file, request, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sys
import os
import base64
import io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from bluesky_bot.bluesky_bot import BlueskyBot
from qwen_vl_integration import generate_qwen_response
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bluesky_app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configure rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# Global variables for the bot instance
bluesky_bot = None
temp_dir = None

# Initialize the bot
def init_bot():
    global bluesky_bot, temp_dir
    if not bluesky_bot:
        bluesky_bot = BlueskyBot()
        if bluesky_bot.initialize(config.BLUESKY_HANDLE):
            temp_dir = bluesky_bot.temp_dir
            return True
    return bluesky_bot is not None

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/posts')
@limiter.limit("10 per minute")
def get_posts():
    """API endpoint to fetch posts with images from followed users only (includes reposts from followed users)"""
    try:
        if not init_bot():
            logger.error("Failed to initialize Bluesky bot")
            return jsonify({'error': 'Failed to initialize Bluesky bot. Please check your credentials and try again.'}), 500
        
        target_count = request.args.get('count', 6, type=int)
        max_posts_per_user = request.args.get('max_per_user', 1, type=int)
        
        # Validate parameters
        if target_count < 1 or target_count > 18:
            return jsonify({'error': 'Count must be between 1 and 18'}), 400
        if max_posts_per_user < 1 or max_posts_per_user > 1:
            return jsonify({'error': 'Max posts per user must be 1'}), 400
        
        logger.info(f"Fetching {target_count} posts with max {max_posts_per_user} per user from followed users only (includes reposts from followed users)")
        posts = bluesky_bot.fetch_posts_with_images_web(target_count, max_posts_per_user=max_posts_per_user)
        
        logger.info(f"Successfully fetched {len(posts)} posts with images from followed users")
        
        return jsonify({
            'success': True,
            'posts': posts,
            'count': len(posts),
            'max_per_user': max_posts_per_user,
            'source': 'custom_feed_followed_users_only'
        })
    except Exception as e:
        logger.error(f"Error in get_posts: {e}")
        return jsonify({'error': f'Failed to fetch posts: {str(e)}'}), 500

@app.route('/api/image/<filename>')
@limiter.limit("100 per minute")
def serve_image(filename):
    """Serve images from temporary directory with security checks"""
    try:
        if not temp_dir:
            logger.error("No temporary directory available")
            return jsonify({'error': 'No temporary directory available'}), 404
        
        # Security check: prevent directory traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            logger.warning(f"Attempted directory traversal with filename: {filename}")
            return jsonify({'error': 'Invalid filename'}), 400
        
        image_path = os.path.join(temp_dir, filename)
        
        # Additional security check
        if not os.path.exists(image_path) or not os.path.isfile(image_path):
            logger.warning(f"Image not found: {filename}")
            return jsonify({'error': 'Image not found'}), 404
        
        # Check if file is within temp directory (prevent directory traversal)
        if not os.path.abspath(image_path).startswith(os.path.abspath(temp_dir)):
            logger.warning(f"Attempted access outside temp directory: {filename}")
            return jsonify({'error': 'Access denied'}), 403
        
        return send_file(image_path)
    except Exception as e:
        logger.error(f"Error serving image {filename}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def status():
    """API endpoint to check bot status"""
    try:
        # Try to initialize if not already done
        is_initialized = init_bot()
        
        return jsonify({
            'initialized': is_initialized,
            'temp_dir': temp_dir,
            'handle': config.BLUESKY_HANDLE,
            'timeline_source': 'custom_feed_followed_users_only',
            'version': '2.1.0',
            'status': 'ready' if is_initialized else 'initializing'
        })
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return jsonify({
            'initialized': False,
            'temp_dir': None,
            'handle': config.BLUESKY_HANDLE,
            'timeline_source': 'custom_feed_followed_users_only',
            'version': '2.1.0',
            'status': 'error',
            'error': str(e)
        })

@app.route('/api/user')
def user_info():
    """API endpoint to get current user information"""
    try:
        return jsonify({
            'handle': config.BLUESKY_HANDLE,
            'display_name': config.BLUESKY_HANDLE.split('.')[0].replace('_', ' ').title(),
            'domain': config.BLUESKY_HANDLE.split('.')[1] if '.' in config.BLUESKY_HANDLE else 'bsky.social'
        })
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/posts/stream')
@limiter.limit("5 per minute")
def get_posts_stream():
    """API endpoint to fetch posts with images with real-time progress updates (includes reposts from followed users)"""
    try:
        if not init_bot():
            logger.error("Failed to initialize Bluesky bot")
            return jsonify({'error': 'Failed to initialize Bluesky bot. Please check your credentials and try again.'}), 500
        
        target_count = request.args.get('count', 6, type=int)
        max_posts_per_user = request.args.get('max_per_user', 1, type=int)
        
        # Validate parameters
        if target_count < 1 or target_count > 18:
            return jsonify({'error': 'Count must be between 1 and 18'}), 400
        if max_posts_per_user < 1 or max_posts_per_user > 1:
            return jsonify({'error': 'Max posts per user must be 1'}), 400
        
        def generate():
            try:
                # Send initial progress
                yield f"data: {json.dumps({'type': 'start', 'message': f'Starting search for {target_count} posts with images from followed users only (includes reposts from followed users)...'})}\n\n"
                
                # Use the streaming method that yields progress updates
                for progress_update in bluesky_bot.fetch_posts_with_images_web_stream_generator(
                    target_count, 
                    max_posts_per_user=max_posts_per_user
                ):
                    if progress_update['type'] == 'progress':
                        yield f"data: {json.dumps(progress_update)}\n\n"
                    elif progress_update['type'] == 'complete':
                        yield f"data: {json.dumps(progress_update)}\n\n"
                        break
                
            except Exception as e:
                logger.error(f"Error in stream: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control'
        })
        
    except Exception as e:
        logger.error(f"Error in get_posts_stream: {e}")
        return jsonify({'error': f'Failed to fetch posts: {str(e)}'}), 500

@app.route('/api/magic-response', methods=['POST'])
@limiter.limit("10 per minute")
def generate_magic_response():
    """API endpoint to generate witty AI responses to images using Qwen-VL-chat-7B"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        post_index = data.get('post_index')
        image_filenames = data.get('image_filenames', [])
        post_text = data.get('post_text', '')
        image_alt_texts = data.get('image_alt_texts', [])
        
        if post_index is None:
            return jsonify({'error': 'post_index is required'}), 400
        
        if not image_filenames:
            return jsonify({'error': 'No image filenames provided'}), 400
        
        if not temp_dir:
            logger.error("No temporary directory available")
            return jsonify({'error': 'No temporary directory available'}), 500
        
        # Validate and prepare images
        image_paths = []
        for filename in image_filenames:
            # Security check: prevent directory traversal
            if '..' in filename or '/' in filename or '\\' in filename:
                logger.warning(f"Attempted directory traversal with filename: {filename}")
                continue
            
            image_path = os.path.join(temp_dir, filename)
            
            # Additional security check
            if not os.path.exists(image_path) or not os.path.isfile(image_path):
                logger.warning(f"Image not found: {filename}")
                continue
            
            # Check if file is within temp directory (prevent directory traversal)
            if not os.path.abspath(image_path).startswith(os.path.abspath(temp_dir)):
                logger.warning(f"Attempted access outside temp directory: {filename}")
                continue
            
            image_paths.append(image_path)
        
        if not image_paths:
            return jsonify({'error': 'No valid images found'}), 400
        
        # Prepare enhanced context for the AI model
        enhanced_context = {
            'post_text': post_text,
            'image_alt_texts': image_alt_texts,
            'image_count': len(image_paths)
        }
        
        logger.info(f"Generating smart reply with context: post_text='{post_text[:100]}...', alt_texts={image_alt_texts}")
        
        # Generate smart reply using Qwen-VL-chat-7B with enhanced context
        magic_response = generate_qwen_response(image_paths, enhanced_context)
        
        return jsonify({
            'success': True,
            'magic_response': magic_response,
            'images_processed': len(image_paths)
        })
        
    except Exception as e:
        logger.error(f"Error in generate_magic_response: {e}")
        return jsonify({'error': f'Failed to generate magic response: {str(e)}'}), 500


@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'bluesky-custom-feed-followed-users'
    })

if __name__ == '__main__':
    app.run(debug=config.FLASK_DEBUG, host=config.FLASK_HOST, port=config.FLASK_PORT)
