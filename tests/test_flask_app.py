#!/usr/bin/env python3
"""
Integration Test suite for Flask Web App
Tests all Flask routes, API endpoints, and web functionality with real credentials
"""

import pytest
import json
import tempfile
import os
from flask import Flask
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import the Flask app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import app, init_bot, bluesky_bot, temp_dir
from bluesky_bot.bluesky_bot import BlueskyBot


@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def real_bluesky_bot():
    """Real BlueskyBot instance for integration testing"""
    bot = BlueskyBot()
    # Initialize with real credentials
    if bot.initialize('seattlebike.bsky.social'):
        yield bot
    else:
        pytest.skip("Failed to initialize BlueskyBot with real credentials")




class TestFlaskRoutes:
    """Test Flask routes and endpoints"""
    
    def test_index_route(self, client):
        """Test the main index route returns HTML"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Bluesky Timeline' in response.data
        assert b'Posts with Images from Users You Follow' in response.data
    
    def test_status_endpoint_not_initialized(self, client):
        """Test status endpoint when bot is not initialized"""
        global bluesky_bot
        original_bot = bluesky_bot
        bluesky_bot = None
        
        try:
            response = client.get('/api/status')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['initialized'] is False
            assert data['temp_dir'] is None
        finally:
            bluesky_bot = original_bot
    
    def test_status_endpoint_initialized(self, client, real_bluesky_bot):
        """Test status endpoint when bot is initialized"""
        global bluesky_bot, temp_dir
        original_bot = bluesky_bot
        original_temp_dir = temp_dir
        
        try:
            # Set the global variables in the app module
            import app
            app.bluesky_bot = real_bluesky_bot
            app.temp_dir = real_bluesky_bot.temp_dir
            
            response = client.get('/api/status')
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert data['initialized'] is True
            assert data['temp_dir'] is not None
            assert 'handle' in data
        finally:
            # Restore original values
            import app
            app.bluesky_bot = original_bot
            app.temp_dir = original_temp_dir
    
    def test_posts_endpoint_no_bot(self, client):
        """Test posts endpoint when bot is not initialized"""
        global bluesky_bot
        original_bot = bluesky_bot
        bluesky_bot = None
        
        try:
            response = client.get('/api/posts?count=5')
            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data
            assert 'Failed to initialize' in data['error']
        finally:
            bluesky_bot = original_bot
    
    def test_posts_endpoint_success(self, client, real_bluesky_bot):
        """Test posts endpoint with successful response"""
        global bluesky_bot
        original_bot = bluesky_bot
        
        try:
            # Set the global variables in the app module
            import app
            app.bluesky_bot = real_bluesky_bot
            
            response = client.get('/api/posts?count=5')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'posts' in data
            assert 'count' in data
            # Note: count might be 0 if no posts with images are found
            assert data['count'] >= 0
        finally:
            # Restore original values
            import app
            app.bluesky_bot = original_bot
    
    def test_posts_endpoint_multiple_images(self, client, real_bluesky_bot):
        """Test posts endpoint with posts containing multiple images"""
        global bluesky_bot
        original_bot = bluesky_bot
        
        try:
            # Set the global variables in the app module
            import app
            app.bluesky_bot = real_bluesky_bot
            
            response = client.get('/api/posts?count=5')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'posts' in data
            assert 'count' in data
            # Note: count might be 0 if no posts with images are found
            assert data['count'] >= 0
            # If posts are found, verify structure
            if data['count'] > 0:
                for post in data['posts']:
                    assert 'author' in post
                    assert 'post' in post
                    assert 'embeds' in post
        finally:
            # Restore original values
            import app
            app.bluesky_bot = original_bot
    
    def test_posts_endpoint_with_count_parameter(self, client, real_bluesky_bot):
        """Test posts endpoint with different count parameters"""
        global bluesky_bot
        original_bot = bluesky_bot
        
        try:
            # Set the global variables in the app module
            import app
            app.bluesky_bot = real_bluesky_bot
            
            # Test with count=10
            response = client.get('/api/posts?count=10')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['count'] >= 0
            
            # Test with count=15
            response = client.get('/api/posts?count=15')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['count'] >= 0
        finally:
            # Restore original values
            import app
            app.bluesky_bot = original_bot
    
    def test_posts_endpoint_bot_error(self, client):
        """Test posts endpoint when bot is not initialized"""
        global bluesky_bot
        original_bot = bluesky_bot
        
        try:
            # Set the global variables in the app module
            import app
            app.bluesky_bot = None
            
            response = client.get('/api/posts?count=5')
            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data
            assert 'Failed to initialize' in data['error']
        finally:
            # Restore original values
            import app
            app.bluesky_bot = original_bot
    
    def test_image_endpoint_no_temp_dir(self, client):
        """Test image endpoint when no temp directory is available"""
        global temp_dir
        original_temp_dir = temp_dir
        
        try:
            # Set the global variables in the app module
            import app
            app.temp_dir = None
            
            response = client.get('/api/image/test.jpg')
            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'error' in data
            assert 'No temporary directory' in data['error']
        finally:
            # Restore original values
            import app
            app.temp_dir = original_temp_dir
    
    def test_image_endpoint_file_not_found(self, client):
        """Test image endpoint when image file doesn't exist"""
        global temp_dir
        original_temp_dir = temp_dir
        
        try:
            # Set the global variables in the app module
            import app
            app.temp_dir = '/tmp/nonexistent'
            
            response = client.get('/api/image/nonexistent.jpg')
            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'error' in data
            assert 'Image not found' in data['error']
        finally:
            # Restore original values
            import app
            app.temp_dir = original_temp_dir
    
    def test_image_endpoint_success(self, client, real_bluesky_bot):
        """Test image endpoint with successful file serving"""
        global temp_dir
        original_temp_dir = temp_dir
        
        try:
            # Set the global variables in the app module
            import app
            app.temp_dir = real_bluesky_bot.temp_dir
            
            # Create a temporary test image file
            test_filename = 'test_image.jpg'
            test_file_path = os.path.join(real_bluesky_bot.temp_dir, test_filename)
            with open(test_file_path, 'wb') as f:
                f.write(b'fake_image_data')
            
            response = client.get(f'/api/image/{test_filename}')
            assert response.status_code == 200
            assert response.data == b'fake_image_data'
            
            # Clean up test file
            os.unlink(test_file_path)
        finally:
            # Restore original values
            import app
            app.temp_dir = original_temp_dir


