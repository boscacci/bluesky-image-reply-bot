#!/usr/bin/env python3
"""
Unit Tests for Flask API Endpoints
Tests Flask endpoints with mocked dependencies
"""

import pytest
import tempfile
import os
import shutil
import sys
import json
from unittest.mock import Mock, patch, MagicMock

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import Flask app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import app


class TestFlaskAPIUnit:
    """Unit tests for Flask API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create a test client for the Flask app"""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    @pytest.mark.unit
    def test_status_endpoint(self, client):
        """Test status endpoint returns proper structure"""
        with patch('app.bluesky_bot') as mock_bot:
            mock_bot.client = Mock()
            mock_bot.client.me.return_value = Mock(handle='test.bsky.social')
            
            response = client.get('/api/status')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert 'initialized' in data
            assert 'handle' in data
    
    @pytest.mark.unit
    def test_posts_endpoint_no_bot(self, client):
        """Test posts endpoint when bot is not initialized"""
        with patch('app.bluesky_bot', None):
            response = client.get('/api/posts')
            assert response.status_code == 500
            
            data = json.loads(response.data)
            assert 'error' in data
    
    @pytest.mark.unit
    def test_posts_endpoint_with_bot(self, client):
        """Test posts endpoint with mocked bot"""
        with patch('app.bluesky_bot') as mock_bot:
            mock_bot.fetch_posts_with_images_web.return_value = [
                {
                    'author': {'handle': 'test.bsky.social', 'display_name': 'Test User'},
                    'post': {'text': 'Test post', 'uri': 'at://test/post1'},
                    'embeds': []
                }
            ]
            
            response = client.get('/api/posts?count=1')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert 'posts' in data
            assert len(data['posts']) == 1
    
    @pytest.mark.unit
    def test_image_endpoint_security(self, client):
        """Test image endpoint security checks"""
        with patch('app.temp_dir', '/tmp/test'):
            # Test directory traversal attempt
            response = client.get('/api/image/../../../etc/passwd')
            assert response.status_code == 400
            
            data = json.loads(response.data)
            assert 'error' in data
    
    @pytest.mark.unit
    def test_image_endpoint_nonexistent_file(self, client):
        """Test image endpoint with nonexistent file"""
        with patch('app.temp_dir', '/tmp/test'):
            response = client.get('/api/image/nonexistent.jpg')
            assert response.status_code == 404
            
            data = json.loads(response.data)
            assert 'error' in data
    
    @pytest.mark.unit
    def test_ai_reply_endpoint_no_data(self, client):
        """Test AI reply endpoint with no JSON data"""
        response = client.post('/api/ai-reply')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'No JSON data provided' in data['error']
    
    @pytest.mark.unit
    def test_ai_reply_endpoint_missing_post_index(self, client):
        """Test AI reply endpoint with missing post_index"""
        response = client.post('/api/ai-reply', 
                             json={'image_filenames': ['test.jpg']})
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'post_index is required' in data['error']
    
    @pytest.mark.unit
    def test_ai_reply_endpoint_no_images(self, client):
        """Test AI reply endpoint with no image filenames"""
        response = client.post('/api/ai-reply', 
                             json={'post_index': 0})
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'No image filenames provided' in data['error']
    
    @pytest.mark.unit
    def test_ai_reply_endpoint_no_temp_dir(self, client):
        """Test AI reply endpoint when temp directory is not available"""
        with patch('app.temp_dir', None):
            response = client.post('/api/ai-reply', 
                                 json={'post_index': 0, 'image_filenames': ['test.jpg']})
            assert response.status_code == 500
            
            data = json.loads(response.data)
            assert 'error' in data
            assert 'No temporary directory available' in data['error']
    
    @pytest.mark.unit
    def test_ai_reply_endpoint_invalid_filename(self, client):
        """Test AI reply endpoint with invalid filename (directory traversal)"""
        with patch('app.temp_dir', '/tmp/test'):
            response = client.post('/api/ai-reply', 
                                 json={'post_index': 0, 'image_filenames': ['../../../etc/passwd']})
            assert response.status_code == 400
            
            data = json.loads(response.data)
            assert 'error' in data
            assert 'No valid images found' in data['error']
    
    @pytest.mark.unit
    def test_ai_reply_endpoint_success(self, client):
        """Test AI reply endpoint with valid data"""
        with patch('app.temp_dir', '/tmp/test'):
            with patch('app.generate_ai_reply_adapter') as mock_generate:
                mock_generate.return_value = "Test AI reply"
                
                # Create a temporary test file
                test_file = '/tmp/test/test.jpg'
                os.makedirs('/tmp/test', exist_ok=True)
                with open(test_file, 'w') as f:
                    f.write('test')
                
                try:
                    response = client.post('/api/ai-reply', 
                                         json={'post_index': 0, 'image_filenames': ['test.jpg']})
                    assert response.status_code == 200
                    
                    data = json.loads(response.data)
                    assert 'success' in data
                    assert data['success'] is True
                    assert 'ai_reply' in data
                    assert data['ai_reply'] == "Test AI reply"
                finally:
                    # Clean up test file
                    if os.path.exists(test_file):
                        os.remove(test_file)
    
    @pytest.mark.unit
    def test_post_reply_endpoint_no_data(self, client):
        """Test post reply endpoint with no JSON data"""
        response = client.post('/api/post-reply')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'No JSON data provided' in data['error']
    
    @pytest.mark.unit
    def test_post_reply_endpoint_missing_uri(self, client):
        """Test post reply endpoint with missing post_uri"""
        response = client.post('/api/post-reply', 
                             json={'reply_text': 'Test reply'})
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'post_uri is required' in data['error']
    
    @pytest.mark.unit
    def test_post_reply_endpoint_missing_text(self, client):
        """Test post reply endpoint with missing reply_text"""
        response = client.post('/api/post-reply', 
                             json={'post_uri': 'at://test/post1'})
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'reply_text is required' in data['error']
    
    @pytest.mark.unit
    def test_post_reply_endpoint_no_bot(self, client):
        """Test post reply endpoint when bot is not initialized"""
        with patch('app.bluesky_bot', None):
            response = client.post('/api/post-reply', 
                                 json={'post_uri': 'at://test/post1', 'reply_text': 'Test reply'})
            assert response.status_code == 500
            
            data = json.loads(response.data)
            assert 'error' in data
    
    @pytest.mark.unit
    def test_like_status_endpoint_no_data(self, client):
        """Test like status endpoint with no JSON data"""
        response = client.post('/api/like-status')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'No JSON data provided' in data['error']
    
    @pytest.mark.unit
    def test_like_status_endpoint_missing_uri(self, client):
        """Test like status endpoint with missing post_uri"""
        response = client.post('/api/like-status', 
                             json={})
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'post_uri is required' in data['error']
    
    @pytest.mark.unit
    def test_like_status_endpoint_no_bot(self, client):
        """Test like status endpoint when bot is not initialized"""
        with patch('app.bluesky_bot', None):
            response = client.post('/api/like-status', 
                                 json={'post_uri': 'at://test/post1'})
            assert response.status_code == 500
            
            data = json.loads(response.data)
            assert 'error' in data
    
    @pytest.mark.unit
    def test_like_action_endpoint_no_data(self, client):
        """Test like action endpoint with no JSON data"""
        response = client.post('/api/like-action')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'No JSON data provided' in data['error']
    
    @pytest.mark.unit
    def test_like_action_endpoint_missing_uri(self, client):
        """Test like action endpoint with missing post_uri"""
        response = client.post('/api/like-action', 
                             json={'is_liked': False})
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'post_uri is required' in data['error']
    
    @pytest.mark.unit
    def test_like_action_endpoint_missing_is_liked(self, client):
        """Test like action endpoint with missing is_liked"""
        response = client.post('/api/like-action', 
                             json={'post_uri': 'at://test/post1'})
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'is_liked is required' in data['error']
    
    @pytest.mark.unit
    def test_like_action_endpoint_no_bot(self, client):
        """Test like action endpoint when bot is not initialized"""
        with patch('app.bluesky_bot', None):
            response = client.post('/api/like-action', 
                                 json={'post_uri': 'at://test/post1', 'is_liked': False})
            assert response.status_code == 500
            
            data = json.loads(response.data)
            assert 'error' in data


class TestFlaskErrorHandling:
    """Unit tests for Flask error handling"""
    
    @pytest.fixture
    def client(self):
        """Create a test client for the Flask app"""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    @pytest.mark.unit
    def test_404_handling(self, client):
        """Test 404 error handling for non-existent endpoints"""
        response = client.get('/api/nonexistent')
        assert response.status_code == 404
    
    @pytest.mark.unit
    def test_method_not_allowed(self, client):
        """Test method not allowed error handling"""
        response = client.post('/api/status')  # GET-only endpoint
        assert response.status_code == 405
    
    @pytest.mark.unit
    def test_invalid_json_handling(self, client):
        """Test handling of invalid JSON in POST requests"""
        response = client.post('/api/ai-reply', 
                             data='invalid json',
                             content_type='application/json')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
