#!/usr/bin/env python3
"""
Test script to show how configuration is being read
Run this to debug configuration issues
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings

print("=" * 80)
print("CONFIGURATION READING TEST")
print("=" * 80)
print()

# Show raw environment variables
print("📋 Raw Environment Variables:")
print(f"  MASSIVE_ENABLED (env): {os.getenv('MASSIVE_ENABLED', 'NOT SET')}")
print(f"  MASSIVE_API_KEY (env): {'SET' if os.getenv('MASSIVE_API_KEY') else 'NOT SET'} (length: {len(os.getenv('MASSIVE_API_KEY', ''))})")
print(f"  PRIMARY_DATA_PROVIDER (env): {os.getenv('PRIMARY_DATA_PROVIDER', 'NOT SET')}")
print(f"  FALLBACK_DATA_PROVIDER (env): {os.getenv('FALLBACK_DATA_PROVIDER', 'NOT SET')}")
print(f"  DEFAULT_DATA_PROVIDER (env): {os.getenv('DEFAULT_DATA_PROVIDER', 'NOT SET')}")
print()

# Show parsed settings
print("⚙️  Parsed Settings (from pydantic-settings):")
print(f"  settings.massive_enabled: {settings.massive_enabled} (type: {type(settings.massive_enabled)})")
print(f"  settings.massive_api_key: {'SET' if settings.massive_api_key else 'NOT SET'} (length: {len(settings.massive_api_key) if settings.massive_api_key else 0})")
print(f"  settings.primary_data_provider: {settings.primary_data_provider}")
print(f"  settings.fallback_data_provider: {settings.fallback_data_provider}")
print(f"  settings.default_data_provider: {settings.default_data_provider}")
print()

# Check .env file location
env_file = Path(".env")
if env_file.exists():
    print(f"✅ .env file found at: {env_file.absolute()}")
    print(f"   File size: {env_file.stat().st_size} bytes")
    
    # Try to read MASSIVE_ENABLED from .env
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('MASSIVE_ENABLED'):
                print(f"   Found in .env: {line}")
            elif line.startswith('MASSIVE_API_KEY'):
                key_val = line.split('=', 1)[1] if '=' in line else ''
                print(f"   Found in .env: MASSIVE_API_KEY={'SET' if key_val else 'NOT SET'} (length: {len(key_val)})")
else:
    print(f"❌ .env file NOT found at: {env_file.absolute()}")
    print(f"   Current working directory: {os.getcwd()}")
    print(f"   Looking for .env in: {Path.cwd()}")
print()

# Show data source configuration
print("🔌 Data Source Configuration:")
from app.data_sources import PRIMARY_DATA_SOURCE, FALLBACK_DATA_SOURCE, DATA_SOURCES
print(f"  PRIMARY_DATA_SOURCE: {PRIMARY_DATA_SOURCE}")
print(f"  FALLBACK_DATA_SOURCE: {FALLBACK_DATA_SOURCE}")
print(f"  Available sources: {list(DATA_SOURCES.keys())}")
print()

# Test data source creation
print("🧪 Testing Data Source Creation:")
try:
    from app.data_sources import get_data_source
    source = get_data_source()
    print(f"  ✅ Created data source: {source.name}")
    if hasattr(source, 'primary_source'):
        print(f"     Primary: {source.primary_source.name}")
    if hasattr(source, 'fallback_source') and source.fallback_source:
        print(f"     Fallback: {source.fallback_source.name}")
except Exception as e:
    print(f"  ❌ Failed to create data source: {e}")
    import traceback
    traceback.print_exc()
print()

print("=" * 80)

