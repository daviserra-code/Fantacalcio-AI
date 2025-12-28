# cost_monitor.py - OpenAI cost tracking and alerts
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import redis

LOG = logging.getLogger("cost_monitor")

@dataclass
class APIUsage:
    """Single API call usage record"""
    timestamp: str
    user_id: Optional[int]
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    query_type: str
    cached: bool = False

class CostMonitor:
    """
    Track OpenAI API costs and usage patterns
    Provides alerts and optimization recommendations
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.usage_key = "api_usage:"
        self.daily_stats_key = "api_stats:daily:"
        self.monthly_stats_key = "api_stats:monthly"
        
        # Pricing (per 1M tokens)
        self.pricing = {
            'gpt-4o-mini': {
                'input': 0.150,
                'output': 0.600
            },
            'gpt-4o': {
                'input': 5.00,
                'output': 15.00
            },
            'gpt-4-turbo': {
                'input': 10.00,
                'output': 30.00
            }
        }
        
        # Cost alert thresholds
        self.thresholds = {
            'daily_warning': 10.00,   # $10/day
            'daily_critical': 20.00,  # $20/day
            'monthly_warning': 200.00,
            'monthly_critical': 500.00
        }
    
    def track_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_id: Optional[int] = None,
        query_type: str = 'general',
        cached: bool = False
    ):
        """
        Track API usage and calculate cost
        
        Args:
            model: Model name (gpt-4o-mini, etc.)
            input_tokens: Input token count
            output_tokens: Output token count
            user_id: User ID (if authenticated)
            query_type: Type of query
            cached: Whether response was cached
        """
        try:
            # Calculate cost
            pricing = self.pricing.get(model, self.pricing['gpt-4o-mini'])
            cost = (
                (input_tokens / 1_000_000 * pricing['input']) +
                (output_tokens / 1_000_000 * pricing['output'])
            )
            
            # Create usage record
            usage = APIUsage(
                timestamp=datetime.utcnow().isoformat(),
                user_id=user_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                query_type=query_type,
                cached=cached
            )
            
            # Store in Redis
            self._store_usage(usage)
            
            # Update daily/monthly stats
            self._update_stats(usage)
            
            # Check thresholds
            self._check_thresholds()
            
            LOG.info(f"💰 API Usage tracked: {model}, ${cost:.4f}, {input_tokens+output_tokens} tokens")
            
        except Exception as e:
            LOG.error(f"Cost tracking error: {e}")
    
    def _store_usage(self, usage: APIUsage):
        """Store individual usage record"""
        today = datetime.utcnow().strftime('%Y-%m-%d')
        key = f"{self.usage_key}{today}"
        
        # Add to list (keep for 30 days)
        self.redis.rpush(key, json.dumps(asdict(usage)))
        self.redis.expire(key, 30 * 24 * 3600)
    
    def _update_stats(self, usage: APIUsage):
        """Update aggregate statistics"""
        today = datetime.utcnow().strftime('%Y-%m-%d')
        month = datetime.utcnow().strftime('%Y-%m')
        
        # Daily stats
        daily_key = f"{self.daily_stats_key}{today}"
        self.redis.hincrby(daily_key, 'total_requests', 1)
        self.redis.hincrbyfloat(daily_key, 'total_cost', usage.cost)
        self.redis.hincrby(daily_key, 'total_tokens', usage.input_tokens + usage.output_tokens)
        
        if usage.cached:
            self.redis.hincrby(daily_key, 'cached_requests', 1)
        
        self.redis.expire(daily_key, 30 * 24 * 3600)
        
        # Monthly stats
        self.redis.hincrby(self.monthly_stats_key, f'{month}:requests', 1)
        self.redis.hincrbyfloat(self.monthly_stats_key, f'{month}:cost', usage.cost)
    
    def get_daily_stats(self, date: Optional[str] = None) -> Dict:
        """Get statistics for a specific day"""
        if not date:
            date = datetime.utcnow().strftime('%Y-%m-%d')
        
        key = f"{self.daily_stats_key}{date}"
        
        try:
            stats = self.redis.hgetall(key)
            
            if not stats:
                return {
                    'date': date,
                    'total_requests': 0,
                    'cached_requests': 0,
                    'total_cost': 0.0,
                    'total_tokens': 0,
                    'cache_rate': 0.0
                }
            
            total_requests = int(stats.get(b'total_requests', 0))
            cached = int(stats.get(b'cached_requests', 0))
            
            return {
                'date': date,
                'total_requests': total_requests,
                'cached_requests': cached,
                'total_cost': float(stats.get(b'total_cost', 0)),
                'total_tokens': int(stats.get(b'total_tokens', 0)),
                'cache_rate': round((cached / total_requests * 100) if total_requests > 0 else 0, 2)
            }
        except Exception as e:
            LOG.error(f"Error getting daily stats: {e}")
            return {}
    
    def get_monthly_stats(self, month: Optional[str] = None) -> Dict:
        """Get statistics for a specific month"""
        if not month:
            month = datetime.utcnow().strftime('%Y-%m')
        
        try:
            stats = self.redis.hgetall(self.monthly_stats_key)
            
            requests_key = f'{month}:requests'.encode()
            cost_key = f'{month}:cost'.encode()
            
            return {
                'month': month,
                'total_requests': int(stats.get(requests_key, 0)),
                'total_cost': float(stats.get(cost_key, 0)),
                'projected_monthly': self._project_monthly_cost(month)
            }
        except Exception as e:
            LOG.error(f"Error getting monthly stats: {e}")
            return {}
    
    def _project_monthly_cost(self, month: str) -> float:
        """Project monthly cost based on current usage"""
        try:
            # Get current month stats
            stats = self.get_monthly_stats(month)
            
            if not stats or stats['total_requests'] == 0:
                return 0.0
            
            # Calculate days elapsed this month
            now = datetime.utcnow()
            days_elapsed = now.day
            days_in_month = 30  # Approximate
            
            # Project based on current rate
            daily_avg = stats['total_cost'] / days_elapsed
            projected = daily_avg * days_in_month
            
            return round(projected, 2)
        except:
            return 0.0
    
    def _check_thresholds(self):
        """Check if cost thresholds are exceeded"""
        try:
            # Check daily
            daily = self.get_daily_stats()
            daily_cost = daily.get('total_cost', 0)
            
            if daily_cost >= self.thresholds['daily_critical']:
                LOG.error(f"🚨 CRITICAL: Daily cost ${daily_cost:.2f} >= ${self.thresholds['daily_critical']}")
            elif daily_cost >= self.thresholds['daily_warning']:
                LOG.warning(f"⚠️  WARNING: Daily cost ${daily_cost:.2f} >= ${self.thresholds['daily_warning']}")
            
            # Check monthly
            monthly = self.get_monthly_stats()
            monthly_cost = monthly.get('total_cost', 0)
            projected = monthly.get('projected_monthly', 0)
            
            if projected >= self.thresholds['monthly_critical']:
                LOG.error(f"🚨 CRITICAL: Projected monthly cost ${projected:.2f} >= ${self.thresholds['monthly_critical']}")
            elif projected >= self.thresholds['monthly_warning']:
                LOG.warning(f"⚠️  WARNING: Projected monthly cost ${projected:.2f} >= ${self.thresholds['monthly_warning']}")
                
        except Exception as e:
            LOG.error(f"Threshold check error: {e}")
    
    def get_cost_report(self) -> Dict:
        """Generate comprehensive cost report"""
        today = self.get_daily_stats()
        monthly = self.get_monthly_stats()
        
        # Calculate savings from cache
        cache_hits = today.get('cached_requests', 0)
        avg_cost_per_request = 0.0004  # ~$0.0004 per request
        estimated_savings = cache_hits * avg_cost_per_request
        
        return {
            'today': today,
            'this_month': monthly,
            'cache_savings': {
                'requests_saved': cache_hits,
                'cost_saved': round(estimated_savings, 2),
                'cache_rate': today.get('cache_rate', 0)
            },
            'recommendations': self._get_recommendations(today, monthly)
        }
    
    def _get_recommendations(self, daily: Dict, monthly: Dict) -> List[str]:
        """Generate cost optimization recommendations"""
        recommendations = []
        
        cache_rate = daily.get('cache_rate', 0)
        if cache_rate < 50:
            recommendations.append(
                f"📊 Cache hit rate is {cache_rate}% - Consider increasing cache TTL or improving query normalization"
            )
        
        projected = monthly.get('projected_monthly', 0)
        if projected > 100:
            recommendations.append(
                f"💰 Projected monthly cost ${projected:.2f} - Consider implementing local LLM for free tier users"
            )
        
        daily_requests = daily.get('total_requests', 0)
        if daily_requests > 1000:
            recommendations.append(
                "🔄 High request volume - Implement rate limiting per user or hybrid LLM approach"
            )
        
        if not recommendations:
            recommendations.append("✅ Cost optimization looks good!")
        
        return recommendations
