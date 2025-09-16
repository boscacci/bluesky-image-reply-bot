#!/usr/bin/env python3
"""
Qwen-VL Model Integration for Magic Button Responses
"""

import os
import logging
import torch
from PIL import Image
from transformers import Qwen2VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from typing import List, Optional
import gc

logger = logging.getLogger(__name__)

class QwenVLModel:
    """Qwen-VL model wrapper for generating witty responses to images"""
    
    def __init__(self, model_name: str = "Qwen/Qwen2-VL-7B-Instruct"):
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.processor = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_loaded = False
        
        logger.info(f"Initializing Qwen-VL model on device: {self.device}")
    
    def load_model(self):
        """Load the Qwen-VL model and tokenizer"""
        try:
            if self.is_loaded:
                logger.info("Model already loaded")
                return True
                
            logger.info(f"Loading Qwen-VL model: {self.model_name}")
            
            # Load tokenizer and processor
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )
            
            self.processor = AutoProcessor.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )
            
            # Load model with appropriate device and memory optimization
            if self.device == "cuda":
                # Use 4-bit quantization to reduce memory usage
                self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float16,
                    device_map="auto",
                    trust_remote_code=True,
                    load_in_4bit=True
                )
            else:
                # CPU fallback
                self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float32,
                    trust_remote_code=True
                )
                self.model.to(self.device)
            
            self.is_loaded = True
            logger.info("Qwen-VL model loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load Qwen-VL model: {e}")
            return False
    
    def unload_model(self):
        """Unload the model to free memory"""
        try:
            if self.model is not None:
                del self.model
                self.model = None
            
            if self.tokenizer is not None:
                del self.tokenizer
                self.tokenizer = None
                
            if self.processor is not None:
                del self.processor
                self.processor = None
            
            # Clear CUDA cache if available
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            gc.collect()
            self.is_loaded = False
            logger.info("Qwen-VL model unloaded successfully")
            
        except Exception as e:
            logger.error(f"Error unloading model: {e}")
    
    def generate_response(self, image_paths: List[str], context: dict = None) -> str:
        """
        Generate a smart reply to images using Qwen-VL with enhanced context
        
        Args:
            image_paths: List of paths to images
            context: Dictionary containing post_text, image_alt_texts, and image_count
            
        Returns:
            Generated smart reply
        """
        try:
            if not self.is_loaded:
                if not self.load_model():
                    return self._get_fallback_response()
            
            # Prepare the prompt for smart, context-aware response
            prompt = self._create_enhanced_prompt(context)
            
            # Load and prepare images
            images = []
            for image_path in image_paths:
                try:
                    image = Image.open(image_path).convert('RGB')
                    images.append(image)
                except Exception as e:
                    logger.warning(f"Failed to load image {image_path}: {e}")
                    continue
            
            if not images:
                logger.warning("No valid images found")
                return self._get_fallback_response()
            
            # Prepare the conversation format
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": images[0]},  # Use first image
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
            
            # Process the conversation
            text = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            
            # Tokenize
            image_inputs, video_inputs = self.processor(
                text=[text], images=images, return_tensors="pt"
            )
            
            # Move to device
            image_inputs = {k: v.to(self.device) for k, v in image_inputs.items()}
            
            # Generate response
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **image_inputs,
                    max_new_tokens=150,
                    do_sample=True,
                    temperature=0.7,
                    top_p=0.8,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            # Decode response
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(image_inputs.input_ids, generated_ids)
            ]
            
            response = self.tokenizer.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]
            
            # Clean up the response
            response = self._clean_response(response)
            
            logger.info(f"Generated Qwen-VL response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error generating Qwen-VL response: {e}")
            return self._get_fallback_response()
    
    def _create_enhanced_prompt(self, context: dict = None) -> str:
        """Create an enhanced prompt for generating smart replies with full context"""
        if context is None:
            context = {}
        
        post_text = context.get('post_text', '')
        image_alt_texts = context.get('image_alt_texts', [])
        image_count = context.get('image_count', 1)
        
        base_prompt = """Look at this image and generate a smart, engaging reply that would be perfect for a social media comment. 

Requirements:
- Be creative, witty, and positive
- Keep it concise (1-2 sentences)
- Make it feel natural and conversational
- Focus on what's interesting, beautiful, or fun about the image
- Use emojis appropriately
- Be encouraging and engaging
- Consider the context of the original post

Generate a response that would make someone smile and want to engage with the content."""
        
        # Add post context if available
        if post_text:
            base_prompt += f"\n\nOriginal Post Context: '{post_text}'"
        
        # Add accessibility context if available
        if image_alt_texts and any(alt_text.strip() for alt_text in image_alt_texts):
            alt_text_context = [alt for alt in image_alt_texts if alt.strip()]
            if alt_text_context:
                base_prompt += f"\n\nImage Descriptions: {', '.join(alt_text_context)}"
        
        # Add image count context
        if image_count > 1:
            base_prompt += f"\n\nNote: This post contains {image_count} images. Consider all of them in your response."
        
        return base_prompt
    
    def _clean_response(self, response: str) -> str:
        """Clean and format the generated response"""
        # Remove any unwanted prefixes or suffixes
        response = response.strip()
        
        # Remove common model artifacts
        unwanted_phrases = [
            "Here's a witty response:",
            "Here's a response:",
            "Response:",
            "Here's what I think:",
            "I think this is:",
        ]
        
        for phrase in unwanted_phrases:
            if response.lower().startswith(phrase.lower()):
                response = response[len(phrase):].strip()
        
        # Ensure it's not too long
        if len(response) > 200:
            # Try to find a good stopping point
            sentences = response.split('. ')
            if len(sentences) > 1:
                response = '. '.join(sentences[:2])
                if not response.endswith('.'):
                    response += '.'
        
        return response
    
    def _get_fallback_response(self) -> str:
        """Get a fallback response when the model fails"""
        fallback_responses = [
            "These images are absolutely stunning! The composition and colors are giving me serious art gallery vibes ✨",
            "Wow, this is pure visual poetry! I'm getting major inspiration from these beautiful shots 📸",
            "This is the kind of content that makes me want to grab my camera and start exploring! Absolutely gorgeous! 🌟",
            "The creativity in these images is off the charts! This is exactly the kind of visual storytelling I love to see 🎨",
            "These photos are like a breath of fresh air! The attention to detail is incredible 👏",
            "I'm getting serious wanderlust vibes from these images! The world is such a beautiful place 🌍",
            "This is pure visual magic! The way these images capture the moment is absolutely perfect ✨",
            "These shots are giving me all the feels! The composition and lighting are just chef's kiss 👌"
        ]
        
        import random
        return random.choice(fallback_responses)

# Global model instance
_qwen_model = None

def get_qwen_model() -> QwenVLModel:
    """Get or create the global Qwen-VL model instance"""
    global _qwen_model
    if _qwen_model is None:
        _qwen_model = QwenVLModel()
    return _qwen_model

def generate_qwen_response(image_paths: List[str], context: dict = None) -> str:
    """
    Generate a smart reply using Qwen-VL model with enhanced context
    
    Args:
        image_paths: List of paths to images
        context: Dictionary containing post_text, image_alt_texts, and image_count
        
    Returns:
        Generated smart reply
    """
    model = get_qwen_model()
    return model.generate_response(image_paths, context)
