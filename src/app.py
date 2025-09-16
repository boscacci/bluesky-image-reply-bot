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
try:
    from .bluesky_bot import BlueskyBot
    from .ai_config import generate_ai_reply as generate_ai_reply_adapter, get_ai_config_manager
    from . import config
except ImportError:
    from bluesky_bot import BlueskyBot
    from ai_config import generate_ai_reply as generate_ai_reply_adapter, get_ai_config_manager
    import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'bluesky_app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, 
           template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'),
           static_folder=os.path.join(os.path.dirname(__file__), '..', 'static'))
CORS(app)

# Configure rate limiting with Redis storage (fallback to memory if Redis not available)
try:
    # Try to use Redis for rate limiting storage
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="redis://localhost:6379"
    )
    limiter.init_app(app)
    logger.info("Rate limiting configured with Redis storage")
except Exception as e:
    # Fallback to memory storage with warning suppression
    import warnings
    warnings.filterwarnings("ignore", message="Using the in-memory storage for tracking rate limits")
    
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
    limiter.init_app(app)
    logger.info("Rate limiting configured with in-memory storage (Redis not available)")

# Global variables for the bot instance
bluesky_bot = None
temp_dir = None

# Pagination state management - in production, this should be stored in a database or Redis
pagination_state = {}  # {session_id: {'cursor': cursor, 'seen_posts': set_of_post_uris}}

# Initialize the bot
def init_bot():
    global bluesky_bot, temp_dir
    if not bluesky_bot or not bluesky_bot.client:
        logger.info("Initializing Bluesky bot...")
        bluesky_bot = BlueskyBot()
        if bluesky_bot.initialize(config.BLUESKY_HANDLE):
            temp_dir = bluesky_bot.temp_dir
            logger.info("Bluesky bot initialized successfully")
            return True
        else:
            logger.error("Failed to initialize Bluesky bot")
            bluesky_bot = None  # Reset if initialization failed
            return False
    logger.info("Bluesky bot already initialized")
    return bluesky_bot is not None and bluesky_bot.client is not None

# Pagination state management
def get_session_id():
    """Get a unique session ID for pagination state"""
    # In production, this should use a proper session ID from Flask session
    # For now, we'll use a combination of IP and a longer time window
    import hashlib
    import time
    try:
        client_ip = request.remote_addr or 'unknown'
    except RuntimeError:
        # Working outside of request context (e.g., in streaming)
        # Try to get IP from headers if available
        try:
            client_ip = request.headers.get('X-Forwarded-For', request.headers.get('X-Real-IP', 'unknown'))
        except:
            client_ip = 'unknown'
    # Use a 30-minute window instead of 5 minutes for better session persistence
    timestamp = str(int(time.time() / 1800))  # 30-minute windows
    return hashlib.md5(f"{client_ip}_{timestamp}".encode()).hexdigest()

def get_pagination_state(session_id):
    """Get pagination state for a session"""
    if session_id not in pagination_state:
        pagination_state[session_id] = {
            'cursor': None,
            'seen_posts': set()
        }
    return pagination_state[session_id]

def update_pagination_state(session_id, cursor, new_posts):
    """Update pagination state with new cursor and seen posts"""
    state = get_pagination_state(session_id)
    state['cursor'] = cursor
    # Add new post URIs to seen posts
    for post in new_posts:
        if 'post' in post and 'uri' in post['post']:
            state['seen_posts'].add(post['post']['uri'])
    return state

