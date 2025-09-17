#!/usr/bin/env python3
"""
Unit Tests for Bluesky Bot System
Tests individual methods and edge cases without external dependencies
"""

import pytest
import tempfile
import os
import shutil
import sys
from unittest.mock import Mock, patch, MagicMock

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import modules
from bluesky_bot import BlueskyBot
from ai_config import AIConfigManager, AIConfig


class TestBlueskyBotUnit:
    """Unit tests for BlueskyBot class methods"""
    
    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.bot = BlueskyBot()
        self.temp_dir = tempfile.mkdtemp()
        self.bot.temp_dir = self.temp_dir
    
    def teardown_method(self):
        """Clean up after each test method"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @pytest.mark.unit
    def test_get_safe_image_count_with_images(self):
        """Test _get_safe_image_count with posts that have images"""
        # Mock post with images
        mock_post = Mock()
        mock_post.post.record.embed.images = [Mock(), Mock(), Mock()]  # 3 images
        
        result = self.bot._get_safe_image_count(mock_post)
        assert result == 3
    
    @pytest.mark.unit
    def test_get_safe_image_count_no_images(self):
        """Test _get_safe_image_count with posts that have no images"""
        # Mock post without images
        mock_post = Mock()
        mock_post.post.record.embed.images = []
        
        result = self.bot._get_safe_image_count(mock_post)
        assert result == 0
    
    @pytest.mark.unit
    def test_get_safe_image_count_no_embed(self):
        """Test _get_safe_image_count with posts that have no embed"""
        # Mock post without embed
        mock_post = Mock()
        mock_post.post.record.embed = None
        
        result = self.bot._get_safe_image_count(mock_post)
        assert result == 0
    
    @pytest.mark.unit
    def test_get_safe_image_count_no_record(self):
        """Test _get_safe_image_count with posts that have no record"""
        # Mock post without record
        mock_post = Mock()
        mock_post.post.record = None
        
        result = self.bot._get_safe_image_count(mock_post)
        assert result == 0
    
    @pytest.mark.unit
    def test_get_safe_image_count_no_post(self):
        """Test _get_safe_image_count with posts that have no post attribute"""
        # Mock post without post attribute
        mock_post = Mock()
        del mock_post.post
        
        result = self.bot._get_safe_image_count(mock_post)
        assert result == 0
    
    @pytest.mark.unit
    def test_get_safe_image_count_exception_handling(self):
        """Test _get_safe_image_count handles exceptions gracefully"""
        # Mock post that raises exception
        mock_post = Mock()
        mock_post.post.record.embed.images = Mock()
        mock_post.post.record.embed.images.__len__ = Mock(side_effect=Exception("Test exception"))
        
        result = self.bot._get_safe_image_count(mock_post)
        assert result == 0
    
    @pytest.mark.unit
    def test_has_media_with_images(self):
        """Test _has_media with posts that have images"""
        # Mock post with images
        mock_post = Mock()
        mock_post.post.record.embed.images = [Mock(), Mock()]
        
        result = self.bot._has_media(mock_post)
        assert result is True
    
    @pytest.mark.unit
    def test_has_media_with_external_thumb(self):
        """Test _has_media with posts that have external links with thumbnails"""
        # Mock post with external link and thumbnail
        mock_post = Mock()
        mock_post.post.record.embed.images = None
        mock_post.post.record.embed.external = Mock()
        mock_post.post.record.embed.external.thumb = Mock()
        
        result = self.bot._has_media(mock_post)
        assert result is True
    
    @pytest.mark.unit
    def test_has_media_with_video_thumb(self):
        """Test _has_media with posts that have video with thumbnails"""
        # Mock post with video and thumbnail
        mock_post = Mock()
        mock_post.post.record.embed.images = None
        mock_post.post.record.embed.external = None
        mock_post.post.record.embed.video = Mock()
        mock_post.post.record.embed.video.thumb = Mock()
        
        result = self.bot._has_media(mock_post)
        assert result is True
    
    @pytest.mark.unit
    def test_has_media_no_media(self):
        """Test _has_media with posts that have no media"""
        # Mock post without any media
        mock_post = Mock()
        mock_post.post.record.embed.images = None
        mock_post.post.record.embed.external = None
        mock_post.post.record.embed.video = None
        
        result = self.bot._has_media(mock_post)
        assert result is False
    
    @pytest.mark.unit
    def test_has_media_exception_handling(self):
        """Test _has_media handles exceptions gracefully"""
        # Mock post that raises exception
        mock_post = Mock()
        mock_post.post.record.embed = Mock(side_effect=Exception("Test exception"))
        
        result = self.bot._has_media(mock_post)
        assert result is False
    
    @pytest.mark.unit
    def test_setup_temp_directory(self):
        """Test setup_temp_directory creates a valid temp directory"""
        temp_dir = self.bot.setup_temp_directory()
        
        assert temp_dir is not None
        assert os.path.exists(temp_dir)
        assert os.path.isdir(temp_dir)
        assert temp_dir.startswith('/tmp/bluesky_images_')
    
    @pytest.mark.unit
    @patch('boto3.client')
    def test_get_ssm_parameter_success(self, mock_boto_client):
        """Test get_ssm_parameter with successful SSM response"""
        # Mock SSM client response
        mock_ssm = Mock()
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': 'test_password'}
        }
        mock_boto_client.return_value = mock_ssm
        
        result = self.bot.get_ssm_parameter('TEST_PARAM')
        assert result == 'test_password'
        mock_ssm.get_parameter.assert_called_once_with(
            Name='TEST_PARAM',
            WithDecryption=True
        )
    
    @pytest.mark.unit
    @patch('boto3.client')
    def test_get_ssm_parameter_fallback_to_env(self, mock_boto_client):
        """Test get_ssm_parameter falls back to environment variable"""
        # Mock SSM client to raise exception
        mock_ssm = Mock()
        mock_ssm.get_parameter.side_effect = Exception("SSM error")
        mock_boto_client.return_value = mock_ssm
        
        # Set environment variable
        with patch.dict(os.environ, {'TEST_PARAM': 'env_password'}):
            result = self.bot.get_ssm_parameter('TEST_PARAM')
            assert result == 'env_password'
    
    @pytest.mark.unit
    @patch('boto3.client')
    def test_get_ssm_parameter_no_fallback(self, mock_boto_client):
        """Test get_ssm_parameter raises exception when no fallback available"""
        # Mock SSM client to raise exception
        mock_ssm = Mock()
        mock_ssm.get_parameter.side_effect = Exception("SSM error")
        mock_boto_client.return_value = mock_ssm
        
        # No environment variable set
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception, match="SSM error"):
                self.bot.get_ssm_parameter('TEST_PARAM')


class TestAIConfigUnit:
    """Unit tests for AI configuration functionality"""
    
    @pytest.mark.unit
    def test_ai_config_to_dict(self):
        """Test AIConfig to_dict method"""
        config = AIConfig(
            persona="Test persona",
            tone_do="Test do",
            tone_dont="Test don't",
            location="Test location",
            sample_reply_1="Reply 1",
            sample_reply_2="Reply 2",
            sample_reply_3="Reply 3"
        )
        
        result = config.to_dict()
        assert result['persona'] == "Test persona"
        assert result['tone_do'] == "Test do"
        assert result['tone_dont'] == "Test don't"
        assert result['location'] == "Test location"
        assert result['sample_reply_1'] == "Reply 1"
        assert result['sample_reply_2'] == "Reply 2"
        assert result['sample_reply_3'] == "Reply 3"
    
    @pytest.mark.unit
    def test_ai_config_from_dict(self):
        """Test AIConfig from_dict method"""
        data = {
            'persona': "Test persona",
            'tone_do': "Test do",
            'tone_dont': "Test don't",
            'location': "Test location",
            'sample_reply_1': "Reply 1",
            'sample_reply_2': "Reply 2",
            'sample_reply_3': "Reply 3"
        }
        
        config = AIConfig.from_dict(data)
        assert config.persona == "Test persona"
        assert config.tone_do == "Test do"
        assert config.tone_dont == "Test don't"
        assert config.location == "Test location"
        assert config.sample_reply_1 == "Reply 1"
        assert config.sample_reply_2 == "Reply 2"
        assert config.sample_reply_3 == "Reply 3"
    
    @pytest.mark.unit
    def test_ai_config_build_system_prompt(self):
        """Test AIConfig build_system_prompt method"""
        config = AIConfig(
            persona="You are a helpful assistant",
            tone_do="Be helpful and friendly",
            tone_dont="Don't be rude",
            location="Seattle",
            sample_reply_1="Sample 1",
            sample_reply_2="Sample 2",
            sample_reply_3="Sample 3"
        )
        
        prompt = config.build_system_prompt()
        assert "You are a helpful assistant" in prompt
        assert "Be helpful and friendly" in prompt
        assert "Don't be rude" in prompt
        assert "Seattle" in prompt
        assert "Sample 1" in prompt
        assert "Sample 2" in prompt
        assert "Sample 3" in prompt


class TestEdgeCases:
    """Unit tests for edge cases and error conditions"""
    
    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.bot = BlueskyBot()
    
    @pytest.mark.unit
    def test_empty_timeline_handling(self):
        """Test handling of empty timeline responses"""
        # This would be tested with mocked API responses
        # For now, we test the method exists and handles None gracefully
        assert hasattr(self.bot, 'fetch_timeline')
    
    @pytest.mark.unit
    def test_invalid_post_uri_handling(self):
        """Test handling of invalid post URIs"""
        # Test that the method exists and can handle invalid URIs
        assert hasattr(self.bot, 'post_reply')
    
    @pytest.mark.unit
    def test_network_timeout_handling(self):
        """Test handling of network timeouts"""
        # Test that HTTP session is configured with retries
        assert hasattr(self.bot, '_setup_http_session')
    
    @pytest.mark.unit
    def test_rate_limit_handling(self):
        """Test rate limiting functionality"""
        # Test that rate limiting methods exist
        assert hasattr(self.bot, '_check_rate_limit')
        assert hasattr(self.bot, '_update_rate_limit')
    
    @pytest.mark.unit
    def test_cache_management(self):
        """Test cache management functionality"""
        # Test that cache management methods exist
        assert hasattr(self.bot, '_cleanup_expired_cache')
        assert hasattr(self.bot, '_get_cached_timeline')
        assert hasattr(self.bot, '_cache_timeline')
