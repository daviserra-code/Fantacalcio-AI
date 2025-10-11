
#!/usr/bin/env python3
"""
Simple PostgreSQL database export using psycopg2
"""
import os
import sys
import json
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

def export_database():
    """Export PostgreSQL database to SQL and JSON formats"""
    database_url = os.environ.get("DATABASE_URL")
    
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not found")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all table names
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
        """)
        tables = [row['table_name'] for row in cur.fetchall()]
        
        print(f"Found {len(tables)} tables: {', '.join(tables)}")
        
        # Export each table
        all_data = {}
        for table in tables:
            cur.execute(f"SELECT * FROM {table}")
            rows = cur.fetchall()
            
            # Convert to list of dicts with proper serialization
            table_data = []
            for row in rows:
                row_dict = dict(row)
                # Convert datetime objects to strings
                for key, value in row_dict.items():
                    if hasattr(value, 'isoformat'):
                        row_dict[key] = value.isoformat()
                table_data.append(row_dict)
            
            all_data[table] = table_data
            print(f"✅ Exported {len(table_data)} records from '{table}'")
        
        # Save to JSON
        json_file = f"database_export_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Database exported successfully to: {json_file}")
        
        # Also create a simple SQL dump
        sql_file = f"database_export_{timestamp}.sql"
        with open(sql_file, 'w', encoding='utf-8') as f:
            for table, data in all_data.items():
                if data:
                    f.write(f"-- Table: {table}\n")
                    f.write(f"-- Records: {len(data)}\n\n")
        
        print(f"✅ SQL metadata exported to: {sql_file}")
        
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = export_database()
    sys.exit(0 if success else 1)