# Using OpenAI API instead of local models

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
        max_fetches = request.args.get('max_fetches', 300, type=int)
        is_fetch_more = request.args.get('fetch_more', 'false').lower() == 'true'
        session_id_param = request.args.get('session_id', None)
        
        # Validate parameters
        if target_count < 1 or target_count > 18:
            return jsonify({'error': 'Count must be between 1 and 18'}), 400
        if max_posts_per_user < 1 or max_posts_per_user > 10:
            return jsonify({'error': 'Max posts per user must be between 1 and 10'}), 400
        if max_fetches < 1 or max_fetches > 2000:
            return jsonify({'error': 'max_fetches must be between 1 and 2000'}), 400
        
        # Get session ID and pagination state
        # Use provided session_id if available, otherwise generate one
        if session_id_param:
            session_id = session_id_param
        else:
            session_id = get_session_id()
        pagination_state = get_pagination_state(session_id)
        
        if is_fetch_more:
            # For fetch more, we want to get NEW posts, not replace existing ones
            # So we fetch the same number of posts but starting from where we left off
            logger.info(f"Fetching MORE {target_count} posts (max_fetches={max_fetches}) with max {max_posts_per_user} per user from followed users only (pagination mode)")
            
            result = bluesky_bot.fetch_posts_with_images_web_paginated(
                target_count=target_count,
                max_fetches=max_fetches,
                max_posts_per_user=max_posts_per_user,
                start_cursor=pagination_state['cursor'],
                seen_post_uris=pagination_state['seen_posts']
            )
            
            # Update pagination state
            update_pagination_state(session_id, result['cursor'], result['posts'])
            
            logger.info(f"Successfully fetched {len(result['posts'])} NEW posts with images from followed users (pagination mode)")
            
            return jsonify({
                'success': True,
                'posts': result['posts'],
                'count': len(result['posts']),
                'max_per_user': max_posts_per_user,
                'max_fetches': max_fetches,
                'source': 'custom_feed_followed_users_only',
                'pagination': {
                    'cursor': result['cursor'],
                    'total_checked': result['total_checked'],
                    'fetch_count': result['fetch_count']
                },
                'is_fetch_more': True
            })
        else:
            # For regular refresh, start fresh
            logger.info(f"Fetching {target_count} posts (max_fetches={max_fetches}) with max {max_posts_per_user} per user from followed users only (refresh mode)")
            
            # Reset pagination state for fresh start
            pagination_state['cursor'] = None
            pagination_state['seen_posts'] = set()
            
            result = bluesky_bot.fetch_posts_with_images_web_paginated(
                target_count=target_count,
                max_fetches=max_fetches,
                max_posts_per_user=max_posts_per_user,
                start_cursor=None,
                seen_post_uris=set()
            )
            
            # Update pagination state
            update_pagination_state(session_id, result['cursor'], result['posts'])
            
            logger.info(f"Successfully fetched {len(result['posts'])} posts with images from followed users (refresh mode)")
            
            return jsonify({
                'success': True,
                'posts': result['posts'],
                'count': len(result['posts']),
                'max_per_user': max_posts_per_user,
                'max_fetches': max_fetches,
                'source': 'custom_feed_followed_users_only',
                'pagination': {
                    'cursor': result['cursor'],
                    'total_checked': result['total_checked'],
                    'fetch_count': result['fetch_count']
                },
                'is_fetch_more': False
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
        
        # Get API usage statistics if bot is initialized
        api_stats = None
        if is_initialized and bluesky_bot:
            api_stats = bluesky_bot.get_api_usage_stats()
        
        return jsonify({
            'initialized': is_initialized,
            'temp_dir': temp_dir,
            'handle': config.BLUESKY_HANDLE,
            'timeline_source': 'custom_feed_followed_users_only',
            'version': '2.2.0',
            'status': 'ready' if is_initialized else 'initializing',
            'api_usage': api_stats
        })
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return jsonify({
            'initialized': False,
            'temp_dir': None,
            'handle': config.BLUESKY_HANDLE,
            'timeline_source': 'custom_feed_followed_users_only',
            'version': '2.2.0',
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

@app.route('/api/usage-stats')
def api_usage_stats():
    """API endpoint to get detailed API usage statistics"""
    try:
        if not init_bot():
            return jsonify({'error': 'Bot not initialized'}), 500
        
        stats = bluesky_bot.get_api_usage_stats()
        return jsonify({
            'success': True,
            'api_usage': stats,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting API usage stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset-stats', methods=['POST'])
@limiter.limit("5 per minute")
def reset_api_stats():
    """API endpoint to reset API usage statistics"""
    try:
        if not init_bot():
            return jsonify({'error': 'Bot not initialized'}), 500
        
        bluesky_bot.reset_api_stats()
        return jsonify({
            'success': True,
            'message': 'API usage statistics reset successfully',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error resetting API stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-config')
def get_ai_config():
    """API endpoint to get current AI configuration"""
    try:
        manager = get_ai_config_manager()
        config = manager.load_config()
        return jsonify({
            'success': True,
            'settings': config.to_dict()
        })
    except Exception as e:
        logger.error(f"Error getting AI config: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-config', methods=['POST'])
@limiter.limit("10 per minute")
def update_ai_config():
    """API endpoint to update AI configuration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        persona = data.get('persona')
        tone_do = data.get('tone_do')
        tone_dont = data.get('tone_dont')
        location = data.get('location')
        sample_reply_1 = data.get('sample_reply_1')
        sample_reply_2 = data.get('sample_reply_2')
        sample_reply_3 = data.get('sample_reply_3')
        
        if all(x is None for x in [persona, tone_do, tone_dont, location, sample_reply_1, sample_reply_2, sample_reply_3]):
            return jsonify({'error': 'At least one setting must be provided'}), 400
        
        manager = get_ai_config_manager()
        config = manager.load_config()
        
        if persona is not None:
            config.persona = persona
        
        if tone_do is not None:
            config.tone_do = tone_do
        
        if tone_dont is not None:
            config.tone_dont = tone_dont
        
        if location is not None:
            config.location = location
        
        if sample_reply_1 is not None:
            config.sample_reply_1 = sample_reply_1
        
        if sample_reply_2 is not None:
            config.sample_reply_2 = sample_reply_2
        
        if sample_reply_3 is not None:
            config.sample_reply_3 = sample_reply_3
        
        success = manager.save_config(config)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'AI configuration updated successfully',
                'settings': config.to_dict()
            })
        else:
            return jsonify({'error': 'Failed to save AI configuration'}), 500
            
    except Exception as e:
        logger.error(f"Error updating AI config: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-config/reset', methods=['POST'])
@limiter.limit("5 per minute")
def reset_ai_config():
    """API endpoint to reset AI configuration to defaults"""
    try:
        manager = get_ai_config_manager()
        success = manager.reset_to_defaults()
        
        if success:
            config = manager.load_config()
            return jsonify({
                'success': True,
                'message': 'AI configuration reset to defaults',
                'settings': config.to_dict()
            })
        else:
            return jsonify({'error': 'Failed to reset AI configuration'}), 500
            
    except Exception as e:
        logger.error(f"Error resetting AI config: {e}")
        return jsonify({'error': str(e)}), 500

# Removed endpoints related to local model lifecycle

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
        max_fetches = request.args.get('max_fetches', 300, type=int)
        is_fetch_more = request.args.get('fetch_more', 'false').lower() == 'true'
        session_id_param = request.args.get('session_id', None)
        
        # Validate parameters
        if target_count < 1 or target_count > 18:
            return jsonify({'error': 'Count must be between 1 and 18'}), 400
        if max_posts_per_user < 1 or max_posts_per_user > 10:
            return jsonify({'error': 'Max posts per user must be between 1 and 10'}), 400
        if max_fetches < 1 or max_fetches > 2000:
            return jsonify({'error': 'max_fetches must be between 1 and 2000'}), 400
        
        # Get session ID and pagination state from request context
        # Use provided session_id if available, otherwise generate one
        if session_id_param:
            session_id = session_id_param
        else:
            session_id = get_session_id()
        pagination_state = get_pagination_state(session_id)
        
        logger.info(f"Stream request - session_id: {session_id}, fetch_more: {is_fetch_more}, pagination_state: cursor={pagination_state['cursor'] is not None}, seen_posts={len(pagination_state['seen_posts'])}")
        
        # Store results for pagination state update after streaming
        stream_results = {'cursor': None, 'posts': []}
        
        def generate():
            try:
                
                if is_fetch_more:
                    # Send initial progress for fetch more
                    yield f"data: {json.dumps({'type': 'start', 'message': f'Fetching MORE {target_count} posts with images from followed users only (pagination mode)...', 'max_fetches': max_fetches})}\n\n"
                    
                    # Use the paginated method for fetch more
                    result = bluesky_bot.fetch_posts_with_images_web_paginated(
                        target_count=target_count,
                        max_fetches=max_fetches,
                        max_posts_per_user=max_posts_per_user,
                        start_cursor=pagination_state['cursor'],
                        seen_post_uris=pagination_state['seen_posts']
                    )
                    
                    # Store results for later pagination state update
                    stream_results['cursor'] = result['cursor']
                    stream_results['posts'] = result['posts']
                    
                    # Update pagination state immediately for fetch_more
                    update_pagination_state(session_id, result['cursor'], result['posts'])
                    logger.info(f"Updated pagination state for fetch_more - session_id: {session_id}, new cursor: {result['cursor'] is not None}, new seen_posts: {len(result.get('seen_uris', set()))}")
                    
                    # Send progress updates
                    if len(result["posts"]) > 0:
                        progress_message = f'Found {len(result["posts"])} new posts with images'
                    else:
                        progress_message = f'No new posts with images found - timeline may be exhausted'
                    yield f"data: {json.dumps({'type': 'progress', 'message': progress_message, 'posts_found': len(result['posts']), 'posts_checked': result['total_checked'], 'current_batch': result['fetch_count'], 'progress_percent': 100})}\n\n"
                    
                    # Send complete with results
                    yield f"data: {json.dumps({'type': 'complete', 'posts': result['posts'], 'count': len(result['posts']), 'is_fetch_more': True})}\n\n"
                    
                else:
                    # Send initial progress for refresh
                    yield f"data: {json.dumps({'type': 'start', 'message': f'Starting search for {target_count} posts with images from followed users only (refresh mode)...', 'max_fetches': max_fetches})}\n\n"
                    
                    # Reset pagination state for fresh start
                    pagination_state['cursor'] = None
                    pagination_state['seen_posts'] = set()
                    
                    # Use the streaming method that yields progress updates
                    for progress_update in bluesky_bot.fetch_posts_with_images_web_stream_generator(
                        target_count,
                        max_fetches=max_fetches,
                        max_posts_per_user=max_posts_per_user
                    ):
                        if progress_update['type'] == 'progress':
                            yield f"data: {json.dumps(progress_update)}\n\n"
                        elif progress_update['type'] == 'complete':
                            # Store results for later pagination state update
                            if progress_update.get('posts'):
                                stream_results['posts'] = progress_update['posts']
                                # Update pagination state immediately for regular refresh
                                update_pagination_state(session_id, progress_update.get('cursor'), progress_update['posts'])
                            yield f"data: {json.dumps(progress_update)}\n\n"
                            break
                
            except Exception as e:
                logger.error(f"Error in stream: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        # Create the streaming response
        response = Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control'
        })
        
        # Pagination state is now updated during streaming to ensure it's available for subsequent requests
        
        return response
        
    except Exception as e:
        logger.error(f"Error in get_posts_stream: {e}")
        return jsonify({'error': f'Failed to fetch posts: {str(e)}'}), 500

@app.route('/api/like', methods=['POST'])
@limiter.limit("30 per minute")
def like_post_endpoint():
    """API endpoint to like a post via AT protocol"""
    try:
        if not init_bot():
            return jsonify({'error': 'Bluesky bot not initialized'}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        post_uri = data.get('post_uri')
        if not post_uri:
            return jsonify({'error': 'post_uri is required'}), 400
        
        # Call the bot's like method
        result = bluesky_bot.like_post(post_uri)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error in like endpoint: {e}")
        return jsonify({'error': f'Failed to like post: {str(e)}'}), 500

@app.route('/api/unlike', methods=['POST'])
@limiter.limit("30 per minute")
def unlike_post_endpoint():
    """API endpoint to unlike a post via AT protocol"""
    try:
        if not init_bot():
            return jsonify({'error': 'Bluesky bot not initialized'}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        post_uri = data.get('post_uri')
        if not post_uri:
            return jsonify({'error': 'post_uri is required'}), 400
        
        # Call the bot's unlike method
        result = bluesky_bot.unlike_post(post_uri)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error in unlike endpoint: {e}")
        return jsonify({'error': f'Failed to unlike post: {str(e)}'}), 500

@app.route('/api/like-status', methods=['POST'])
@limiter.limit("60 per minute")
def get_like_status_endpoint():
    """API endpoint to get the like status of a post"""
    try:
        if not init_bot():
            return jsonify({'error': 'Bluesky bot not initialized'}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        post_uri = data.get('post_uri')
        if not post_uri:
            return jsonify({'error': 'post_uri is required'}), 400
        
        # Call the bot's refresh like status method
        result = bluesky_bot.refresh_like_status(post_uri)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error in like status endpoint: {e}")
        return jsonify({'error': f'Failed to get like status: {str(e)}'}), 500

@app.route('/api/ai-reply', methods=['POST'])
@limiter.limit("10 per minute")
def generate_ai_reply_endpoint():
    """API endpoint to generate a witty AI reply using OpenAI GPT-5 (single call)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        post_index = data.get('post_index')
        image_filenames = data.get('image_filenames', [])
        post_text = data.get('post_text', '')
        image_alt_texts = data.get('image_alt_texts', [])
        theme_config = data.get('theme_config', {})
        
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
        
        logger.info(f"Generating OpenAI GPT-5 reply with context: post_text='{post_text[:100]}...', alt_texts={image_alt_texts}")
        ai_reply = generate_ai_reply_adapter(image_paths, enhanced_context, theme_config)
        
        return jsonify({
            'success': True,
            'ai_reply': ai_reply,
            'images_processed': len(image_paths)
        })
        
    except Exception as e:
        logger.error(f"Error in generate_ai_reply: {e}")
        return jsonify({'error': f'Failed to generate AI reply: {str(e)}'}), 500


@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'bluesky-custom-feed-followed-users'
    })

# Entry point moved to main.py
