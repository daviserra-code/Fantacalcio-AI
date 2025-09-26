-- Player Statistics and Status Management Schema
-- Creates tables for tracking dynamic player data and transfer status

-- Player identity mapping table
CREATE TABLE IF NOT EXISTS player_identity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_key TEXT UNIQUE NOT NULL,  -- normalized name@@team format
    name TEXT NOT NULL,
    birth_year INTEGER,
    transfermarkt_id TEXT,
    sofascore_id TEXT,
    team_history TEXT,  -- JSON array of team changes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Player current status table
CREATE TABLE IF NOT EXISTS player_status (
    canonical_key TEXT PRIMARY KEY,
    current_team TEXT NOT NULL,
    current_league TEXT NOT NULL,  -- 'Serie A', 'Premier League', etc.
    status TEXT NOT NULL,  -- 'active', 'transferred_out', 'loaned_out', 'injured'
    last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transfer_window TEXT,  -- '2025-summer', '2025-winter', etc.
    FOREIGN KEY (canonical_key) REFERENCES player_identity(canonical_key)
);

-- Player statistics by season/matchday
CREATE TABLE IF NOT EXISTS player_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_key TEXT NOT NULL,
    season TEXT NOT NULL,  -- '2025-26'
    matchday INTEGER,
    appearances INTEGER DEFAULT 0,
    minutes_played INTEGER DEFAULT 0,
    starts INTEGER DEFAULT 0,
    substitutions INTEGER DEFAULT 0,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_source TEXT,  -- 'transfermarkt', 'sofascore', 'manual'
    FOREIGN KEY (canonical_key) REFERENCES player_identity(canonical_key),
    UNIQUE(canonical_key, season, matchday)
);

-- Cumulative season stats view
CREATE VIEW IF NOT EXISTS player_season_stats AS
SELECT 
    canonical_key,
    season,
    SUM(appearances) as total_appearances,
    SUM(minutes_played) as total_minutes,
    SUM(starts) as total_starts,
    SUM(substitutions) as total_subs,
    SUM(goals) as total_goals,
    SUM(assists) as total_assists,
    MAX(last_updated) as last_updated
FROM player_stats 
GROUP BY canonical_key, season;

-- Transfer tracking table
CREATE TABLE IF NOT EXISTS player_transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_key TEXT NOT NULL,
    from_team TEXT,
    to_team TEXT,
    transfer_date TEXT,
    transfer_type TEXT,  -- 'permanent', 'loan', 'free'
    fee_amount TEXT,
    source TEXT,  -- 'transfermarkt', 'manual'
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (canonical_key) REFERENCES player_identity(canonical_key)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_player_status_league ON player_status(current_league);
CREATE INDEX IF NOT EXISTS idx_player_status_team ON player_status(current_team);
CREATE INDEX IF NOT EXISTS idx_player_stats_season ON player_stats(season);
CREATE INDEX IF NOT EXISTS idx_player_stats_canonical ON player_stats(canonical_key);
CREATE INDEX IF NOT EXISTS idx_player_transfers_date ON player_transfers(transfer_date);