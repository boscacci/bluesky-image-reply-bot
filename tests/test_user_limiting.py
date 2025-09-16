#!/usr/bin/env python3
"""
Test suite for user limiting functionality - TDD approach
Tests that posts are limited per user to behave like a human
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'bluesky_bot'))

# Import the Flask app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import BlueskyWebBot


class TestUserLimiting:
    """Test user limiting functionality"""
    
    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.bot = BlueskyWebBot()
        self.temp_dir = tempfile.mkdtemp()
        self.bot.temp_dir = self.temp_dir
    
    def teardown_method(self):
        """Clean up after each test method"""
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def create_mock_post(self, user_handle, post_text, has_images=True):
        """Helper to create mock posts"""
        mock_post = Mock()
        mock_post.post.author.handle = user_handle
        mock_post.post.author.display_name = f"User {user_handle.split('.')[0]}"
        mock_post.post.author.avatar = None
        mock_post.post.record.text = post_text
        mock_post.post.uri = f"at://did:plc:123/{user_handle.replace('.', '_')}"
        mock_post.post.indexed_at = "2024-01-01T00:00:00Z"
        mock_post.post.reply_count = 0
        mock_post.post.repost_count = 0
        mock_post.post.like_count = 0
        
        if has_images:
            mock_image = Mock()
            mock_image.image.ref.link = "bafkrei123456"
            mock_image.alt = "Test image"
            mock_embed = Mock()
            mock_embed.images = [mock_image]
            mock_post.post.record.embed = mock_embed
        else:
            mock_post.post.record.embed = None
        
        return mock_post
    
    @patch('app.Client')
    @patch('app.requests.get')
    def test_user_limiting_respects_max_posts_per_user(self, mock_get, mock_client_class):
        """Test that user limiting respects the max_posts_per_user parameter"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_get.return_value = mock_response
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        self.bot.client = mock_client
        
        # Create mock posts from the same user
        mock_posts = [
            self.create_mock_post("user1.bsky.social", "Post 1"),
            self.create_mock_post("user1.bsky.social", "Post 2"),
            self.create_mock_post("user1.bsky.social", "Post 3"),
            self.create_mock_post("user2.bsky.social", "Post 4"),
            self.create_mock_post("user2.bsky.social", "Post 5"),
        ]
        
        mock_timeline = Mock()
        mock_timeline.feed = mock_posts
        mock_timeline.cursor = None
        mock_client.get_timeline.return_value = mock_timeline
        
        # Act - limit to 2 posts per user
        result = self.bot.fetch_posts_with_images(target_count=10, max_fetches=1, max_posts_per_user=2)
        
        # Assert - should only get 2 posts from user1 and 2 from user2
        assert len(result) == 4
        user1_posts = [post for post in result if post['author']['handle'] == 'user1.bsky.social']
        user2_posts = [post for post in result if post['author']['handle'] == 'user2.bsky.social']
        assert len(user1_posts) == 2
        assert len(user2_posts) == 2
    
    @patch('app.Client')
    @patch('app.requests.get')
    def test_user_limiting_with_different_limits(self, mock_get, mock_client_class):
        """Test user limiting with different max_posts_per_user values"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_get.return_value = mock_response
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        self.bot.client = mock_client
        
        # Create mock posts from the same user
        mock_posts = [
            self.create_mock_post("user1.bsky.social", "Post 1"),
            self.create_mock_post("user1.bsky.social", "Post 2"),
            self.create_mock_post("user1.bsky.social", "Post 3"),
        ]
        
        mock_timeline = Mock()
        mock_timeline.feed = mock_posts
        mock_timeline.cursor = None
        mock_client.get_timeline.return_value = mock_timeline
        
        # Act - limit to 1 post per user
        result = self.bot.fetch_posts_with_images(target_count=10, max_fetches=1, max_posts_per_user=1)
        
        # Assert - should only get 1 post from user1
        assert len(result) == 1
        assert result[0]['author']['handle'] == 'user1.bsky.social'
    
    @patch('app.Client')
    @patch('app.requests.get')
    def test_user_limiting_skips_posts_after_limit(self, mock_get, mock_client_class):
        """Test that posts are skipped after reaching the limit per user"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_get.return_value = mock_response
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        self.bot.client = mock_client
        
        # Create mock posts - first 3 from user1, then 1 from user2
        mock_posts = [
            self.create_mock_post("user1.bsky.social", "Post 1"),
            self.create_mock_post("user1.bsky.social", "Post 2"),
            self.create_mock_post("user1.bsky.social", "Post 3"),  # This should be skipped
            self.create_mock_post("user2.bsky.social", "Post 4"),
        ]
        
        mock_timeline = Mock()
        mock_timeline.feed = mock_posts
        mock_timeline.cursor = None
        mock_client.get_timeline.return_value = mock_timeline
        
        # Act - limit to 2 posts per user
        result = self.bot.fetch_posts_with_images(target_count=10, max_fetches=1, max_posts_per_user=2)
        
        # Assert - should get 2 from user1 and 1 from user2
        assert len(result) == 3
        user1_posts = [post for post in result if post['author']['handle'] == 'user1.bsky.social']
        user2_posts = [post for post in result if post['author']['handle'] == 'user2.bsky.social']
        assert len(user1_posts) == 2
        assert len(user2_posts) == 1
        
        # Verify the posts are the first two from user1
        assert user1_posts[0]['post']['text'] == "Post 1"
        assert user1_posts[1]['post']['text'] == "Post 2"
    
    @patch('app.Client')
    @patch('app.requests.get')
    def test_user_limiting_with_mixed_posts(self, mock_get, mock_client_class):
        """Test user limiting with mixed posts (some with images, some without)"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_get.return_value = mock_response
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        self.bot.client = mock_client
        
        # Create mock posts - mix of posts with and without images
        mock_posts = [
            self.create_mock_post("user1.bsky.social", "Post 1 with image", has_images=True),
            self.create_mock_post("user1.bsky.social", "Post 2 without image", has_images=False),
            self.create_mock_post("user1.bsky.social", "Post 3 with image", has_images=True),
            self.create_mock_post("user1.bsky.social", "Post 4 with image", has_images=True),  # Should be skipped
        ]
        
        mock_timeline = Mock()
        mock_timeline.feed = mock_posts
        mock_timeline.cursor = None
        mock_client.get_timeline.return_value = mock_timeline
        
        # Act - limit to 2 posts per user
        result = self.bot.fetch_posts_with_images(target_count=10, max_fetches=1, max_posts_per_user=2)
        
        # Assert - should only get 2 posts with images from user1
        assert len(result) == 2
        assert all(post['author']['handle'] == 'user1.bsky.social' for post in result)
        assert result[0]['post']['text'] == "Post 1 with image"
        assert result[1]['post']['text'] == "Post 3 with image"
    
    @patch('app.Client')
    @patch('app.requests.get')
    def test_user_limiting_pagination(self, mock_get, mock_client_class):
        """Test user limiting works across multiple pagination batches"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_get.return_value = mock_response
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        self.bot.client = mock_client
        
        # First batch - 2 posts from user1
        batch1_posts = [
            self.create_mock_post("user1.bsky.social", "Post 1"),
            self.create_mock_post("user1.bsky.social", "Post 2"),
        ]
        
        # Second batch - 1 more from user1 (should be skipped), 1 from user2
        batch2_posts = [
            self.create_mock_post("user1.bsky.social", "Post 3"),  # Should be skipped
            self.create_mock_post("user2.bsky.social", "Post 4"),
        ]
        
        mock_timeline1 = Mock()
        mock_timeline1.feed = batch1_posts
        mock_timeline1.cursor = "cursor1"
        
        mock_timeline2 = Mock()
        mock_timeline2.feed = batch2_posts
        mock_timeline2.cursor = None
        
        mock_client.get_timeline.side_effect = [mock_timeline1, mock_timeline2]
        
        # Act - limit to 2 posts per user
        result = self.bot.fetch_posts_with_images(target_count=10, max_fetches=2, max_posts_per_user=2)
        
        # Assert - should get 2 from user1 and 1 from user2
        assert len(result) == 3
        user1_posts = [post for post in result if post['author']['handle'] == 'user1.bsky.social']
        user2_posts = [post for post in result if post['author']['handle'] == 'user2.bsky.social']
        assert len(user1_posts) == 2
        assert len(user2_posts) == 1
        
        # Verify get_timeline was called twice
        assert mock_client.get_timeline.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
