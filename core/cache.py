"""
Professional Caching System
In-memory cache with TTL, LRU eviction, and metrics
"""
import time
import threading
import json
import pickle
import hashlib
from typing import Any, Optional, Dict, Callable, Union
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
from core.logging import get_logger

logger = get_logger(__name__)

@dataclass
class CacheEntry:
    """Cache entry with metadata"""
    value: Any
    created_at: float
    expires_at: Optional[float]
    access_count: int = 0
    last_accessed: float = 0

class LRUCache:
    """LRU (Least Recently Used) cache with TTL support"""
    
    def __init__(self, max_size: int = 1000, default_ttl: Optional[float] = None):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expires': 0
        }
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry is expired"""
        if entry.expires_at is None:
            return False
        return time.time() > entry.expires_at
    
    def _evict_expired(self):
        """Remove expired entries"""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self._cache.items():
            if self._is_expired(entry):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
            self._stats['expires'] += 1
    
    def _evict_lru(self):
        """Evict least recently used entry"""
        if self._cache:
            self._cache.popitem(last=False)
            self._stats['evictions'] += 1
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self._lock:
            if key not in self._cache:
                self._stats['misses'] += 1
                return None
            
            entry = self._cache[key]
            
            # Check if expired
            if self._is_expired(entry):
                del self._cache[key]
                self._stats['expires'] += 1
                self._stats['misses'] += 1
                return None
            
            # Update access metadata
            entry.access_count += 1
            entry.last_accessed = time.time()
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            
            self._stats['hits'] += 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set value in cache"""
        with self._lock:
            current_time = time.time()
            ttl_to_use = ttl if ttl is not None else self.default_ttl
            expires_at = current_time + ttl_to_use if ttl_to_use else None
            
            entry = CacheEntry(
                value=value,
                created_at=current_time,
                expires_at=expires_at,
                access_count=0,
                last_accessed=current_time
            )
            
            # Remove existing entry if present
            if key in self._cache:
                del self._cache[key]
            
            # Add new entry
            self._cache[key] = entry
            
            # Clean up expired entries
            self._evict_expired()
            
            # Evict LRU if over max size
            while len(self._cache) > self.max_size:
                self._evict_lru()
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size"""
        with self._lock:
            return len(self._cache)
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = self._stats['hits'] / total_requests if total_requests > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': hit_rate,
                'evictions': self._stats['evictions'],
                'expires': self._stats['expires'],
                'total_requests': total_requests
            }

class CacheManager:
    """Manages multiple named caches"""
    
    def __init__(self):
        self._caches: Dict[str, LRUCache] = {}
        self._lock = threading.Lock()
    
    def get_cache(self, name: str, max_size: int = 1000, default_ttl: Optional[float] = None) -> LRUCache:
        """Get or create a named cache"""
        with self._lock:
            if name not in self._caches:
                self._caches[name] = LRUCache(max_size=max_size, default_ttl=default_ttl)
                logger.info(f"Created cache '{name}' with max_size={max_size}, default_ttl={default_ttl}")
            return self._caches[name]
    
    def delete_cache(self, name: str) -> bool:
        """Delete a named cache"""
        with self._lock:
            if name in self._caches:
                del self._caches[name]
                logger.info(f"Deleted cache '{name}'")
                return True
            return False
    
    def clear_all(self) -> None:
        """Clear all caches"""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()
            logger.info("Cleared all caches")
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all caches"""
        with self._lock:
            return {name: cache.stats() for name, cache in self._caches.items()}

# Global cache manager
cache_manager = CacheManager()

def make_cache_key(*args, **kwargs) -> str:
    """Create a cache key from function arguments"""
    # Create a hash of the arguments
    key_data = {
        'args': args,
        'kwargs': kwargs
    }
    
    # Convert to JSON string (sorted for consistency)
    json_str = json.dumps(key_data, sort_keys=True, default=str)
    
    # Create hash
    return hashlib.md5(json_str.encode()).hexdigest()

