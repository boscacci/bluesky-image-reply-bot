#!/usr/bin/env python3
"""
Modular Theme Configuration System
Handles theme, tone, and style configuration with both predefined and custom options
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class ThemeConfig:
    """Configuration for AI reply themes"""
    theme: str
    tone: str
    style: str
    custom_theme: Optional[str] = None
    custom_tone: Optional[str] = None
    custom_style: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThemeConfig':
        """Create from dictionary"""
        return cls(**data)
    
    def get_effective_theme(self) -> str:
        """Get the effective theme (custom if provided, otherwise predefined)"""
        return self.custom_theme if self.custom_theme else self.theme
    
    def get_effective_tone(self) -> str:
        """Get the effective tone (custom if provided, otherwise predefined)"""
        return self.custom_tone if self.custom_tone else self.tone
    
    def get_effective_style(self) -> str:
        """Get the effective style (custom if provided, otherwise predefined)"""
        return self.custom_style if self.custom_style else self.style

class ThemeManager:
    """Manages theme configurations and provides theme-specific content"""
    
    def __init__(self):
        self.predefined_themes = self._load_predefined_themes()
        self.predefined_tones = self._load_predefined_tones()
        self.predefined_styles = self._load_predefined_styles()
    
    def _load_predefined_themes(self) -> Dict[str, Dict[str, Any]]:
        """Load predefined theme configurations"""
        return {
            'cycling': {
                'name': 'Cycling & Accessibility',
                'emoji': '🚲',
                'description': 'Cycling and accessibility advocacy',
                'persona': 'You are a passionate cycling advocate and accessibility champion.',
                'focus_areas': 'cycling as sustainable, healthy, and joyful transportation, accessible infrastructure for all users, safe cycling infrastructure, accessibility features, sustainable transportation, community building, urban planning, and the joy of cycling.',
                'emojis': 'bike, accessibility, urban planning related',
                'keywords': ['cycling', 'bike', 'bicycle', 'bike lane', 'cycling infrastructure', 'bike parking', 'accessibility', 'accessible', 'wheelchair', 'mobility', 'inclusive design']
            },
            'environment': {
                'name': 'Environment & Sustainability',
                'emoji': '🌱',
                'description': 'Environmental sustainability and climate action',
                'persona': 'You are an environmental advocate focused on sustainability and climate action.',
                'focus_areas': 'environmental protection, sustainability, climate action, renewable energy, conservation, green living, and protecting our planet for future generations.',
                'emojis': 'environment, nature, sustainability related',
                'keywords': ['environment', 'sustainability', 'climate', 'green', 'renewable', 'conservation', 'carbon', 'emissions', 'eco-friendly', 'sustainable']
            },
            'technology': {
                'name': 'Technology & Innovation',
                'emoji': '💻',
                'description': 'Technology innovation and digital progress',
                'persona': 'You are a technology enthusiast who loves innovation and digital progress.',
                'focus_areas': 'technology innovation, digital transformation, AI, automation, connectivity, and how technology can improve our lives and society.',
                'emojis': 'technology, innovation, digital related',
                'keywords': ['technology', 'innovation', 'digital', 'AI', 'automation', 'connectivity', 'software', 'hardware', 'tech', 'digital transformation']
            },
            'community': {
                'name': 'Community & Engagement',
                'emoji': '🤝',
                'description': 'Community building and local engagement',
                'persona': 'You are a community builder who values connection and local engagement.',
                'focus_areas': 'community building, local engagement, social connection, neighborhood development, and bringing people together.',
                'emojis': 'community, people, connection related',
                'keywords': ['community', 'local', 'engagement', 'neighborhood', 'social', 'connection', 'civic', 'volunteer', 'grassroots', 'collective']
            }
        }
    
    def _load_predefined_tones(self) -> Dict[str, Dict[str, Any]]:
        """Load predefined tone configurations"""
        return {
            'enthusiastic': {
                'name': 'Enthusiastic & Energetic',
                'emoji': '😊',
                'description': 'Positive, energetic, and inspiring',
                'characteristics': 'enthusiastic, energetic, and inspiring',
                'keywords': ['amazing', 'awesome', 'great', 'love', 'beautiful', 'wonderful', 'fantastic', 'incredible', 'exciting', 'brilliant']
            },
            'professional': {
                'name': 'Professional & Informative',
                'emoji': '💼',
                'description': 'Professional, informative, and well-reasoned',
                'characteristics': 'professional, informative, and well-reasoned',
                'keywords': ['demonstrates', 'effective', 'implementation', 'strategic', 'comprehensive', 'systematic', 'methodical', 'analytical', 'evidence-based', 'thorough']
            },
            'casual': {
                'name': 'Casual & Friendly',
                'emoji': '😎',
                'description': 'Casual, friendly, and approachable',
                'characteristics': 'casual, friendly, and approachable',
                'keywords': ['nice', 'cool', 'awesome', 'love', 'like', 'great', 'good', 'solid', 'decent', 'pretty good']
            },
            'humorous': {
                'name': 'Light-hearted & Witty',
                'emoji': '😄',
                'description': 'Light-hearted, witty, and engaging',
                'characteristics': 'light-hearted, witty, and engaging',
                'keywords': ['hilarious', 'funny', 'witty', 'clever', 'amusing', 'entertaining', 'charming', 'delightful', 'playful', 'humorous']
            }
        }
    
    def _load_predefined_styles(self) -> Dict[str, Dict[str, Any]]:
        """Load predefined style configurations"""
        return {
            'conversational': {
                'name': 'Conversational & Natural',
                'emoji': '💬',
                'description': 'Natural and conversational',
                'characteristics': 'natural and conversational',
                'length': 'medium',
                'formality': 'informal'
            },
            'formal': {
                'name': 'Formal & Polished',
                'emoji': '📝',
                'description': 'Polished and articulate',
                'characteristics': 'polished and articulate',
                'length': 'longer',
                'formality': 'formal'
            },
            'brief': {
                'name': 'Brief & Concise',
                'emoji': '⚡',
                'description': 'Concise and to the point',
                'length': 'short',
                'formality': 'neutral'
            }
        }
    
    def get_available_themes(self) -> Dict[str, Dict[str, Any]]:
        """Get all available predefined themes"""
        return self.predefined_themes.copy()
    
    def get_available_tones(self) -> Dict[str, Dict[str, Any]]:
        """Get all available predefined tones"""
        return self.predefined_tones.copy()
    
    def get_available_styles(self) -> Dict[str, Dict[str, Any]]:
        """Get all available predefined styles"""
        return self.predefined_styles.copy()
    
    def get_theme_info(self, theme_key: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific theme"""
        return self.predefined_themes.get(theme_key)
    
    def get_tone_info(self, tone_key: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific tone"""
        return self.predefined_tones.get(tone_key)
    
    def get_style_info(self, style_key: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific style"""
        return self.predefined_styles.get(style_key)
    
    def create_prompt(self, config: ThemeConfig, caption: str, post_text: str) -> str:
        """Create a themed prompt based on configuration"""
        effective_theme = config.get_effective_theme()
        effective_tone = config.get_effective_tone()
        effective_style = config.get_effective_style()
        
        # Get theme info (use custom or predefined)
        if config.custom_theme:
            theme_info = {
                'persona': f'You are {config.custom_theme}.',
                'focus_areas': config.custom_theme,
                'emojis': 'relevant to your theme'
            }
        else:
            theme_info = self.get_theme_info(effective_theme) or self.get_theme_info('cycling')
        
        # Get tone info (use custom or predefined)
        if config.custom_tone:
            tone_info = {
                'characteristics': config.custom_tone
            }
        else:
            tone_info = self.get_tone_info(effective_tone) or self.get_tone_info('enthusiastic')
        
        # Get style info (use custom or predefined)
        if config.custom_style:
            style_info = {
                'characteristics': config.custom_style
            }
        else:
            style_info = self.get_style_info(effective_style) or self.get_style_info('conversational')
        
        # Create messages in the format expected by TinyLlama
        messages = [
            {
                'role': 'system',
                'content': theme_info['persona']
            },
            {
                'role': 'user', 
                'content': f"""Someone posted an image with the caption: "{post_text}"
The image shows: {caption}

Write a short, engaging reply (1-2 sentences) that:
- Celebrates {theme_info['focus_areas']}
- Connects what's in the image to {effective_theme} themes
- Uses appropriate emojis ({theme_info['emojis']})
- Feels {style_info['characteristics']}
- Is {tone_info['characteristics']}
- Is positive, encouraging, and community-focused

Write a response that would inspire others to support {effective_theme} initiatives."""
            }
        ]
        
        return messages
    
    def get_fallback_response(self, config: ThemeConfig) -> str:
        """Get a themed fallback response"""
        import random
        
        effective_theme = config.get_effective_theme()
        
        # Custom theme fallbacks
        if config.custom_theme:
            return f"This is exactly the kind of {config.custom_theme} content we need! Keep sharing these inspiring examples 🌟"
        
        # Predefined theme fallbacks
        fallbacks = {
            'cycling': [
                "This is exactly the kind of infrastructure we need more of! Safe cycling and accessible design benefit everyone in our community 🚲♿",
                "Love seeing cycling and accessibility features working together! This is how we build truly inclusive cities 🌟",
                "Beautiful example of sustainable transportation infrastructure! Every city should prioritize safe cycling and accessibility 🚴‍♀️",
                "This is what progressive urban planning looks like! Cycling and accessibility go hand in hand for better communities 🏙️",
                "Amazing to see cycling infrastructure that considers everyone's needs! This is the future of transportation 🚲✨"
            ],
            'environment': [
                "This is exactly the kind of environmental progress we need! Every step toward sustainability makes a difference 🌱",
                "Love seeing environmental initiatives in action! This is how we protect our planet for future generations 🌍",
                "Beautiful example of environmental stewardship! These efforts inspire hope for a greener future 🌿",
                "This is what environmental leadership looks like! Small actions create big change 🌎",
                "Amazing to see environmental consciousness in practice! This is how we build a sustainable future 🌱✨"
            ],
            'technology': [
                "This is exactly the kind of innovation we need! Technology that makes life better for everyone 💻",
                "Love seeing technology used for good! This is how we build a better digital future 🚀",
                "Beautiful example of technological progress! Innovation that serves the community 💡",
                "This is what tech leadership looks like! Solutions that actually help people 🤖",
                "Amazing to see technology making a real difference! This is the future we want to build 💻✨"
            ],
            'community': [
                "This is exactly the kind of community spirit we need! Connection and support make neighborhoods stronger 🤝",
                "Love seeing community initiatives in action! This is how we build better neighborhoods together 🏘️",
                "Beautiful example of community building! These efforts bring people together 🌟",
                "This is what community leadership looks like! People supporting people 🏠",
                "Amazing to see community connections in action! This is how we build stronger neighborhoods 🤝✨"
            ]
        }
        
        theme_responses = fallbacks.get(effective_theme, fallbacks['cycling'])
        return random.choice(theme_responses)
    
    def validate_config(self, config: ThemeConfig) -> List[str]:
        """Validate a theme configuration and return any issues"""
        issues = []
        
        # Check if theme is valid (either predefined or custom)
        if not config.custom_theme and config.theme not in self.predefined_themes:
            issues.append(f"Invalid theme: {config.theme}")
        
        # Check if tone is valid (either predefined or custom)
        if not config.custom_tone and config.tone not in self.predefined_tones:
            issues.append(f"Invalid tone: {config.tone}")
        
        # Check if style is valid (either predefined or custom)
        if not config.custom_style and config.style not in self.predefined_styles:
            issues.append(f"Invalid style: {config.style}")
        
        return issues
    
    def get_default_config(self) -> ThemeConfig:
        """Get the default theme configuration"""
        return ThemeConfig(
            theme='cycling',
            tone='enthusiastic',
            style='conversational'
        )

# Global theme manager instance
_theme_manager = None

def get_theme_manager() -> ThemeManager:
    """Get or create the global theme manager instance"""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager

def create_theme_config(theme: str = 'cycling', tone: str = 'enthusiastic', style: str = 'conversational',
                       custom_theme: Optional[str] = None, custom_tone: Optional[str] = None, 
                       custom_style: Optional[str] = None) -> ThemeConfig:
    """Create a theme configuration"""
    return ThemeConfig(
        theme=theme,
        tone=tone,
        style=style,
        custom_theme=custom_theme,
        custom_tone=custom_tone,
        custom_style=custom_style
    )

def get_available_themes() -> Dict[str, Dict[str, Any]]:
    """Get available theme configurations"""
    manager = get_theme_manager()
    return manager.get_available_themes()
