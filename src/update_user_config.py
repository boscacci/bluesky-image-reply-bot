#!/usr/bin/env python3
"""
Simple script to update the user_config.json file
"""

import json
import os
import sys

def update_user_config():
    """Interactive script to update user config"""
    # Go up one directory to find user_config.json in project root
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, 'user_config.json')
    
    print("🤖 AI Persona Configuration Updater")
    print("=" * 50)
    
    # Load existing config if it exists
    existing_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
            print("📁 Loaded existing configuration")
        except Exception as e:
            print(f"⚠️  Could not load existing config: {e}")
    
    print("\nEnter new values (press Enter to keep existing value):")
    print("-" * 50)
    
    # Get persona
    current_persona = existing_config.get('persona', '')
    print(f"\n🤖 AI Persona (current: {current_persona[:50]}...)")
    persona = input("New persona: ").strip()
    if not persona:
        persona = current_persona
    
    # Get location
    current_location = existing_config.get('location', '')
    print(f"\n📍 Location & Context (current: {current_location[:50]}...)")
    location = input("New location: ").strip()
    if not location:
        location = current_location
    
    # Get tone DO guidelines
    current_tone_do = existing_config.get('tone_do', '')
    print(f"\n✅ Tone DO Guidelines (current: {current_tone_do[:50]}...)")
    tone_do = input("New tone DO guidelines: ").strip()
    if not tone_do:
        tone_do = current_tone_do
    
    # Get tone DON'T guidelines
    current_tone_dont = existing_config.get('tone_dont', '')
    print(f"\n❌ Tone DON'T Guidelines (current: {current_tone_dont[:50]}...)")
    tone_dont = input("New tone DON'T guidelines: ").strip()
    if not tone_dont:
        tone_dont = current_tone_dont
    
    # Get sample replies
    current_sample_1 = existing_config.get('sample_reply_1', '')
    print(f"\n📝 Sample Reply 1 (current: {current_sample_1[:50]}...)")
    sample_reply_1 = input("New sample reply 1: ").strip()
    if not sample_reply_1:
        sample_reply_1 = current_sample_1
    
    current_sample_2 = existing_config.get('sample_reply_2', '')
    print(f"\n📝 Sample Reply 2 (current: {current_sample_2[:50]}...)")
    sample_reply_2 = input("New sample reply 2: ").strip()
    if not sample_reply_2:
        sample_reply_2 = current_sample_2
    
    current_sample_3 = existing_config.get('sample_reply_3', '')
    print(f"\n📝 Sample Reply 3 (current: {current_sample_3[:50]}...)")
    sample_reply_3 = input("New sample reply 3: ").strip()
    if not sample_reply_3:
        sample_reply_3 = current_sample_3
    
    # Save the config
    config = {
        'persona': persona,
        'tone_do': tone_do,
        'tone_dont': tone_dont,
        'location': location,
        'sample_reply_1': sample_reply_1,
        'sample_reply_2': sample_reply_2,
        'sample_reply_3': sample_reply_3
    }
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Configuration saved to {config_path}")
        print("🔄 The next time you start the app, these will be the default values!")
    except Exception as e:
        print(f"\n❌ Error saving config: {e}")
        return False
    
    return True

if __name__ == '__main__':
    update_user_config()
