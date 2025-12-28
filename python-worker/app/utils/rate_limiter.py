"""
Rate Limiter Utility
Implements token bucket algorithm for API rate limiting
Industry Standard: Prevents API rate limit violations
"""
import time
import threading
from typing import Optional
from collections import deque
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for API calls
    
    Industry Standard: Token bucket algorithm
    - Allows bursts up to max_tokens
    - Refills tokens at rate of max_tokens per time_window
    - Thread-safe for concurrent API calls
    """
    
    def __init__(
        self,
        max_calls: int,
        time_window: float = 60.0,  # seconds
        name: str = "RateLimiter"
    ):
        """
        Initialize rate limiter
        
        Args:
            max_calls: Maximum number of calls allowed in time_window
            time_window: Time window in seconds (default: 60 for per-minute)
            name: Name for logging purposes
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.name = name
        
        # Thread-safe call tracking
        self._lock = threading.Lock()
        self._call_times = deque()  # Timestamps of recent calls
        
        logger.info(
            f"Initialized {name}: {max_calls} calls per {time_window}s "
            f"({max_calls / (time_window / 60):.2f} calls/minute)"
        )
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to make an API call
        
        Blocks until a token is available or timeout expires
        
        Args:
            timeout: Maximum time to wait in seconds (None = wait indefinitely)
        
        Returns:
            True if permission granted, False if timeout
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                # Clean old call times outside the time window
                current_time = time.time()
                cutoff_time = current_time - self.time_window
                
                while self._call_times and self._call_times[0] < cutoff_time:
                    self._call_times.popleft()
                
                # Check if we can make a call
                if len(self._call_times) < self.max_calls:
                    # We have capacity, record the call
                    self._call_times.append(current_time)
                    logger.debug(
                        f"{self.name}: Call allowed. "
                        f"Used: {len(self._call_times)}/{self.max_calls} calls"
                    )
                    return True
                
                # No capacity, calculate wait time
                oldest_call = self._call_times[0]
                wait_time = (oldest_call + self.time_window) - current_time
                
                # If wait time is negative or very small, try again immediately
                if wait_time <= 0.01:
                    continue
            
            # Wait outside the lock to allow other threads to proceed
            if timeout is not None:
                elapsed = time.time() - start_time
                remaining_timeout = timeout - elapsed
                
                if remaining_timeout <= 0:
                    logger.warning(
                        f"{self.name}: Rate limit timeout. "
                        f"Could not acquire token within {timeout}s"
                    )
                    return False
                
                wait_time = min(wait_time, remaining_timeout)
            else:
                # Wait indefinitely
                if wait_time <= 0:
                    continue  # Retry immediately
            
            if wait_time > 0:
                logger.debug(
                    f"{self.name}: Rate limit reached. "
                    f"Waiting {wait_time:.2f}s for next available slot"
                )
                time.sleep(wait_time)
            
            # Continue loop to retry
    
    def __call__(self, func):
        """
        Decorator for rate limiting function calls
        
        Usage:
            @rate_limiter
            def api_call():
                ...
        """
        def wrapper(*args, **kwargs):
            self.acquire()
            return func(*args, **kwargs)
        return wrapper
    
    def get_stats(self) -> dict:
        """Get current rate limiter statistics"""
        with self._lock:
            current_time = time.time()
            cutoff_time = current_time - self.time_window
            
            # Clean old calls
            while self._call_times and self._call_times[0] < cutoff_time:
                self._call_times.popleft()
            
            return {
                "name": self.name,
                "max_calls": self.max_calls,
                "time_window": self.time_window,
                "current_calls": len(self._call_times),
                "available_calls": max(0, self.max_calls - len(self._call_times)),
                "calls_per_minute": self.max_calls / (self.time_window / 60),
            }


class RateLimitedClient:
    """
    Wrapper for API clients with rate limiting
    
    Automatically applies rate limiting to all method calls
    """
    
    def __init__(self, client, rate_limiter: RateLimiter):
        """
        Initialize rate-limited client
        
        Args:
            client: The API client to wrap
            rate_limiter: RateLimiter instance
        """
        self._client = client
        self._rate_limiter = rate_limiter
    
    def __getattr__(self, name):
        """Proxy all method calls through rate limiter"""
        attr = getattr(self._client, name)
        
        if callable(attr):
            def rate_limited_method(*args, **kwargs):
                self._rate_limiter.acquire()
                return attr(*args, **kwargs)
            return rate_limited_method
        else:
            return attr

