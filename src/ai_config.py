#!/usr/bin/env python3
"""
AI Configuration System
Handles AI persona, OpenAI integration, and configuration management
"""

import os
import base64
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

import boto3
import requests

try:
    from . import config
except ImportError:
    import config

logger = logging.getLogger(__name__)


@dataclass
class AIConfig:
    """Configuration for AI persona and behavior"""
    persona: str
    tone_do: str
    tone_dont: str
    location: str
    sample_reply_1: str
    sample_reply_2: str
    sample_reply_3: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AIConfig':
        """Create from dictionary"""
        return cls(**data)
    
    def build_system_prompt(self) -> str:
        """Build the complete system prompt from components"""
        prompt_parts = []
        
        # Persona
        if self.persona.strip():
            prompt_parts.append(f"PERSONA: {self.persona.strip()}")
        
        # Location context
        if self.location.strip():
            prompt_parts.append(f"LOCATION: {self.location.strip()}")
        
        # Tone guidelines
        tone_guidelines = []
        if self.tone_do.strip():
            tone_guidelines.append(f"DO: {self.tone_do.strip()}")
        if self.tone_dont.strip():
            tone_guidelines.append(f"DON'T: {self.tone_dont.strip()}")
        
        if tone_guidelines:
            prompt_parts.append(f"TONE GUIDELINES:\n" + "\n\n".join(tone_guidelines))
        
        # Sample replies for style reference
        sample_replies = []
        if self.sample_reply_1.strip():
            sample_replies.append(self.sample_reply_1.strip())
        if self.sample_reply_2.strip():
            sample_replies.append(self.sample_reply_2.strip())
        if self.sample_reply_3.strip():
            sample_replies.append(self.sample_reply_3.strip())
        
        if sample_replies:
            prompt_parts.append(f"WRITING STYLE REFERENCE: Here are some approved sample replies that demonstrate the desired tone and style:\n" + "\n\n".join(sample_replies))
        
        # Core instructions
        prompt_parts.append("TASK: Given a Bluesky post (caption) and its images, write a short, funny, topical reply. Keep it under 220 characters unless absolutely necessary. Avoid hashtags unless they enhance the joke.")
        
        return "\n\n".join(prompt_parts)
    
    def build_user_header(self, post_text: str, image_alt_texts: Optional[list] = None, image_count: int = 0) -> str:
        """Build the user header for the AI request"""
        header_parts = []
        
        # Post content
        if post_text:
            header_parts.append(f"Bluesky post caption: {post_text}")
        
        # Alt texts if available
        if image_alt_texts:
            header_parts.append("Accessibility alt texts:")
            header_parts.extend(image_alt_texts)
        
        # Image count and instruction
        header_parts.append(f"There are {image_count} image(s). Analyze the images and the text together and craft one funny, hyper-relevant reply.")
        
        return "\n\n".join(header_parts)


