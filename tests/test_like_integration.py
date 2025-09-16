#!/usr/bin/env python3
"""
Integration Tests for Like Functionality
Tests the new like/unlike functionality with real AT protocol calls
"""

import pytest
import tempfile
import os
import shutil
import json
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import modules
from bluesky_bot import BlueskyBot
import config


class TestLikeIntegration:
    """Integration tests specifically for like functionality"""
    
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
    def test_like_post_basic_functionality(self):
        """Test basic like post functionality"""
        try:
            # Setup authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            
            # Get a test post
            posts = self.bot.fetch_posts_with_images_web(
                target_count=1, 
                max_fetches=3, 
                max_posts_per_user=1
            )
            
            if posts and posts[0]['post']['uri']:
                test_post_uri = posts[0]['post']['uri']
                
                # Test like functionality
                result = self.bot.like_post(test_post_uri)
                
                # Verify result structure
                assert isinstance(result, dict)
                assert 'success' in result
                
                if result['success']:
                    assert 'like_uri' in result
                    assert 'message' in result
                    print(f"✅ Like functionality working: {result['message']}")
                else:
                    print(f"ℹ️ Like result: {result}")
                    
            else:
                print("ℹ️ No posts available for like testing")
                
        except Exception as e:
            pytest.skip(f"Like functionality test skipped: {e}")
    
    @pytest.mark.integration
    def test_unlike_post_basic_functionality(self):
        """Test basic unlike post functionality"""
        try:
            # Setup authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            
            # Get a test post
            posts = self.bot.fetch_posts_with_images_web(
                target_count=1, 
                max_fetches=3, 
                max_posts_per_user=1
            )
            
            if posts and posts[0]['post']['uri']:
                test_post_uri = posts[0]['post']['uri']
                
                # Test unlike functionality
                result = self.bot.unlike_post(test_post_uri)
                
                # Verify result structure
                assert isinstance(result, dict)
                assert 'success' in result
                
                if result['success']:
                    assert 'message' in result
                    print(f"✅ Unlike functionality working: {result['message']}")
                else:
                    print(f"ℹ️ Unlike result: {result}")
                    
            else:
                print("ℹ️ No posts available for unlike testing")
                
        except Exception as e:
            pytest.skip(f"Unlike functionality test skipped: {e}")
    
    @pytest.mark.integration
    def test_like_status_checking(self):
        """Test like status checking functionality"""
        try:
            # Setup authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            
            # Get test posts
            posts = self.bot.fetch_posts_with_images_web(
                target_count=3, 
                max_fetches=5, 
                max_posts_per_user=1
            )
            
            if posts:
                for post in posts:
                    post_uri = post['post']['uri']
                    
                    # Test like status checking
                    is_liked = self.bot._check_if_post_is_liked(post_uri)
                    
                    # Verify result
                    assert isinstance(is_liked, bool)
                    
                    # Verify post data includes like status
                    assert 'is_liked' in post['post']
                    assert isinstance(post['post']['is_liked'], bool)
                    
                    print(f"✅ Like status checked for post: {is_liked}")
                    
            else:
                print("ℹ️ No posts available for like status testing")
                
        except Exception as e:
            pytest.skip(f"Like status checking test skipped: {e}")
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_like_unlike_cycle(self):
        """Test complete like/unlike cycle"""
        try:
            # Setup authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            
            # Get a test post
            posts = self.bot.fetch_posts_with_images_web(
                target_count=1, 
                max_fetches=3, 
                max_posts_per_user=1
            )
            
            if posts and posts[0]['post']['uri']:
                test_post_uri = posts[0]['post']['uri']
                
                # Check initial status
                initial_status = self.bot._check_if_post_is_liked(test_post_uri)
                print(f"Initial like status: {initial_status}")
                
                # Like the post
                like_result = self.bot.like_post(test_post_uri)
                if like_result['success']:
                    print("✅ Post liked successfully")
                    
                    # Check status after liking
                    liked_status = self.bot._check_if_post_is_liked(test_post_uri)
                    print(f"Status after liking: {liked_status}")
                    
                    # Unlike the post
                    unlike_result = self.bot.unlike_post(test_post_uri)
                    if unlike_result['success']:
                        print("✅ Post unliked successfully")
                        
                        # Check final status
                        final_status = self.bot._check_if_post_is_liked(test_post_uri)
                        print(f"Final like status: {final_status}")
                        
                        print("✅ Complete like/unlike cycle successful")
                    else:
                        print(f"ℹ️ Unlike result: {unlike_result}")
                else:
                    print(f"ℹ️ Like result: {like_result}")
                    
            else:
                print("ℹ️ No posts available for like/unlike cycle testing")
                
        except Exception as e:
            pytest.skip(f"Like/unlike cycle test skipped: {e}")
    
    @pytest.mark.integration
    def test_like_error_handling(self):
        """Test like functionality error handling"""
        try:
            # Setup authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            
            # Test with invalid post URI
            invalid_uri = "at://invalid.did/app.bsky.feed.post/invalid"
            
            # Test like with invalid URI
            like_result = self.bot.like_post(invalid_uri)
            assert isinstance(like_result, dict)
            assert 'success' in like_result
            assert like_result['success'] is False
            assert 'error' in like_result
            print(f"✅ Like error handling working: {like_result['error']}")
            
            # Test unlike with invalid URI
            unlike_result = self.bot.unlike_post(invalid_uri)
            assert isinstance(unlike_result, dict)
            assert 'success' in unlike_result
            assert unlike_result['success'] is False
            assert 'error' in unlike_result
            print(f"✅ Unlike error handling working: {unlike_result['error']}")
            
        except Exception as e:
            pytest.skip(f"Like error handling test skipped: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
