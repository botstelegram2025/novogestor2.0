"""
Professional Rate Limiting System
Implements various rate limiting strategies for API protection
"""
import time
import threading
from typing import Dict, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from core.logging import get_logger
from core.exceptions import RateLimitError

logger = get_logger(__name__)

class RateLimitStrategy(Enum):
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"

@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    max_requests: int
    window_seconds: int
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    burst_allowance: Optional[int] = None  # For token bucket
    
class TokenBucket:
    """Token bucket rate limiter implementation"""
    
    def __init__(self, max_tokens: int, refill_rate: float, burst_allowance: Optional[int] = None):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate  # tokens per second
        self.burst_allowance = burst_allowance or max_tokens
        self.tokens = max_tokens
        self.last_refill = time.time()
        self._lock = threading.Lock()
    
    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        
        self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def allow_request(self, tokens_needed: int = 1) -> Tuple[bool, float]:
        """
        Check if request is allowed
        Returns: (allowed, wait_time_seconds)
        """
        with self._lock:
            self._refill()
            
            if self.tokens >= tokens_needed:
                self.tokens -= tokens_needed
                return True, 0.0
            else:
                # Calculate wait time
                tokens_needed_to_wait = tokens_needed - self.tokens
                wait_time = tokens_needed_to_wait / self.refill_rate
                return False, wait_time

class SlidingWindowCounter:
    """Sliding window rate limiter implementation"""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()
        self._lock = threading.Lock()
    
    def _cleanup_old_requests(self):
        """Remove requests outside the current window"""
        cutoff_time = time.time() - self.window_seconds
        while self.requests and self.requests[0] <= cutoff_time:
            self.requests.popleft()
    
    def allow_request(self) -> Tuple[bool, float]:
        """
        Check if request is allowed
        Returns: (allowed, wait_time_seconds)
        """
        with self._lock:
            current_time = time.time()
            self._cleanup_old_requests()
            
            if len(self.requests) < self.max_requests:
                self.requests.append(current_time)
                return True, 0.0
            else:
                # Calculate wait time until oldest request expires
                oldest_request = self.requests[0]
                wait_time = (oldest_request + self.window_seconds) - current_time
                return False, max(0, wait_time)

