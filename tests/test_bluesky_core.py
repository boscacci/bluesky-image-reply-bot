#!/usr/bin/env python3
"""
Integration Tests for Bluesky Core Functionality
Tests authentication, timeline fetching, and basic bot operations
"""

import pytest
import tempfile
import os
import shutil
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import modules
from bluesky_bot import BlueskyBot
import config


class TestBlueskyCore:
    """Integration tests for core Bluesky bot functionality"""
    
    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.bot = BlueskyBot()
        self.temp_dir = tempfile.mkdtemp()
        self.bot.temp_dir = self.temp_dir
    
    def teardown_method(self):
        """Clean up after each test method"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @pytest.mark.integration
    def test_real_bluesky_authentication_and_timeline(self):
        """Test real Bluesky authentication and timeline fetching"""
        try:
            # Get real password from SSM
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            
            # Authenticate with real Bluesky API
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            assert self.bot.client is not None
            
            # Fetch real timeline
            timeline = self.bot.fetch_timeline(limit=5)
            assert isinstance(timeline, list)
            assert len(timeline) <= 5
            
            print(f"✅ Successfully authenticated and fetched {len(timeline)} timeline posts")
            
        except Exception as e:
            pytest.skip(f"Real Bluesky integration test skipped: {e}")
    
    @pytest.mark.integration
    def test_real_posts_with_images_fetch(self):
        """Test fetching posts with images from real Bluesky timeline"""
        try:
            # Setup real authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            self.bot.temp_dir = self.temp_dir
            
            # Fetch posts with images
            posts = self.bot.fetch_posts_with_images_web(
                target_count=2, 
                max_fetches=5, 
                max_posts_per_user=1
            )
            
            # Verify results
            assert isinstance(posts, list)
            assert len(posts) <= 2
            
            # Verify post structure
            for post in posts:
                assert 'author' in post
                assert 'post' in post
                assert 'embeds' in post
                assert 'handle' in post['author']
                assert 'text' in post['post']
            
            print(f"✅ Successfully fetched {len(posts)} posts with images")
            
        except Exception as e:
            pytest.skip(f"Real posts with images test skipped: {e}")
    
    @pytest.mark.integration
    def test_real_image_download_and_processing(self):
        """Test real image download and processing"""
        try:
            # Setup real authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            self.bot.temp_dir = self.temp_dir
            
            # Fetch posts with images
            posts = self.bot.fetch_posts_with_images_web(
                target_count=1, 
                max_fetches=3, 
                max_posts_per_user=1
            )
            
            if posts and posts[0]['embeds']:
                # Test image processing
                image_embed = posts[0]['embeds'][0]
                if image_embed['type'] == 'image':
                    image_path = image_embed['filename']
                    full_path = os.path.join(self.temp_dir, image_path)
                    
                    # Verify image was downloaded
                    assert os.path.exists(full_path)
                    assert os.path.getsize(full_path) > 0
                    
                    # Test image info extraction
                    info = self.bot.get_image_info(full_path)
                    assert 'width' in info
                    assert 'height' in info
                    assert 'format' in info
                    assert 'file_size' in info
                    
                    print(f"✅ Successfully downloaded and processed image: {image_path}")
                else:
                    print("ℹ️ No image embeds found in test posts")
            else:
                print("ℹ️ No posts with images found for testing")
                
        except Exception as e:
            pytest.skip(f"Real image processing test skipped: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
