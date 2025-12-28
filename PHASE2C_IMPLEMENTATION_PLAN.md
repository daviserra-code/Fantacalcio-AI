# Phase 2C Implementation Plan: Enhanced League System

## 📋 Overview
**Priority**: 1 (High)  
**Status**: Ready to Start  
**Previous Phase**: Phase 2B (Player Comparison Tool) ✅ Complete

## 🎯 Objectives
Implement a comprehensive league management system that allows users to:
1. Create and manage multiple fantasy leagues
2. Invite participants to leagues
3. Configure league rules (budget, roster limits, scoring system)
4. Track matchdays and schedules
5. Calculate weekly scores automatically

## 🏗️ Architecture

### Database Schema
```sql
-- Leagues table (already exists in migrations)
CREATE TABLE leagues (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    owner_id INTEGER REFERENCES users(id),
    code VARCHAR(20) UNIQUE NOT NULL,  -- Join code
    budget INTEGER DEFAULT 500,         -- Starting budget
    max_players INTEGER DEFAULT 25,     -- Max roster size
    scoring_type VARCHAR(20) DEFAULT 'classic',  -- 'classic' or 'mantra'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- League participants
CREATE TABLE league_participants (
    id SERIAL PRIMARY KEY,
    league_id INTEGER REFERENCES leagues(id),
    user_id INTEGER REFERENCES users(id),
    team_name VARCHAR(100),
    budget_used INTEGER DEFAULT 0,
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(league_id, user_id)
);

-- Matchdays schedule
CREATE TABLE matchdays (
    id SERIAL PRIMARY KEY,
    league_id INTEGER REFERENCES leagues(id),
    matchday_number INTEGER NOT NULL,
    scheduled_date DATE,
    is_completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(league_id, matchday_number)
);

-- Weekly scores
CREATE TABLE matchday_scores (
    id SERIAL PRIMARY KEY,
    matchday_id INTEGER REFERENCES matchdays(id),
    participant_id INTEGER REFERENCES league_participants(id),
    total_score DECIMAL(5,2),
    bonus_points DECIMAL(5,2) DEFAULT 0,
    calculated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(matchday_id, participant_id)
);
```

### API Endpoints

#### League Management
- `POST /api/leagues/create` - Create new league
- `GET /api/leagues` - List user's leagues
- `GET /api/leagues/<id>` - Get league details
- `PUT /api/leagues/<id>` - Update league settings (owner only)
- `DELETE /api/leagues/<id>` - Delete league (owner only)
- `POST /api/leagues/<id>/join` - Join league with code
- `POST /api/leagues/<id>/leave` - Leave league

#### Participants
- `GET /api/leagues/<id>/participants` - List participants
- `PUT /api/leagues/<id>/participants/<user_id>` - Update participant (team name, etc.)
- `DELETE /api/leagues/<id>/participants/<user_id>` - Remove participant (owner only)

#### Matchdays
- `GET /api/leagues/<id>/matchdays` - List matchdays
- `POST /api/leagues/<id>/matchdays` - Create matchday schedule
- `GET /api/matchdays/<id>/scores` - Get scores for matchday
- `POST /api/matchdays/<id>/calculate` - Calculate scores (admin/owner)

### Frontend Pages

#### 1. League List (`/leagues`)
**Components**:
- My Leagues section
- "Create League" button
- "Join League" button with code input
- League cards showing:
  - League name
  - Number of participants
  - Next matchday
  - Your current rank

#### 2. League Detail (`/leagues/<id>`)
**Tabs**:
- **Overview**: League info, rules, join code
- **Participants**: List of teams with budget used
- **Matchdays**: Schedule with scores
- **Settings**: League configuration (owner only)

#### 3. Matchday View (`/leagues/<id>/matchdays/<num>`)
**Features**:
- Date and matchday number
- Scores table with:
  - Team name
  - Formation
  - Player points breakdown
  - Total score
  - Rank for the week
- Player performance highlights

## 📝 Implementation Steps

### Step 1: Database Migrations ✅
- Tables already exist from `alembic_version`
- Verify schema with existing models
- Add indexes for performance

### Step 2: Backend Models
Create/update SQLAlchemy models:
- `League` model with relationships
- `LeagueParticipant` model
- `Matchday` model
- `MatchdayScore` model

