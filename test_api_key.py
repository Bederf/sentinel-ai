#!/usr/bin/env python3
"""Test if the API key is being loaded correctly"""

import sys
sys.path.insert(0, '/opt/bms-intelligence/backend')

from app.config.settings import settings

print("Testing API Key Configuration:")
print("=" * 50)

# Check if API key exists
api_key = settings.anthropic_api_key
print(f"API Key present: {bool(api_key)}")
print(f"API Key length: {len(api_key) if api_key else 0}")

if api_key:
    # Check key format (without exposing it)
    print(f"Starts with 'sk-ant-': {api_key.startswith('sk-ant-')}")
    print(f"Contains API version: {'api03' in api_key}")
else:
    print("No API key found!")

print("\nOther settings:")
print(f"Claude Model: {settings.claude_model}")
print(f"Demo Mode: {settings.demo_mode}")

# Test loading from environment directly
import os
print(f"\nDirect environment check:")
print(f"ANTHROPIC_API_KEY in env: {'ANTHROPIC_API_KEY' in os.environ}")
if 'ANTHROPIC_API_KEY' in os.environ:
    env_key = os.environ['ANTHROPIC_API_KEY']
    print(f"Env key length: {len(env_key)}")
    print(f"Same as settings: {env_key == api_key}")
