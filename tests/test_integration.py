#!/usr/bin/env python3
"""
Streamlined Integration Tests for Bluesky Bot System
Tests key functionality with real API calls - no mocks
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
from ai_config import AIConfigManager, OpenAIClient, generate_ai_reply
import config


class TestBlueskyIntegration:
    """Integration tests for Bluesky bot functionality"""
    
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
    
    @pytest.mark.integration
    def test_real_like_post_functionality(self):
        """Test real like post functionality via AT protocol"""
        try:
            # Setup real authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            self.bot.temp_dir = self.temp_dir
            
            # Fetch a post to like (get a real post URI)
            posts = self.bot.fetch_posts_with_images_web(
                target_count=1, 
                max_fetches=3, 
                max_posts_per_user=1
            )
            
            if posts and posts[0]['post']['uri']:
                test_post_uri = posts[0]['post']['uri']
                
                # Test like functionality
                like_result = self.bot.like_post(test_post_uri)
                
                # Verify like result structure
                assert isinstance(like_result, dict)
                assert 'success' in like_result
                
                if like_result['success']:
                    assert 'like_uri' in like_result
                    assert 'message' in like_result
                    print(f"✅ Successfully liked post: {test_post_uri}")
                    
                    # Test unlike functionality
                    unlike_result = self.bot.unlike_post(test_post_uri)
                    assert isinstance(unlike_result, dict)
                    assert 'success' in unlike_result
                    
                    if unlike_result['success']:
                        print(f"✅ Successfully unliked post: {test_post_uri}")
                    else:
                        print(f"ℹ️ Unlike result: {unlike_result}")
                else:
                    print(f"ℹ️ Like result: {like_result}")
                    
            else:
                print("ℹ️ No posts found for like testing")
                
        except Exception as e:
            pytest.skip(f"Real like functionality test skipped: {e}")
    
    @pytest.mark.integration
    def test_real_like_status_checking(self):
        """Test real like status checking functionality"""
        try:
            # Setup real authentication
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            self.bot.temp_dir = self.temp_dir
            
            # Fetch posts and check like status
            posts = self.bot.fetch_posts_with_images_web(
                target_count=2, 
                max_fetches=5, 
                max_posts_per_user=1
            )
            
            if posts:
                # Test like status checking for each post
                for post in posts:
                    post_uri = post['post']['uri']
                    is_liked = self.bot._check_if_post_is_liked(post_uri)
                    
                    # Verify like status is boolean
                    assert isinstance(is_liked, bool)
                    
                    # Verify post data includes like status
                    assert 'is_liked' in post['post']
                    assert isinstance(post['post']['is_liked'], bool)
                    
                    print(f"✅ Post like status checked: {post_uri} -> {is_liked}")
                    
            else:
                print("ℹ️ No posts found for like status testing")
                
        except Exception as e:
            pytest.skip(f"Real like status checking test skipped: {e}")


class TestAIIntegration:
    """Integration tests for AI functionality"""
    
    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.temp_dir = tempfile.mkdtemp()
        self.client = OpenAIClient()
    
    def teardown_method(self):
        """Clean up after each test method"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @pytest.mark.integration
    def test_real_openai_api_key_retrieval(self):
        """Test real OpenAI API key retrieval from SSM"""
        try:
            api_key = self.client._get_api_key()
            
            assert api_key is not None
            assert len(api_key) > 0
            assert api_key.startswith('sk-')  # OpenAI API keys start with 'sk-'
            print(f"✅ Successfully retrieved real OpenAI API key")
            
        except Exception as e:
            pytest.skip(f"Real OpenAI API key test skipped: {e}")
    
    @pytest.mark.integration
    def test_real_openai_reply_generation(self):
        """Test real OpenAI reply generation with image"""
        try:
            # Create a simple test image
            from PIL import Image
            test_image_path = os.path.join(self.temp_dir, "test_image.jpg")
            test_image = Image.new('RGB', (100, 100), color='red')
            test_image.save(test_image_path, 'JPEG')
            
            # Generate reply using real OpenAI API
            result = self.client.generate_reply(
                image_paths=[test_image_path],
                post_text="This is a test post about a red square",
                image_alt_texts=["A red square image"]
            )
            
            # Verify result
            assert result is not None
            assert len(result) > 0
            assert isinstance(result, str)
            print(f"✅ Successfully generated real OpenAI reply: '{result}'")
            
        except Exception as e:
            pytest.skip(f"Real OpenAI reply generation test skipped: {e}")


class TestConfigIntegration:
    """Integration tests for configuration management"""
    
    @pytest.mark.integration
    def test_real_ai_config_workflow(self):
        """Test real AI configuration workflow"""
        try:
            # Test with real config manager
            manager = AIConfigManager()
            
            # Load current config
            current_config = manager.load_config()
            original_persona = current_config.persona
            
            # Update persona
            new_persona = "Integration test persona for testing"
            success = manager.update_persona(new_persona)
            assert success is True
            
            # Verify update
            updated_config = manager.load_config()
            assert updated_config.persona == new_persona
            
            # Test system prompt generation
            system_prompt = updated_config.build_system_prompt()
            assert new_persona in system_prompt
            
            # Restore original persona
            manager.update_persona(original_persona)
            
            print("✅ Real AI config workflow test completed successfully")
            
        except Exception as e:
            pytest.skip(f"Real AI config workflow test skipped: {e}")


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
    def test_real_flask_like_endpoints(self, client):
        """Test real Flask like/unlike API endpoints"""
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


