
import time
import logging
from typing import Dict, Optional
from collections import defaultdict, deque
import os

LOG = logging.getLogger("rate_limiter")

class RateLimiter:
    """Rate limiter to protect against API abuse in deployed environment"""
    
    def __init__(self, max_requests: int = 999999, time_window: int = 3600):
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
            os.getenv("ENVIRONMENT") == "production",
            # Additional deployment detection
            os.getenv("HOSTNAME", "").startswith("runner-"),
            "replit.dev" in os.getenv("REPLIT_URL", ""),
            ".repl.co" in os.getenv("REPLIT_URL", ""),
            os.path.exists("/.replit_deployment")
        ]
        is_deployed = any(deployment_indicators)
        LOG.info(f"Deployment detection: {dict(zip(['REPLIT_DEPLOYMENT', 'REPL_DEPLOYMENT', 'fantacalcioai.it', 'ENVIRONMENT', 'HOSTNAME', 'replit.dev', 'repl.co', 'deployment_file'], [os.getenv('REPLIT_DEPLOYMENT'), os.getenv('REPL_DEPLOYMENT'), 'fantacalcioai.it' in os.getenv('REPLIT_URL', ''), os.getenv('ENVIRONMENT'), os.getenv('HOSTNAME', '').startswith('runner-'), 'replit.dev' in os.getenv('REPLIT_URL', ''), '.repl.co' in os.getenv('REPLIT_URL', ''), os.path.exists('/.replit_deployment')]))} -> {is_deployed}")
        return is_deployed
    
    def _get_client_key(self, request) -> str:
        """Generate a unique key for the client based on IP address"""
        # Try to get real IP from headers (in case of proxy/load balancer)
        real_ip = None
        
        # Check various headers for the real IP
        forwarded_for = request.headers.get('X-Forwarded-For', '')
        if forwarded_for:
            # Take the first IP in the chain (original client)
            real_ip = forwarded_for.split(',')[0].strip()
        
        if not real_ip:
            real_ip = request.headers.get('X-Real-IP', '')
        
        if not real_ip:
            real_ip = request.environ.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        
        if not real_ip:
            real_ip = request.environ.get('REMOTE_ADDR', '')
        
        if not real_ip:
            real_ip = request.remote_addr
        
        # Clean up the IP address
        if real_ip:
            real_ip = real_ip.strip()
            # Remove port if present (e.g., "192.168.1.1:8080" -> "192.168.1.1")
            if ':' in real_ip and not real_ip.startswith('['):  # Not IPv6
                real_ip = real_ip.split(':')[0]
        
        # In development, use a default key to avoid rate limiting
        if not self.is_deployed:
            return "dev_environment"
        
        # Use IP as the key, fallback to 'unknown' if we can't determine it
        client_key = real_ip or 'unknown'
        
        LOG.debug(f"Client key determined: {client_key} from request headers")
        return client_key
    
    def _cleanup_old_requests(self, client_key: str) -> None:
        """Remove requests older than time window"""
        current_time = time.time()
        client_requests = self.requests[client_key]
        
        while client_requests and current_time - client_requests[0] > self.time_window:
            client_requests.popleft()
    
    def is_allowed(self, request) -> bool:
        """Check if request is allowed based on rate limits"""
        # Rate limiting completely disabled
        LOG.debug("Rate limiting disabled for all environments")
        return True
    
    def get_remaining_requests(self, request) -> int:
        """Get number of remaining requests for client"""
        return 999999  # Unlimited for all environments
    
    def get_reset_time(self, request) -> Optional[int]:
        """Get timestamp when rate limit resets"""
        return None  # No rate limits, so no reset time
    
    def get_status(self) -> dict:
        """Get current rate limiter status"""
        return {
            "is_deployed": self.is_deployed,
            "max_requests": self.max_requests,
            "time_window": self.time_window,
            "active_clients": len(self.requests),
            "total_requests": sum(len(client_requests) for client_requests in self.requests.values())
        }