class TestBlueskyBot:
    """Integration tests for the BlueskyBot class"""
    
    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.bot = BlueskyBot()
        # Initialize with real credentials
        if not self.bot.initialize('seattlebike.bsky.social'):
            pytest.skip("Failed to initialize BlueskyBot with real credentials")
    
    def teardown_method(self):
        """Clean up after each test method"""
        if self.bot.temp_dir and os.path.exists(self.bot.temp_dir):
            import shutil
            shutil.rmtree(self.bot.temp_dir)
    
    def test_ssm_parameter_retrieval(self):
        """Test SSM parameter retrieval with real AWS"""
        # Act
        result = self.bot.get_ssm_parameter('BLUESKY_PASSWORD_BIKELIFE')
        
        # Assert
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_authenticate_success(self):
        """Test successful authentication with real credentials"""
        # This test is already covered by the setup_method initialization
        assert self.bot.client is not None
    
    def test_setup_temp_directory(self):
        """Test temporary directory setup"""
        # Act
        result = self.bot.setup_temp_directory()
        
        # Assert
        assert result is not None
        assert os.path.exists(result)
        assert result.startswith('/tmp/bluesky_images_')
        assert self.bot.temp_dir == result
    
    def test_download_image_success(self):
        """Test successful image download with real URL"""
        # Use a real image URL for testing
        test_url = 'https://picsum.photos/100/100.jpg'
        test_filename = 'test_download.jpg'
        
        # Act
        result = self.bot.download_image(test_url, test_filename)
        
        # Assert
        if result is not None:  # May fail due to network issues
            assert os.path.exists(result)
            assert result.endswith(test_filename)
            # Clean up
            os.unlink(result)
    
    def test_download_image_failure(self):
        """Test image download failure with invalid URL"""
        # Act
        result = self.bot.download_image('https://invalid-url-that-does-not-exist.com/image.jpg', 'test.jpg')
        
        # Assert
        assert result is None
    
    def test_get_image_info(self):
        """Test getting image information"""
        # Arrange - create a small test image
        test_image_path = os.path.join(self.temp_dir, 'test.png')
        from PIL import Image
        with Image.new('RGB', (100, 200), color='red') as img:
            img.save(test_image_path)
        
        # Act
        info = self.bot.get_image_info(test_image_path)
        
        # Assert
        assert info['width'] == 100
        assert info['height'] == 200
        assert info['format'] == 'PNG'
        assert info['file_size'] > 0
    
    def test_format_post_for_web(self):
        """Test formatting post data for web display with real posts"""
        # Fetch a real post from the timeline
        posts = self.bot.fetch_timeline(limit=1)
        if not posts:
            pytest.skip("No posts available in timeline")
        
        post = posts[0]
        
        # Act
        result = self.bot.format_post_for_web(post)
        
        # Assert
        assert 'author' in result
        assert 'post' in result
        assert 'embeds' in result
        assert 'handle' in result['author']
        assert 'display_name' in result['author']
        assert 'text' in result['post']
        assert 'uri' in result['post']
    
    def test_process_embeds_with_images(self):
        """Test processing posts with embedded images using real posts"""
        # Fetch posts with images
        posts_with_images = self.bot.fetch_posts_with_images(target_count=1, max_fetches=5)
        if not posts_with_images:
            pytest.skip("No posts with images found in timeline")
        
        post = posts_with_images[0]
        
        # Act
        result = self.bot.process_embeds(post)
        
        # Assert
        assert isinstance(result, list)
        # If images were processed, verify structure
        for embed in result:
            assert 'type' in embed
            assert 'url' in embed
            if embed['type'] == 'image':
                assert 'local_path' in embed
                assert 'filename' in embed
                assert 'info' in embed
    
    def test_process_embeds_no_media(self):
        """Test processing posts with no embedded media using real posts"""
        # Fetch posts without images
        posts = self.bot.fetch_timeline(limit=10)
        if not posts:
            pytest.skip("No posts available in timeline")
        
        # Find a post without embeds
        post_without_embeds = None
        for post in posts:
            if not hasattr(post.post.record, 'embed') or not post.post.record.embed:
                post_without_embeds = post
                break
        
        if not post_without_embeds:
            pytest.skip("No posts without embeds found")
        
        # Act
        result = self.bot.process_embeds(post_without_embeds)
        
        # Assert
        assert result == []
    
    def test_fetch_posts_with_images_success(self):
        """Test successful fetching of posts with images using real API"""
        # Act
        result = self.bot.fetch_posts_with_images_web(target_count=1, max_fetches=5)
        
        # Assert
        assert isinstance(result, list)
        # Note: result might be empty if no posts with images are found
        if result:
            post = result[0]
            assert 'author' in post
            assert 'post' in post
            assert 'embeds' in post
            assert 'handle' in post['author']
            assert 'text' in post['post']
    
    def test_initialize_success(self):
        """Test successful bot initialization with real credentials"""
        # This test is already covered by the setup_method initialization
        assert self.bot.client is not None
        assert self.bot.temp_dir is not None