### Step 3: League CRUD Operations
Implement in `routes.py`:
```python
@app.route('/api/leagues', methods=['GET'])
@login_required
def get_user_leagues():
    # Return leagues where user is owner or participant
    pass

@app.route('/api/leagues/create', methods=['POST'])
@login_required
def create_league():
    # Generate unique join code
    # Create league with user as owner
    pass

@app.route('/api/leagues/<int:league_id>/join', methods=['POST'])
@login_required
def join_league(league_id):
    # Validate join code
    # Add user as participant
    pass
```

### Step 4: Matchday Management
```python
@app.route('/api/leagues/<int:league_id>/matchdays', methods=['POST'])
@login_required
def create_matchdays(league_id):
    # Create 38 matchdays for Serie A season
    # Set scheduled dates (weekly)
    pass

@app.route('/api/matchdays/<int:matchday_id>/calculate', methods=['POST'])
@login_required
def calculate_matchday_scores(matchday_id):
    # Get all participants' rosters
    # Calculate scores based on actual player performances
    # Store in matchday_scores table
    pass
```

### Step 5: Frontend - League List Page
Create `templates/leagues.html`:
- Bootstrap cards for leagues
- Modal for "Create League"
- Modal for "Join League"
- Dark mode compatible

### Step 6: Frontend - League Detail Page
Create `templates/league_detail.html`:
- Tab navigation (Overview, Participants, Matchdays, Settings)
- Participants table with budget tracking
- Matchdays calendar view
- Settings form for league owner

### Step 7: Frontend - Matchday Scores Page
Create `templates/matchday_scores.html`:
- Scores table with player breakdowns
- Charts showing top performers
- Comparison with league average

### Step 8: Integration with Dashboard
Update `templates/dashboard.html`:
- Add "My Leagues" quick access card
- Show upcoming matchdays
- Display current rankings

## 🎨 UI/UX Considerations

### Design Patterns
1. **League Cards**: Gradient backgrounds matching team colors
2. **Join Code**: Prominently displayed, easy to copy
3. **Participant Avatars**: Profile images in circles
4. **Score Tables**: Sortable columns, highlight top 3
5. **Matchday Calendar**: Visual schedule with status indicators

### Dark Mode
- All components must support dark theme
- Use CSS variables from existing pages
- Match players_search.html and players_compare.html styling

### Mobile Responsiveness
- Stack league cards vertically on mobile
- Horizontal scroll for wide score tables
- Bottom navigation for league detail tabs

## 🔧 Technical Requirements

### Dependencies
- Flask-Login (already installed)
- SQLAlchemy relationships
- Flask-Migrate for schema updates

### Validation Rules
1. **League Name**: 3-100 characters, required
2. **Budget**: 100-1000, default 500
3. **Max Players**: 11-30, default 25
4. **Join Code**: 6-character alphanumeric, unique
5. **Team Name**: 3-50 characters per participant

### Error Handling
- League not found → 404
- Insufficient permissions → 403
- Invalid join code → 400 with message
- Budget exceeded → 400 with details

## 📊 Testing Strategy

### Manual Testing
1. Create league as user A
2. Join league as user B with code
3. Update league settings (owner only)
4. Create matchday schedule
5. Calculate scores with mock data
6. Verify rankings update correctly
7. Test leave/remove participant flows

### Edge Cases
- User tries to join already-joined league
- Owner tries to delete league with active matchdays
- Non-owner tries to change settings
- Invalid or expired join codes
- Budget calculations with transfers

## 🚀 Deployment Checklist

### Pre-deployment
- [ ] Run database migrations
- [ ] Test all API endpoints
- [ ] Verify dark mode on all pages
- [ ] Mobile responsiveness check
- [ ] Error handling validation

### Post-deployment
- [ ] Monitor database performance
- [ ] Check logs for errors
- [ ] User feedback collection
- [ ] Performance metrics

## 📈 Success Metrics
1. Users can create leagues successfully
2. Join code system works reliably
3. Matchday scores calculate correctly
4. Page load times < 2 seconds
5. No SQL injection vulnerabilities
6. Mobile usage > 30% of total

## 🔄 Future Enhancements (Phase 3)
- Real-time matchday updates via WebSocket
- League chat/messaging
- Transfer market between participants
- Historical statistics and trends
- Export league data to CSV/Excel
- Custom scoring rules builder

---

**Ready to Start**: YES ✅  
**Estimated Time**: 8-12 hours  
**Complexity**: Medium-High
