
#!/usr/bin/env python3
"""
Complete PostgreSQL database export including schema and data using Python
"""
import os
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

def export_complete_database():
    """Export PostgreSQL database with full schema and data using psycopg2"""
    database_url = os.environ.get("DATABASE_URL")
    
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not found")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sql_file = f"database_complete_export_{timestamp}.sql"
    
    print("Starting complete database export...")
    print(f"Output file: {sql_file}")
    print("-" * 50)
    
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        with open(sql_file, 'w', encoding='utf-8') as f:
            # Export schema and data
            f.write("-- PostgreSQL Database Export\n")
            f.write(f"-- Generated: {datetime.now().isoformat()}\n")
            f.write("-- Database: Neon PostgreSQL 16.9\n\n")
            
            # Get all tables
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [row['table_name'] for row in cur.fetchall()]
            
            print(f"Found {len(tables)} tables: {', '.join(tables)}\n")
            
            table_count = 0
            insert_count = 0
            
            for table in tables:
                # Get table schema
                cur.execute(f"""
                    SELECT 
                        column_name,
                        data_type,
                        character_maximum_length,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table,))
                columns = cur.fetchall()
                
                # Write CREATE TABLE statement
                f.write(f"\n-- Table: {table}\n")
                f.write(f"DROP TABLE IF EXISTS {table} CASCADE;\n")
                f.write(f"CREATE TABLE {table} (\n")
                
                col_defs = []
                for col in columns:
                    col_def = f"  {col['column_name']} {col['data_type']}"
                    if col['character_maximum_length']:
                        col_def += f"({col['character_maximum_length']})"
                    if col['is_nullable'] == 'NO':
                        col_def += " NOT NULL"
                    if col['column_default']:
                        col_def += f" DEFAULT {col['column_default']}"
                    col_defs.append(col_def)
                
                f.write(",\n".join(col_defs))
                f.write("\n);\n\n")
                
                # Get primary key
                cur.execute(f"""
                    SELECT a.attname
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid
                        AND a.attnum = ANY(i.indkey)
                    WHERE i.indrelid = %s::regclass
                        AND i.indisprimary
                """, (table,))
                pk_cols = [row['attname'] for row in cur.fetchall()]
                
                if pk_cols:
                    f.write(f"ALTER TABLE {table} ADD PRIMARY KEY ({', '.join(pk_cols)});\n\n")
                
                # Export data
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                
                if rows:
                    f.write(f"-- Data for {table}\n")
                    for row in rows:
                        row_dict = dict(row)
                        cols = ', '.join(row_dict.keys())
                        
                        # Format values properly
                        values = []
                        for val in row_dict.values():
                            if val is None:
                                values.append('NULL')
                            elif isinstance(val, str):
                                # Escape single quotes
                                escaped = val.replace("'", "''")
                                values.append(f"'{escaped}'")
                            elif hasattr(val, 'isoformat'):
                                values.append(f"'{val.isoformat()}'")
                            else:
                                values.append(str(val))
                        
                        vals = ', '.join(values)
                        f.write(f"INSERT INTO {table} ({cols}) VALUES ({vals});\n")
                        insert_count += 1
                    
                    f.write("\n")
                    print(f"✅ Exported {len(rows)} records from '{table}'")
                else:
                    print(f"   Empty table: '{table}'")
                
                table_count += 1
            
            # Get foreign keys
            cur.execute("""
                SELECT
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name,
                    tc.constraint_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
            """)
            fks = cur.fetchall()
            
            if fks:
                f.write("\n-- Foreign Keys\n")
                for fk in fks:
                    f.write(f"ALTER TABLE {fk['table_name']} ADD CONSTRAINT {fk['constraint_name']} ")
                    f.write(f"FOREIGN KEY ({fk['column_name']}) ")
                    f.write(f"REFERENCES {fk['foreign_table_name']}({fk['foreign_column_name']});\n")
        
        file_size = os.path.getsize(sql_file)
        
        print(f"\n✅ Complete database export successful!")
        print(f"\nExported contents:")
        print(f"  - {table_count} tables with full schema")
        print(f"  - {insert_count} data INSERT statements")
        print(f"  - {len(fks)} foreign key constraints")
        print(f"\nFile: {sql_file}")
        print(f"Size: {file_size:,} bytes")
        
        print("\n" + "=" * 50)
        print("RESTORE INSTRUCTIONS:")
        print("=" * 50)
        print(f"To restore this database to a new PostgreSQL instance:")
        print(f"  psql <NEW_DATABASE_URL> < {sql_file}")
        print("\nOr if you have the database URL in environment:")
        print(f"  psql $DATABASE_URL < {sql_file}")
        print("=" * 50)
        
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = export_complete_database()
    sys.exit(0 if success else 1)
