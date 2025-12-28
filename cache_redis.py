# cache_redis.py - Redis caching layer for performance optimization
import os
import json
import logging
import functools
from typing import Any, Optional, Callable
from datetime import timedelta

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not installed. Caching disabled. Install with: pip install redis")

LOG = logging.getLogger("cache_redis")

class RedisCache:
    """Redis caching layer for FantaCalcio-AI"""
    
    def __init__(self):
        self.enabled = REDIS_AVAILABLE and os.getenv("REDIS_ENABLED", "true").lower() == "true"
        self.client = None
        
        if self.enabled:
            try:
                redis_host = os.getenv("REDIS_HOST", "redis")
                redis_port = int(os.getenv("REDIS_PORT", "6379"))
                redis_db = int(os.getenv("REDIS_DB", "0"))
                
                self.client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                
                # Test connection
                self.client.ping()
                LOG.info(f"Redis cache initialized: {redis_host}:{redis_port}/{redis_db}")
            except Exception as e:
                LOG.warning(f"Redis connection failed, caching disabled: {e}")
                self.enabled = False
                self.client = None
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.enabled or not self.client:
            return None
        
        try:
            value = self.client.get(key)
            if value:
                LOG.debug(f"Cache HIT: {key}")
                return json.loads(value)
            LOG.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            LOG.error(f"Cache get error for {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in cache with TTL (default 5 minutes)"""
        if not self.enabled or not self.client:
            return False
        
        try:
            serialized = json.dumps(value)
            self.client.setex(key, ttl, serialized)
            LOG.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            LOG.error(f"Cache set error for {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.enabled or not self.client:
            return False
        
        try:
            self.client.delete(key)
            LOG.debug(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            LOG.error(f"Cache delete error for {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        if not self.enabled or not self.client:
            return 0
        
        try:
            keys = self.client.keys(pattern)
            if keys:
                deleted = self.client.delete(*keys)
                LOG.info(f"Cache CLEAR: {len(keys)} keys matching '{pattern}'")
                return deleted
            return 0
        except Exception as e:
            LOG.error(f"Cache clear pattern error for {pattern}: {e}")
            return 0
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        if not self.enabled or not self.client:
            return {"enabled": False, "status": "disabled"}
        
        try:
            info = self.client.info("stats")
            return {
                "enabled": True,
                "status": "connected",
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "keys": self.client.dbsize(),
                "memory_used": info.get("used_memory_human", "N/A")
            }
        except Exception as e:
            return {"enabled": True, "status": "error", "error": str(e)}

# Global cache instance
_redis_cache = None

def get_redis_cache() -> RedisCache:
    """Get or create Redis cache singleton"""
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache()
    return _redis_cache

def cached_redis(ttl: int = 300, key_prefix: str = ""):
    """Decorator for caching function results in Redis
    
    Args:
        ttl: Time to live in seconds (default 5 minutes)
        key_prefix: Prefix for cache key
    
    Usage:
        @cached_redis(ttl=600, key_prefix="roster")
        def get_roster():
            return expensive_operation()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_redis_cache()
            
            if not cache.enabled:
                # Cache disabled, call function directly
                return func(*args, **kwargs)
            
            # Create cache key from function name and arguments
            key_parts = [key_prefix or func.__name__]
            if args:
                key_parts.append(str(hash(str(args))))
            if kwargs:
                key_parts.append(str(hash(str(sorted(kwargs.items())))))
            cache_key = ":".join(key_parts)
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Cache miss, call function and store result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl=ttl)
            return result
        
        # Add cache management methods
        wrapper.clear_cache = lambda: get_redis_cache().clear_pattern(f"{key_prefix or func.__name__}:*")
        return wrapper
    
    return decorator

# Cache key helpers
def roster_cache_key(filters: dict = None) -> str:
    """Generate cache key for roster queries"""
    if not filters:
        return "roster:all"
    filter_str = "_".join(f"{k}:{v}" for k, v in sorted(filters.items()))
    return f"roster:{filter_str}"

def player_cache_key(player_name: str) -> str:
    """Generate cache key for player data"""
    return f"player:{player_name.lower().replace(' ', '_')}"

def league_cache_key(user_id: int, league_id: int = None) -> str:
    """Generate cache key for league data"""
    if league_id:
        return f"league:{user_id}:{league_id}"
    return f"league:{user_id}:all"

def analytics_cache_key(user_id: int, query_type: str) -> str:
    """Generate cache key for analytics queries"""
    return f"analytics:{user_id}:{query_type}"
