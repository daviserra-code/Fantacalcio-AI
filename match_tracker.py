
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json

class MatchTracker:
    def __init__(self):
        self.live_matches = {}
        self.upcoming_matches = self._generate_sample_fixtures()
        
    def _generate_sample_fixtures(self) -> List[Dict[str, Any]]:
        """Generate sample upcoming fixtures"""
        fixtures = []
        base_date = datetime.now() + timedelta(days=1)
        
        teams = ["Juventus", "Inter", "Milan", "Napoli", "Roma", "Lazio", "Atalanta", "Fiorentina"]
        
        for i in range(0, len(teams), 2):
            if i + 1 < len(teams):
                fixtures.append({
                    'match_id': f"match_{i//2 + 1}",
                    'home_team': teams[i],
                    'away_team': teams[i + 1],
                    'date': (base_date + timedelta(hours=i*2)).isoformat(),
                    'difficulty_home': self._calculate_difficulty(teams[i], teams[i + 1]),
                    'difficulty_away': self._calculate_difficulty(teams[i + 1], teams[i])
                })
        
        return fixtures
    
    def _calculate_difficulty(self, team: str, opponent: str) -> int:
        """Calculate fixture difficulty (1-5 scale)"""
        strong_teams = ["Juventus", "Inter", "Milan", "Napoli"]
        
        if opponent in strong_teams and team not in strong_teams:
            return 4
        elif opponent in strong_teams and team in strong_teams:
            return 3
        elif team in strong_teams and opponent not in strong_teams:
            return 2
        else:
            return 3
    
    def get_player_fixture_analysis(self, player_name: str, team: str) -> Dict[str, Any]:
        """Get fixture analysis for a specific player"""
        team_fixtures = [f for f in self.upcoming_matches if f['home_team'] == team or f['away_team'] == team]
        
        if not team_fixtures:
            return {'error': 'No upcoming fixtures found'}
        
        next_fixture = team_fixtures[0]
        is_home = next_fixture['home_team'] == team
        difficulty = next_fixture['difficulty_home'] if is_home else next_fixture['difficulty_away']
        
        return {
            'player': player_name,
            'team': team,
            'next_opponent': next_fixture['away_team'] if is_home else next_fixture['home_team'],
            'is_home': is_home,
            'match_date': next_fixture['date'],
            'difficulty': difficulty,
            'recommendation': self._get_fixture_recommendation(difficulty, is_home),
            'upcoming_fixtures': team_fixtures[:5]
        }
    
    def _get_fixture_recommendation(self, difficulty: int, is_home: bool) -> str:
        """Get recommendation based on fixture difficulty"""
        home_bonus = " (vantaggio casa)" if is_home else " (trasferta)"
        
        if difficulty <= 2:
            return f"Ottima giornata per schierarlo{home_bonus}"
        elif difficulty == 3:
            return f"Partita equilibrata{home_bonus}"
        else:
            return f"Partita difficile, valuta alternative{home_bonus}"
    
    def get_gameweek_recommendations(self) -> List[Dict[str, Any]]:
        """Get recommendations for the upcoming gameweek"""
        recommendations = []
        
        for fixture in self.upcoming_matches:
            recommendations.append({
                'match': f"{fixture['home_team']} vs {fixture['away_team']}",
                'home_difficulty': fixture['difficulty_home'],
                'away_difficulty': fixture['difficulty_away'],
                'key_players_home': self._get_key_players(fixture['home_team']),
                'key_players_away': self._get_key_players(fixture['away_team']),
                'betting_tips': self._generate_betting_tips(fixture)
            })
        
        return recommendations
    
    def _get_key_players(self, team: str) -> List[str]:
        """Get key players for a team"""
        from fantacalcio_data import SAMPLE_PLAYERS
        
        team_players = [p for p in SAMPLE_PLAYERS if p.team == team]
        return [p.name for p in sorted(team_players, key=lambda x: x.fantamedia, reverse=True)[:3]]
    
    def _generate_betting_tips(self, fixture: Dict[str, Any]) -> List[str]:
        """Generate fantasy betting tips for a fixture"""
        tips = []
        
        if fixture['difficulty_home'] <= 2:
            tips.append(f"Punta sui giocatori del {fixture['home_team']}")
        
        if fixture['difficulty_away'] <= 2:
            tips.append(f"Punta sui giocatori del {fixture['away_team']}")
        
        if fixture['difficulty_home'] == fixture['difficulty_away']:
            tips.append("Partita equilibrata - punta sui rigoristi e sui clean sheet")
        
        return tips

