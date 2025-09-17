#!/usr/bin/env python3
"""
Bluesky Bot - Fetches timeline and displays posts with embedded media
Includes both CLI and web functionality
"""

import os
import tempfile
import requests
from typing import List, Dict, Any, Optional, Set
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
        
        # Media-focused feed URIs (can be customized)
        self._media_feed_uris = [
            # Add custom feed URIs here when available
            # "at://did:plc:your-feed-did/app.bsky.feed.generator/media-posts"
        ]
        
        # API usage tracking
        self._api_call_count = 0
        self._api_call_window_start = time.time()
        self._max_calls_per_window = 50  # Conservative limit
        self._window_duration = 300  # 5 minutes
        
        # Media user caching for optimization
        self._media_user_cache = {}  # Cache users who frequently post media
        self._media_user_cache_ttl = 3600  # 1 hour cache TTL
        self._media_user_threshold = 0.3  # Users with >30% media posts are cached
        
        # Optimized batch sizes for different operations
        self._timeline_batch_size = 20  # Optimized for media filtering efficiency
        self._media_focused_batch_size = 10  # Smaller batches when specifically looking for media
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
    
    def _is_media_user_cached(self, user_handle: str) -> bool:
        """Check if user is cached as a frequent media poster"""
        if user_handle not in self._media_user_cache:
            return False
        
        cache_entry = self._media_user_cache[user_handle]
        if time.time() - cache_entry['timestamp'] > self._media_user_cache_ttl:
            del self._media_user_cache[user_handle]
            return False
        
        return cache_entry['is_media_user']
    
    def _cache_media_user(self, user_handle: str, is_media_user: bool):
        """Cache whether a user frequently posts media"""
        self._media_user_cache[user_handle] = {
            'is_media_user': is_media_user,
            'timestamp': time.time()
        }
    
    def _analyze_user_media_ratio(self, user_handle: str, sample_size: int = 20) -> float:
        """Analyze a user's media posting ratio from recent posts"""
        try:
            # Get recent posts from user
            author_feed = self.client.app.bsky.feed.get_author_feed(
                actor=user_handle,
                limit=sample_size
            )
            
            if not author_feed or not hasattr(author_feed, 'feed'):
                return 0.0
            
            media_posts = 0
            total_posts = len(author_feed.feed)
            
            for post in author_feed.feed:
                if self._has_media(post):
                    media_posts += 1
            
            ratio = media_posts / total_posts if total_posts > 0 else 0.0
            return ratio
            
        except Exception as e:
            logger.warning(f"Failed to analyze media ratio for {user_handle}: {e}")
            return 0.0
    
    def _has_media(self, post) -> bool:
        """Check if a post has embedded media (images or external links with thumbnails)"""
        try:
            if not hasattr(post, 'post') or not hasattr(post.post, 'record'):
                return False
            
            record = post.post.record
            if not hasattr(record, 'embed') or not record.embed:
                return False
            
            embed = record.embed
            
            # Check for images
            if hasattr(embed, 'images') and embed.images:
                return True
            
            # Check for external links with thumbnails
            if hasattr(embed, 'external') and embed.external:
                if hasattr(embed.external, 'thumb') and embed.external.thumb:
                    return True
            
            # Check for video embeds with thumbnails
            if hasattr(embed, 'video') and embed.video:
                if hasattr(embed.video, 'thumb') and embed.video.thumb:
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking media in post: {e}")
            return False
    
    def _get_safe_image_count(self, post) -> int:
        """Safely get the number of images in a post"""
        try:
            if not hasattr(post, 'post') or not hasattr(post.post, 'record'):
                return 0
            
            record = post.post.record
            if not hasattr(record, 'embed') or not record.embed:
                return 0
            
            embed = record.embed
            if hasattr(embed, 'images') and embed.images:
                return len(embed.images)
            
            return 0
        except Exception as e:
            logger.debug(f"Error getting image count: {e}")
            return 0
        
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
            'last_api_call_ago_seconds': current_time - self._last_api_call if self._last_api_call > 0 else None,
            'media_user_cache_entries': len(self._media_user_cache),
            'media_feed_uris_configured': len(self._media_feed_uris)
        }
    
    def reset_api_stats(self):
        """Reset API usage statistics (useful for testing or after errors)"""
        self._api_call_count = 0
        self._api_call_window_start = time.time()
        self._consecutive_errors = 0
    
    def get_media_user_stats(self) -> Dict[str, Any]:
        """Get statistics about cached media users"""
        current_time = time.time()
        active_users = 0
        expired_users = 0
        
        for user_handle, cache_entry in self._media_user_cache.items():
            if current_time - cache_entry['timestamp'] > self._media_user_cache_ttl:
                expired_users += 1
            else:
                active_users += 1
        
        return {
            'total_cached_users': len(self._media_user_cache),
            'active_cached_users': active_users,
            'expired_cached_users': expired_users,
            'cache_ttl_seconds': self._media_user_cache_ttl,
            'media_threshold': self._media_user_threshold
        }
    
    def add_media_feed_uri(self, feed_uri: str):
        """Add a custom media feed URI to the list of feeds to try"""
        if feed_uri not in self._media_feed_uris:
            self._media_feed_uris.append(feed_uri)
            logger.info(f"Added media feed URI: {feed_uri}")
    
    def remove_media_feed_uri(self, feed_uri: str):
        """Remove a custom media feed URI from the list"""
        if feed_uri in self._media_feed_uris:
            self._media_feed_uris.remove(feed_uri)
            logger.info(f"Removed media feed URI: {feed_uri}")
    
    def clear_media_feed_uris(self):
        """Clear all custom media feed URIs"""
        self._media_feed_uris.clear()
        logger.info("Cleared all media feed URIs")
        
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
        
        # Handle external links with thumbnails (website cards)
        elif hasattr(embed, 'external') and embed.external:
            external = embed.external
            if hasattr(external, 'thumb') and external.thumb:
                # Extract the blob reference from the thumb
                thumb_ref = None
                if hasattr(external.thumb, 'ref') and hasattr(external.thumb.ref, 'link'):
                    thumb_ref = external.thumb.ref.link
                elif hasattr(external.thumb, 'ref') and hasattr(external.thumb.ref, '$link'):
                    thumb_ref = external.thumb.ref['$link']
                
                if thumb_ref:
                    # Construct the blob URL
                    post_did = post.post.uri.split('/')[2]
                    blob_url = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={post_did}&cid={thumb_ref}"
                    
                    filename = f"external_{post.post.uri.split('/')[-1]}.jpg"
                    image_path = self.download_image(blob_url, filename)
                    
                    if image_path:
                        image_info = self.get_image_info(image_path)
                        embeds.append({
                            'type': 'external',
                            'url': external.uri if hasattr(external, 'uri') else '',
                            'title': external.title if hasattr(external, 'title') else '',
                            'description': external.description if hasattr(external, 'description') else '',
                            'thumb_path': image_path,
                            'filename': filename,
                            'info': image_info
                        })
        
        # Handle video embeds (if they exist)
        elif hasattr(embed, 'video') and embed.video:
            video = embed.video
            if hasattr(video, 'thumb') and video.thumb:
                # Extract the blob reference from the thumb
                thumb_ref = None
                if hasattr(video.thumb, 'ref') and hasattr(video.thumb.ref, 'link'):
                    thumb_ref = video.thumb.ref.link
                elif hasattr(video.thumb, 'ref') and hasattr(video.thumb.ref, '$link'):
                    thumb_ref = video.thumb.ref['$link']
                
                if thumb_ref:
                    # Construct the blob URL
                    post_did = post.post.uri.split('/')[2]
                    blob_url = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={post_did}&cid={thumb_ref}"
                    
                    filename = f"video_{post.post.uri.split('/')[-1]}.jpg"
                    image_path = self.download_image(blob_url, filename)
                    
                    if image_path:
                        image_info = self.get_image_info(image_path)
                        embeds.append({
                            'type': 'video',
                            'url': video.uri if hasattr(video, 'uri') else '',
                            'title': video.title if hasattr(video, 'title') else '',
                            'description': video.description if hasattr(video, 'description') else '',
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
                elif embed['type'] == 'video':
                    print(f"  🎥 Video: {embed['url']}")
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
    
    def fetch_media_feed(self, limit: int = 50, cursor: Optional[str] = None) -> List[models.AppBskyFeedDefs.FeedViewPost]:
        """Fetch from custom media-focused feeds if available, fallback to optimized timeline"""
        try:
            # Try custom media feeds first
            for feed_uri in self._media_feed_uris:
                try:
                    if not self._check_rate_limit():
                        logger.warning("Rate limit exceeded, cannot fetch media feed")
                        return []
                    
                    feed = self.client.app.bsky.feed.get_feed(
                        feed=feed_uri,
                        limit=limit,
                        cursor=cursor
                    )
                    self._record_api_call()
                    
                    logger.info(f"Successfully fetched from custom media feed: {feed_uri}")
                    return feed.feed
                    
                except Exception as e:
                    logger.warning(f"Failed to fetch from custom feed {feed_uri}: {e}")
                    continue
            
            # Fallback to optimized timeline with reliable algorithm
            logger.info("No custom media feeds available, using optimized timeline")
            return self.fetch_timeline(limit=limit, cursor=cursor, algorithm='home')
            
        except Exception as e:
            logger.error(f"Error fetching media feed: {e}")
            return []
    
    def fetch_posts_from_media_users(self, user_handles: List[str], limit: int = 10) -> List[models.AppBskyFeedDefs.FeedViewPost]:
        """Fetch posts from users known to post media frequently"""
        posts = []
        
        for handle in user_handles:
            try:
                # Check if user is cached as media user
                if not self._is_media_user_cached(handle):
                    # Analyze user's media ratio
                    media_ratio = self._analyze_user_media_ratio(handle)
                    self._cache_media_user(handle, media_ratio > self._media_user_threshold)
                
                # Only fetch from users who frequently post media
                if self._is_media_user_cached(handle):
                    if not self._check_rate_limit():
                        logger.warning("Rate limit exceeded, cannot fetch user posts")
                        break
                    
                    user_posts = self.client.app.bsky.feed.get_author_feed(
                        actor=handle,
                        limit=limit
                    )
                    self._record_api_call()
                    
                    # Filter for media posts
                    for post in user_posts.feed:
                        if self._has_media(post):
                            posts.append(post)
                            if len(posts) >= limit:
                                break
                
                if len(posts) >= limit:
                    break
                    
            except Exception as e:
                logger.warning(f"Failed to fetch posts from {handle}: {e}")
                continue
        
        return posts[:limit]
    
    def fetch_posts_with_images(self, target_count: int = 5, max_fetches: int = 10) -> List[models.AppBskyFeedDefs.FeedViewPost]:
        """Fetch posts until we have a good number of posts with images - OPTIMIZED VERSION"""
        import time
        
        posts_with_images = []
        cursor = None
        fetch_count = 0
        
        print(f"🔍 Searching for {target_count} posts with images (optimized)...")
        
        # Try media feed first for better efficiency
        try:
            media_feed = self.fetch_media_feed(limit=target_count * 2, cursor=cursor)
            if media_feed:
                for post in media_feed:
                    if self._has_media(post):
                        posts_with_images.append(post)
                        print(f"📸 Found post with media from custom feed - {len(posts_with_images)}/{target_count}")
                        if len(posts_with_images) >= target_count:
                            break
                
                if len(posts_with_images) >= target_count:
                    print(f"✅ Found {len(posts_with_images)} posts with images from custom media feed")
                    return posts_with_images[:target_count]
        except Exception as e:
            logger.warning(f"Custom media feed failed, falling back to timeline: {e}")
        
        # Fallback to optimized timeline fetching
        while len(posts_with_images) < target_count and fetch_count < max_fetches:
            try:
                # Use appropriate batch size - ensure we fetch enough posts to find media
                remaining_needed = target_count - len(posts_with_images)
                batch_size = max(self._media_focused_batch_size, remaining_needed * 3)  # Fetch 3x what we need to account for non-media posts
                timeline_feed = self.fetch_timeline(limit=batch_size, cursor=cursor, algorithm='home')
                
                if not timeline_feed:
                    print("No more posts available in timeline")
                    break
                
                # Get cursor from cache for next iteration
                cached_data = self._get_cached_timeline(batch_size, cursor, 'home')
                if cached_data:
                    cursor = cached_data.get('cursor')
                
                # Check each post for images with early exit
                for post in timeline_feed:
                    if self._has_media(post):
                        posts_with_images.append(post)
                        print(f"📸 Found post with media - {len(posts_with_images)}/{target_count}")
                        
                        # Early exit when target reached
                        if len(posts_with_images) >= target_count:
                            break
                
                # Early exit if we have enough posts
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
        if len(posts_with_images) < target_count:
            print(f"⚠️  Warning: Only found {len(posts_with_images)} posts, requested {target_count}")
            print(f"   - Fetches attempted: {fetch_count}/{max_fetches}")
            print(f"   - Timeline exhausted: {cursor is None}")
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
    
    def post_reply(self, post_uri: str, reply_text: str) -> Dict[str, Any]:
        """Post a reply to a Bluesky post"""
        try:
            if not self.client:
                raise Exception("Not authenticated")
            
            # Check rate limits before making API calls
            if not self._check_rate_limit():
                return {
                    "success": False,
                    "error": "Rate limit exceeded. Please try again later."
                }
            
            # Parse the post URI to get the root post info
            # Format: at://did:plc:xxx/app.bsky.feed.post/rkey
            uri_parts = post_uri.split('/')
            if len(uri_parts) < 5 or uri_parts[3] != 'app.bsky.feed.post':
                raise Exception(f"Invalid post URI format: {post_uri}")
            
            repo_did = uri_parts[2]
            record_key = uri_parts[4]
            
            # Get the root post record to build the reply structure
            root_post_record = self.client.com.atproto.repo.get_record(
                params={
                    "repo": repo_did,
                    "collection": "app.bsky.feed.post",
                    "rkey": record_key
                }
            )
            
            # Build the reply record
            reply_record = {
                "text": reply_text,
                "reply": {
                    "root": {
                        "uri": post_uri,
                        "cid": root_post_record.cid
                    },
                    "parent": {
                        "uri": post_uri,
                        "cid": root_post_record.cid
                    }
                },
                "createdAt": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            }
            
            # Post the reply
            response = self.client.com.atproto.repo.create_record(
                data={
                    "repo": self.client.me.did,
                    "collection": "app.bsky.feed.post",
                    "record": reply_record
                }
            )
            
            logger.info(f"Successfully posted reply to {post_uri}: {response.uri}")
            
            # Store the reply for analytics tracking
            self._store_reply_for_analytics(post_uri, reply_text, response.uri)
            
            return {
                "success": True,
                "reply_uri": response.uri,
                "message": "Reply posted successfully",
                "post_uri": post_uri
            }
            
        except Exception as e:
            logger.error(f"Failed to post reply to {post_uri}: {e}")
            return {
                "success": False,
                "error": str(e),
                "post_uri": post_uri
            }
    
    def _store_reply_for_analytics(self, post_uri: str, reply_text: str, reply_uri: str):
        """Store reply data for analytics tracking"""
        try:
            # Create a simple JSON file to track replies
            replies_file = os.path.join(os.path.dirname(__file__), '..', 'replies_tracking.json')
            
            # Load existing replies
            replies_data = []
            if os.path.exists(replies_file):
                with open(replies_file, 'r', encoding='utf-8') as f:
                    replies_data = json.load(f)
            
            # Add new reply
            reply_entry = {
                "post_uri": post_uri,
                "reply_text": reply_text,
                "reply_uri": reply_uri,
                "timestamp": datetime.now().isoformat(),
                "author_handle": self.client.me.handle if self.client and hasattr(self.client, 'me') else "unknown"
            }
            
            replies_data.append(reply_entry)
            
            # Keep only last 30 days of replies to prevent file from growing too large
            cutoff_date = datetime.now() - timedelta(days=30)
            replies_data = [
                reply for reply in replies_data 
                if datetime.fromisoformat(reply['timestamp']) > cutoff_date
            ]
            
            # Save back to file
            with open(replies_file, 'w', encoding='utf-8') as f:
                json.dump(replies_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.warning(f"Failed to store reply for analytics: {e}")
    
    def fetch_posts_with_images_web_filtered(self, target_count: int, max_fetches: int = 300, 
                                           max_posts_per_user: int = 1, start_cursor: Optional[str] = None,
                                           seen_post_uris: Optional[Set[str]] = None,
                                           reply_filter_threshold: int = 0,
                                           replied_post_uris: Optional[List[str]] = None,
                                           followed_accounts: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fetch posts with images, applying filters during fetch to ensure we get enough posts"""
        try:
            if not self.client:
                raise Exception("Not authenticated")
            
            if seen_post_uris is None:
                seen_post_uris = set()
            
            if replied_post_uris is None:
                replied_post_uris = []
            
            if followed_accounts is None:
                followed_accounts = []
            
            replied_post_uris_set = set(replied_post_uris)
            followed_accounts_set = set(followed_accounts)
            
            # Get reply analytics if threshold filtering is needed
            reply_analytics = {}
            if reply_filter_threshold > 0:
                analytics_result = self.get_reply_analytics(days=7, limit=20)
                if analytics_result.get('success'):
                    reply_analytics = analytics_result.get('replies_per_user', {})
            
            posts = []
            cursor = start_cursor
            total_checked = 0
            fetch_count = 0
            
            while len(posts) < target_count and fetch_count < max_fetches:
                fetch_count += 1
                
                # Fetch a batch of posts
                batch_result = self.fetch_posts_with_images_web_paginated(
                    target_count=min(target_count * 2, 18),  # Fetch more than needed
                    max_fetches=50,  # Smaller batches for filtering
                    max_posts_per_user=max_posts_per_user,
                    start_cursor=cursor,
                    seen_post_uris=seen_post_uris
                )
                
                if not batch_result.get('posts'):
                    break
                
                cursor = batch_result.get('cursor')
                total_checked += batch_result.get('total_checked', 0)
                
                # Apply filters to the batch
                filtered_batch = []
                for post in batch_result['posts']:
                    # Check if already replied to
                    if post.get('post', {}).get('uri') in replied_post_uris_set:
                        continue
                    
                    # Check if author is in followed accounts (if filtering is enabled)
                    if followed_accounts_set:
                        author_handle = post.get('author', {}).get('handle')
                        if author_handle and author_handle not in followed_accounts_set:
                            continue
                    
                    # Check reply count threshold
                    if reply_filter_threshold > 0:
                        author_handle = post.get('author', {}).get('handle')
                        if author_handle:
                            reply_count = reply_analytics.get(author_handle, 0)
                            if reply_count > reply_filter_threshold:
                                continue
                    
                    # Post passed all filters
                    filtered_batch.append(post)
                    if len(posts) + len(filtered_batch) >= target_count:
                        break
                
                posts.extend(filtered_batch)
                
                # Update seen posts
                for post in batch_result['posts']:
                    if 'post' in post and 'uri' in post['post']:
                        seen_post_uris.add(post['post']['uri'])
            
            # Trim to exact target count
            posts = posts[:target_count]
            
            return {
                'posts': posts,
                'cursor': cursor,
                'total_checked': total_checked,
                'fetch_count': fetch_count,
                'seen_uris': seen_post_uris
            }
            
        except Exception as e:
            logger.error(f"Error in fetch_posts_with_images_web_filtered: {e}")
            return {
                'posts': [],
                'cursor': None,
                'total_checked': 0,
                'fetch_count': 0,
                'seen_uris': seen_post_uris or set(),
                'error': str(e)
            }
    
    def get_replied_post_uris(self) -> List[str]:
        """Get list of post URIs that have been replied to"""
        try:
            replies_file = os.path.join(os.path.dirname(__file__), '..', 'replies_tracking.json')
            
            if not os.path.exists(replies_file):
                return []
            
            with open(replies_file, 'r', encoding='utf-8') as f:
                replies_data = json.load(f)
            
            # Extract unique post URIs
            replied_uris = set()
            for reply in replies_data:
                if 'post_uri' in reply:
                    replied_uris.add(reply['post_uri'])
            
            return list(replied_uris)
            
        except Exception as e:
            logger.warning(f"Failed to get replied post URIs: {e}")
            return []
    
    def get_reply_analytics(self, days: int = 3, limit: int = 5) -> Dict[str, Any]:
        """Get analytics about replies posted in the last N days by fetching from Bluesky"""
        try:
            if not self.client:
                raise Exception("Not authenticated")
            
            # Calculate cutoff date (make it timezone-aware)
            cutoff_date = datetime.now().replace(tzinfo=None) - timedelta(days=days)
            
            # Fetch user's posts (including replies) from their timeline
            replies_per_user = {}
            total_replies = 0
            cursor = None
            
            # Fetch posts in batches to find replies
            for batch in range(10):  # Limit to 10 batches to avoid infinite loops
                try:
                    # Get user's posts from their timeline
                    timeline_response = self.client.get_author_feed(
                        actor=self.client.me.did,
                        limit=100,
                        cursor=cursor
                    )
                    
                    if not timeline_response or not hasattr(timeline_response, 'feed'):
                        break
                    
                    # Process posts in this batch
                    for post_view in timeline_response.feed:
                        post = post_view.post
                        
                        # Check if this is a reply (has reply context)
                        if hasattr(post.record, 'reply') and post.record.reply:
                            # Check if this reply is within our time window
                            post_date = datetime.fromisoformat(post.indexed_at.replace('Z', '+00:00')).replace(tzinfo=None)
                            if post_date > cutoff_date:
                                total_replies += 1
                                
                                # Get the parent post to find who we replied to
                                try:
                                    parent_uri = post.record.reply.parent.uri
                                    # Extract author DID from parent URI
                                    # Format: at://did:plc:xxx/app.bsky.feed.post/rkey
                                    uri_parts = parent_uri.split('/')
                                    if len(uri_parts) >= 3:
                                        parent_author_did = uri_parts[2]  # DID is at index 2
                                        
                                        # Try to resolve DID to handle
                                        try:
                                            # Get profile info for the parent author
                                            profile_response = self.client.get_profile(actor=parent_author_did)
                                            if profile_response and hasattr(profile_response, 'handle'):
                                                author_handle = profile_response.handle
                                            else:
                                                # Fallback to truncated DID
                                                author_handle = parent_author_did[:20] + "..."
                                        except:
                                            # Fallback to truncated DID if profile lookup fails
                                            author_handle = parent_author_did[:20] + "..."
                                        
                                        if author_handle not in replies_per_user:
                                            replies_per_user[author_handle] = 0
                                        replies_per_user[author_handle] += 1
                                        
                                except Exception as e:
                                    logger.warning(f"Failed to parse parent URI {parent_uri}: {e}")
                                    continue
                    
                    # Check if we have more posts to fetch
                    if hasattr(timeline_response, 'cursor') and timeline_response.cursor:
                        cursor = timeline_response.cursor
                    else:
                        break
                        
                except Exception as e:
                    logger.warning(f"Failed to fetch timeline batch {batch}: {e}")
                    break
            
            # Sort by reply count (highest to lowest) and get top N
            sorted_users = sorted(replies_per_user.items(), key=lambda x: x[1], reverse=True)[:limit]
            
            return {
                "success": True,
                "replies_per_user": dict(sorted_users),
                "total_replies": total_replies,
                "days_analyzed": days
            }
            
        except Exception as e:
            logger.error(f"Failed to get reply analytics: {e}")
            return {
                "success": False,
                "error": str(e)
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
                # For pagination, we need to make fresh API calls to get new posts
                # Don't use cache when we have a cursor (fetch more scenario)
                if cursor:
                    print(f"🔄 Making fresh API call for pagination (cursor: {cursor[:20]}...)")
                    # Clear cache for this specific request to force fresh data
                    cache_key = self._get_cache_key('get_timeline', limit=self._timeline_batch_size, cursor=cursor, algorithm='home')
                    if cache_key in self._timeline_cache:
                        del self._timeline_cache[cache_key]
                
                # Fetch a batch of posts from HOME timeline (followed users only)
                # Try media feed first, fallback to timeline
                timeline_feed = self.fetch_media_feed(limit=self._timeline_batch_size, cursor=cursor)
                if not timeline_feed:
                    timeline_feed = self.fetch_timeline(limit=self._timeline_batch_size, cursor=cursor, algorithm='home')
                fetch_count += 1  # Always increment fetch count when we attempt to fetch
                
                if not timeline_feed:
                    print("No more posts available in home timeline (followed users)")
                    break
                
                # Get cursor from cache (should be fresh now)
                cached_data = self._get_cached_timeline(self._timeline_batch_size, cursor, 'home')
                if cached_data:
                    cursor = cached_data.get('cursor')
                    print(f"📍 Updated cursor: {cursor[:20] if cursor else 'None'}...")
                
                # Check each post for images and deduplication
                for post in timeline_feed:
                    total_posts_checked += 1
                    user_handle = post.post.author.handle
                    post_uri = post.post.uri
                    
                    # Skip if we've already seen this post
                    if post_uri in seen_uris:
                        print(f"⏭️  Skipping already seen post from {user_handle} (URI: {post_uri[:30]}...)")
                        continue
                    
                    # Note: We include reposts from followed users since they appear in our home timeline
                    if hasattr(post, 'reason') and post.reason:
                        print(f"🔄 Including repost from {user_handle} (followed user)")
                    
                    # Check if we've already seen enough posts from this user
                    if user_handle in user_post_counts and user_post_counts[user_handle] >= max_posts_per_user:
                        print(f"⏭️  Skipping post from {user_handle} (already have {user_post_counts[user_handle]} posts)")
                        continue
                    
                    # Check if post has images using optimized method
                    has_images = self._has_media(post)
                    
                    if has_images:
                        try:
                            formatted_post = self.format_post_for_web(post)
                            posts_with_images.append(formatted_post)
                            
                            # Update user post count and seen URIs
                            user_post_counts[user_handle] = user_post_counts.get(user_handle, 0) + 1
                            seen_uris.add(post_uri)
                            
                            post_type = "repost" if hasattr(post, 'reason') and post.reason else "original"
                            image_count = self._get_safe_image_count(post)
                            print(f"📸 Found {post_type} post with {image_count} image(s) from {user_handle} ({user_post_counts[user_handle]}/{max_posts_per_user}) - {len(posts_with_images)}/{target_count} total posts")
                            
                            # Early exit when target reached
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
        print(f"   - Final cursor: {cursor[:20] if cursor else 'None'}...")
        print(f"   - Seen URIs count: {len(seen_uris)}")
        if len(posts_with_images) < target_count:
            print(f"⚠️  Warning: Only found {len(posts_with_images)} posts, requested {target_count}")
            print(f"   - Fetches attempted: {fetch_count}/{max_fetches}")
            print(f"   - Timeline exhausted: {cursor is None}")
            print(f"   - User post limits: {max_posts_per_user} per user")
        
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
                # Try media feed first, fallback to timeline
                timeline_feed = self.fetch_media_feed(limit=self._timeline_batch_size, cursor=cursor)
                if not timeline_feed:
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
                    
                    # Check if post has images using optimized method
                    has_images = self._has_media(post)
                    
                    if has_images:
                        try:
                            formatted_post = self.format_post_for_web(post)
                            posts_with_images.append(formatted_post)
                            
                            # Update user post count
                            user_post_counts[user_handle] = user_post_counts.get(user_handle, 0) + 1
                            
                            post_type = "repost" if hasattr(post, 'reason') and post.reason else "original"
                            image_count = self._get_safe_image_count(post)
                            print(f"📸 Found {post_type} post with {image_count} image(s) from {user_handle} ({user_post_counts[user_handle]}/{max_posts_per_user}) - {len(posts_with_images)}/{target_count} total posts")
                            
                            # Early exit when target reached
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
        if len(posts_with_images) < target_count:
            print(f"⚠️  Warning: Only found {len(posts_with_images)} posts, requested {target_count}")
            print(f"   - Fetches attempted: {fetch_count}/{max_fetches}")
            print(f"   - Timeline exhausted: {cursor is None}")
            print(f"   - User post limits: {max_posts_per_user} per user")
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
                # Try media feed first, fallback to timeline
                timeline_feed = self.fetch_media_feed(limit=self._timeline_batch_size, cursor=cursor)
                if not timeline_feed:
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
                    
                    # Check if post has images using optimized method
                    has_images = self._has_media(post)
                    
                    if has_images:
                        try:
                            formatted_post = self.format_post_for_web(post)
                            posts_with_images.append(formatted_post)
                            
                            # Update user post count
                            user_post_counts[user_handle] = user_post_counts.get(user_handle, 0) + 1
                            
                            post_type = "repost" if hasattr(post, 'reason') and post.reason else "original"
                            if progress_callback:
                                image_count = self._get_safe_image_count(post)
                                progress_callback(f"📸 Found {post_type} post with {image_count} image(s) from {user_handle} ({user_post_counts[user_handle]}/{max_posts_per_user}) - {len(posts_with_images)}/{target_count} total posts", 
                                                posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                            
                            # Early exit when target reached
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
                # Try media feed first, fallback to timeline
                timeline_feed = self.fetch_media_feed(limit=self._timeline_batch_size, cursor=cursor)
                if not timeline_feed:
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
                    
                    # Check if post has images using optimized method
                    has_images = self._has_media(post)
                    
                    if has_images:
                        try:
                            formatted_post = self.format_post_for_web(post)
                            posts_with_images.append(formatted_post)
                            
                            # Update user post count
                            user_post_counts[user_handle] = user_post_counts.get(user_handle, 0) + 1
                            
                            post_type = "repost" if hasattr(post, 'reason') and post.reason else "original"
                            image_count = self._get_safe_image_count(post)
                            yield {
                                'type': 'progress',
                                'message': f"📸 Found {post_type} post with {image_count} image(s) from {user_handle} ({user_post_counts[user_handle]}/{max_posts_per_user}) - {len(posts_with_images)}/{target_count} total posts",
                                'posts_found': len(posts_with_images),
                                'posts_checked': total_posts_checked,
                                'current_batch': fetch_count,
                                'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                            }
                            
                            # Early exit when target reached
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
    
    def _authenticate_and_setup(self, handle: str):
        """Common authentication and setup logic"""
        # Get password from SSM
        print("Fetching password from AWS SSM...")
        password = self.get_ssm_parameter('BLUESKY_PASSWORD_BIKELIFE')
        
        # Authenticate
        self.authenticate(handle, password)
        
        # Setup temp directory
        self.temp_dir = self.setup_temp_directory()
    
    def initialize(self, handle: str):
        """Initialize the bot with authentication"""
        try:
            self._authenticate_and_setup(handle)
            return True
        except Exception as e:
            print(f"Error initializing bot: {e}")
            return False
    
    def run(self, handle: str, target_posts_with_images: int = 5):
        """Main bot execution - fetches posts with images"""
        try:
            self._authenticate_and_setup(handle)
            
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

    def get_followed_accounts(self, limit: int = 1000) -> List[str]:
        """Get list of account handles that the user follows"""
        try:
            if not self.client:
                raise Exception("Not authenticated")
            
            followed_handles = []
            cursor = None
            
            while len(followed_handles) < limit:
                # Fetch follows
                if cursor:
                    follows_response = self.client.get_follows(
                        actor=self.client.me.did,
                        limit=min(100, limit - len(followed_handles)),
                        cursor=cursor
                    )
                else:
                    follows_response = self.client.get_follows(
                        actor=self.client.me.did,
                        limit=min(100, limit - len(followed_handles))
                    )
                
                if not follows_response.follows:
                    break
                
                # Extract handles
                for follow in follows_response.follows:
                    if hasattr(follow, 'handle') and follow.handle:
                        followed_handles.append(follow.handle)
                
                # Check if we have more to fetch
                if not hasattr(follows_response, 'cursor') or not follows_response.cursor:
                    break
                
                cursor = follows_response.cursor
                
                # Rate limiting
                time.sleep(0.1)
            
            logger.info(f"Fetched {len(followed_handles)} followed accounts")
            return followed_handles
            
        except Exception as e:
            logger.error(f"Error fetching followed accounts: {e}")
            return []


# CLI functionality removed - this is now a web-only application