def cached(cache_name: str = "default",
          ttl: Optional[float] = None,
          max_size: int = 1000,
          key_func: Optional[Callable] = None):
    """
    Decorator for caching function results
    
    Args:
        cache_name: Name of the cache to use
        ttl: Time to live in seconds
        max_size: Maximum cache size
        key_func: Custom function to generate cache key
    """
    def decorator(func: Callable) -> Callable:
        # Get or create cache
        cache = cache_manager.get_cache(cache_name, max_size=max_size, default_ttl=ttl)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Use function name + arguments as key
                cache_key = f"{func.__name__}:{make_cache_key(*args, **kwargs)}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                return result
            
            # Execute function and cache result
            logger.debug(f"Cache miss for {func.__name__}: {cache_key}")
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl=ttl)
            
            return result
        
        # Add cache management methods to function
        wrapper.cache_clear = lambda: cache.clear()
        wrapper.cache_delete = lambda key: cache.delete(key)
        wrapper.cache_stats = lambda: cache.stats()
        
        return wrapper
    return decorator

class QueryCache:
    """Specialized cache for database queries"""
    
    def __init__(self, max_size: int = 500, default_ttl: float = 300):  # 5 minutes default
        self.cache = LRUCache(max_size=max_size, default_ttl=default_ttl)
    
    def get_user(self, user_id: int) -> Optional[Any]:
        """Get cached user data"""
        return self.cache.get(f"user:{user_id}")
    
    def set_user(self, user_id: int, user_data: Any, ttl: Optional[float] = None):
        """Cache user data"""
        self.cache.set(f"user:{user_id}", user_data, ttl=ttl)
    
    def invalidate_user(self, user_id: int):
        """Invalidate user cache"""
        self.cache.delete(f"user:{user_id}")
    
    def get_client(self, client_id: int) -> Optional[Any]:
        """Get cached client data"""
        return self.cache.get(f"client:{client_id}")
    
    def set_client(self, client_id: int, client_data: Any, ttl: Optional[float] = None):
        """Cache client data"""
        self.cache.set(f"client:{client_id}", client_data, ttl=ttl)
    
    def invalidate_client(self, client_id: int):
        """Invalidate client cache"""
        self.cache.delete(f"client:{client_id}")
    
    def get_clients_for_user(self, user_id: int) -> Optional[Any]:
        """Get cached clients list for user"""
        return self.cache.get(f"clients:user:{user_id}")
    
    def set_clients_for_user(self, user_id: int, clients_data: Any, ttl: Optional[float] = None):
        """Cache clients list for user"""
        self.cache.set(f"clients:user:{user_id}", clients_data, ttl=ttl)
    
    def invalidate_clients_for_user(self, user_id: int):
        """Invalidate clients cache for user"""
        self.cache.delete(f"clients:user:{user_id}")
    
    def get_templates_for_user(self, user_id: int) -> Optional[Any]:
        """Get cached templates for user"""
        return self.cache.get(f"templates:user:{user_id}")
    
    def set_templates_for_user(self, user_id: int, templates_data: Any, ttl: Optional[float] = None):
        """Cache templates for user"""
        self.cache.set(f"templates:user:{user_id}", templates_data, ttl=ttl)
    
    def invalidate_templates_for_user(self, user_id: int):
        """Invalidate templates cache for user"""
        self.cache.delete(f"templates:user:{user_id}")

# Global query cache
query_cache = QueryCache()

class SessionCache:
    """Cache for user session data"""
    
    def __init__(self, default_ttl: float = 1800):  # 30 minutes
        self.cache = LRUCache(max_size=1000, default_ttl=default_ttl)
    
    def get_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user session data"""
        return self.cache.get(f"session:{user_id}")
    
    def set_session(self, user_id: int, session_data: Dict[str, Any], ttl: Optional[float] = None):
        """Set user session data"""
        self.cache.set(f"session:{user_id}", session_data, ttl=ttl)
    
    def update_session(self, user_id: int, **updates):
        """Update specific session fields"""
        session_data = self.get_session(user_id) or {}
        session_data.update(updates)
        self.set_session(user_id, session_data)
    
    def clear_session(self, user_id: int):
        """Clear user session"""
        self.cache.delete(f"session:{user_id}")

# Global session cache
session_cache = SessionCache()

def warm_cache():
    """Pre-populate cache with commonly accessed data"""
    logger.info("Starting cache warm-up...")
    
    try:
        # This would be implemented with actual data loading
        # For now, just log that it would happen
        logger.info("Cache warm-up completed")
    except Exception as e:
        logger.error(f"Cache warm-up failed: {e}")

def get_cache_overview() -> Dict[str, Any]:
    """Get overview of all cache statistics"""
    return {
        'query_cache': query_cache.cache.stats(),
        'session_cache': session_cache.cache.stats(),
        'all_caches': cache_manager.get_all_stats(),
        'timestamp': time.time()
    }