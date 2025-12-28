# match_tracker_enhanced.py - Enhanced live match tracking with WebSockets
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
from flask_socketio import emit
from app import socketio
from cache_redis import get_redis_cache, cached_redis

LOG = logging.getLogger("match_tracker_enhanced")

class EnhancedMatchTracker:
    """Enhanced real-time match tracking with fantasy points calculation"""
    
    def __init__(self):
        self.active_matches = {}
        self.user_teams = {}  # user_id -> {player_ids, formation}
        self.cache = get_redis_cache()
        
        # Fantasy points scoring rules (Classic)
        self.scoring_rules = {
            'goal': {'P': 0, 'D': 6, 'C': 5, 'A': 3},
            'assist': 1,
            'yellow_card': -0.5,
            'red_card': -1,
            'penalty_scored': 3,
            'penalty_missed': -3,
            'penalty_saved': 3,
            'own_goal': -2,
            'clean_sheet': {'P': 1, 'D': 1, 'C': 0, 'A': 0},
            'goals_conceded_3+': {'P': -1, 'D': -1, 'C': 0, 'A': 0}
        }
    
    def start_match(self, match_id: str, home_team: str, away_team: str):
        """Start tracking a new match"""
        self.active_matches[match_id] = {
            'id': match_id,
            'home_team': home_team,
            'away_team': away_team,
            'score': {'home': 0, 'away': 0},
            'minute': 0,
            'status': 'live',
            'events': [],
            'player_stats': {},
            'started_at': datetime.now()
        }
        
        LOG.info(f"Started tracking match: {match_id} - {home_team} vs {away_team}")
        
        # Broadcast match start
        socketio.emit('match_started', {
            'match_id': match_id,
            'home_team': home_team,
            'away_team': away_team
        }, namespace='/')
    
    def update_match_event(self, match_id: str, event: Dict):
        """Process a match event and update fantasy points"""
        if match_id not in self.active_matches:
            return
        
        match = self.active_matches[match_id]
        match['events'].append(event)
        
        event_type = event['type']
        player_name = event.get('player')
        player_role = event.get('role', 'C')
        minute = event.get('minute', 0)
        
        # Calculate fantasy points
        points = self.calculate_event_points(event_type, player_role)
        
        # Update player stats
        if player_name not in match['player_stats']:
            match['player_stats'][player_name] = {
                'name': player_name,
                'role': player_role,
                'team': event.get('team'),
                'points': 6.0,  # Base vote
                'events': []
            }
        
        match['player_stats'][player_name]['points'] += points
        match['player_stats'][player_name]['events'].append({
            'type': event_type,
            'minute': minute,
            'points': points
        })
        
        # Update score if goal
        if event_type == 'goal':
            team_side = event.get('team_side', 'home')
            match['score'][team_side] += 1
        
        match['minute'] = minute
        
        # Broadcast update to all connected clients
        socketio.emit('match_update', {
            'match_id': match_id,
            'minute': minute,
            'score': match['score'],
            'event': {
                'type': event_type,
                'player': player_name,
                'minute': minute,
                'points': points
            },
            'player_stats': match['player_stats']
        }, namespace='/')
        
        # Update user-specific fantasy scores
        self.update_user_scores(match_id, match['player_stats'])
        
        LOG.info(f"Match {match_id} - Event: {event_type} by {player_name} ({points} pts)")
    
    def calculate_event_points(self, event_type: str, role: str) -> float:
        """Calculate fantasy points for an event"""
        if event_type == 'goal':
            return self.scoring_rules['goal'].get(role, 3)
        elif event_type == 'assist':
            return self.scoring_rules['assist']
        elif event_type == 'yellow_card':
            return self.scoring_rules['yellow_card']
        elif event_type == 'red_card':
            return self.scoring_rules['red_card']
        elif event_type == 'penalty_scored':
            return self.scoring_rules['penalty_scored']
        elif event_type == 'penalty_missed':
            return self.scoring_rules['penalty_missed']
        elif event_type == 'penalty_saved':
            return self.scoring_rules['penalty_saved']
        elif event_type == 'own_goal':
            return self.scoring_rules['own_goal']
        
        return 0
    
    def update_user_scores(self, match_id: str, player_stats: Dict):
        """Update fantasy scores for all users with players in this match"""
        for user_id, team_info in self.user_teams.items():
            player_ids = team_info.get('player_ids', [])
            
            user_score = 0
            scored_players = []
            
            for player_name, stats in player_stats.items():
                if player_name in player_ids:
                    user_score += stats['points']
                    scored_players.append({
                        'name': player_name,
                        'points': stats['points'],
                        'events': stats['events']
                    })
            
            if scored_players:
                # Emit user-specific update
                socketio.emit('user_match_update', {
                    'match_id': match_id,
                    'total_points': round(user_score, 2),
                    'players': scored_players
                }, room=f'user_{user_id}', namespace='/')
    
    def register_user_team(self, user_id: int, player_ids: List[str], formation: str):
        """Register a user's team for live tracking"""
        self.user_teams[user_id] = {
            'player_ids': player_ids,
            'formation': formation,
            'registered_at': datetime.now()
        }
        LOG.info(f"Registered team for user {user_id}: {len(player_ids)} players")
    
    def get_match_summary(self, match_id: str) -> Optional[Dict]:
        """Get current match summary"""
        if match_id not in self.active_matches:
            return None
        
        match = self.active_matches[match_id]
        
        # Calculate top performers
        top_performers = sorted(
            match['player_stats'].items(),
            key=lambda x: x[1]['points'],
            reverse=True
        )[:5]
        
        return {
            'match_id': match_id,
            'home_team': match['home_team'],
            'away_team': match['away_team'],
            'score': match['score'],
            'minute': match['minute'],
            'status': match['status'],
            'top_performers': [
                {
                    'name': name,
                    'team': stats['team'],
                    'role': stats['role'],
                    'points': stats['points']
                }
                for name, stats in top_performers
            ],
            'total_events': len(match['events'])
        }
    
    def end_match(self, match_id: str):
        """End match tracking and compute final stats"""
        if match_id not in self.active_matches:
            return
        
        match = self.active_matches[match_id]
        match['status'] = 'finished'
        match['ended_at'] = datetime.now()
        
        # Apply end-of-match bonuses (clean sheets, etc.)
        self.apply_end_of_match_bonuses(match)
        
        # Broadcast final stats
        socketio.emit('match_ended', {
            'match_id': match_id,
            'final_score': match['score'],
            'player_stats': match['player_stats'],
            'summary': self.get_match_summary(match_id)
        }, namespace='/')
        
        # Cache final results
        self.cache.set(f"match_result:{match_id}", match, ttl=86400)  # 24 hours
        
        LOG.info(f"Match {match_id} ended: {match['score']}")
    
    def apply_end_of_match_bonuses(self, match: Dict):
        """Apply bonuses for clean sheets, goals conceded, etc."""
        home_goals = match['score']['home']
        away_goals = match['score']['away']
        
        for player_name, stats in match['player_stats'].items():
            role = stats['role']
            team = stats['team']
            
            # Determine if player's team kept clean sheet
            goals_conceded = away_goals if team == match['home_team'] else home_goals
            
            # Clean sheet bonus
            if goals_conceded == 0 and role in ['P', 'D']:
                bonus = self.scoring_rules['clean_sheet'].get(role, 0)
                stats['points'] += bonus
                stats['events'].append({
                    'type': 'clean_sheet',
                    'minute': 90,
                    'points': bonus
                })
            
            # Goals conceded penalty
            elif goals_conceded >= 3 and role in ['P', 'D']:
                penalty = self.scoring_rules['goals_conceded_3+'].get(role, 0)
                stats['points'] += penalty
                stats['events'].append({
                    'type': 'goals_conceded',
                    'minute': 90,
                    'points': penalty
                })
    
    @cached_redis(ttl=60, key_prefix="live_matches")
    def get_active_matches(self) -> List[Dict]:
        """Get all currently active matches"""
        return [
            {
                'match_id': match_id,
                'home_team': match['home_team'],
                'away_team': match['away_team'],
                'score': match['score'],
                'minute': match['minute'],
                'status': match['status']
            }
            for match_id, match in self.active_matches.items()
            if match['status'] == 'live'
        ]

# Global tracker instance
_tracker_instance = None

def get_match_tracker() -> EnhancedMatchTracker:
    """Get or create match tracker singleton"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = EnhancedMatchTracker()
    return _tracker_instance

# SocketIO event handlers
@socketio.on('subscribe_match')
def handle_subscribe_match(data):
    """User subscribes to match updates"""
    match_id = data.get('match_id')
    if match_id:
        from flask import request
        from flask_socketio import join_room
        join_room(f'match_{match_id}')
        LOG.info(f"Client {request.sid} subscribed to match {match_id}")

@socketio.on('unsubscribe_match')
def handle_unsubscribe_match(data):
    """User unsubscribes from match updates"""
    match_id = data.get('match_id')
    if match_id:
        from flask import request
        from flask_socketio import leave_room
        leave_room(f'match_{match_id}')
        LOG.info(f"Client {request.sid} unsubscribed from match {match_id}")
