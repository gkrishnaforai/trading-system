#!/usr/bin/env python3
"""
Fix trigger functions for stock grades system
Run this script to create the trigger functions directly in PostgreSQL
"""

import os
import sys
from pathlib import Path

# Add the parent directory to Python path to import app modules
sys.path.append(str(Path(__file__).parent.parent))

try:
    from app.database import get_db
    
    # Read the SQL file
    sql_file = Path(__file__).parent / "fix_trigger_functions.sql"
    with open(sql_file, 'r') as f:
        sql_content = f.read()
    
    print("🔧 Fixing trigger functions...")
    
    # Get database connection
    db = get_db()
    
    # Split SQL into individual statements (same as migration runner)
    statements = []
    current_statement = ""
    in_string = False
    string_char = None
    
    for char in sql_content:
        if char in ("'", '"') and not in_string:
            in_string = True
            string_char = char
        elif char == string_char and in_string:
            in_string = False
            string_char = None
        
        if char == ';' and not in_string:
            current_statement += char
            if current_statement.strip():
                statements.append(current_statement.strip())
            current_statement = ""
        else:
            current_statement += char
    
    # Add any remaining statement
    if current_statement.strip():
        statements.append(current_statement.strip())
    
    # Execute each statement
    for i, statement in enumerate(statements, 1):
        if statement.strip():
            try:
                db.execute_update(statement.strip())
                print(f"✅ Statement {i}/{len(statements)} executed")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"⚠️ Statement {i} skipped (already exists): {e}")
                    continue
                else:
                    print(f"❌ Statement {i} failed: {e}")
                    raise
    
    print("✅ Trigger functions created successfully!")
        
except ImportError as e:
    print(f"❌ Cannot import database modules: {e}")
    print("Trying direct database access...")
    
    try:
        # Try to import the database module directly
        from app.database import Database
        
        # Read the SQL file
        sql_file = Path(__file__).parent / "fix_trigger_functions.sql"
        with open(sql_file, 'r') as f:
            sql_content = f.read()
        
        print("🔧 Fixing trigger functions...")
        
        # Create database instance
        db = Database()
        
        # Split and execute statements (same as above)
        statements = []
        current_statement = ""
        in_string = False
        string_char = None
        
        for char in sql_content:
            if char in ("'", '"') and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
            
            if char == ';' and not in_string:
                current_statement += char
                if current_statement.strip():
                    statements.append(current_statement.strip())
                current_statement = ""
            else:
                current_statement += char
        
        if current_statement.strip():
            statements.append(current_statement.strip())
        
        # Execute each statement
        for i, statement in enumerate(statements, 1):
            if statement.strip():
                try:
                    db.execute_update(statement.strip())
                    print(f"✅ Statement {i}/{len(statements)} executed")
                except Exception as e:
                    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                        print(f"⚠️ Statement {i} skipped (already exists): {e}")
                        continue
                    else:
                        print(f"❌ Statement {i} failed: {e}")
                        raise
        
        print("✅ Trigger functions created successfully!")
            
    except ImportError:
        print("❌ Database modules not available. Please check your app setup.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

print("🎉 Fix completed! You can now run the migrations again.")
