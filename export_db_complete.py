
#!/usr/bin/env python3
"""
Complete PostgreSQL database export including schema and data
"""
import os
import subprocess
import sys
from datetime import datetime

def export_complete_database():
    """Export PostgreSQL database with full schema and data using pg_dump"""
    database_url = os.environ.get("DATABASE_URL")
    
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not found")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sql_file = f"database_complete_export_{timestamp}.sql"
    
    print("Starting complete database export...")
    print(f"Output file: {sql_file}")
    print("-" * 50)
    
    # Use pg_dump to export complete database
    # This includes: schema (CREATE TABLE, ALTER TABLE, etc.) and all data (INSERT statements)
    try:
        result = subprocess.run(
            ['pg_dump', database_url],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"❌ pg_dump failed with error:")
            print(result.stderr)
            return False
        
        # Write the complete SQL dump to file
        with open(sql_file, 'w', encoding='utf-8') as f:
            f.write(result.stdout)
        
        # Count what was exported
        sql_content = result.stdout
        create_table_count = sql_content.count('CREATE TABLE')
        insert_count = sql_content.count('INSERT INTO')
        constraint_count = sql_content.count('ALTER TABLE')
        
        print(f"✅ Complete database export successful!")
        print(f"\nExported contents:")
        print(f"  - {create_table_count} tables with full schema")
        print(f"  - {insert_count} data INSERT statements")
        print(f"  - {constraint_count} constraints/alterations")
        print(f"\nFile: {sql_file}")
        print(f"Size: {os.path.getsize(sql_file):,} bytes")
        
        print("\n" + "=" * 50)
        print("RESTORE INSTRUCTIONS:")
        print("=" * 50)
        print(f"To restore this database to a new PostgreSQL instance:")
        print(f"  psql <NEW_DATABASE_URL> < {sql_file}")
        print("\nOr if you have the database URL in environment:")
        print(f"  psql $DATABASE_URL < {sql_file}")
        print("=" * 50)
        
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ Export timed out after 60 seconds")
        return False
    except FileNotFoundError:
        print("❌ pg_dump command not found. PostgreSQL client tools may not be installed.")
        print("The Nix package should install automatically. Try reloading the Repl.")
        return False
    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = export_complete_database()
    sys.exit(0 if success else 1)
