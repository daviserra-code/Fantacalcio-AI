
# models.py - Database models for authentication and league management
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    profile_image_url = db.Column(db.String(255), nullable=True)
    
    # Pro subscription fields
    pro_expires_at = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # Admin flag
    is_admin = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    leagues = db.relationship('UserLeague', back_populates='user', cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        try:
            result = check_password_hash(self.password_hash, password)
            print(f"Password check for user {self.username}: {'SUCCESS' if result else 'FAILED'}")
            return result
        except Exception as e:
            print(f"Password check error for user {self.username}: {e}")
            return False
    
    @property
    def is_pro(self):
        """Check if user has an active pro subscription"""
        from datetime import datetime
        if hasattr(self, 'subscriptions') and self.subscriptions:
            for subscription in self.subscriptions:
                if (subscription.status == 'active' and 
                    subscription.current_period_end > datetime.utcnow()):
                    return True
        return False

# Keep OAuth table for backward compatibility (optional)
class OAuth(OAuthConsumerMixin, db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    browser_session_key = db.Column(db.String, nullable=False)
    user = db.relationship(User)

    __table_args__ = (UniqueConstraint(
        'user_id',
        'browser_session_key',
        'provider',
        name='uq_user_browser_session_key_provider',
    ),)

# League management models
class UserLeague(db.Model):
    __tablename__ = 'user_leagues'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    league_name = db.Column(db.String(100), nullable=False)
    league_data = db.Column(db.Text)  # JSON stored as text
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    user = db.relationship('User', back_populates='leagues')
    
    __table_args__ = (UniqueConstraint('user_id', 'league_name', name='uq_user_league_name'),)

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # active, canceled, etc.
    current_period_start = db.Column(db.DateTime, nullable=False)
    current_period_end = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    user = db.relationship('User', backref='subscriptions')


# Phase 2C: Enhanced League System Models

class League(db.Model):
    """Main league model for fantasy football competitions"""
    __tablename__ = 'leagues'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)  # Join code
    
    # League settings
    budget = db.Column(db.Integer, default=500)  # Starting budget for participants
    max_players = db.Column(db.Integer, default=25)  # Max roster size
    scoring_type = db.Column(db.String(20), default='classic')  # 'classic' or 'mantra'
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_leagues')
    participants = db.relationship('LeagueParticipant', back_populates='league', cascade='all, delete-orphan')
    matchdays = db.relationship('Matchday', back_populates='league', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<League {self.name} ({self.code})>'
    
    @staticmethod
    def generate_unique_code():
        """Generate a unique 6-character alphanumeric code"""
        import random
        import string
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not League.query.filter_by(code=code).first():
                return code


class LeagueParticipant(db.Model):
    """Participants in a league"""
    __tablename__ = 'league_participants'
    
    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Participant details
    team_name = db.Column(db.String(100), nullable=False)
    budget_used = db.Column(db.Integer, default=0)
    
    # Timestamps
    joined_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    league = db.relationship('League', back_populates='participants')
    user = db.relationship('User', backref='league_participations')
    scores = db.relationship('MatchdayScore', back_populates='participant', cascade='all, delete-orphan')
    
    # Ensure user can only join a league once
    __table_args__ = (UniqueConstraint('league_id', 'user_id', name='uq_league_participant'),)
    
    def __repr__(self):
        return f'<LeagueParticipant {self.team_name} in League {self.league_id}>'


class Matchday(db.Model):
    """Serie A matchdays (giornate) - typically 38 per season"""
    __tablename__ = 'matchdays'
    
    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False)
    matchday_number = db.Column(db.Integer, nullable=False)  # 1-38 for Serie A
    
    # Schedule
    scheduled_date = db.Column(db.Date, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    league = db.relationship('League', back_populates='matchdays')
    scores = db.relationship('MatchdayScore', back_populates='matchday', cascade='all, delete-orphan')
    
    # Ensure matchday number is unique within a league
    __table_args__ = (
        UniqueConstraint('league_id', 'matchday_number', name='uq_league_matchday'),
        db.Index('idx_matchday_league_number', 'league_id', 'matchday_number'),
    )
    
    def __repr__(self):
        return f'<Matchday {self.matchday_number} for League {self.league_id}>'


class MatchdayScore(db.Model):
    """Scores for each participant in each matchday"""
    __tablename__ = 'matchday_scores'
    
    id = db.Column(db.Integer, primary_key=True)
    matchday_id = db.Column(db.Integer, db.ForeignKey('matchdays.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('league_participants.id'), nullable=False)
    
    # Score data
    total_score = db.Column(db.Numeric(5, 2), nullable=True)  # e.g., 68.50
    bonus_points = db.Column(db.Numeric(5, 2), default=0)  # Captain bonus, etc.
    
    # Timestamps
    calculated_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    matchday = db.relationship('Matchday', back_populates='scores')
    participant = db.relationship('LeagueParticipant', back_populates='scores')
    
    # Ensure one score per participant per matchday
    __table_args__ = (
        UniqueConstraint('matchday_id', 'participant_id', name='uq_matchday_participant_score'),
        db.Index('idx_score_matchday_participant', 'matchday_id', 'participant_id'),
    )
    
    def __repr__(self):
        return f'<MatchdayScore {self.total_score} for Participant {self.participant_id} in Matchday {self.matchday_id}>'

