# live_matches_service.py
"""
Service to fetch real live Serie A matches from football-data.org API
"""
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from cache_manager import CacheManager

LOG = logging.getLogger("live_matches_service")

class LiveMatchesService:
    """Fetch real-time Serie A match data"""
    
    def __init__(self):
        # football-data.org API (free tier: 10 requests/minute)
        self.api_key = os.getenv("FOOTBALL_DATA_API_KEY", "")
        self.base_url = "https://api.football-data.org/v4"
        self.serie_a_id = "SA"  # Serie A competition code
        self.cache = CacheManager()
        
    def get_todays_matches(self) -> List[Dict]:
        """Get all Serie A matches happening today"""
        cache_key = f"serie_a_matches_{datetime.now().date()}"
        
        # Check cache first (5 minute TTL)
        cached = self.cache.get(cache_key)
        if cached:
            return cached
            
        try:
            headers = {"X-Auth-Token": self.api_key} if self.api_key else {}
            
            # Get matches for today
            today = datetime.now().date()
            url = f"{self.base_url}/competitions/{self.serie_a_id}/matches"
            params = {
                "dateFrom": today.isoformat(),
                "dateTo": today.isoformat()
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                matches = data.get("matches", [])
                
                # Transform to our format
                formatted_matches = []
                for match in matches:
                    # Only include matches that are currently live or about to start
                    status = match.get("status")
                    if status in ["IN_PLAY", "PAUSED", "SCHEDULED"]:
                        formatted = self._format_match(match)
                        if formatted:
                            formatted_matches.append(formatted)
                
                # Cache for 5 minutes
                self.cache.set(cache_key, formatted_matches, ttl=300)
                return formatted_matches
                
            elif response.status_code == 429:
                LOG.warning("API rate limit exceeded")
                return []
            else:
                LOG.error(f"API error: {response.status_code}")
                return []
                
        except Exception as e:
            LOG.error(f"Error fetching matches: {e}")
            return []
    
    def get_live_matches(self) -> List[Dict]:
        """Get only currently live Serie A matches"""
        all_matches = self.get_todays_matches()
        return [m for m in all_matches if m['status'] in ['IN_PLAY', 'PAUSED']]
    
    def get_match_details(self, match_id: str) -> Optional[Dict]:
        """Get detailed information about a specific match"""
        cache_key = f"match_details_{match_id}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
            
        try:
            headers = {"X-Auth-Token": self.api_key} if self.api_key else {}
            url = f"{self.base_url}/matches/{match_id}"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                match = response.json()
                formatted = self._format_match(match)
                
                # Cache for 1 minute (live data changes frequently)
                self.cache.set(cache_key, formatted, ttl=60)
                return formatted
            else:
                LOG.error(f"Error fetching match {match_id}: {response.status_code}")
                return None
                
        except Exception as e:
            LOG.error(f"Error fetching match details: {e}")
            return None
    
    def _format_match(self, match: Dict) -> Dict:
        """Transform API match data to our format"""
        try:
            home_team = match.get("homeTeam", {})
            away_team = match.get("awayTeam", {})
            score = match.get("score", {})
            fulltime = score.get("fullTime", {})
            
            # Map status
            status_map = {
                "IN_PLAY": "live",
                "PAUSED": "live",
                "SCHEDULED": "scheduled",
                "FINISHED": "finished",
                "POSTPONED": "postponed",
                "CANCELLED": "cancelled"
            }
            
            return {
                "match_id": str(match.get("id")),
                "home_team": home_team.get("name", home_team.get("shortName", "Home")),
                "away_team": away_team.get("name", away_team.get("shortName", "Away")),
                "home_team_short": home_team.get("tla", "HOM"),
                "away_team_short": away_team.get("tla", "AWA"),
                "score": {
                    "home": fulltime.get("home") or 0,
                    "away": fulltime.get("away") or 0
                },
                "status": status_map.get(match.get("status"), "unknown"),
                "minute": match.get("minute"),
                "kickoff": match.get("utcDate"),
                "venue": match.get("venue"),
                "competition": "Serie A"
            }
        except Exception as e:
            LOG.error(f"Error formatting match: {e}")
            return None
    
    def sync_to_tracker(self, tracker):
        """Sync live matches to the enhanced match tracker"""
        live_matches = self.get_live_matches()
        
        for match in live_matches:
            match_id = match['match_id']
            
            # Start tracking if not already tracked
            if match_id not in tracker.active_matches:
                tracker.start_match(
                    match_id=match_id,
                    home_team=match['home_team'],
                    away_team=match['away_team']
                )
                LOG.info(f"Started tracking match {match_id}: {match['home_team']} vs {match['away_team']}")
            else:
                # Update existing match
                existing = tracker.active_matches[match_id]
                existing['score'] = match['score']
                existing['minute'] = match.get('minute', existing.get('minute', 0))
                existing['status'] = match['status']
        
        return len(live_matches)


# Singleton instance
_service_instance = None

def get_live_matches_service() -> LiveMatchesService:
    """Get or create live matches service singleton"""
    global _service_instance
    if _service_instance is None:
        _service_instance = LiveMatchesService()
    return _service_instance
