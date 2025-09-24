
import os
import json
import time
import hashlib
import logging
from typing import Any, Dict, Optional, List
from functools import wraps
import sqlite3
from datetime import datetime, timedelta

LOG = logging.getLogger("cache_manager")

class CacheManager:
    """Comprehensive caching system for Fantasy Football Assistant"""
    
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = cache_dir
        self.db_path = os.path.join(cache_dir, "cache.db")
        os.makedirs(cache_dir, exist_ok=True)
        self._init_db()
        
        # Cache configuration
        self.cache_ttl = {
            'player_data': 3600,      # 1 hour
            'formations': 1800,       # 30 minutes  
            'transfers': 7200,        # 2 hours
            'search_results': 600,    # 10 minutes
            'statistics': 1800,       # 30 minutes
            'km_queries': 3600,       # 1 hour
            'default': 1800          # 30 minutes
        }
    
    def _init_db(self):
        """Initialize SQLite cache database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    size INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category ON cache(category)
            """)
            LOG.info("[Cache] Database initialized at %s", self.db_path)
    
    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Create cache key from arguments"""
        key_data = f"{prefix}:{':'.join(map(str, args))}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value, expires_at FROM cache WHERE key = ? AND expires_at > ?",
                    (key, time.time())
                )
                result = cursor.fetchone()
                
                if result:
                    return json.loads(result[0])
                return None
        except Exception as e:
            LOG.error("[Cache] Error getting key %s: %s", key, e)
            return None
    
    def set(self, key: str, value: Any, category: str = 'default', ttl: Optional[int] = None) -> bool:
        """Set cached value"""
        try:
            if ttl is None:
                ttl = self.cache_ttl.get(category, self.cache_ttl['default'])
            
            serialized_value = json.dumps(value, ensure_ascii=False)
            size = len(serialized_value.encode('utf-8'))
            expires_at = time.time() + ttl
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cache 
                    (key, value, category, created_at, expires_at, size)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (key, serialized_value, category, time.time(), expires_at, size))
            
            return True
        except Exception as e:
            LOG.error("[Cache] Error setting key %s: %s", key, e)
            return False
    
    def invalidate_category(self, category: str) -> int:
        """Remove all cached items in a category"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache WHERE category = ?", (category,))
                return cursor.rowcount
        except Exception as e:
            LOG.error("[Cache] Error invalidating category %s: %s", category, e)
            return 0
    
    def cleanup_expired(self) -> int:
        """Remove expired cache entries"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache WHERE expires_at <= ?", (time.time(),))
                return cursor.rowcount
        except Exception as e:
            LOG.error("[Cache] Error cleaning up: %s", e)
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total items and size
                cursor.execute("SELECT COUNT(*), SUM(size) FROM cache WHERE expires_at > ?", (time.time(),))
                total_items, total_size = cursor.fetchone()
                
                # Items by category
                cursor.execute("""
                    SELECT category, COUNT(*), SUM(size) 
                    FROM cache WHERE expires_at > ? 
                    GROUP BY category
                """, (time.time(),))
                by_category = {row[0]: {'count': row[1], 'size': row[2]} for row in cursor.fetchall()}
                
                return {
                    'total_items': total_items or 0,
                    'total_size_bytes': total_size or 0,
                    'by_category': by_category
                }
        except Exception as e:
            LOG.error("[Cache] Error getting stats: %s", e)
            return {}

# Global cache instance
_cache_manager = None

def get_cache_manager() -> CacheManager:
    """Get global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

def cached(category: str = 'default', ttl: Optional[int] = None):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache_manager()
            cache_key = cache._make_key(f"func_{func.__name__}", *args, **kwargs)
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, category, ttl)
            return result
        return wrapper
    return decorator
