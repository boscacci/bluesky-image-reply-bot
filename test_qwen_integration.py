#!/usr/bin/env python3
"""
Test script for Qwen-VL integration
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from qwen_vl_integration import generate_qwen_response
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_qwen_integration():
    """Test the Qwen-VL integration with a sample image"""
    try:
        # Create a simple test image using PIL
        from PIL import Image, ImageDraw, ImageFont
        
        # Create a test image
        img = Image.new('RGB', (300, 200), color='lightblue')
        draw = ImageDraw.Draw(img)
        
        # Add some text to the image
        try:
            # Try to use a default font
            font = ImageFont.load_default()
        except:
            font = None
        
        draw.text((50, 80), "Test Image for Qwen-VL", fill='darkblue', font=font)
        draw.text((50, 100), "Magic Button Test", fill='darkblue', font=font)
        
        # Save the test image
        test_image_path = '/tmp/test_image.jpg'
        img.save(test_image_path)
        
        logger.info(f"Created test image: {test_image_path}")
        
        # Test the Qwen-VL response generation
        logger.info("Testing Qwen-VL response generation...")
        response = generate_qwen_response([test_image_path], "This is a test post with an image")
        
        logger.info(f"Generated response: {response}")
        
        # Clean up
        os.remove(test_image_path)
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Qwen-VL integration...")
    success = test_qwen_integration()
    if success:
        print("✅ Qwen-VL integration test passed!")
    else:
        print("❌ Qwen-VL integration test failed!")
        sys.exit(1)
