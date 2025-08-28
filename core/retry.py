"""
Professional Retry and Circuit Breaker System
Implements resilient patterns for external service calls
"""
import asyncio
import time
import random
from typing import Callable, Any, Optional, Dict, List
from functools import wraps
from enum import Enum
from dataclasses import dataclass, field
from core.logging import get_logger
from core.exceptions import ExternalServiceError

logger = get_logger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered

@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    backoff_strategy: str = "exponential"  # "exponential", "linear", "fixed"
    retry_on_exceptions: tuple = (Exception,)
    stop_on_exceptions: tuple = ()

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: tuple = (Exception,)
    half_open_max_calls: int = 3

class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring"""
    
    def __init__(self):
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.state_changes = 0
        self.last_failure_time: Optional[float] = None
        self.failure_streak = 0
        self.half_open_calls = 0

class CircuitBreaker:
    """Circuit breaker implementation for service resilience"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self.last_state_change = time.time()
        
    def _should_attempt_call(self) -> bool:
        """Determine if call should be attempted based on circuit state"""
        current_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            return True
        
        elif self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if current_time - self.last_state_change >= self.config.recovery_timeout:
                self._transition_to_half_open()
                return True
            return False
        
        elif self.state == CircuitState.HALF_OPEN:
            # Allow limited calls to test service
            return self.stats.half_open_calls < self.config.half_open_max_calls
        
        return False
    
    def _transition_to_open(self):
        """Transition circuit to OPEN state"""
        self.state = CircuitState.OPEN
        self.last_state_change = time.time()
        self.stats.state_changes += 1
        logger.warning(f"Circuit breaker '{self.name}' opened due to failures", extra={
            'circuit_breaker': self.name,
            'failure_streak': self.stats.failure_streak,
            'total_failures': self.stats.failed_calls
        })
    
    def _transition_to_half_open(self):
        """Transition circuit to HALF_OPEN state"""
        self.state = CircuitState.HALF_OPEN
        self.last_state_change = time.time()
        self.stats.half_open_calls = 0
        self.stats.state_changes += 1
        logger.info(f"Circuit breaker '{self.name}' entering half-open state")
    
    def _transition_to_closed(self):
        """Transition circuit to CLOSED state"""
        self.state = CircuitState.CLOSED
        self.last_state_change = time.time()
        self.stats.failure_streak = 0
        self.stats.state_changes += 1
        logger.info(f"Circuit breaker '{self.name}' closed - service recovered")
    
    def _record_success(self):
        """Record successful call"""
        self.stats.total_calls += 1
        self.stats.successful_calls += 1
        self.stats.failure_streak = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.stats.half_open_calls += 1
            # If enough successful calls in half-open, close circuit
            if self.stats.half_open_calls >= self.config.half_open_max_calls:
                self._transition_to_closed()
    
    def _record_failure(self):
        """Record failed call"""
        self.stats.total_calls += 1
        self.stats.failed_calls += 1
        self.stats.failure_streak += 1
        self.stats.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            # If failure in half-open, go back to open
            self._transition_to_open()
        elif self.state == CircuitState.CLOSED:
            # Check if should open circuit
            if self.stats.failure_streak >= self.config.failure_threshold:
                self._transition_to_open()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function call with circuit breaker protection"""
        if not self._should_attempt_call():
            raise ExternalServiceError(
                f"Circuit breaker '{self.name}' is open",
                service=self.name
            )
        
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        
        except self.config.expected_exception as e:
            self._record_failure()
            raise e

class RetryExecutor:
    """Handles retry logic with various backoff strategies"""
    
    def __init__(self, config: RetryConfig):
        self.config = config
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        if self.config.backoff_strategy == "fixed":
            delay = self.config.base_delay
        elif self.config.backoff_strategy == "linear":
            delay = self.config.base_delay * attempt
        else:  # exponential
            delay = self.config.base_delay * (self.config.exponential_base ** (attempt - 1))
        
        # Cap at max delay
        delay = min(delay, self.config.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.config.jitter:
            jitter_range = delay * 0.1
            jitter = random.uniform(-jitter_range, jitter_range)
            delay += jitter
        
        return max(0, delay)
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry logic"""
        last_exception = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                logger.debug(f"Executing function attempt {attempt}/{self.config.max_attempts}")
                return func(*args, **kwargs)
            
            except self.config.stop_on_exceptions as e:
                # Don't retry on these exceptions
                logger.info(f"Stopping retries due to exception: {e}")
                raise e
            
            except self.config.retry_on_exceptions as e:
                last_exception = e
                logger.warning(f"Attempt {attempt} failed: {e}")
                
                # Don't delay after last attempt
                if attempt < self.config.max_attempts:
                    delay = self._calculate_delay(attempt)
                    logger.debug(f"Retrying in {delay:.2f} seconds")
                    time.sleep(delay)
                else:
                    logger.error(f"All {self.config.max_attempts} attempts failed")
        
        # All attempts failed
        raise last_exception

# Global circuit breakers registry
_circuit_breakers: Dict[str, CircuitBreaker] = {}

def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create circuit breaker instance"""
    if name not in _circuit_breakers:
        if config is None:
            config = CircuitBreakerConfig()
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]

def retry(config: Optional[RetryConfig] = None):
    """Decorator for adding retry logic to functions"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_config = config or RetryConfig()
            executor = RetryExecutor(retry_config)
            return executor.execute(func, *args, **kwargs)
        return wrapper
    return decorator

def with_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """Decorator for adding circuit breaker protection to functions"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            circuit_breaker = get_circuit_breaker(name, config)
            return circuit_breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator

def resilient_call(name: str, 
                  func: Callable,
                  retry_config: Optional[RetryConfig] = None,
                  circuit_config: Optional[CircuitBreakerConfig] = None,
                  *args, **kwargs) -> Any:
    """Execute function with both retry and circuit breaker protection"""
    
    # Get circuit breaker
    circuit_breaker = get_circuit_breaker(name, circuit_config)
    
    # Create retry executor
    retry_executor = RetryExecutor(retry_config or RetryConfig())
    
    # Execute with both protections
    def protected_call():
        return circuit_breaker.call(func, *args, **kwargs)
    
    return retry_executor.execute(protected_call)

# Async versions
async def async_retry(func: Callable, config: Optional[RetryConfig] = None, *args, **kwargs) -> Any:
    """Async version of retry logic"""
    retry_config = config or RetryConfig()
    last_exception = None
    
    for attempt in range(1, retry_config.max_attempts + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        except retry_config.stop_on_exceptions as e:
            raise e
        
        except retry_config.retry_on_exceptions as e:
            last_exception = e
            
            if attempt < retry_config.max_attempts:
                executor = RetryExecutor(retry_config)
                delay = executor._calculate_delay(attempt)
                await asyncio.sleep(delay)
    
    raise last_exception

def get_all_circuit_breaker_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all circuit breakers"""
    stats = {}
    for name, breaker in _circuit_breakers.items():
        stats[name] = {
            'state': breaker.state.value,
            'total_calls': breaker.stats.total_calls,
            'successful_calls': breaker.stats.successful_calls,
            'failed_calls': breaker.stats.failed_calls,
            'failure_streak': breaker.stats.failure_streak,
            'state_changes': breaker.stats.state_changes,
            'success_rate': (
                breaker.stats.successful_calls / breaker.stats.total_calls 
                if breaker.stats.total_calls > 0 else 0
            )
        }
    return stats