class AIConfigManager:
    """Manages AI configuration with file persistence"""
    
    def __init__(self, config_file: str = "ai_config.json"):
        self.config_file = config_file
        self._config: Optional[AIConfig] = None
    
    def _get_default_config(self) -> AIConfig:
        """Get default AI configuration from user_config.json or minimal defaults"""
        # Try to load from user_config.json in the project root
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            user_config_path = os.path.join(project_root, 'user_config.json')
            
            if os.path.exists(user_config_path):
                with open(user_config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    logger.info(f"Loaded user defaults from {user_config_path}")
                    return AIConfig(
                        persona=user_config.get('persona', 'You are a witty social media persona.'),
                        tone_do=user_config.get('tone_do', 'Be positive, engaging, and concise.'),
                        tone_dont=user_config.get('tone_dont', ''),
                        location=user_config.get('location', ''),
                        sample_reply_1=user_config.get('sample_reply_1', ''),
                        sample_reply_2=user_config.get('sample_reply_2', ''),
                        sample_reply_3=user_config.get('sample_reply_3', '')
                    )
        except Exception as e:
            logger.warning(f"Failed to load user config: {e}")
        
        # Fallback to minimal defaults
        return AIConfig(
            persona="You are a witty social media persona.",
            tone_do="Be positive, engaging, and concise.",
            tone_dont="",
            location="",
            sample_reply_1="",
            sample_reply_2="",
            sample_reply_3=""
        )
    
    def _get_config_file_path(self) -> str:
        """Get the full path to the config file"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, self.config_file)
    
    def load_config(self) -> AIConfig:
        """Load configuration from file or return defaults"""
        if self._config is not None:
            return self._config
        
        config_path = self._get_config_file_path()
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._config = AIConfig.from_dict(data)
                    logger.info(f"Loaded AI config from {config_path}")
            else:
                self._config = self._get_default_config()
                logger.info("Using default AI config")
        except Exception as e:
            logger.error(f"Failed to load AI config: {e}")
            self._config = self._get_default_config()
        
        return self._config
    
    def save_config(self, ai_config: AIConfig) -> bool:
        """Save configuration to file"""
        try:
            config_path = self._get_config_file_path()
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(ai_config.to_dict(), f, indent=2, ensure_ascii=False)
            
            self._config = ai_config
            logger.info(f"Saved AI config to {config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save AI config: {e}")
            return False
    
    def get_system_prompt(self) -> str:
        """Get the current system prompt"""
        config = self.load_config()
        return config.build_system_prompt()
    
    def get_user_header(self, post_text: str, image_alt_texts: Optional[list] = None, image_count: int = 0) -> str:
        """Get the formatted user header"""
        config = self.load_config()
        return config.build_user_header(post_text, image_alt_texts, image_count)
    
    def update_persona(self, new_persona: str) -> bool:
        """Update the persona"""
        config = self.load_config()
        config.persona = new_persona
        return self.save_config(config)
    
    def update_tone_do(self, new_tone_do: str) -> bool:
        """Update the tone DO guidelines"""
        config = self.load_config()
        config.tone_do = new_tone_do
        return self.save_config(config)
    
    def update_tone_dont(self, new_tone_dont: str) -> bool:
        """Update the tone DON'T guidelines"""
        config = self.load_config()
        config.tone_dont = new_tone_dont
        return self.save_config(config)
    
    def update_location(self, new_location: str) -> bool:
        """Update the location"""
        config = self.load_config()
        config.location = new_location
        return self.save_config(config)
    
    def update_sample_reply_1(self, new_sample: str) -> bool:
        """Update the first sample reply"""
        config = self.load_config()
        config.sample_reply_1 = new_sample
        return self.save_config(config)
    
    def update_sample_reply_2(self, new_sample: str) -> bool:
        """Update the second sample reply"""
        config = self.load_config()
        config.sample_reply_2 = new_sample
        return self.save_config(config)
    
    def update_sample_reply_3(self, new_sample: str) -> bool:
        """Update the third sample reply"""
        config = self.load_config()
        config.sample_reply_3 = new_sample
        return self.save_config(config)
    
    def reset_to_defaults(self) -> bool:
        """Reset configuration to defaults"""
        self._config = self._get_default_config()
        return self.save_config(self._config)
    
    def update_user_config(self, persona: str, tone_do: str, tone_dont: str, location: str, 
                          sample_reply_1: str, sample_reply_2: str, sample_reply_3: str) -> bool:
        """Update the user_config.json file with new defaults"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            user_config_path = os.path.join(project_root, 'user_config.json')
            
            user_config = {
                'persona': persona,
                'tone_do': tone_do,
                'tone_dont': tone_dont,
                'location': location,
                'sample_reply_1': sample_reply_1,
                'sample_reply_2': sample_reply_2,
                'sample_reply_3': sample_reply_3
            }
            
            with open(user_config_path, 'w', encoding='utf-8') as f:
                json.dump(user_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Updated user config at {user_config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to update user config: {e}")
            return False


class OpenAIClient:
    """OpenAI GPT-5 integration for generating humorous, context-aware replies"""

    def __init__(self, ssm_parameter_name: str = 'OPENAI_API_KEY_BSKY_BOT'):
        self.ssm_parameter_name = ssm_parameter_name
        self._openai_api_key: Optional[str] = None
        self._ssm = boto3.client('ssm', region_name=getattr(config, 'AWS_REGION', None))

    def _get_api_key(self) -> str:
        if self._openai_api_key:
            return self._openai_api_key
        try:
            response = self._ssm.get_parameter(Name=self.ssm_parameter_name, WithDecryption=True)
            self._openai_api_key = response['Parameter']['Value']
            return self._openai_api_key
        except Exception as e:
            logger.error(f"Failed to retrieve OpenAI API key from SSM '{self.ssm_parameter_name}': {e}")
            logger.info("Attempting to use environment variable fallback...")
            
            # Fallback to environment variable for CI/GitHub Actions
            env_value = os.getenv('OPENAI_API_KEY')
            if env_value:
                logger.info("Using OPENAI_API_KEY from environment variable")
                self._openai_api_key = env_value
                return self._openai_api_key
            
            # If no fallback available, raise the original exception
            raise

    def _encode_image_to_base64(self, image_path: str) -> str:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def generate_reply(
        self,
        image_paths: List[str],
        post_text: str,
        image_alt_texts: Optional[List[str]] = None,
        style_instructions: Optional[str] = None,
    ) -> str:
        """
        Send images and context to OpenAI GPT-4o and return a single humorous reply.
        """
        if not image_paths:
            return "No images provided."

        api_key = self._get_api_key()

        # Build the multimodal message
        content: List[Dict[str, Any]] = []

        # Get AI configuration
        config_manager = get_ai_config_manager()
        
        # System/style prompt - use custom style instructions if provided, otherwise use configured system prompt
        system_prompt = style_instructions or config_manager.get_system_prompt()

        # User content: use configured user header template
        user_header = config_manager.get_user_header(
            post_text=post_text or "",
            image_alt_texts=image_alt_texts,
            image_count=len(image_paths)
        )

        content.append({"type": "text", "text": user_header})

        for image_path in image_paths[:4]:  # limit to 4 images for payload size
            try:
                b64 = self._encode_image_to_base64(image_path)
                # Best effort to set mime based on extension
                ext = os.path.splitext(image_path)[1].lower()
                mime = 'image/jpeg'
                if ext in ['.png']:
                    mime = 'image/png'
                elif ext in ['.webp']:
                    mime = 'image/webp'
                # chat.completions expects image_url with data URL
                data_url = f"data:{mime};base64,{b64}"
                content.append({
                    "type": "image_url",
                    "image_url": {"url": data_url},
                })
            except Exception as e:
                logger.warning(f"Failed to encode image {image_path}: {e}")

        # Call OpenAI REST API directly to avoid extra deps
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            "model": "gpt-5",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.9,
            "max_tokens": 120,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=45)
            if resp.status_code >= 400:
                try:
                    logger.error(f"OpenAI error {resp.status_code}: {resp.text}")
                finally:
                    resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise


# Global instances
_config_manager: Optional[AIConfigManager] = None
_openai_client: Optional[OpenAIClient] = None


def get_ai_config_manager() -> AIConfigManager:
    """Get or create the global AI config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = AIConfigManager()
    return _config_manager


def get_openai_client() -> OpenAIClient:
    """Get or create the global OpenAI client instance"""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client


def generate_ai_reply(image_paths: List[str], context: Dict[str, Any], theme_config: Dict[str, Any]) -> str:
    """
    Adapter used by the Flask endpoint, mirroring the staged pipeline signature.
    Ignores theme_config for now, but accepts it for compatibility.
    """
    client = get_openai_client()
    post_text = context.get('post_text', '') if context else ''
    image_alt_texts = context.get('image_alt_texts', []) if context else []

    style = None
    if theme_config and isinstance(theme_config, dict):
        # Allow optional style hint
        style = theme_config.get('style_instructions')

    return client.generate_reply(
        image_paths=image_paths,
        post_text=post_text,
        image_alt_texts=image_alt_texts,
        style_instructions=style,
    )


# Convenience functions for backward compatibility
def get_system_prompt() -> str:
    """Get the current system prompt"""
    manager = get_ai_config_manager()
    return manager.get_system_prompt()


def get_user_header(post_text: str, image_alt_texts: Optional[list] = None, image_count: int = 0) -> str:
    """Get the formatted user header"""
    manager = get_ai_config_manager()
    return manager.get_user_header(post_text, image_alt_texts, image_count)


def update_persona(new_persona: str) -> bool:
    """Update the persona"""
    manager = get_ai_config_manager()
    return manager.update_persona(new_persona)


def update_tone_do(new_tone_do: str) -> bool:
    """Update the tone DO guidelines"""
    manager = get_ai_config_manager()
    return manager.update_tone_do(new_tone_do)


def update_tone_dont(new_tone_dont: str) -> bool:
    """Update the tone DON'T guidelines"""
    manager = get_ai_config_manager()
    return manager.update_tone_dont(new_tone_dont)


def update_location(new_location: str) -> bool:
    """Update the location"""
    manager = get_ai_config_manager()
    return manager.update_location(new_location)


def update_sample_replies(new_samples: str) -> bool:
    """Update the sample replies"""
    manager = get_ai_config_manager()
    return manager.update_sample_replies(new_samples)


def reset_ai_config() -> bool:
    """Reset AI configuration to defaults"""
    manager = get_ai_config_manager()
    return manager.reset_to_defaults()


def update_user_config(persona: str, tone_guidelines: str, location: str, sample_replies: str) -> bool:
    """Update the user_config.json file with new defaults"""
    manager = get_ai_config_manager()
    return manager.update_user_config(persona, tone_guidelines, location, sample_replies)
