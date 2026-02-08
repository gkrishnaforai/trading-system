"""
Cache Manager for FMP Data
Provides caching functionality with TTL support
"""
import time
import json
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import hashlib
import logging

from app.observability.logging import get_logger

logger = get_logger("cache_manager")


class CacheManager:
    """Simple in-memory cache manager with TTL support"""
    
    def __init__(self, prefix: str = "cache"):
        self.prefix = prefix
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.logger = get_logger(f"cache_{prefix}")
        
    def _generate_key(self, key: str) -> str:
        """Generate a cache key with prefix"""
        return f"{self.prefix}:{key}"
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """
        Set a cache value with TTL
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._generate_key(key)
            expiry_time = time.time() + ttl
            
            self._cache[cache_key] = {
                "value": value,
                "expiry": expiry_time,
                "created_at": time.time()
            }
            
            self.logger.debug(f"✅ Cached key: {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error setting cache for key {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get a cache value
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        try:
            cache_key = self._generate_key(key)
            
            if cache_key not in self._cache:
                return None
            
            cache_item = self._cache[cache_key]
            
            # Check if expired
            if time.time() > cache_item["expiry"]:
                del self._cache[cache_key]
                self.logger.debug(f"🕐 Cache expired for key: {key}")
                return None
            
            self.logger.debug(f"🎯 Cache hit for key: {key}")
            return cache_item["value"]
            
        except Exception as e:
            self.logger.error(f"❌ Error getting cache for key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """
        Delete a cache key
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted, False if not found
        """
        try:
            cache_key = self._generate_key(key)
            
            if cache_key in self._cache:
                del self._cache[cache_key]
                self.logger.debug(f"🗑️ Deleted cache key: {key}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"❌ Error deleting cache for key {key}: {e}")
            return False
    
    def clear(self, pattern: str = None) -> int:
        """
        Clear cache keys
        
        Args:
            pattern: Optional pattern to match (e.g., "price:*")
            
        Returns:
            Number of keys cleared
        """
        try:
            keys_to_delete = []
            
            if pattern:
                # Find keys matching pattern
                for cache_key in self._cache.keys():
                    if pattern.replace(f"{self.prefix}:", "") in cache_key:
                        keys_to_delete.append(cache_key)
            else:
                # Delete all keys
                keys_to_delete = list(self._cache.keys())
            
            for key in keys_to_delete:
                del self._cache[key]
            
            self.logger.info(f"🧹 Cleared {len(keys_to_delete)} cache keys (pattern: {pattern or 'all'})")
            return len(keys_to_delete)
            
        except Exception as e:
            self.logger.error(f"❌ Error clearing cache: {e}")
            return 0
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired cache entries
        
        Returns:
            Number of expired entries removed
        """
        try:
            current_time = time.time()
            expired_keys = []
            
            for cache_key, cache_item in self._cache.items():
                if current_time > cache_item["expiry"]:
                    expired_keys.append(cache_key)
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                self.logger.info(f"🧹 Cleaned up {len(expired_keys)} expired cache entries")
            
            return len(expired_keys)
            
        except Exception as e:
            self.logger.error(f"❌ Error cleaning up expired cache: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            current_time = time.time()
            total_entries = len(self._cache)
            expired_entries = 0
            
            for cache_item in self._cache.values():
                if current_time > cache_item["expiry"]:
                    expired_entries += 1
            
            # Calculate memory usage (rough estimate)
            cache_size_bytes = len(json.dumps(self._cache).encode('utf-8'))
            
            return {
                "cache_size": total_entries,
                "expired_entries": expired_entries,
                "active_entries": total_entries - expired_entries,
                "memory_usage_bytes": cache_size_bytes,
                "memory_usage_mb": round(cache_size_bytes / (1024 * 1024), 2),
                "prefix": self.prefix
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error getting cache stats: {e}")
            return {
                "cache_size": 0,
                "expired_entries": 0,
                "active_entries": 0,
                "memory_usage_bytes": 0,
                "memory_usage_mb": 0,
                "prefix": self.prefix,
                "error": str(e)
            }
    
    def get_keys(self, pattern: str = None) -> list:
        """
        Get list of cache keys
        
        Args:
            pattern: Optional pattern to match
            
        Returns:
            List of cache keys
        """
        try:
            keys = []
            
            for cache_key in self._cache.keys():
                # Remove prefix for return
                clean_key = cache_key.replace(f"{self.prefix}:", "")
                
                if pattern:
                    if pattern in clean_key:
                        keys.append(clean_key)
                else:
                    keys.append(clean_key)
            
            return sorted(keys)
            
        except Exception as e:
            self.logger.error(f"❌ Error getting cache keys: {e}")
            return []
    
    def exists(self, key: str) -> bool:
        """
        Check if a cache key exists and is not expired
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists and is not expired
        """
        return self.get(key) is not None
    
    def get_ttl(self, key: str) -> Optional[int]:
        """
        Get remaining TTL for a cache key
        
        Args:
            key: Cache key
            
        Returns:
            Remaining TTL in seconds, or None if key doesn't exist
        """
        try:
            cache_key = self._generate_key(key)
            
            if cache_key not in self._cache:
                return None
            
            cache_item = self._cache[cache_key]
            remaining_ttl = cache_item["expiry"] - time.time()
            
            return max(0, int(remaining_ttl))
            
        except Exception as e:
            self.logger.error(f"❌ Error getting TTL for key {key}: {e}")
            return None
    
    def set_with_tags(self, key: str, value: Any, ttl: int = 3600, tags: list = None) -> bool:
        """
        Set a cache value with tags for easier management
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            tags: List of tags for this cache entry
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._generate_key(key)
            expiry_time = time.time() + ttl
            
            self._cache[cache_key] = {
                "value": value,
                "expiry": expiry_time,
                "created_at": time.time(),
                "tags": tags or []
            }
            
            self.logger.debug(f"✅ Cached key: {key} with tags: {tags}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error setting cache with tags for key {key}: {e}")
            return False
    
    def get_by_tag(self, tag: str) -> Dict[str, Any]:
        """
        Get all cache entries with a specific tag
        
        Args:
            tag: Tag to search for
            
        Returns:
            Dictionary of key-value pairs with the specified tag
        """
        try:
            current_time = time.time()
            tagged_entries = {}
            
            for cache_key, cache_item in self._cache.items():
                # Check if expired
                if current_time > cache_item["expiry"]:
                    continue
                
                # Check if tag exists
                if "tags" in cache_item and tag in cache_item["tags"]:
                    clean_key = cache_key.replace(f"{self.prefix}:", "")
                    tagged_entries[clean_key] = cache_item["value"]
            
            return tagged_entries
            
        except Exception as e:
            self.logger.error(f"❌ Error getting cache entries by tag {tag}: {e}")
            return {}
    
    def clear_by_tag(self, tag: str) -> int:
        """
        Clear all cache entries with a specific tag
        
        Args:
            tag: Tag to clear
            
        Returns:
            Number of entries cleared
        """
        try:
            keys_to_delete = []
            
            for cache_key, cache_item in self._cache.items():
                if "tags" in cache_item and tag in cache_item["tags"]:
                    keys_to_delete.append(cache_key)
            
            for key in keys_to_delete:
                del self._cache[key]
            
            self.logger.info(f"🧹 Cleared {len(keys_to_delete)} cache entries with tag: {tag}")
            return len(keys_to_delete)
            
        except Exception as e:
            self.logger.error(f"❌ Error clearing cache by tag {tag}: {e}")
            return 0


# Global cache instances
fmp_cache = CacheManager("fmp")
price_cache = CacheManager("price")
profile_cache = CacheManager("profile")
financials_cache = CacheManager("financials")
news_cache = CacheManager("news")


def get_cache_manager(prefix: str) -> CacheManager:
    """Get a cache manager with a specific prefix"""
    return CacheManager(prefix)


def clear_all_caches() -> Dict[str, int]:
    """Clear all global cache instances"""
    results = {}
    
    caches = [
        ("fmp", fmp_cache),
        ("price", price_cache),
        ("profile", profile_cache),
        ("financials", financials_cache),
        ("news", news_cache)
    ]
    
    for name, cache in caches:
        cleared = cache.clear()
        results[name] = cleared
    
    return results


def get_all_cache_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all global cache instances"""
    results = {}
    
    caches = [
        ("fmp", fmp_cache),
        ("price", price_cache),
        ("profile", profile_cache),
        ("financials", financials_cache),
        ("news", news_cache)
    ]
    
    for name, cache in caches:
        results[name] = cache.get_stats()
    
    return results