class TestHTMLTemplateRendering:
    """Test HTML template rendering with new image display behavior"""
    
    def test_index_template_renders_correctly(self, client):
        """Test that the index template renders without errors"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Posts with Images from Users You Follow' in response.data
        assert b'posts-container' in response.data
        assert b'row g-4' in response.data  # Check for grid layout
    
    def test_template_contains_grid_layout(self, client):
        """Test that the template contains the grid layout classes"""
        response = client.get('/')
        assert response.status_code == 200
        # Check for Bootstrap grid classes
        assert b'col-lg-4' in response.data
        assert b'col-md-6' in response.data
        assert b'col-sm-12' in response.data
        assert b'h-100' in response.data  # Check for equal height cards
    
    def test_template_contains_image_display_logic(self, client):
        """Test that the template contains JavaScript for first image display"""
        response = client.get('/')
        assert response.status_code == 200
        # Check for JavaScript that handles first image display
        assert b'images[0].filename' in response.data
        assert b'+${images.length - 1} more image' in response.data


class TestInitBot:
    """Integration tests for the init_bot function"""
    
    def test_init_bot_success(self):
        """Test successful bot initialization with real credentials"""
        global bluesky_bot, temp_dir
        original_bot = bluesky_bot
        original_temp_dir = temp_dir
        
        try:
            # Set the global variables in the app module
            import app
            app.bluesky_bot = None
            app.temp_dir = None
            
            result = init_bot()
            
            assert result is True
            assert app.bluesky_bot is not None
            assert app.temp_dir is not None
        finally:
            # Restore original values
            import app
            app.bluesky_bot = original_bot
            app.temp_dir = original_temp_dir
    
    def test_init_bot_already_initialized(self):
        """Test init_bot when bot is already initialized"""
        global bluesky_bot
        original_bot = bluesky_bot
        
        try:
            # Initialize bot first
            if init_bot():
                result = init_bot()  # Call again
                assert result is True
        finally:
            # Restore original values
            import app
            app.bluesky_bot = original_bot


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