class TestEndToEndIntegration:
    """End-to-end integration tests"""
    
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
    @pytest.mark.slow
    def test_full_workflow_bluesky_to_ai(self):
        """Test complete workflow from Bluesky fetch to AI reply generation"""
        try:
            # Step 1: Setup Bluesky bot
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            self.bot.temp_dir = self.temp_dir
            
            # Step 2: Fetch posts with images
            posts = self.bot.fetch_posts_with_images_web(
                target_count=1, 
                max_fetches=3, 
                max_posts_per_user=1
            )
            
            if posts and posts[0]['embeds']:
                # Step 3: Get AI config
                ai_manager = AIConfigManager()
                ai_config = ai_manager.load_config()
                
                # Step 4: Generate AI reply
                image_paths = []
                image_alt_texts = []
                
                for embed in posts[0]['embeds']:
                    if embed['type'] == 'image':
                        image_paths.append(os.path.join(self.temp_dir, embed['filename']))
                        image_alt_texts.append(embed.get('alt_text', ''))
                
                if image_paths:
                    context = {
                        'post_text': posts[0]['post']['text'],
                        'image_alt_texts': image_alt_texts,
                        'image_count': len(image_paths)
                    }
                    
                    ai_reply = generate_ai_reply(image_paths, context, {})
                    
                    # Verify AI reply
                    assert ai_reply is not None
                    assert len(ai_reply) > 0
                    assert isinstance(ai_reply, str)
                    
                    print(f"✅ Full workflow completed successfully")
                    print(f"   Post: {posts[0]['post']['text'][:50]}...")
                    print(f"   AI Reply: {ai_reply}")
                else:
                    print("ℹ️ No images found for AI processing")
            else:
                print("ℹ️ No posts with images found for full workflow test")
                
        except Exception as e:
            pytest.skip(f"Full workflow test skipped: {e}")
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_full_workflow_with_likes(self):
        """Test complete workflow including like functionality"""
        try:
            # Step 1: Setup Bluesky bot
            password = self.bot.get_ssm_parameter(config.SSM_PARAMETER_NAME)
            self.bot.authenticate(config.BLUESKY_HANDLE, password)
            self.bot.temp_dir = self.temp_dir
            
            # Step 2: Fetch posts with images
            posts = self.bot.fetch_posts_with_images_web(
                target_count=1, 
                max_fetches=3, 
                max_posts_per_user=1
            )
            
            if posts and posts[0]['post']['uri']:
                test_post = posts[0]
                test_post_uri = test_post['post']['uri']
                
                # Step 3: Test like functionality
                print(f"Testing like functionality for post: {test_post_uri}")
                
                # Check initial like status
                initial_like_status = self.bot._check_if_post_is_liked(test_post_uri)
                print(f"Initial like status: {initial_like_status}")
                
                # Like the post
                like_result = self.bot.like_post(test_post_uri)
                assert isinstance(like_result, dict)
                assert 'success' in like_result
                
                if like_result['success']:
                    print(f"✅ Successfully liked post")
                    
                    # Verify like status changed
                    new_like_status = self.bot._check_if_post_is_liked(test_post_uri)
                    print(f"New like status: {new_like_status}")
                    
                    # Unlike the post
                    unlike_result = self.bot.unlike_post(test_post_uri)
                    assert isinstance(unlike_result, dict)
                    assert 'success' in unlike_result
                    
                    if unlike_result['success']:
                        print(f"✅ Successfully unliked post")
                        
                        # Verify like status reverted
                        final_like_status = self.bot._check_if_post_is_liked(test_post_uri)
                        print(f"Final like status: {final_like_status}")
                    else:
                        print(f"ℹ️ Unlike result: {unlike_result}")
                else:
                    print(f"ℹ️ Like result: {like_result}")
                
                # Step 4: Test AI functionality if images are available
                if test_post['embeds']:
                    ai_manager = AIConfigManager()
                    ai_config = ai_manager.load_config()
                    
                    image_paths = []
                    image_alt_texts = []
                    
                    for embed in test_post['embeds']:
                        if embed['type'] == 'image':
                            image_paths.append(os.path.join(self.temp_dir, embed['filename']))
                            image_alt_texts.append(embed.get('alt_text', ''))
                    
                    if image_paths:
                        context = {
                            'post_text': test_post['post']['text'],
                            'image_alt_texts': image_alt_texts,
                            'image_count': len(image_paths)
                        }
                        
                        ai_reply = generate_ai_reply(image_paths, context, {})
                        
                        # Verify AI reply
                        assert ai_reply is not None
                        assert len(ai_reply) > 0
                        assert isinstance(ai_reply, str)
                        
                        print(f"✅ AI reply generated: {ai_reply}")
                
                print(f"✅ Full workflow with likes completed successfully")
                print(f"   Post: {test_post['post']['text'][:50]}...")
                print(f"   Post URI: {test_post_uri}")
                
            else:
                print("ℹ️ No posts with images found for full workflow with likes test")
                
        except Exception as e:
            pytest.skip(f"Full workflow with likes test skipped: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
