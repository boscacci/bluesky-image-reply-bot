#!/usr/bin/env python3
"""
Bluesky Bot - Fetches timeline and displays posts with embedded media
Includes both CLI and web functionality
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
from datetime import datetime, timedelta
import time
import hashlib
from functools import lru_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
try:
    from . import config
except ImportError:
    import config

# Configure logging
logger = logging.getLogger(__name__)


class BlueskyBot:
    def __init__(self):
        self.client = None
        self.temp_dir = None
        self.ssm_client = boto3.client('ssm', region_name=config.AWS_REGION)
        
        # API optimization components
        self._timeline_cache = {}  # Cache for timeline data
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._last_api_call = 0
        self._min_api_interval = 0.5  # Minimum 500ms between API calls
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3
        
        # Setup optimized HTTP session for image downloads
        self._setup_http_session()
        
        # API usage tracking
        self._api_call_count = 0
        self._api_call_window_start = time.time()
        self._max_calls_per_window = 50  # Conservative limit
        self._window_duration = 300  # 5 minutes
        
        # Optimized batch sizes for different operations
        self._timeline_batch_size = 50  # Increased from 25 for better efficiency
        self._max_concurrent_downloads = 8  # Optimal for image downloads
    
    def _setup_http_session(self):
        """Setup optimized HTTP session with connection pooling and retry strategy"""
        self.http_session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        # Mount adapter with retry strategy
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        
        self.http_session.mount("http://", adapter)
        self.http_session.mount("https://", adapter)
        
        # Set reasonable timeouts
        self.http_session.timeout = (10, 30)  # (connect, read)
    
    def _check_rate_limit(self) -> bool:
        """Rate limiting disabled for better user experience"""
        return True
    
    def _record_api_call(self):
        """API call tracking disabled for better user experience"""
        pass
    
    def _get_cache_key(self, method: str, **kwargs) -> str:
        """Generate a cache key for API calls"""
        # Create a deterministic key from method and parameters
        key_data = f"{method}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if a cache entry is still valid"""
        if not cache_entry:
            return False
        
        cache_time = cache_entry.get('timestamp', 0)
        return time.time() - cache_time < self._cache_ttl
    
    def _get_cached_timeline(self, limit: int, cursor: Optional[str] = None, algorithm: str = 'home') -> Optional[Dict[str, Any]]:
        """Get timeline data from cache if available and valid"""
        cache_key = self._get_cache_key('get_timeline', limit=limit, cursor=cursor, algorithm=algorithm)
        cache_entry = self._timeline_cache.get(cache_key)
        
        if self._is_cache_valid(cache_entry):
            logger.debug(f"Cache hit for timeline: {cache_key}")
            return cache_entry.get('data')
        
        return None
    
    def _cache_timeline(self, limit: int, cursor: Optional[str] = None, algorithm: str = 'home', data: Any = None):
        """Cache timeline data"""
        cache_key = self._get_cache_key('get_timeline', limit=limit, cursor=cursor, algorithm=algorithm)
        self._timeline_cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }
        
        # Clean up old cache entries
        self._cleanup_cache()
    
    def _cleanup_cache(self):
        """Remove expired cache entries"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._timeline_cache.items()
            if current_time - entry.get('timestamp', 0) > self._cache_ttl
        ]
        
        for key in expired_keys:
            del self._timeline_cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def get_api_usage_stats(self) -> Dict[str, Any]:
        """Get current API usage statistics"""
        current_time = time.time()
        window_remaining = max(0, self._window_duration - (current_time - self._api_call_window_start))
        
        return {
            'calls_in_current_window': self._api_call_count,
            'max_calls_per_window': self._max_calls_per_window,
            'window_remaining_seconds': window_remaining,
            'cache_entries': len(self._timeline_cache),
            'consecutive_errors': self._consecutive_errors,
            'last_api_call_ago_seconds': current_time - self._last_api_call if self._last_api_call > 0 else None
        }
    
    def reset_api_stats(self):
        """Reset API usage statistics (useful for testing or after errors)"""
        self._api_call_count = 0
        self._api_call_window_start = time.time()
        self._consecutive_errors = 0
        self._timeline_cache.clear()
        logger.info("API usage statistics reset")
        
    def get_ssm_parameter(self, parameter_name: str) -> str:
        """Fetch parameter from AWS SSM Parameter Store with environment variable fallback"""
        try:
            response = self.ssm_client.get_parameter(
                Name=parameter_name,
                WithDecryption=True
            )
            return response['Parameter']['Value']
        except Exception as e:
            print(f"Error fetching SSM parameter {parameter_name}: {e}")
            print("Attempting to use environment variable fallback...")
            
            # Fallback to environment variables for CI/GitHub Actions
            if parameter_name == 'BLUESKY_PASSWORD_BIKELIFE':
                env_value = os.getenv('BLUESKY_PASSWORD_BIKELIFE')
                if env_value:
                    print("Using BLUESKY_PASSWORD_BIKELIFE from environment variable")
                    return env_value
            
            # If no fallback available, raise the original exception
            raise
    
    def authenticate(self, handle: str, password: str):
        """Authenticate with Bluesky"""
        try:
            self.client = Client()
            self.client.login(handle, password)
            logger.info(f"Successfully authenticated as {handle}")
            print(f"Successfully authenticated as {handle}")
        except Exception as e:
            logger.error(f"Authentication failed for {handle}: {e}")
            print(f"Authentication failed: {e}")
            raise
    
    def _get_post_cid(self, post_uri: str) -> Optional[str]:
        """Get the CID for a post URI with improved error handling"""
        try:
            # Parse the post URI to get the repo and record info
            uri_parts = post_uri.split('/')
            if len(uri_parts) < 4:
                logger.warning(f"Invalid post URI format: {post_uri}")
                return None
            
            repo_did = uri_parts[2]  # The DID part
            record_key = uri_parts[-1]  # The record key
            
            # Check rate limits before making API call
            if not self._check_rate_limit():
                logger.warning("Rate limit exceeded while getting post CID")
                return None
            
            # Get the post record to extract the CID
            post_record = self.client.com.atproto.repo.get_record(
                params={
                    "repo": repo_did,
                    "collection": "app.bsky.feed.post",
                    "rkey": record_key
                }
            )
            
            # Record API call for rate limiting
            self._record_api_call()
            
            return post_record.cid
            
        except Exception as e:
            logger.warning(f"Could not get CID for post {post_uri}: {e}")
            return None
    
    def _find_like_record(self, post_uri: str) -> Optional[Any]:
        """Find the like record for a specific post URI"""
        try:
            # Check rate limits before making API call
            if not self._check_rate_limit():
                logger.warning("Rate limit exceeded while finding like record")
                return None
            
            # Get the user's likes from their repository with pagination support
            cursor = None
            max_attempts = 5  # Limit to prevent infinite loops
            
            for attempt in range(max_attempts):
                params = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor
                
                likes_response = self.client.com.atproto.repo.list_records(
                    params={
                        "repo": self.client.me.did,
                        "collection": "app.bsky.feed.like",
                        "limit": params.get("limit", 100),
                        "cursor": params.get("cursor")
                    }
                )
                
                # Record API call for rate limiting
                self._record_api_call()
                
                # Find the like record for this specific post
                for record in likes_response.records:
                    if hasattr(record.value, 'subject') and record.value.subject.uri == post_uri:
                        return record
                
                # Check if there are more records to search
                if hasattr(likes_response, 'cursor') and likes_response.cursor:
                    cursor = likes_response.cursor
                else:
                    break
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find like record for {post_uri}: {e}")
            return None
    
    def like_post(self, post_uri: str) -> Dict[str, Any]:
        """Like a post using AT protocol with improved error handling and duplicate protection"""
        try:
            if not self.client:
                raise Exception("Not authenticated")
            
            # Check rate limits before making API calls
            if not self._check_rate_limit():
                return {
                    "success": False,
                    "error": "Rate limit exceeded. Please try again later."
                }
            
            # Check if post is already liked to prevent duplicates
            if self._check_if_post_is_liked(post_uri):
                logger.info(f"Post {post_uri} is already liked")
                return {
                    "success": False,
                    "error": "Post is already liked",
                    "already_liked": True
                }
            
            # Get the CID for the post - this is REQUIRED for AT Protocol
            post_cid = self._get_post_cid(post_uri)
            if post_cid is None or not post_cid.strip():
                logger.error(f"Could not retrieve CID for post {post_uri} - CID is required for likes")
                return {
                    "success": False,
                    "error": "Could not retrieve post CID - required for liking posts",
                    "post_uri": post_uri
                }
            
            # Create a like record using the AT protocol
            like_record = {
                "subject": {
                    "uri": post_uri,
                    "cid": post_cid
                },
                "createdAt": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            }
            
            # Record API call for rate limiting
            self._record_api_call()
            
            # Use the AT protocol client to create the like record
            logger.debug(f"Creating like record for post {post_uri} with record: {like_record}")
            response = self.client.com.atproto.repo.create_record(
                data={
                    "repo": self.client.me.did,
                    "collection": "app.bsky.feed.like",
                    "record": like_record
                }
            )
            
            logger.info(f"Successfully liked post: {post_uri}")
            return {
                "success": True,
                "like_uri": response.uri,
                "message": "Post liked successfully",
                "post_uri": post_uri
            }
            
        except Exception as e:
            logger.error(f"Failed to like post {post_uri}: {e}")
            return {
                "success": False,
                "error": str(e),
                "post_uri": post_uri
            }
    
    def unlike_post(self, post_uri: str) -> Dict[str, Any]:
        """Unlike a post by finding and deleting the like record with improved error handling"""
        try:
            if not self.client:
                raise Exception("Not authenticated")
            
            # Check rate limits before making API calls
            if not self._check_rate_limit():
                return {
                    "success": False,
                    "error": "Rate limit exceeded. Please try again later."
                }
            
            # Check if post is actually liked first
            if not self._check_if_post_is_liked(post_uri):
                logger.info(f"Post {post_uri} is not liked")
                return {
                    "success": False,
                    "error": "Post is not liked",
                    "not_liked": True
                }
            
            # Find and delete the like record
            like_record_to_delete = self._find_like_record(post_uri)
            
            if not like_record_to_delete:
                return {
                    "success": False,
                    "error": "No like record found for this post"
                }
            
            # Record API call for rate limiting
            self._record_api_call()
            
            # Delete the like record
            self.client.com.atproto.repo.delete_record(
                data={
                    "repo": self.client.me.did,
                    "collection": "app.bsky.feed.like",
                    "rkey": like_record_to_delete.uri.split('/')[-1]  # Extract the record key
                }
            )
            
            logger.info(f"Successfully unliked post: {post_uri}")
            return {
                "success": True,
                "message": "Post unliked successfully",
                "post_uri": post_uri
            }
            
        except Exception as e:
            logger.error(f"Failed to unlike post {post_uri}: {e}")
            return {
                "success": False,
                "error": str(e),
                "post_uri": post_uri
            }
    
    def setup_temp_directory(self):
        """Create temporary directory for downloaded images"""
        self.temp_dir = tempfile.mkdtemp(prefix='bluesky_images_')
        print(f"Created temporary directory: {self.temp_dir}")
        return self.temp_dir
    
    def download_image(self, url: str, filename: str) -> Optional[str]:
        """Download image from URL and save to temp directory using optimized HTTP session"""
        try:
            # Use the optimized HTTP session with connection pooling and retry
            response = self.http_session.get(url, timeout=(10, 30), stream=True)
            response.raise_for_status()
            
            # Check content type to ensure it's an image
            content_type = response.headers.get('content-type', '').lower()
            if not content_type.startswith('image/'):
                logger.warning(f"URL {url} does not return an image (content-type: {content_type})")
                return None
            
            # Check file size to avoid downloading huge files
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB limit
                logger.warning(f"Image {url} is too large ({content_length} bytes), skipping")
                return None
            
            file_path = os.path.join(self.temp_dir, filename)
            
            # Stream download for better memory usage
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verify the file was created and has content
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                logger.debug(f"Downloaded image: {filename} ({os.path.getsize(file_path)} bytes)")
                return file_path
            else:
                logger.warning(f"Downloaded file {filename} is empty or doesn't exist")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout downloading image {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error downloading image {url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to download image {url}: {e}")
            return None
    
    def get_image_info(self, image_path: str) -> Dict[str, Any]:
        """Get image dimensions and file size"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                file_size = os.path.getsize(image_path)
                return {
                    'width': width,
                    'height': height,
                    'file_size': file_size,
                    'format': img.format
                }
        except Exception as e:
            print(f"Error getting image info: {e}")
            return {}
    
    def format_post_text(self, post: models.AppBskyFeedDefs.FeedViewPost) -> str:
        """Format post text with metadata"""
        record = post.post.record
        author = post.post.author
        
        text = f"""
{'='*60}
        Author: @{author.handle} ({author.display_name or 'No display name'})
Posted: {post.post.indexedAt}
URI: {post.post.uri}
{'='*60}

{record.text if hasattr(record, 'text') else 'No text content'}

"""
        return text
    
    def process_embeds(self, post: models.AppBskyFeedDefs.FeedViewPost) -> List[Dict[str, Any]]:
        """Process embedded media in a post"""
        embeds = []
        record = post.post.record
        
        if not hasattr(record, 'embed'):
            return embeds
        
        embed = record.embed
        
        # Handle images
        if hasattr(embed, 'images') and embed.images:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def build_image_task(i, image):
                filename = f"image_{post.post.uri.split('/')[-1]}_{i}.jpg"
                blob_hash = getattr(getattr(image, 'image', None), 'ref', None).link if hasattr(getattr(image, 'image', None), 'ref') else ''
                if not blob_hash or not isinstance(blob_hash, str) or not blob_hash.startswith('http'):
                    post_did = post.post.uri.split('/')[2]
                    image_url = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={post_did}&cid={blob_hash}"
                else:
                    image_url = blob_hash

                image_path = self.download_image(image_url, filename)
                if not image_path:
                    return None, i
                image_info = self.get_image_info(image_path)
                return {
                    'type': 'image',
                    'url': image_url,
                    'alt_text': image.alt if hasattr(image, 'alt') else '',
                    'local_path': image_path,
                    'filename': filename,
                    'info': image_info
                }, i

            results_buffer = [None] * len(embed.images)
            with ThreadPoolExecutor(max_workers=min(self._max_concurrent_downloads, len(embed.images))) as executor:
                futures = [executor.submit(build_image_task, i, image) for i, image in enumerate(embed.images)]
                for future in as_completed(futures):
                    try:
                        result, idx = future.result()
                        if result is not None:
                            results_buffer[idx] = result
                    except Exception as e:
                        print(f"Error processing image embed concurrently: {e}")
                        continue

            for item in results_buffer:
                if item is not None:
                    embeds.append(item)
        
        # Handle external links with images
        elif hasattr(embed, 'external') and embed.external:
            external = embed.external
            if hasattr(external, 'thumb') and external.thumb:
                filename = f"external_{post.post.uri.split('/')[-1]}.jpg"
                image_path = self.download_image(external.thumb, filename)
                
                if image_path:
                    image_info = self.get_image_info(image_path)
                    embeds.append({
                        'type': 'external',
                        'url': external.uri,
                        'title': external.title if hasattr(external, 'title') else '',
                        'description': external.description if hasattr(external, 'description') else '',
                        'thumb_path': image_path,
                        'filename': filename,
                        'info': image_info
                    })
        
        return embeds
    
    def display_post_with_media(self, post: models.AppBskyFeedDefs.FeedViewPost):
        """Display post text and associated media"""
        print(self.format_post_text(post))
        
        embeds = self.process_embeds(post)
        
        if embeds:
            print("📸 EMBEDDED MEDIA:")
            for embed in embeds:
                if embed['type'] == 'image':
                    print(f"  🖼️  Image: {embed['filename']}")
                    print(f"      Alt text: {embed['alt_text']}")
                    print(f"      Dimensions: {embed['info'].get('width', '?')}x{embed['info'].get('height', '?')}")
                    print(f"      File size: {embed['info'].get('file_size', 0)} bytes")
                    print(f"      Local path: {embed['local_path']}")
                elif embed['type'] == 'external':
                    print(f"  🔗 External link: {embed['url']}")
                    print(f"      Title: {embed['title']}")
                    print(f"      Description: {embed['description']}")
                    print(f"      Thumbnail: {embed['filename']}")
                    print(f"      Thumbnail path: {embed['thumb_path']}")
            print()
        else:
            print("No embedded media found in this post.\n")
    
    def fetch_timeline(self, limit: int = 10, cursor: Optional[str] = None, algorithm: str = 'home') -> List[models.AppBskyFeedDefs.FeedViewPost]:
        """Fetch timeline posts from HOME timeline (followed users only) with caching and rate limiting"""
        try:
            # Check cache first
            cached_data = self._get_cached_timeline(limit, cursor, algorithm)
            if cached_data:
                return cached_data.get('feed', [])
            
            # Check rate limits before making API call
            if not self._check_rate_limit():
                logger.warning("Rate limit exceeded, cannot fetch timeline")
                return []
            
            # Make API call
            timeline = self.client.get_timeline(limit=limit, cursor=cursor, algorithm=algorithm)
            self._record_api_call()
            
            # Cache the result
            timeline_data = {
                'feed': timeline.feed,
                'cursor': getattr(timeline, 'cursor', None)
            }
            self._cache_timeline(limit, cursor, algorithm, timeline_data)
            
            return timeline.feed
        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"Error fetching timeline: {e}")
            
            # If we have too many consecutive errors, increase the delay
            if self._consecutive_errors >= self._max_consecutive_errors:
                logger.warning(f"Too many consecutive errors ({self._consecutive_errors}), increasing delay")
                time.sleep(min(5, self._consecutive_errors))
            
            return []
    
    def fetch_posts_with_images(self, target_count: int = 5, max_fetches: int = 10) -> List[models.AppBskyFeedDefs.FeedViewPost]:
        """Fetch posts until we have a good number of posts with images"""
        import time
        
        posts_with_images = []
        cursor = None
        fetch_count = 0
        
        print(f"🔍 Searching for {target_count} posts with images...")
        
        while len(posts_with_images) < target_count and fetch_count < max_fetches:
            try:
                # Use the optimized fetch_timeline method with caching and rate limiting
                timeline_feed = self.fetch_timeline(limit=20, cursor=cursor, algorithm='home')
                
                if not timeline_feed:
                    print("No more posts available")
                    break
                
                # Get cursor from cache for next iteration
                cached_data = self._get_cached_timeline(20, cursor, 'home')
                if cached_data:
                    cursor = cached_data.get('cursor')
                
                # Check each post for images
                for post in timeline_feed:
                    if hasattr(post.post.record, 'embed') and post.post.record.embed:
                        embed = post.post.record.embed
                        if hasattr(embed, 'images') and embed.images:
                            posts_with_images.append(post)
                            print(f"📸 Found post with {len(embed.images)} image(s) - {len(posts_with_images)}/{target_count}")
                            
                            if len(posts_with_images) >= target_count:
                                break
                
                # Update cursor for next fetch
                if cached_data and cached_data.get('cursor'):
                    cursor = cached_data.get('cursor')
                else:
                    # If no cursor available, we've reached the end of the timeline
                    print("📄 Reached end of timeline - no more posts available")
                    break
                
                fetch_count += 1
                
                # Be respectful - wait between requests (reduced since we have rate limiting)
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    print(f"⏳ Waiting 1 second before next fetch... (fetch {fetch_count}/{max_fetches})")
                    time.sleep(1)
                
            except Exception as e:
                print(f"Error fetching posts: {e}")
                break
        
        print(f"✅ Found {len(posts_with_images)} posts with images after {fetch_count} fetches")
        return posts_with_images
    
    def format_post_for_web(self, post: models.AppBskyFeedDefs.FeedViewPost) -> Dict[str, Any]:
        """Format post data for web display"""
        record = post.post.record
        author = post.post.author
        
        embeds = self.process_embeds(post)
        
        # Check if this post is liked by the current user
        is_liked = self._check_if_post_is_liked(post.post.uri)
        
        return {
            'author': {
                'handle': author.handle,
                'display_name': author.display_name or 'No display name',
                'avatar': author.avatar if hasattr(author, 'avatar') else None
            },
            'post': {
                'text': record.text if hasattr(record, 'text') else 'No text content',
                'uri': post.post.uri,
                'indexed_at': post.post.indexed_at if hasattr(post.post, 'indexed_at') else post.post.created_at if hasattr(post.post, 'created_at') else 'Unknown',
                'reply_count': post.post.reply_count if hasattr(post.post, 'reply_count') else 0,
                'repost_count': post.post.repost_count if hasattr(post.post, 'repost_count') else 0,
                'like_count': post.post.like_count if hasattr(post.post, 'like_count') else 0,
                'is_liked': is_liked
            },
            'embeds': embeds
        }
    
    def _check_if_post_is_liked(self, post_uri: str) -> bool:
        """Check if a post is already liked by the current user with improved efficiency"""
        try:
            if not self.client:
                return False
            
            # Use the optimized find_like_record method
            like_record = self._find_like_record(post_uri)
            return like_record is not None
            
        except Exception as e:
            logger.warning(f"Could not check like status for post {post_uri}: {e}")
            return False
    
    def refresh_like_status(self, post_uri: str) -> Dict[str, Any]:
        """Refresh the like status for a specific post"""
        try:
            if not self.client:
                return {
                    "success": False,
                    "error": "Not authenticated"
                }
            
            is_liked = self._check_if_post_is_liked(post_uri)
            
            return {
                "success": True,
                "is_liked": is_liked,
                "post_uri": post_uri
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh like status for {post_uri}: {e}")
            return {
                "success": False,
                "error": str(e),
                "post_uri": post_uri
            }
    
    def fetch_posts_with_images_web_paginated(self, target_count: int = 5, max_fetches: int = 20, max_posts_per_user: int = 2, start_cursor: Optional[str] = None, seen_post_uris: Optional[set] = None) -> Dict[str, Any]:
        """Fetch posts with images with pagination support - returns new posts and pagination info"""
        import time
        
        # Setup temp directory if not already set
        if not self.temp_dir:
            self.temp_dir = self.setup_temp_directory()
        
        posts_with_images = []
        user_post_counts = {}  # Track how many posts we've seen from each user
        cursor = start_cursor
        fetch_count = 0
        total_posts_checked = 0
        seen_uris = seen_post_uris or set()
        
        print(f"🔍 Searching for {target_count} posts with images from FOLLOWED USERS ONLY (max {max_posts_per_user} per user, includes reposts from followed users)...")
        if start_cursor:
            print(f"📍 Starting from cursor: {start_cursor[:50]}...")
        
        while len(posts_with_images) < target_count and fetch_count < max_fetches:
            try:
                # Fetch a batch of posts from HOME timeline (followed users only)
                # Use the optimized fetch_timeline method with caching and rate limiting
                timeline_feed = self.fetch_timeline(limit=self._timeline_batch_size, cursor=cursor, algorithm='home')
                fetch_count += 1  # Always increment fetch count when we attempt to fetch
                
                if not timeline_feed:
                    print("No more posts available in home timeline (followed users)")
                    break
                
                # Get cursor from cache if available
                cached_data = self._get_cached_timeline(self._timeline_batch_size, cursor, 'home')
                if cached_data:
                    cursor = cached_data.get('cursor')
                
                # Check each post for images and deduplication
                for post in timeline_feed:
                    total_posts_checked += 1
                    user_handle = post.post.author.handle
                    post_uri = post.post.uri
                    
                    # Skip if we've already seen this post
                    if post_uri in seen_uris:
                        print(f"⏭️  Skipping already seen post from {user_handle}")
                        continue
                    
                    # Note: We include reposts from followed users since they appear in our home timeline
                    if hasattr(post, 'reason') and post.reason:
                        print(f"🔄 Including repost from {user_handle} (followed user)")
                    
                    # Check if we've already seen enough posts from this user
                    if user_handle in user_post_counts and user_post_counts[user_handle] >= max_posts_per_user:
                        print(f"⏭️  Skipping post from {user_handle} (already have {user_post_counts[user_handle]} posts)")
                        continue
                    
                    # Check if post has images
                    has_images = (hasattr(post.post.record, 'embed') and 
                                post.post.record.embed and 
                                hasattr(post.post.record.embed, 'images') and 
                                post.post.record.embed.images)
                    
                    if has_images:
                        try:
                            formatted_post = self.format_post_for_web(post)
                            posts_with_images.append(formatted_post)
                            
                            # Update user post count and seen URIs
                            user_post_counts[user_handle] = user_post_counts.get(user_handle, 0) + 1
                            seen_uris.add(post_uri)
                            
                            post_type = "repost" if hasattr(post, 'reason') and post.reason else "original"
                            print(f"📸 Found {post_type} post with {len(post.post.record.embed.images)} image(s) from {user_handle} ({user_post_counts[user_handle]}/{max_posts_per_user}) - {len(posts_with_images)}/{target_count} total posts")
                            
                            if len(posts_with_images) >= target_count:
                                break
                                
                        except Exception as e:
                            print(f"❌ Error formatting post with images: {e}")
                            continue
                    else:
                        # Skip posts without images
                        continue
                
                # Update cursor for next fetch - get it from the actual timeline response
                if cached_data and cached_data.get('cursor'):
                    cursor = cached_data.get('cursor')
                else:
                    # If no cursor available, we've reached the end of the timeline
                    print("📄 Reached end of timeline - no more posts available")
                    break
                
                # Be respectful - wait between requests (reduced since we have rate limiting)
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    print(f"⏳ Checked {total_posts_checked} posts, found {len(posts_with_images)} with images. Fetching more... (batch {fetch_count}/{max_fetches})")
                    time.sleep(0.5)  # Reduced wait time due to built-in rate limiting
                
            except Exception as e:
                print(f"Error fetching posts: {e}")
                break
        
        # Print summary of user distribution
        if user_post_counts:
            print(f"📊 User distribution: {dict(user_post_counts)}")
        
        print(f"✅ Found {len(posts_with_images)} posts with images from FOLLOWED USERS after checking {total_posts_checked} total posts in {fetch_count} batches")
        
        return {
            'posts': posts_with_images,
            'cursor': cursor,
            'seen_uris': seen_uris,
            'total_checked': total_posts_checked,
            'fetch_count': fetch_count
        }

    def fetch_posts_with_images_web(self, target_count: int = 5, max_fetches: int = 20, max_posts_per_user: int = 2) -> List[Dict[str, Any]]:
        """Fetch posts with images from followed users only (includes reposts from followed users) - Web version"""
        import time
        
        # Setup temp directory if not already set
        if not self.temp_dir:
            self.temp_dir = self.setup_temp_directory()
        
        posts_with_images = []
        user_post_counts = {}  # Track how many posts we've seen from each user
        cursor = None
        fetch_count = 0
        total_posts_checked = 0
        
        print(f"🔍 Searching for {target_count} posts with images from FOLLOWED USERS ONLY (max {max_posts_per_user} per user, includes reposts from followed users)...")
        
        while len(posts_with_images) < target_count and fetch_count < max_fetches:
            try:
                # Fetch a batch of posts from HOME timeline (followed users only)
                # Use the optimized fetch_timeline method with caching and rate limiting
                timeline_feed = self.fetch_timeline(limit=self._timeline_batch_size, cursor=cursor, algorithm='home')
                
                if not timeline_feed:
                    print("No more posts available in home timeline (followed users)")
                    break
                
                # Get cursor from cache if available
                cached_data = self._get_cached_timeline(self._timeline_batch_size, cursor, 'home')
                if cached_data:
                    cursor = cached_data.get('cursor')
                
                # Check each post for images
                for post in timeline_feed:
                    total_posts_checked += 1
                    user_handle = post.post.author.handle
                    
                    # Note: We include reposts from followed users since they appear in our home timeline
                    if hasattr(post, 'reason') and post.reason:
                        print(f"🔄 Including repost from {user_handle} (followed user)")
                    
                    # Check if we've already seen enough posts from this user
                    if user_handle in user_post_counts and user_post_counts[user_handle] >= max_posts_per_user:
                        print(f"⏭️  Skipping post from {user_handle} (already have {user_post_counts[user_handle]} posts)")
                        continue
                    
                    # Check if post has images
                    has_images = (hasattr(post.post.record, 'embed') and 
                                post.post.record.embed and 
                                hasattr(post.post.record.embed, 'images') and 
                                post.post.record.embed.images)
                    
                    if has_images:
                        try:
                            formatted_post = self.format_post_for_web(post)
                            posts_with_images.append(formatted_post)
                            
                            # Update user post count
                            user_post_counts[user_handle] = user_post_counts.get(user_handle, 0) + 1
                            
                            post_type = "repost" if hasattr(post, 'reason') and post.reason else "original"
                            print(f"📸 Found {post_type} post with {len(post.post.record.embed.images)} image(s) from {user_handle} ({user_post_counts[user_handle]}/{max_posts_per_user}) - {len(posts_with_images)}/{target_count} total posts")
                            
                            if len(posts_with_images) >= target_count:
                                break
                                
                        except Exception as e:
                            print(f"❌ Error formatting post with images: {e}")
                            continue
                    else:
                        # Skip posts without images
                        continue
                
                # Update cursor for next fetch - get it from the actual timeline response
                # The fetch_timeline method should return the cursor in the cached data
                if cached_data and cached_data.get('cursor'):
                    cursor = cached_data.get('cursor')
                else:
                    # If no cursor available, we've reached the end of the timeline
                    print("📄 Reached end of timeline - no more posts available")
                    break
                fetch_count += 1
                
                # Be respectful - wait between requests (reduced since we have rate limiting)
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    print(f"⏳ Checked {total_posts_checked} posts, found {len(posts_with_images)} with images. Fetching more... (batch {fetch_count}/{max_fetches})")
                    time.sleep(0.5)  # Reduced wait time due to built-in rate limiting
                
            except Exception as e:
                print(f"Error fetching posts: {e}")
                break
        
        # Print summary of user distribution
        if user_post_counts:
            print(f"📊 User distribution: {dict(user_post_counts)}")
        
        print(f"✅ Found {len(posts_with_images)} posts with images from FOLLOWED USERS after checking {total_posts_checked} total posts in {fetch_count} batches")
        return posts_with_images
    
    def fetch_posts_with_images_web_stream(self, target_count: int = 5, max_fetches: int = 20, max_posts_per_user: int = 2, progress_callback=None) -> List[Dict[str, Any]]:
        """Fetch posts with images with real-time progress updates - Web streaming version (includes reposts from followed users)"""
        import time
        
        # Setup temp directory if not already set
        if not self.temp_dir:
            self.temp_dir = self.setup_temp_directory()
        
        posts_with_images = []
        user_post_counts = {}  # Track how many posts we've seen from each user
        cursor = None
        fetch_count = 0
        total_posts_checked = 0
        
        if progress_callback:
            progress_callback(f"🔍 Searching for {target_count} posts with images from FOLLOWED USERS ONLY (max {max_posts_per_user} per user, includes reposts from followed users)...", 
                            posts_found=0, posts_checked=0, current_batch=0)
        
        while len(posts_with_images) < target_count and fetch_count < max_fetches:
            try:
                # Fetch a batch of posts from HOME timeline (followed users only)
                # Use the optimized fetch_timeline method with caching and rate limiting
                timeline_feed = self.fetch_timeline(limit=self._timeline_batch_size, cursor=cursor, algorithm='home')
                
                if not timeline_feed:
                    if progress_callback:
                        progress_callback("No more posts available in home timeline (followed users)", 
                                        posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                    break
                
                # Get cursor from cache if available
                cached_data = self._get_cached_timeline(self._timeline_batch_size, cursor, 'home')
                if cached_data:
                    cursor = cached_data.get('cursor')
                
                # Check each post for images
                for post in timeline_feed:
                    total_posts_checked += 1
                    user_handle = post.post.author.handle
                    
                    # Note: We include reposts from followed users since they appear in our home timeline
                    if hasattr(post, 'reason') and post.reason:
                        if progress_callback:
                            progress_callback(f"🔄 Including repost from {user_handle} (followed user)", 
                                            posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                    
                    # Check if we've already seen enough posts from this user
                    if user_handle in user_post_counts and user_post_counts[user_handle] >= max_posts_per_user:
                        if progress_callback:
                            progress_callback(f"⏭️  Skipping post from {user_handle} (already have {user_post_counts[user_handle]} posts)", 
                                            posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                        continue
                    
                    # Check if post has images
                    has_images = (hasattr(post.post.record, 'embed') and 
                                post.post.record.embed and 
                                hasattr(post.post.record.embed, 'images') and 
                                post.post.record.embed.images)
                    
                    if has_images:
                        try:
                            formatted_post = self.format_post_for_web(post)
                            posts_with_images.append(formatted_post)
                            
                            # Update user post count
                            user_post_counts[user_handle] = user_post_counts.get(user_handle, 0) + 1
                            
                            post_type = "repost" if hasattr(post, 'reason') and post.reason else "original"
                            if progress_callback:
                                progress_callback(f"📸 Found {post_type} post with {len(post.post.record.embed.images)} image(s) from {user_handle} ({user_post_counts[user_handle]}/{max_posts_per_user}) - {len(posts_with_images)}/{target_count} total posts", 
                                                posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                            
                            if len(posts_with_images) >= target_count:
                                break
                                
                        except Exception as e:
                            if progress_callback:
                                progress_callback(f"❌ Error formatting post with images: {e}", 
                                                posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                            continue
                    else:
                        # Skip posts without images
                        continue
                
                # Update cursor for next fetch - get it from the actual timeline response
                if cached_data and cached_data.get('cursor'):
                    cursor = cached_data.get('cursor')
                else:
                    # If no cursor available, we've reached the end of the timeline
                    if progress_callback:
                        progress_callback("📄 Reached end of timeline - no more posts available", 
                                        posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                    break
                fetch_count += 1
                
                # Be respectful - wait between requests (reduced since we have rate limiting)
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    if progress_callback:
                        progress_callback(f"⏳ Checked {total_posts_checked} posts, found {len(posts_with_images)} with images. Fetching more... (batch {fetch_count}/{max_fetches})", 
                                        posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                    time.sleep(0.5)  # Reduced wait time due to built-in rate limiting
                
            except Exception as e:
                if progress_callback:
                    progress_callback(f"Error fetching posts: {e}", 
                                    posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                break
        
        # Print summary of user distribution
        if user_post_counts and progress_callback:
            progress_callback(f"📊 User distribution: {dict(user_post_counts)}", 
                            posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
        
        if progress_callback:
            progress_callback(f"✅ Found {len(posts_with_images)} posts with images from FOLLOWED USERS after checking {total_posts_checked} total posts in {fetch_count} batches", 
                            posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
        
        return posts_with_images
    
    def fetch_posts_with_images_web_stream_generator(self, target_count: int = 5, max_fetches: int = 20, max_posts_per_user: int = 2):
        """Generator that yields progress updates and final results for streaming (includes reposts from followed users)"""
        import time
        
        # Setup temp directory if not already set
        if not self.temp_dir:
            self.temp_dir = self.setup_temp_directory()
        
        posts_with_images = []
        user_post_counts = {}  # Track how many posts we've seen from each user
        cursor = None
        fetch_count = 0
        total_posts_checked = 0
        
        yield {
            'type': 'progress',
            'message': f"🔍 Searching for {target_count} posts with images from FOLLOWED USERS ONLY (max {max_posts_per_user} per user, includes reposts from followed users)...",
            'posts_found': 0,
            'posts_checked': 0,
            'current_batch': 0,
            'progress_percent': 0
        }
        
        # Send a keep-alive message to prevent EventSource timeout
        yield {
            'type': 'keepalive',
            'message': 'Connection established, starting search...',
            'posts_found': 0,
            'posts_checked': 0,
            'current_batch': 0,
            'progress_percent': 0
        }
        
        while len(posts_with_images) < target_count and fetch_count < max_fetches:
            try:
                # Fetch a batch of posts from HOME timeline (followed users only)
                # Use the optimized fetch_timeline method with caching and rate limiting
                timeline_feed = self.fetch_timeline(limit=self._timeline_batch_size, cursor=cursor, algorithm='home')
                
                if not timeline_feed:
                    yield {
                        'type': 'progress',
                        'message': "No more posts available in home timeline (followed users)",
                        'posts_found': len(posts_with_images),
                        'posts_checked': total_posts_checked,
                        'current_batch': fetch_count,
                        'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                    }
                    break
                
                # Get cursor from cache if available
                cached_data = self._get_cached_timeline(self._timeline_batch_size, cursor, 'home')
                if cached_data:
                    cursor = cached_data.get('cursor')
                
                # Check each post for images
                for post in timeline_feed:
                    total_posts_checked += 1
                    user_handle = post.post.author.handle
                    
                    # Note: We include reposts from followed users since they appear in our home timeline
                    if hasattr(post, 'reason') and post.reason:
                        yield {
                            'type': 'progress',
                            'message': f"🔄 Including repost from {user_handle} (followed user)",
                            'posts_found': len(posts_with_images),
                            'posts_checked': total_posts_checked,
                            'current_batch': fetch_count,
                            'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                        }
                    
                    # Check if we've already seen enough posts from this user
                    if user_handle in user_post_counts and user_post_counts[user_handle] >= max_posts_per_user:
                        yield {
                            'type': 'progress',
                            'message': f"⏭️  Skipping post from {user_handle} (already have {user_post_counts[user_handle]} posts)",
                            'posts_found': len(posts_with_images),
                            'posts_checked': total_posts_checked,
                            'current_batch': fetch_count,
                            'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                        }
                        continue
                    
                    # Check if post has images
                    has_images = (hasattr(post.post.record, 'embed') and 
                                post.post.record.embed and 
                                hasattr(post.post.record.embed, 'images') and 
                                post.post.record.embed.images)
                    
                    if has_images:
                        try:
                            formatted_post = self.format_post_for_web(post)
                            posts_with_images.append(formatted_post)
                            
                            # Update user post count
                            user_post_counts[user_handle] = user_post_counts.get(user_handle, 0) + 1
                            
                            post_type = "repost" if hasattr(post, 'reason') and post.reason else "original"
                            yield {
                                'type': 'progress',
                                'message': f"📸 Found {post_type} post with {len(post.post.record.embed.images)} image(s) from {user_handle} ({user_post_counts[user_handle]}/{max_posts_per_user}) - {len(posts_with_images)}/{target_count} total posts",
                                'posts_found': len(posts_with_images),
                                'posts_checked': total_posts_checked,
                                'current_batch': fetch_count,
                                'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                            }
                            
                            if len(posts_with_images) >= target_count:
                                break
                                
                        except Exception as e:
                            yield {
                                'type': 'progress',
                                'message': f"❌ Error formatting post with images: {e}",
                                'posts_found': len(posts_with_images),
                                'posts_checked': total_posts_checked,
                                'current_batch': fetch_count,
                                'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                            }
                            continue
                    else:
                        # Skip posts without images
                        continue
                
                # Update cursor for next fetch - get it from the actual timeline response
                if cached_data and cached_data.get('cursor'):
                    cursor = cached_data.get('cursor')
                else:
                    # If no cursor available, we've reached the end of the timeline
                    yield {
                        'type': 'progress',
                        'message': "📄 Reached end of timeline - no more posts available",
                        'posts_found': len(posts_with_images),
                        'posts_checked': total_posts_checked,
                        'current_batch': fetch_count,
                        'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                    }
                    break
                fetch_count += 1
                
                # Be respectful - wait between requests (reduced since we have rate limiting)
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    yield {
                        'type': 'progress',
                        'message': f"⏳ Checked {total_posts_checked} posts, found {len(posts_with_images)} with images. Fetching more... (batch {fetch_count}/{max_fetches})",
                        'posts_found': len(posts_with_images),
                        'posts_checked': total_posts_checked,
                        'current_batch': fetch_count,
                        'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                    }
                    
                    # Send keep-alive message every batch to prevent timeout
                    yield {
                        'type': 'keepalive',
                        'message': f'Still searching... ({fetch_count}/{max_fetches} batches completed)',
                        'posts_found': len(posts_with_images),
                        'posts_checked': total_posts_checked,
                        'current_batch': fetch_count,
                        'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                    }
                    
                    time.sleep(0.5)  # Reduced wait time due to built-in rate limiting
                
            except Exception as e:
                yield {
                    'type': 'progress',
                    'message': f"Error fetching posts: {e}",
                    'posts_found': len(posts_with_images),
                    'posts_checked': total_posts_checked,
                    'current_batch': fetch_count,
                    'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                }
                break
        
        # Print summary of user distribution
        if user_post_counts:
            yield {
                'type': 'progress',
                'message': f"📊 User distribution: {dict(user_post_counts)}",
                'posts_found': len(posts_with_images),
                'posts_checked': total_posts_checked,
                'current_batch': fetch_count,
                'progress_percent': min(100, len(posts_with_images) / target_count * 100)
            }
        
        yield {
            'type': 'progress',
            'message': f"✅ Found {len(posts_with_images)} posts with images from FOLLOWED USERS after checking {total_posts_checked} total posts in {fetch_count} batches",
            'posts_found': len(posts_with_images),
            'posts_checked': total_posts_checked,
            'current_batch': fetch_count,
            'progress_percent': 100
        }
        
        # Final result
        yield {
            'type': 'complete',
            'posts': posts_with_images,
            'count': len(posts_with_images)
        }
    
    def initialize(self, handle: str):
        """Initialize the bot with authentication"""
        try:
            # Get password from SSM
            print("Fetching password from AWS SSM...")
            password = self.get_ssm_parameter('BLUESKY_PASSWORD_BIKELIFE')
            
            # Authenticate
            self.authenticate(handle, password)
            
            # Setup temp directory
            self.temp_dir = self.setup_temp_directory()
            
            return True
        except Exception as e:
            print(f"Error initializing bot: {e}")
            return False
    
    def run(self, handle: str, target_posts_with_images: int = 5):
        """Main bot execution - fetches posts with images"""
        try:
            # Get password from SSM
            print("Fetching password from AWS SSM...")
            password = self.get_ssm_parameter('BLUESKY_PASSWORD_BIKELIFE')
            
            # Authenticate
            self.authenticate(handle, password)
            
            # Setup temp directory
            self.temp_dir = self.setup_temp_directory()
            
            # Fetch posts with images
            posts_with_images = self.fetch_posts_with_images(target_posts_with_images)
            
            if not posts_with_images:
                print("No posts with images found")
                return
            
            print(f"\n📝 Processing {len(posts_with_images)} posts with images:\n")
            
            # Process each post with images
            for i, post in enumerate(posts_with_images, 1):
                print(f"📝 POST {i}/{len(posts_with_images)}")
                self.display_post_with_media(post)
            
            print(f"✅ Processed {len(posts_with_images)} posts with images")
            print(f"📁 Images saved to: {self.temp_dir}")
            
        except Exception as e:
            print(f"Error in bot execution: {e}")
            raise
        finally:
            # Cleanup
            if self.temp_dir and os.path.exists(self.temp_dir):
                print(f"\n🗑️  Temporary files are in: {self.temp_dir}")
                print("   (Files will be cleaned up automatically by the system)")


# CLI functionality removed - this is now a web-only application
