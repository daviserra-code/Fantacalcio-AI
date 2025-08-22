
import time
import logging
from typing import Dict, Optional
from collections import defaultdict, deque
import os

LOG = logging.getLogger("rate_limiter")

class RateLimiter:
    """Rate limiter to protect against API abuse in deployed environment"""
    
    def __init__(self, max_requests: int = 10, time_window: int = 3600):
        self.max_requests = max_requests  # 10 requests
        self.time_window = time_window     # 3600 seconds (1 hour)
        self.requests: Dict[str, deque] = defaultdict(deque)
        self.is_deployed = self._is_deployed_environment()
        
        LOG.info(f"RateLimiter initialized: max_requests={max_requests}, window={time_window}s, deployed={self.is_deployed}")
    
    def _is_deployed_environment(self) -> bool:
        """Detect if running in deployed environment"""
        # Check for deployment indicators
        deployment_indicators = [
            os.getenv("REPLIT_DEPLOYMENT") == "1",
            os.getenv("REPL_DEPLOYMENT") == "1", 
            "fantacalcioai.it" in os.getenv("REPLIT_URL", ""),
            os.getenv("ENVIRONMENT") == "production"
        ]
        return any(deployment_indicators)
    
    def _get_client_key(self, request) -> str:
        """Generate a unique key for the client"""
        # Try to get real IP from headers (in case of proxy/load balancer)
        real_ip = (
            request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or
            request.headers.get('X-Real-IP', '') or
            request.environ.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or
            request.remote_addr or
            'unknown'
        )
        
        # In development, use a default key to avoid rate limiting
        if not self.is_deployed:
            return "dev_environment"
            
        return real_ip
    
    def _cleanup_old_requests(self, client_key: str) -> None:
        """Remove requests older than time window"""
        current_time = time.time()
        client_requests = self.requests[client_key]
        
        while client_requests and current_time - client_requests[0] > self.time_window:
            client_requests.popleft()
    
    def is_allowed(self, request) -> bool:
        """Check if request is allowed based on rate limits"""
        # Skip rate limiting in development
        if not self.is_deployed:
            return True
            
        client_key = self._get_client_key(request)
        current_time = time.time()
        
        # Clean old requests
        self._cleanup_old_requests(client_key)
        
        # Check if under limit
        client_requests = self.requests[client_key]
        if len(client_requests) >= self.max_requests:
            LOG.warning(f"Rate limit exceeded for client {client_key}: {len(client_requests)} requests in window")
            return False
        
        # Add current request
        client_requests.append(current_time)
        LOG.debug(f"Request allowed for client {client_key}: {len(client_requests)}/{self.max_requests}")
        return True
    
    def get_remaining_requests(self, request) -> int:
        """Get number of remaining requests for client"""
        if not self.is_deployed:
            return self.max_requests  # Unlimited in dev
            
        client_key = self._get_client_key(request)
        self._cleanup_old_requests(client_key)
        
        used_requests = len(self.requests[client_key])
        return max(0, self.max_requests - used_requests)
    
    def get_reset_time(self, request) -> Optional[int]:
        """Get timestamp when rate limit resets"""
        if not self.is_deployed:
            return None
            
        client_key = self._get_client_key(request)
        client_requests = self.requests[client_key]
        
        if not client_requests:
            return None
            
        return int(client_requests[0] + self.time_window)
