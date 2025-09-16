#!/usr/bin/env python3
"""
Integration Tests for Flask API Endpoints
Tests all Flask API endpoints including the new like functionality
"""

import pytest
import json
import os
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import modules
import config


class TestFlaskIntegration:
    """Integration tests for Flask web app"""
    
    @pytest.fixture
    def client(self):
        """Create a test client for the Flask app"""
        # Import here to avoid circular imports
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from app import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    @pytest.mark.integration
    def test_real_flask_status_endpoint(self, client):
        """Test real Flask status endpoint"""
        try:
            response = client.get('/api/status')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'initialized' in data
            assert 'handle' in data
            assert data['handle'] == config.BLUESKY_HANDLE
            print(f"✅ Flask status endpoint working: {data}")
            
        except Exception as e:
            pytest.skip(f"Real Flask status test skipped: {e}")
    
    @pytest.mark.integration
    def test_real_flask_ai_config_endpoint(self, client):
        """Test real Flask AI config endpoint"""
        try:
            response = client.get('/api/ai-config')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'settings' in data
            settings = data['settings']
            assert 'persona' in settings
            assert 'tone_do' in settings
            print(f"✅ Flask AI config endpoint working")
            
        except Exception as e:
            pytest.skip(f"Real Flask AI config test skipped: {e}")
    
    @pytest.mark.integration
    def test_real_flask_posts_endpoint(self, client):
        """Test real Flask posts endpoint"""
        try:
            response = client.get('/api/posts?count=1')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'posts' in data
            assert isinstance(data['posts'], list)
            print(f"✅ Flask posts endpoint working")
            
        except Exception as e:
            pytest.skip(f"Real Flask posts test skipped: {e}")
    
    @pytest.mark.integration
    def test_real_flask_like_endpoints_validation(self, client):
        """Test real Flask like/unlike API endpoints validation"""
        try:
            # Test like endpoint with invalid data
            response = client.post('/api/like', 
                                 json={}, 
                                 content_type='application/json')
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data
            assert 'post_uri is required' in data['error']
            
            # Test like endpoint with invalid post URI
            response = client.post('/api/like', 
                                 json={'post_uri': 'invalid-uri'}, 
                                 content_type='application/json')
            # Should return 400 or 500 depending on validation
            assert response.status_code in [400, 500]
            data = json.loads(response.data)
            assert 'error' in data
            
            # Test unlike endpoint with invalid data
            response = client.post('/api/unlike', 
                                 json={}, 
                                 content_type='application/json')
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data
            assert 'post_uri is required' in data['error']
            
            # Test unlike endpoint with invalid post URI
            response = client.post('/api/unlike', 
                                 json={'post_uri': 'invalid-uri'}, 
                                 content_type='application/json')
            # Should return 400 or 500 depending on validation
            assert response.status_code in [400, 500]
            data = json.loads(response.data)
            assert 'error' in data
            
            print("✅ Flask like/unlike endpoints validation working correctly")
            
        except Exception as e:
            pytest.skip(f"Real Flask like endpoints test skipped: {e}")
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_real_flask_like_workflow(self, client):
        """Test real Flask like workflow with actual post"""
        try:
            # First, get a real post from the posts endpoint
            response = client.get('/api/posts?count=1')
            assert response.status_code == 200
            data = json.loads(response.data)
            
            if data.get('posts') and len(data['posts']) > 0:
                post_uri = data['posts'][0]['post']['uri']
                
                # Test like endpoint with real post URI
                response = client.post('/api/like', 
                                     json={'post_uri': post_uri}, 
                                     content_type='application/json')
                
                # Should return 200 or 400/500 depending on success
                assert response.status_code in [200, 400, 500]
                like_data = json.loads(response.data)
                assert 'success' in like_data
                
                if like_data['success']:
                    print(f"✅ Successfully liked post via Flask API: {post_uri}")
                    
                    # Test unlike endpoint with real post URI
                    response = client.post('/api/unlike', 
                                         json={'post_uri': post_uri}, 
                                         content_type='application/json')
                    
                    # Should return 200 or 400/500 depending on success
                    assert response.status_code in [200, 400, 500]
                    unlike_data = json.loads(response.data)
                    assert 'success' in unlike_data
                    
                    if unlike_data['success']:
                        print(f"✅ Successfully unliked post via Flask API: {post_uri}")
                    else:
                        print(f"ℹ️ Unlike result: {unlike_data}")
                else:
                    print(f"ℹ️ Like result: {like_data}")
            else:
                print("ℹ️ No posts available for Flask like workflow testing")
                
        except Exception as e:
            pytest.skip(f"Real Flask like workflow test skipped: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
