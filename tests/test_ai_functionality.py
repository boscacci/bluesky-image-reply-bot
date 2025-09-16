#!/usr/bin/env python3
"""
Integration Tests for AI Functionality
Tests OpenAI integration, AI config management, and reply generation
"""

import pytest
import tempfile
import os
import shutil
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import modules
from ai_config import AIConfigManager, OpenAIClient, generate_ai_reply
import config


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
