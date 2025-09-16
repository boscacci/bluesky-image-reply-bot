#!/usr/bin/env python3
"""
Test suite for Bluesky Bot - TDD approach
Tests authentication, timeline fetching, and image handling
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from atproto import Client, models
import boto3
import requests
from PIL import Image
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import config
from bluesky_bot.bluesky_bot import BlueskyBot


class TestBlueskyBot:
    """Test suite for BlueskyBot class"""
    
    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.bot = BlueskyBot()
        self.temp_dir = tempfile.mkdtemp()
        self.bot.temp_dir = self.temp_dir
    
    def teardown_method(self):
        """Clean up after each test method"""
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
    
    @patch('bluesky_bot.bluesky_bot.boto3.client')
    def test_ssm_parameter_retrieval(self, mock_boto_client):
        """Test that we can retrieve the SSM parameter successfully"""
        # Arrange
        mock_ssm = Mock()
        mock_boto_client.return_value = mock_ssm
        expected_password = "test_password_123"
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': expected_password}
        }
        
        # Act
        result = self.bot.get_ssm_parameter('BLUESKY_PASSWORD_BIKELIFE')
        
        # Assert
        assert result == expected_password
        mock_ssm.get_parameter.assert_called_once_with(
            Name='BLUESKY_PASSWORD_BIKELIFE',
            WithDecryption=True
        )
    
    @patch('bluesky_bot.bluesky_bot.boto3.client')
    def test_ssm_parameter_not_found(self, mock_boto_client):
        """Test handling when SSM parameter is not found"""
        # Arrange
        mock_ssm = Mock()
        mock_boto_client.return_value = mock_ssm
        mock_ssm.get_parameter.side_effect = Exception("ParameterNotFound")
        
        # Act & Assert
        with pytest.raises(Exception, match="ParameterNotFound"):
            self.bot.get_ssm_parameter('NONEXISTENT_PARAM')
    
    @patch('bluesky_bot.bluesky_bot.Client')
    def test_bluesky_authentication_success(self, mock_client_class):
        """Test successful Bluesky authentication"""
        # Arrange
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.login.return_value = None  # Successful login
        
        # Act
        self.bot.authenticate('test.bsky.social', 'test_password')
        
        # Assert
        mock_client.login.assert_called_once_with('test.bsky.social', 'test_password')
        assert self.bot.client == mock_client
    
    @patch('bluesky_bot.bluesky_bot.Client')
    def test_bluesky_authentication_failure(self, mock_client_class):
        """Test Bluesky authentication failure"""
        # Arrange
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.login.side_effect = Exception("Authentication failed")
        
        # Act & Assert
        with pytest.raises(Exception, match="Authentication failed"):
            self.bot.authenticate('test.bsky.social', 'wrong_password')
    
    @patch('bluesky_bot.bluesky_bot.Client')
    def test_timeline_fetch_success(self, mock_client_class):
        """Test successful timeline fetching"""
        # Arrange
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Create mock posts
        mock_post1 = Mock()
        mock_post1.post.record.text = "Test post 1"
        mock_post1.post.author.handle = "user1.bsky.social"
        mock_post1.post.author.display_name = "User One"
        mock_post1.post.indexedAt = "2024-01-01T00:00:00Z"
        mock_post1.post.uri = "at://did:plc:123/post1"
        
        mock_post2 = Mock()
        mock_post2.post.record.text = "Test post 2 with image"
        mock_post2.post.author.handle = "user2.bsky.social"
        mock_post2.post.author.display_name = "User Two"
        mock_post2.post.indexedAt = "2024-01-01T01:00:00Z"
        mock_post2.post.uri = "at://did:plc:456/post2"
        
        mock_timeline = Mock()
        mock_timeline.feed = [mock_post1, mock_post2]
        mock_client.get_timeline.return_value = mock_timeline
        
        self.bot.client = mock_client
        
        # Act
        result = self.bot.fetch_timeline(limit=5)
        
        # Assert
        assert len(result) == 2
        assert result[0].post.record.text == "Test post 1"
        assert result[1].post.record.text == "Test post 2 with image"
        mock_client.get_timeline.assert_called_once_with(limit=5, algorithm='home')
    
    def test_setup_temp_directory(self):
        """Test temporary directory creation"""
        # Act
        self.bot.setup_temp_directory()
        
        # Assert
        assert self.bot.temp_dir is not None
        assert os.path.exists(self.bot.temp_dir)
        assert self.bot.temp_dir.startswith('/tmp/bluesky_images_')
    
    @patch('bluesky_bot.bluesky_bot.requests.get')
    def test_download_image_success(self, mock_get):
        """Test successful image download"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_get.return_value = mock_response
        
        # Act
        result = self.bot.download_image('https://example.com/image.jpg', 'test.jpg')
        
        # Assert
        assert result is not None
        assert os.path.exists(result)
        assert result.endswith('test.jpg')
        mock_get.assert_called_once_with('https://example.com/image.jpg', timeout=10)
    
    @patch('bluesky_bot.bluesky_bot.requests.get')
    def test_download_image_failure(self, mock_get):
        """Test image download failure"""
        # Arrange
        mock_get.side_effect = requests.RequestException("Download failed")
        
        # Act
        result = self.bot.download_image('https://example.com/broken.jpg', 'test.jpg')
        
        # Assert
        assert result is None
    
    def test_get_image_info(self):
        """Test getting image information"""
        # Arrange - create a small test image
        test_image_path = os.path.join(self.temp_dir, 'test.png')
        with Image.new('RGB', (100, 200), color='red') as img:
            img.save(test_image_path)
        
        # Act
        info = self.bot.get_image_info(test_image_path)
        
        # Assert
        assert info['width'] == 100
        assert info['height'] == 200
        assert info['format'] == 'PNG'
        assert info['file_size'] > 0
    
    def test_format_post_text(self):
        """Test post text formatting"""
        # Arrange
        mock_post = Mock()
        mock_post.post.record.text = "Hello, Bluesky!"
        mock_post.post.author.handle = "test.bsky.social"
        mock_post.post.author.display_name = "Test User"
        mock_post.post.indexedAt = "2024-01-01T00:00:00Z"
        mock_post.post.uri = "at://did:plc:123/post1"
        
        # Act
        result = self.bot.format_post_text(mock_post)
        
        # Assert
        assert "Hello, Bluesky!" in result
        assert "test.bsky.social" in result
        assert "Test User" in result
        assert "2024-01-01T00:00:00Z" in result
    
    def test_process_embeds_no_media(self):
        """Test processing posts with no embedded media"""
        # Arrange
        mock_post = Mock()
        mock_post.post.record.embed = None
        
        # Act
        result = self.bot.process_embeds(mock_post)
        
        # Assert
        assert result == []
    
    @patch('bluesky_bot.bluesky_bot.requests.get')
    def test_process_embeds_with_images(self, mock_get):
        """Test processing posts with embedded images"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_get.return_value = mock_response
        
        mock_image = Mock()
        mock_image.image.ref.link = "bafkrei123456"
        mock_image.alt = 'Test image'
        
        mock_embed = Mock()
        mock_embed.images = [mock_image]
        
        mock_post = Mock()
        mock_post.post.record.embed = mock_embed
        mock_post.post.uri = 'at://did:plc:123/post1'
        
        # Act
        result = self.bot.process_embeds(mock_post)
        
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'image'
        assert result[0]['alt_text'] == 'Test image'
        assert result[0]['local_path'] is not None
        assert os.path.exists(result[0]['local_path'])


class TestIntegration:
    """Integration tests that test the full workflow"""
    
    @patch('bluesky_bot.bluesky_bot.boto3.client')
    @patch('bluesky_bot.bluesky_bot.Client')
    def test_full_workflow_mock(self, mock_client_class, mock_boto_client):
        """Test the complete workflow with mocked dependencies"""
        # Arrange
        # Mock SSM
        mock_ssm = Mock()
        mock_boto_client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': 'test_password'}
        }
        
        # Mock Bluesky client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.login.return_value = None
        
        # Mock timeline with posts
        mock_post = Mock()
        mock_post.post.record.text = "Test post with image"
        mock_post.post.author.handle = "test.bsky.social"
        mock_post.post.author.display_name = "Test User"
        mock_post.post.indexedAt = "2024-01-01T00:00:00Z"
        mock_post.post.uri = "at://did:plc:123/post1"
        mock_post.post.record.embed = None
        
        mock_timeline = Mock()
        mock_timeline.feed = [mock_post]
        mock_client.get_timeline.return_value = mock_timeline
        
        # Act
        bot = BlueskyBot()
        bot.run('test.bsky.social', target_posts_with_images=1)
        
        # Assert
        mock_ssm.get_parameter.assert_called_once()
        mock_client.login.assert_called_once()
        mock_client.get_timeline.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
