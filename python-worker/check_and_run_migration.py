#!/usr/bin/env python3
"""
Script to check if migration file exists in Docker container and run it
"""

import os
import sys
import subprocess

def check_container_file():
    """Check if migration file exists in python-worker container"""
    try:
        # Check if container is running
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        containers = result.stdout.strip().split('\n')
        
        python_worker_container = None
        for container in containers:
            if 'python-worker' in container.lower():
                python_worker_container = container
                break
        
        if not python_worker_container:
            print("❌ python-worker container not found")
            return False, None
        
        print(f"✅ Found container: {python_worker_container}")
        
        # Check if migration file exists in container
        result = subprocess.run([
            "docker", "exec", python_worker_container,
            "find", "/app", "-name", "029_fix_column_naming_consistency.sql", "-type", "f"
        ], capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            print("✅ Migration file found in container:")
            print(result.stdout.strip())
            return True, python_worker_container
        else:
            print("❌ Migration file NOT found in container")
            return False, python_worker_container
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Error checking container: {e}")
        return False, None
    except FileNotFoundError:
        print("❌ Docker command not found")
        return False, None

def copy_file_to_container(container_name):
    """Copy migration file to container"""
    try:
        local_file = "/Users/krishnag/tools/trading-system/python-worker/migrations/029_fix_column_naming_consistency.sql"
        remote_path = "/app/migrations/029_fix_column_naming_consistency.sql"
        
        print(f"📋 Copying {local_file} to {container_name}:{remote_path}")
        
        result = subprocess.run([
            "docker", "cp", local_file, f"{container_name}:{remote_path}"
        ], capture_output=True, text=True, check=True)
        
        print("✅ File copied successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error copying file: {e}")
        print(f"Stderr: {e.stderr}")
        return False

def run_migration_in_container(container_name):
    """Run the migration in the container"""
    try:
        print(f"🚀 Running migration in {container_name}...")
        
        # Run the migration using Python
        result = subprocess.run([
            "docker", "exec", container_name, "python", "-c", """
import sys
sys.path.append('/app')

from app.database import db
from sqlalchemy import text

# Read and run the migration
with open('/app/migrations/029_fix_column_naming_consistency.sql', 'r') as f:
    migration_sql = f.read()

print('📝 Executing migration...')
db.execute_update(migration_sql)
print('✅ Migration completed successfully')
"""
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Migration executed successfully!")
            print("Output:", result.stdout)
            return True
        else:
            print("❌ Migration failed!")
            print("Error:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Migration timed out after 60 seconds")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running migration: {e}")
        print(f"Stderr: {e.stderr}")
        return False

def run_local_migration():
    """Run migration locally (not in container)"""
    try:
        print("🚀 Running migration locally...")
        
        # Change to python-worker directory
        os.chdir("/Users/krishnag/tools/trading-system/python-worker")
        
        # Run the migration
        result = subprocess.run([
            "python", "-c", """
from app.database import db
from sqlalchemy import text

# Read and run the migration
with open('migrations/029_fix_column_naming_consistency.sql', 'r') as f:
    migration_sql = f.read()

print('📝 Executing migration...')
db.execute_update(migration_sql)
print('✅ Migration completed successfully')
"""
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Migration executed successfully!")
            print("Output:", result.stdout)
            return True
        else:
            print("❌ Migration failed!")
            print("Error:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Migration timed out after 60 seconds")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running migration: {e}")
        print(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("🔍 Checking migration file and running schema fix...")
    print("=" * 60)
    
    # Check if file exists in container
    file_exists, container_name = check_container_file()
    
    if file_exists and container_name:
        print(f"\n🎯 File exists in {container_name}, running migration...")
        success = run_migration_in_container(container_name)
    elif container_name:
        print(f"\n📋 File not found in {container_name}, copying and running...")
        if copy_file_to_container(container_name):
            success = run_migration_in_container(container_name)
        else:
            print("❌ Failed to copy file, trying local migration...")
            success = run_local_migration()
    else:
        print("\n🏠 Container not found, running migration locally...")
        success = run_local_migration()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("💡 Now try running your data operations again")
    else:
        print("\n💥 Migration failed!")
        print("💡 Check the error messages above and try manually")

if __name__ == "__main__":
    main()
