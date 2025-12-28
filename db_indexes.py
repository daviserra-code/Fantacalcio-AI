# db_indexes.py - Database performance indexes
"""
PostgreSQL indexes for improved query performance.

Run this file to add indexes to existing database:
    python db_indexes.py
"""
import logging
from app import app, db
from sqlalchemy import text

LOG = logging.getLogger("db_indexes")

# Index definitions
INDEXES = [
    # Users table indexes
    {
        'name': 'idx_users_email',
        'table': 'users',
        'columns': ['email'],
        'unique': True,
        'comment': 'Fast email lookup for login'
    },
    {
        'name': 'idx_users_username',
        'table': 'users',
        'columns': ['username'],
        'unique': True,
        'comment': 'Fast username lookup'
    },
    {
        'name': 'idx_users_is_active',
        'table': 'users',
        'columns': ['is_active'],
        'comment': 'Filter active users'
    },
    {
        'name': 'idx_users_pro_expires',
        'table': 'users',
        'columns': ['pro_expires_at'],
        'comment': 'Find expiring subscriptions'
    },
    {
        'name': 'idx_users_stripe_customer',
        'table': 'users',
        'columns': ['stripe_customer_id'],
        'comment': 'Stripe webhook lookups'
    },
    
    # User leagues indexes
    {
        'name': 'idx_user_leagues_user_id',
        'table': 'user_leagues',
        'columns': ['user_id'],
        'comment': 'Fast user league lookup'
    },
    {
        'name': 'idx_user_leagues_name',
        'table': 'user_leagues',
        'columns': ['user_id', 'league_name'],
        'unique': True,
        'comment': 'Unique league names per user'
    },
    {
        'name': 'idx_user_leagues_created',
        'table': 'user_leagues',
        'columns': ['created_at'],
        'comment': 'Sort by creation date'
    },
    
    # Subscriptions indexes
    {
        'name': 'idx_subscriptions_user_id',
        'table': 'subscriptions',
        'columns': ['user_id'],
        'comment': 'Fast subscription lookup by user'
    },
    {
        'name': 'idx_subscriptions_stripe_id',
        'table': 'subscriptions',
        'columns': ['stripe_subscription_id'],
        'unique': True,
        'comment': 'Unique Stripe subscription ID'
    },
    {
        'name': 'idx_subscriptions_status',
        'table': 'subscriptions',
        'columns': ['status'],
        'comment': 'Filter by subscription status'
    },
    {
        'name': 'idx_subscriptions_period_end',
        'table': 'subscriptions',
        'columns': ['current_period_end'],
        'comment': 'Find expiring subscriptions'
    },
    
    # Flask-Dance OAuth indexes
    {
        'name': 'idx_oauth_user_id',
        'table': 'flask_dance_oauth',
        'columns': ['user_id'],
        'comment': 'Fast OAuth lookup by user'
    },
    {
        'name': 'idx_oauth_provider',
        'table': 'flask_dance_oauth',
        'columns': ['provider', 'user_id'],
        'comment': 'OAuth provider lookups'
    }
]

def create_index(index_def: dict) -> bool:
    """Create a single index"""
    try:
        name = index_def['name']
        table = index_def['table']
        columns = index_def['columns']
        unique = index_def.get('unique', False)
        
        # Check if index already exists
        check_query = text("""
            SELECT 1 FROM pg_indexes 
            WHERE indexname = :index_name
        """)
        
        result = db.session.execute(check_query, {'index_name': name}).fetchone()
        
        if result:
            LOG.info(f"Index {name} already exists, skipping")
            return True
        
        # Build CREATE INDEX statement
        unique_clause = "UNIQUE" if unique else ""
        columns_clause = ", ".join(columns)
        
        create_query = text(f"""
            CREATE {unique_clause} INDEX {name}
            ON {table} ({columns_clause})
        """)
        
        db.session.execute(create_query)
        db.session.commit()
        
        LOG.info(f"✓ Created index: {name} on {table}({columns_clause})")
        return True
        
    except Exception as e:
        LOG.error(f"✗ Failed to create index {index_def['name']}: {e}")
        db.session.rollback()
        return False

def drop_index(index_name: str) -> bool:
    """Drop an index"""
    try:
        drop_query = text(f"DROP INDEX IF EXISTS {index_name}")
        db.session.execute(drop_query)
        db.session.commit()
        LOG.info(f"Dropped index: {index_name}")
        return True
    except Exception as e:
        LOG.error(f"Failed to drop index {index_name}: {e}")
        db.session.rollback()
        return False

def create_all_indexes():
    """Create all defined indexes"""
    LOG.info("Creating database indexes...")
    
    success_count = 0
    fail_count = 0
    
    for index_def in INDEXES:
        if create_index(index_def):
            success_count += 1
        else:
            fail_count += 1
    
    LOG.info(f"Index creation complete: {success_count} successful, {fail_count} failed")
    return success_count, fail_count

def analyze_tables():
    """Run ANALYZE to update table statistics"""
    LOG.info("Analyzing tables for query optimization...")
    
    tables = ['users', 'user_leagues', 'subscriptions', 'flask_dance_oauth']
    
    for table in tables:
        try:
            analyze_query = text(f"ANALYZE {table}")
            db.session.execute(analyze_query)
            db.session.commit()
            LOG.info(f"✓ Analyzed table: {table}")
        except Exception as e:
            LOG.error(f"✗ Failed to analyze {table}: {e}")

def get_index_usage_stats():
    """Get statistics on index usage"""
    try:
        query = text("""
            SELECT
                schemaname,
                tablename,
                indexname,
                idx_scan as scans,
                idx_tup_read as tuples_read,
                idx_tup_fetch as tuples_fetched
            FROM pg_stat_user_indexes
            ORDER BY idx_scan DESC
        """)
        
        result = db.session.execute(query)
        stats = []
        
        for row in result:
            stats.append({
                'schema': row[0],
                'table': row[1],
                'index': row[2],
                'scans': row[3],
                'tuples_read': row[4],
                'tuples_fetched': row[5]
            })
        
        return stats
    except Exception as e:
        LOG.error(f"Failed to get index stats: {e}")
        return []

def main():
    """Main execution"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    with app.app_context():
        LOG.info("=" * 60)
        LOG.info("Database Index Creation Tool")
        LOG.info("=" * 60)
        
        # Create indexes
        success, failed = create_all_indexes()
        
        # Analyze tables
        analyze_tables()
        
        LOG.info("=" * 60)
        LOG.info(f"Summary: {success} indexes created, {failed} failed")
        LOG.info("=" * 60)
        
        # Show index usage (if any)
        stats = get_index_usage_stats()
        if stats:
            LOG.info("\nCurrent Index Usage:")
            for stat in stats[:10]:  # Top 10
                LOG.info(f"  {stat['index']}: {stat['scans']} scans")

if __name__ == '__main__':
    main()
