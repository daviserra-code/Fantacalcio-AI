# live_matches_service.py
"""
Service to fetch real live Serie A matches from API-Football (RapidAPI)
"""
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from cache_manager import CacheManager

LOG = logging.getLogger("live_matches_service")

class LiveMatchesService:
    """Fetch real-time Serie A match data from API-Football"""
    
    def __init__(self):
        # API-Football via RapidAPI (free tier: 100 requests/day)
        self.api_key = os.getenv("RAPIDAPI_KEY", "")
        self.base_url = "https://api-football-v1.p.rapidapi.com/v3"
        self.serie_a_id = "135"  # Serie A league ID in API-Football
        self.cache = CacheManager()
        
    def get_todays_matches(self) -> List[Dict]:
        """Get all Serie A matches happening today"""
        cache_key = f"serie_a_matches_{datetime.now().date()}"
        
        # Check cache first (5 minute TTL)
        cached = self.cache.get(cache_key)
        if cached:
            return cached
            
        try:
            if not self.api_key:
                LOG.error("RAPIDAPI_KEY not set")
                return []
                
            headers = {
                "X-RapidAPI-Key": self.api_key,
                "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
            }
            
            # Get matches for today
            today = datetime.now().date()
            url = f"{self.base_url}/fixtures"
            params = {
                "league": self.serie_a_id,
                "season": datetime.now().year,
                "date": today.isoformat()
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get("response", [])
                
                # Transform to our format
                formatted_matches = []
                for fixture in fixtures:
                    formatted = self._format_match(fixture)
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
        return [m for m in all_matches if m['status'] in ['IN_PLAY', 'PAUSED', 'LIVE', '1H', '2H', 'HT']]
    
    def get_match_details(self, match_id: str) -> Optional[Dict]:
        """Get detailed information about a specific match"""
        cache_key = f"match_details_{match_id}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
            
        try:
            if not self.api_key:
                return None
                
            headers = {
                "X-RapidAPI-Key": self.api_key,
                "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
            }
            url = f"{self.base_url}/fixtures"
            params = {"id": match_id}
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get("response", [])
                if fixtures:
                    formatted = self._format_match(fixtures[0])
                    # Cache for 1 minute (live data changes frequently)
                    self.cache.set(cache_key, formatted, ttl=60)
                    return formatted
            else:
                LOG.error(f"Error fetching match {match_id}: {response.status_code}")
                return None
                
        except Exception as e:
            LOG.error(f"Error fetching match details: {e}")
            return None
    
    def _format_match(self, fixture: Dict) -> Dict:
        """Transform API-Football fixture data to our format"""
        try:
            teams = fixture.get("teams", {})
            fixture_info = fixture.get("fixture", {})
            goals = fixture.get("goals", {})
            league = fixture.get("league", {})
            
            home_team = teams.get("home", {})
            away_team = teams.get("away", {})
            
            # Map status - API-Football uses different status codes
            status = fixture_info.get("status", {}).get("short", "NS")
            status_map = {
                "1H": "IN_PLAY",
                "HT": "PAUSED", 
                "2H": "IN_PLAY",
                "ET": "IN_PLAY",
                "P": "PAUSED",
                "LIVE": "IN_PLAY",
                "FT": "FINISHED",
                "AET": "FINISHED",
                "PEN": "FINISHED",
                "PST": "POSTPONED",
                "CANC": "CANCELLED",
                "ABD": "CANCELLED",
                "NS": "SCHEDULED",
                "TBD": "SCHEDULED"
            }
            
            mapped_status = status_map.get(status, "SCHEDULED")
            
            return {
                "match_id": str(fixture_info.get("id")),
                "home_team": home_team.get("name", "Home"),
                "away_team": away_team.get("name", "Away"),
                "home_team_short": home_team.get("name", "HOM")[:3].upper(),
                "away_team_short": away_team.get("name", "AWA")[:3].upper(),
                "score": {
                    "home": goals.get("home") or 0,
                    "away": goals.get("away") or 0
                },
                "status": mapped_status,
                "minute": fixture_info.get("status", {}).get("elapsed"),
                "kickoff": fixture_info.get("date"),
                "venue": fixture_info.get("venue", {}).get("name"),
                "competition": league.get("name", "Serie A")
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
