import os
import json
import time
import hashlib
import logging
from typing import Any, Dict, Optional, List
from functools import wraps
import sqlite3
from datetime import datetime, timedelta
import sys # Added for sys.getsizeof

LOG = logging.getLogger("cache_manager")

class CacheManager:
    """Comprehensive caching system for Fantasy Football Assistant"""

    def __init__(self, cache_dir: str = "./cache"):
        # The original code used SQLite, but the provided changes imply an in-memory cache.
        # We will proceed with the in-memory cache implementation as per the changes.
        self.cache_dir = cache_dir # This might be vestigial if not used by the new methods
        # os.makedirs(cache_dir, exist_ok=True) # Not needed for in-memory cache
        # self.db_path = os.path.join(cache_dir, "cache.db") # Not needed for in-memory cache
        # self._init_db() # Not needed for in-memory cache

        self.cache: Dict[str, Dict[str, Any]] = {} # In-memory cache
        self.stats = {
            'hits': 0,
            'misses': 0,
            'start_time': datetime.now()
        }
        # Cache configuration - these TTLs might be used by set, but the original changes don't show how they're integrated.
        # For now, we'll keep them but they aren't directly used in the provided 'set' or 'get' implementations.
        self.cache_ttl = {
            'player_data': 3600,      # 1 hour
            'formations': 1800,       # 30 minutes
            'transfers': 7200,        # 2 hours
            'search_results': 600,    # 10 minutes
            'statistics': 1800,       # 30 minutes
            'km_queries': 3600,       # 1 hour
            'default': 1800          # 30 minutes
        }

    # The following methods are replacements based on the provided <changes> snippet.
    # They replace the original SQLite-based methods.

    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Create cache key from arguments"""
        key_data = f"{prefix}:{':'.join(map(str, args))}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def get(self, key: str) -> Any:
        """Get a value from cache with hit/miss tracking"""
        if key not in self.cache:
            self.stats['misses'] = self.stats.get('misses', 0) + 1
            return None

        entry = self.cache[key]

        # Check if expired
        if datetime.now() > entry['expires_at']:
            del self.cache[key]
            self.stats['misses'] = self.stats.get('misses', 0) + 1
            return None

        # Update access time for LRU (This part of the original changes was slightly different, assuming simple LRU for now)
        # The provided snippet did not include an explicit LRU eviction policy, just access time update.
        entry['accessed_at'] = datetime.now()
        self.stats['hits'] = self.stats.get('hits', 0) + 1
        return entry['value']

    def get_multi(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from cache efficiently"""
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result

    def set(self, key: str, value: Any, category: str = 'default', ttl: Optional[int] = None) -> bool:
        """Set cached value with category and optional TTL"""
        if ttl is None:
            # Using the category TTLs, though the original provided changes for set didn't explicitly use 'category'
            # Assuming category is meant to influence TTL here.
            ttl = self.cache_ttl.get(category, self.cache_ttl['default'])

        expires_at = datetime.now() + timedelta(seconds=ttl)
        self.cache[key] = {
            'value': value,
            'expires_at': expires_at,
            'accessed_at': datetime.now(),
            'category': category # Keeping category info if needed later
        }
        return True

    def set_with_tags(self, key: str, value: Any, ttl: int = 3600, tags: List[str] = None):
        """Set cache with tags for bulk invalidation"""
        # The original 'set' method is used here as a base.
        # The 'category' parameter from the original 'set' is not used in this new method signature.
        # We will use the provided ttl and tags.
        self.set(key, value, category='tagged', ttl=ttl) # Using 'tagged' as a default category for tagged items

        if tags:
            if 'tag_index' not in self.cache:
                self.cache['tag_index'] = {}
            for tag in tags:
                if tag not in self.cache['tag_index']:
                    self.cache['tag_index'][tag] = set()
                self.cache['tag_index'][tag].add(key)

    def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all cache entries with a specific tag"""
        if 'tag_index' not in self.cache or tag not in self.cache['tag_index']:
            return 0

        keys_to_remove = list(self.cache['tag_index'][tag])
        count = 0

        for key in keys_to_remove:
            if key in self.cache:
                del self.cache[key]
                count += 1

        # Clean up tag index
        del self.cache['tag_index'][tag]
        return count

    # The following methods are from the original SQLiteCacheManager, but are not present in the provided changes.
    # Therefore, they are omitted as per the instructions to only include modifications from the changes snippet.
    # def _init_db(self): ...
    # def invalidate_category(self, category: str) -> int: ...
    # def cleanup_expired(self) -> int: ...
    # def get_stats(self) -> Dict[str, Any]: ...

    # New methods from the changes snippet:
    def get_cache_stats(self) -> Dict:
        """Get detailed cache statistics"""
        hits = self.stats.get('hits', 0)
        misses = self.stats.get('misses', 0)
        total = hits + misses

        # Filter out internal cache keys like 'tag_index'
        active_keys_count = len([k for k in self.cache.keys() if k != 'tag_index' and not (k.startswith('func_') and k.endswith('_tag_index'))]) # Added check for potential decorator keys

        return {
            'hits': hits,
            'misses': misses,
            'hit_rate': hits / total if total > 0 else 0,
            'total_keys': active_keys_count,
            'memory_usage': self.get_memory_usage(),
            'uptime': (datetime.now() - self.stats.get('start_time', datetime.now())).total_seconds()
        }

    def get_memory_usage(self) -> int:
        """Estimate memory usage of cache"""
        total_size = 0
        # Iterate over actual cache entries, not internal structures like tag_index
        for key, value_entry in self.cache.items():
            if key != 'tag_index': # Exclude the tag_index itself
                total_size += sys.getsizeof(key)
                # Estimate size of the value entry dictionary
                for sub_key, sub_value in value_entry.items():
                    total_size += sys.getsizeof(sub_key)
                    total_size += sys.getsizeof(sub_value)
        return total_size

# Global cache instance
_cache_manager = None

def get_cache_manager() -> CacheManager:
    """Get global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        # Initialize with the new CacheManager that uses in-memory cache
        _cache_manager = CacheManager()
    return _cache_manager

def cached(category: str = 'default', ttl: Optional[int] = None):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache_manager()
            # The _make_key method is still relevant for creating cache keys for function results.
            cache_key = cache._make_key(f"func_{func.__name__}", *args, **kwargs)

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Execute function and cache result
            result = func(*args, **kwargs)
            # Using the set method which now handles the in-memory storage.
            cache.set(cache_key, result, category, ttl)
            return result
        return wrapper
    return decorator