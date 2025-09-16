#!/usr/bin/env python3
"""
Real integration tests for Bluesky Bot - TDD approach
Tests actual AWS SSM and Bluesky API integration
"""

import pytest
import tempfile
import os
import shutil
from bluesky_bot import BlueskyBot
import config


class TestBlueskyBotIntegration:
    """Real integration tests for BlueskyBot"""
    
    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.bot = BlueskyBot()
        self.temp_dir = None
    
    def teardown_method(self):
        """Clean up after each test method"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_ssm_parameter_retrieval_real(self):
        """Test that we can retrieve the real SSM parameter"""
        # Act
        password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
        
        # Assert
        assert password is not None
        assert len(password) > 0
        assert isinstance(password, str)
        print(f"✅ Successfully retrieved SSM parameter (length: {len(password)})")
    
    def test_bluesky_authentication_real(self):
        """Test real Bluesky authentication with SSM credentials"""
        # Arrange
        password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
        
        # Act
        self.bot.authenticate(config.BLUESKY_HANDLE, password)
        
        # Assert
        assert self.bot.client is not None
        print(f"✅ Successfully authenticated as {config.BLUESKY_HANDLE}")
    
    def test_timeline_fetch_real(self):
        """Test fetching real timeline posts"""
        # Arrange
        password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
        self.bot.authenticate(config.BLUESKY_HANDLE, password)
        
        # Act
        timeline = self.bot.fetch_timeline(limit=5)
        
        # Assert
        assert timeline is not None
        assert len(timeline) > 0
        assert len(timeline) <= 5
        print(f"✅ Successfully fetched {len(timeline)} posts from timeline")
        
        # Verify post structure
        for post in timeline:
            assert hasattr(post, 'post')
            assert hasattr(post.post, 'record')
            assert hasattr(post.post, 'author')
            assert hasattr(post.post.author, 'handle')
            assert hasattr(post.post.author, 'display_name')
    
    def test_posts_with_images_detection(self):
        """Test detecting posts that contain embedded images"""
        # Arrange
        password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
        self.bot.authenticate(config.BLUESKY_HANDLE, password)
        
        # Act - use the new method to find posts with images
        posts_with_images = self.bot.fetch_posts_with_images(target_count=3, max_fetches=5)
        
        # Assert
        assert len(posts_with_images) > 0, "Should find at least one post with images"
        print(f"✅ Found {len(posts_with_images)} posts with embedded images")
        
        # Verify the posts have images
        for post in posts_with_images:
            assert hasattr(post.post.record, 'embed')
            assert post.post.record.embed is not None
            assert hasattr(post.post.record.embed, 'images')
            assert len(post.post.record.embed.images) > 0
            print(f"✅ Post has {len(post.post.record.embed.images)} image(s)")
    
    def test_image_download_real(self):
        """Test downloading real images from posts"""
        # Arrange
        password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
        self.bot.authenticate(config.BLUESKY_HANDLE, password)
        self.bot.setup_temp_directory()
        
        # Get posts with images
        posts_with_images = self.bot.fetch_posts_with_images(target_count=2, max_fetches=5)
        
        # Act
        downloaded_images = []
        for post in posts_with_images:
            embeds = self.bot.process_embeds(post)
            for embed in embeds:
                if embed['type'] == 'image' and embed['local_path']:
                    downloaded_images.append(embed)
        
        # Assert
        assert len(downloaded_images) > 0, "Should download at least one image"
        print(f"✅ Downloaded {len(downloaded_images)} images")
        
        # Verify downloaded images
        for image_info in downloaded_images:
            assert os.path.exists(image_info['local_path'])
            assert os.path.getsize(image_info['local_path']) > 0
            
            # Test image info extraction
            info = self.bot.get_image_info(image_info['local_path'])
            assert 'width' in info
            assert 'height' in info
            assert 'file_size' in info
            assert 'format' in info
            assert info['width'] > 0
            assert info['height'] > 0
            assert info['file_size'] > 0
            print(f"✅ Image: {info['width']}x{info['height']}, {info['file_size']} bytes, {info['format']}")
    
    def test_full_workflow_integration(self):
        """Test the complete workflow end-to-end"""
        # Act
        self.bot.run(config.BLUESKY_HANDLE, target_posts_with_images=2)
        
        # Assert - if we get here without exceptions, the workflow worked
        assert self.bot.temp_dir is not None
        assert os.path.exists(self.bot.temp_dir)
        print("✅ Full workflow completed successfully")
    
    def test_post_formatting_real(self):
        """Test formatting real post data"""
        # Arrange
        password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
        self.bot.authenticate(config.BLUESKY_HANDLE, password)
        timeline = self.bot.fetch_timeline(limit=1)
        
        # Act
        formatted_text = self.bot.format_post_text(timeline[0])
        
        # Assert
        assert formatted_text is not None
        assert len(formatted_text) > 0
        assert config.BLUESKY_HANDLE in formatted_text or timeline[0].post.author.handle in formatted_text
        print("✅ Post formatting works correctly")
    
    def test_timeline_posts_have_required_fields(self):
        """Test that timeline posts have all required fields"""
        # Arrange
        password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
        self.bot.authenticate(config.BLUESKY_HANDLE, password)
        timeline = self.bot.fetch_timeline(limit=5)
        
        # Act & Assert
        for i, post in enumerate(timeline):
            # Check post structure
            assert hasattr(post, 'post'), f"Post {i} missing 'post' attribute"
            assert hasattr(post.post, 'record'), f"Post {i} missing 'record' attribute"
            assert hasattr(post.post, 'author'), f"Post {i} missing 'author' attribute"
            assert hasattr(post.post, 'indexedAt'), f"Post {i} missing 'indexedAt' attribute"
            assert hasattr(post.post, 'uri'), f"Post {i} missing 'uri' attribute"
            
            # Check author structure
            assert hasattr(post.post.author, 'handle'), f"Post {i} author missing 'handle' attribute"
            assert hasattr(post.post.author, 'display_name'), f"Post {i} author missing 'display_name' attribute"
            
            # Check record structure
            assert hasattr(post.post.record, 'text'), f"Post {i} record missing 'text' attribute"
            
            print(f"✅ Post {i+1} has all required fields")
    
    def test_image_processing_workflow(self):
        """Test the complete image processing workflow"""
        # Arrange
        password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
        self.bot.authenticate(config.BLUESKY_HANDLE, password)
        self.bot.setup_temp_directory()
        
        timeline = self.bot.fetch_timeline(limit=10)
        
        # Act
        processed_posts = []
        for post in timeline:
            embeds = self.bot.process_embeds(post)
            if embeds:
                processed_posts.append((post, embeds))
        
        # Assert
        print(f"✅ Processed {len(processed_posts)} posts with media")
        
        for post, embeds in processed_posts:
            for embed in embeds:
                if embed['type'] == 'image':
                    # Verify image was downloaded
                    assert os.path.exists(embed['local_path'])
                    
                    # Verify image info was extracted
                    assert 'info' in embed
                    assert embed['info']['width'] > 0
                    assert embed['info']['height'] > 0
                    assert embed['info']['file_size'] > 0
                    
                    print(f"✅ Image processed: {embed['filename']} ({embed['info']['width']}x{embed['info']['height']})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
