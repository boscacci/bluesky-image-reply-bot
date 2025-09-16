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
from datetime import datetime
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
    
    def setup_temp_directory(self):
        """Create temporary directory for downloaded images"""
        self.temp_dir = tempfile.mkdtemp(prefix='bluesky_images_')
        print(f"Created temporary directory: {self.temp_dir}")
        return self.temp_dir
    
    def download_image(self, url: str, filename: str) -> Optional[str]:
        """Download image from URL and save to temp directory"""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            file_path = os.path.join(self.temp_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            print(f"Downloaded image: {filename}")
            return file_path
        except Exception as e:
            print(f"Failed to download image {url}: {e}")
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
            with ThreadPoolExecutor(max_workers=min(8, len(embed.images))) as executor:
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
    
    def fetch_timeline(self, limit: int = 10) -> List[models.AppBskyFeedDefs.FeedViewPost]:
        """Fetch timeline posts from HOME timeline (followed users only)"""
        try:
            timeline = self.client.get_timeline(limit=limit, algorithm='home')
            return timeline.feed
        except Exception as e:
            print(f"Error fetching timeline: {e}")
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
                # Fetch a batch of posts from HOME timeline (followed users only)
                if cursor:
                    timeline = self.client.get_timeline(limit=20, cursor=cursor, algorithm='home')
                else:
                    timeline = self.client.get_timeline(limit=20, algorithm='home')
                
                if not timeline.feed:
                    print("No more posts available")
                    break
                
                # Check each post for images
                for post in timeline.feed:
                    if hasattr(post.post.record, 'embed') and post.post.record.embed:
                        embed = post.post.record.embed
                        if hasattr(embed, 'images') and embed.images:
                            posts_with_images.append(post)
                            print(f"📸 Found post with {len(embed.images)} image(s) - {len(posts_with_images)}/{target_count}")
                            
                            if len(posts_with_images) >= target_count:
                                break
                
                # Update cursor for next fetch
                cursor = timeline.cursor
                fetch_count += 1
                
                # Be respectful - wait between requests
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    print(f"⏳ Waiting 2 seconds before next fetch... (fetch {fetch_count}/{max_fetches})")
                    time.sleep(2)
                
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
                'like_count': post.post.like_count if hasattr(post.post, 'like_count') else 0
            },
            'embeds': embeds
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
                # Use the home timeline which only shows posts from users you follow
                if cursor:
                    timeline = self.client.get_timeline(limit=25, cursor=cursor, algorithm='home')
                else:
                    timeline = self.client.get_timeline(limit=25, algorithm='home')
                
                if not timeline.feed:
                    print("No more posts available in home timeline (followed users)")
                    break
                
                # Check each post for images
                for post in timeline.feed:
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
                
                # Update cursor for next fetch
                cursor = timeline.cursor
                fetch_count += 1
                
                # Be respectful - wait between requests
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    print(f"⏳ Checked {total_posts_checked} posts, found {len(posts_with_images)} with images. Fetching more... (batch {fetch_count}/{max_fetches})")
                    time.sleep(1)  # Shorter wait for better UX
                
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
                if cursor:
                    timeline = self.client.get_timeline(limit=25, cursor=cursor, algorithm='home')
                else:
                    timeline = self.client.get_timeline(limit=25, algorithm='home')
                
                if not timeline.feed:
                    if progress_callback:
                        progress_callback("No more posts available in home timeline (followed users)", 
                                        posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                    break
                
                # Check each post for images
                for post in timeline.feed:
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
                
                # Update cursor for next fetch
                cursor = timeline.cursor
                fetch_count += 1
                
                # Be respectful - wait between requests
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    if progress_callback:
                        progress_callback(f"⏳ Checked {total_posts_checked} posts, found {len(posts_with_images)} with images. Fetching more... (batch {fetch_count}/{max_fetches})", 
                                        posts_found=len(posts_with_images), posts_checked=total_posts_checked, current_batch=fetch_count)
                    time.sleep(1)  # Shorter wait for better UX
                
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
        
        while len(posts_with_images) < target_count and fetch_count < max_fetches:
            try:
                # Fetch a batch of posts from HOME timeline (followed users only)
                if cursor:
                    timeline = self.client.get_timeline(limit=25, cursor=cursor, algorithm='home')
                else:
                    timeline = self.client.get_timeline(limit=25, algorithm='home')
                
                if not timeline.feed:
                    yield {
                        'type': 'progress',
                        'message': "No more posts available in home timeline (followed users)",
                        'posts_found': len(posts_with_images),
                        'posts_checked': total_posts_checked,
                        'current_batch': fetch_count,
                        'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                    }
                    break
                
                # Check each post for images
                for post in timeline.feed:
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
                
                # Update cursor for next fetch
                cursor = timeline.cursor
                fetch_count += 1
                
                # Be respectful - wait between requests
                if len(posts_with_images) < target_count and fetch_count < max_fetches:
                    yield {
                        'type': 'progress',
                        'message': f"⏳ Checked {total_posts_checked} posts, found {len(posts_with_images)} with images. Fetching more... (batch {fetch_count}/{max_fetches})",
                        'posts_found': len(posts_with_images),
                        'posts_checked': total_posts_checked,
                        'current_batch': fetch_count,
                        'progress_percent': min(100, len(posts_with_images) / target_count * 100)
                    }
                    time.sleep(1)  # Shorter wait for better UX
                
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