class FixedWindowCounter:
    """Fixed window rate limiter implementation"""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.current_window_start = None
        self.current_window_count = 0
        self._lock = threading.Lock()
    
    def _get_current_window_start(self) -> int:
        """Get the start time of the current window"""
        now = int(time.time())
        return (now // self.window_seconds) * self.window_seconds
    
    def allow_request(self) -> Tuple[bool, float]:
        """
        Check if request is allowed
        Returns: (allowed, wait_time_seconds)
        """
        with self._lock:
            current_window_start = self._get_current_window_start()
            
            # Reset counter if we're in a new window
            if self.current_window_start != current_window_start:
                self.current_window_start = current_window_start
                self.current_window_count = 0
            
            if self.current_window_count < self.max_requests:
                self.current_window_count += 1
                return True, 0.0
            else:
                # Calculate wait time until next window
                next_window_start = current_window_start + self.window_seconds
                wait_time = next_window_start - time.time()
                return False, max(0, wait_time)

class RateLimiter:
    """Main rate limiter that manages different strategies and keys"""
    
    def __init__(self):
        self._limiters: Dict[str, object] = {}
        self._configs: Dict[str, RateLimitConfig] = {}
        self._lock = threading.Lock()
    
    def add_limit(self, key: str, config: RateLimitConfig):
        """Add a rate limit for a specific key"""
        with self._lock:
            self._configs[key] = config
            
            if config.strategy == RateLimitStrategy.TOKEN_BUCKET:
                refill_rate = config.max_requests / config.window_seconds
                self._limiters[key] = TokenBucket(
                    max_tokens=config.max_requests,
                    refill_rate=refill_rate,
                    burst_allowance=config.burst_allowance
                )
            elif config.strategy == RateLimitStrategy.SLIDING_WINDOW:
                self._limiters[key] = SlidingWindowCounter(
                    max_requests=config.max_requests,
                    window_seconds=config.window_seconds
                )
            elif config.strategy == RateLimitStrategy.FIXED_WINDOW:
                self._limiters[key] = FixedWindowCounter(
                    max_requests=config.max_requests,
                    window_seconds=config.window_seconds
                )
            
            logger.info(f"Rate limit added for key '{key}': {config.max_requests} requests per {config.window_seconds}s using {config.strategy.value}")
    
    def check_limit(self, key: str, identifier: str, cost: int = 1) -> Tuple[bool, float]:
        """
        Check if request is within rate limit
        Args:
            key: Rate limit rule key
            identifier: Unique identifier (user_id, ip, etc.)
            cost: Cost of this request in tokens
        Returns: (allowed, wait_time_seconds)
        """
        full_key = f"{key}:{identifier}"
        
        with self._lock:
            if key not in self._configs:
                # No rate limit configured for this key
                return True, 0.0
            
            # Create limiter instance for this specific identifier if needed
            if full_key not in self._limiters:
                config = self._configs[key]
                
                if config.strategy == RateLimitStrategy.TOKEN_BUCKET:
                    refill_rate = config.max_requests / config.window_seconds
                    self._limiters[full_key] = TokenBucket(
                        max_tokens=config.max_requests,
                        refill_rate=refill_rate,
                        burst_allowance=config.burst_allowance
                    )
                elif config.strategy == RateLimitStrategy.SLIDING_WINDOW:
                    self._limiters[full_key] = SlidingWindowCounter(
                        max_requests=config.max_requests,
                        window_seconds=config.window_seconds
                    )
                elif config.strategy == RateLimitStrategy.FIXED_WINDOW:
                    self._limiters[full_key] = FixedWindowCounter(
                        max_requests=config.max_requests,
                        window_seconds=config.window_seconds
                    )
            
            limiter = self._limiters[full_key]
            
            # Check rate limit
            if hasattr(limiter, 'allow_request'):
                if isinstance(limiter, TokenBucket):
                    return limiter.allow_request(cost)
                else:
                    return limiter.allow_request()
            
            return True, 0.0
    
    def enforce_limit(self, key: str, identifier: str, cost: int = 1):
        """
        Enforce rate limit, raising exception if exceeded
        Args:
            key: Rate limit rule key
            identifier: Unique identifier (user_id, ip, etc.)
            cost: Cost of this request in tokens
        """
        allowed, wait_time = self.check_limit(key, identifier, cost)
        
        if not allowed:
            config = self._configs.get(key)
            raise RateLimitError(
                f"Rate limit exceeded for {key}. Try again in {wait_time:.1f} seconds.",
                limit=config.max_requests if config else None,
                window=config.window_seconds if config else None
            )
    
    def get_status(self, key: str, identifier: str) -> Dict[str, any]:
        """Get rate limit status for a key/identifier combination"""
        full_key = f"{key}:{identifier}"
        config = self._configs.get(key)
        
        if not config:
            return {"error": "Rate limit not configured"}
        
        limiter = self._limiters.get(full_key)
        if not limiter:
            return {
                "remaining": config.max_requests,
                "limit": config.max_requests,
                "window_seconds": config.window_seconds,
                "strategy": config.strategy.value
            }
        
        # Calculate remaining for different strategies
        if isinstance(limiter, TokenBucket):
            with limiter._lock:
                limiter._refill()
                remaining = int(limiter.tokens)
        elif isinstance(limiter, SlidingWindowCounter):
            with limiter._lock:
                limiter._cleanup_old_requests()
                remaining = config.max_requests - len(limiter.requests)
        elif isinstance(limiter, FixedWindowCounter):
            with limiter._lock:
                current_window_start = limiter._get_current_window_start()
                if limiter.current_window_start != current_window_start:
                    remaining = config.max_requests
                else:
                    remaining = config.max_requests - limiter.current_window_count
        else:
            remaining = config.max_requests
        
        return {
            "remaining": max(0, remaining),
            "limit": config.max_requests,
            "window_seconds": config.window_seconds,
            "strategy": config.strategy.value
        }
    
    def cleanup_old_limiters(self, max_age_seconds: int = 3600):
        """Clean up old limiter instances to prevent memory leaks"""
        with self._lock:
            # This is a simplified cleanup - in production you'd track last access times
            # For now, we'll keep all limiters since they're cleaned internally
            pass

# Global rate limiter instance
rate_limiter = RateLimiter()

def rate_limit(key: str, max_requests: int, window_seconds: int, 
               strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW):
    """Decorator for adding rate limiting to functions"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Try to extract identifier from arguments
            identifier = "default"
            if args and hasattr(args[0], 'effective_user'):
                # Telegram update object
                identifier = str(args[0].effective_user.id)
            elif 'user_id' in kwargs:
                identifier = str(kwargs['user_id'])
            
            # Add rate limit if not exists
            if key not in rate_limiter._configs:
                config = RateLimitConfig(
                    max_requests=max_requests,
                    window_seconds=window_seconds,
                    strategy=strategy
                )
                rate_limiter.add_limit(key, config)
            
            # Enforce rate limit
            rate_limiter.enforce_limit(key, identifier)
            
            return func(*args, **kwargs)
        return wrapper
    return decorator