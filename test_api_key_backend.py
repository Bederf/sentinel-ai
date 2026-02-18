#!/usr/bin/env python3
"""Test API key from backend directory"""

import os
os.chdir('/opt/bms-intelligence/backend')

from app.config.settings import settings

print("Testing API Key from Backend Directory:")
print("=" * 50)
print(f"Current directory: {os.getcwd()}")
print(f".env file exists: {os.path.exists('.env')}")

api_key = settings.anthropic_api_key
print(f"API Key present: {bool(api_key)}")
print(f"API Key length: {len(api_key) if api_key else 0}")

if api_key:
    print(f"Starts with 'sk-ant-': {api_key.startswith('sk-ant-')}")
    print(f"Contains API version: {'api03' in api_key}")
    print(f"First 20 chars: {api_key[:20]}...")
    print(f"Last 10 chars: ...{api_key[-10:]}")
else:
    print("No API key loaded from .env!")

# Also test direct loading
from pydantic_settings import BaseSettings

class TestSettings(BaseSettings):
    anthropic_api_key: str = ""
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

test_settings = TestSettings()
print(f"\nDirect test - API Key: {bool(test_settings.anthropic_api_key)}")
print(f"Same as settings: {test_settings.anthropic_api_key == api_key}")
