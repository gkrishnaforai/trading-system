"""
Unit test to verify configuration loading from .env file.
Tests both local execution and Docker container environment.
"""
import unittest
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import settings


class TestConfigLoading(unittest.TestCase):
    """Test that configuration values are loaded from .env file."""

    def test_database_url_loaded(self):
        """Test DATABASE_URL is loaded from .env."""
        # Should be Postgres URL from .env, not SQLite fallback
        self.assertIn("postgresql://", settings.database_url)
        self.assertIn("trading", settings.database_url)
        self.assertNotEqual(settings.database_url, "sqlite:///./db/trading.db")

    def test_massive_config_loaded(self):
        """Test Massive API configuration is loaded from .env."""
        # Check if MASSIVE_ENABLED is set (may be true or false)
        self.assertIsNotNone(settings.massive_enabled)
        self.assertIsInstance(settings.massive_enabled, bool)
        
        # Check if MASSIVE_API_KEY is loaded (may be None if not set)
        self.assertIsNotNone(settings.massive_api_key)
        # If API key is set, it should be a non-empty string
        if settings.massive_api_key:
            self.assertIsInstance(settings.massive_api_key, str)
            self.assertGreater(len(settings.massive_api_key), 0)

    def test_postgres_config_loaded(self):
        """Test Postgres connection parameters are loaded from .env."""
        # These should be loaded from environment variables via docker-compose
        self.assertIsNotNone(settings.database_url)
        
        # Verify Postgres connection string format
        if "postgresql://" in settings.database_url:
            self.assertIn("sslmode=disable", settings.database_url)
            self.assertIn("postgres:5432", settings.database_url)

    def test_redis_config_loaded(self):
        """Test Redis configuration is loaded."""
        self.assertIsNotNone(settings.redis_url)
        self.assertIn("redis://", settings.redis_url)

    def test_environment_detection(self):
        """Test environment variables are properly detected."""
        # Test that we're running in the expected environment
        self.assertIsNotNone(settings.environment)
        self.assertIn(settings.environment.lower(), ["development", "production", "test"])

    def test_config_source_detection(self):
        """Test we can detect if running in Docker vs local."""
        # Check if we're in Docker by looking for Docker indicators
        is_docker = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER')
        
        print(f"\n=== Configuration Loading Test ===")
        print(f"Running in Docker: {is_docker}")
        print(f"Environment: {settings.environment}")
        print(f"Database URL: {settings.database_url}")
        print(f"Massive Enabled: {settings.massive_enabled}")
        print(f"Massive API Key: {'SET' if settings.massive_api_key else 'NOT SET'}")
        print(f"Redis URL: {settings.redis_url}")
        print("=" * 40)

    def test_env_file_paths(self):
        """Test which .env files are being read."""
        # Check if .env files exist at expected locations
        local_env = Path(".env").exists()
        parent_env = Path("../.env").exists()
        
        print(f"\n=== .env File Detection ===")
        print(f"Local .env exists: {local_env}")
        print(f"Parent .env exists: {parent_env}")
        
        # At least one .env file should exist for proper configuration
        self.assertTrue(local_env or parent_env, 
                       "Neither local .env nor parent .env file found")


if __name__ == "__main__":
    unittest.main(verbosity=2)
