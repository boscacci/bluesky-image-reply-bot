#!/usr/bin/env python3
"""
OpenAI GPT-4o integration for generating humorous, context-aware replies
using images and post text in a single call. Retrieves API key from AWS SSM
Parameter Store (parameter name: OPENAI_API_KEY_BSKY_BOT).
"""

import os
import base64
import logging
from typing import List, Dict, Any, Optional

import boto3
import requests

try:
    # Local import style
    from . import config
except ImportError:
    # Direct import when running without package context
    import config

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Small helper to call OpenAI's chat completions with vision (gpt-4o)."""

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

        # System/style prompt
        system_prompt = (
            style_instructions
            or "You are a witty social media persona. Given a Bluesky post (caption) and its images, write a short, funny, topical reply. Keep it under 220 characters unless absolutely necessary. Avoid hashtags unless they enhance the joke."
        )

        # User content: include text then images
        user_header = (
            "Bluesky post caption:\n" + (post_text or "") + "\n\n"
            + ("Accessibility alt texts:\n" + "\n".join(image_alt_texts or []) + "\n\n" if image_alt_texts else "")
            + f"There are {len(image_paths)} image(s). Analyze the images and the text together and craft one funny, hyper-relevant reply."
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
            "model": "gpt-4o",
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


_client_singleton: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = OpenAIClient()
    return _client_singleton


def generate_openai_ai_reply(image_paths: List[str], context: Dict[str, Any], theme_config: Dict[str, Any]) -> str:
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


