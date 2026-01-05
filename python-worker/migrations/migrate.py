#!/usr/bin/env python3
"""
Migration manager for the trading system
Handles running and tracking database migrations
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add the python-worker directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import db, init_database
from app.observability.logging import get_logger

logger = get_logger(__name__)

class MigrationManager:
    """Manages database migrations with tracking"""
    
    def __init__(self):
        self.migrations_dir = Path(__file__).parent
        self.init_migration_tracking()
    
    def init_migration_tracking(self):
        """Create the migrations tracking table"""
        try:
            init_database()
            
            create_table_query = """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                migration_name VARCHAR(255) NOT NULL UNIQUE,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checksum VARCHAR(64),
                execution_time_ms INTEGER
            );
            """
            
            db.execute_query(create_table_query)
            logger.info("✅ Migration tracking table ready")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize migration tracking: {e}")
            raise
    
    def get_executed_migrations(self):
        """Get list of already executed migrations"""
        try:
            query = "SELECT migration_name, executed_at FROM schema_migrations ORDER BY executed_at"
            results = db.execute_query(query)
            return {row['migration_name']: row['executed_at'] for row in results}
        except Exception as e:
            logger.error(f"❌ Failed to get executed migrations: {e}")
            return {}
    
    def run_migration(self, migration_file):
        """Run a single migration"""
        migration_name = migration_file.stem
        
        try:
            logger.info(f"🔄 Running migration: {migration_name}")
            start_time = datetime.now()
            
            # Import and run the migration
            spec = __import__(f"migrations.{migration_name}", fromlist=['create_trading_signals_table'])
            if hasattr(spec, 'create_trading_signals_table'):
                spec.create_trading_signals_table()
            else:
                raise ImportError(f"Migration function not found in {migration_name}")
            
            # Record the migration
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            insert_query = """
            INSERT INTO schema_migrations (migration_name, execution_time_ms) 
            VALUES (:migration_name, :execution_time_ms)
            """
            
            db.execute_query(insert_query, {
                'migration_name': migration_name,
                'execution_time_ms': int(execution_time)
            })
            
            logger.info(f"✅ Migration {migration_name} completed in {execution_time:.0f}ms")
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration {migration_name} failed: {e}")
            return False
    
    def run_all_migrations(self):
        """Run all pending migrations"""
        logger.info("🚀 Starting migration process...")
        
        # Get all migration files
        migration_files = sorted(self.migrations_dir.glob("*.py"))
        migration_files = [f for f in migration_files if f.name.startswith('create_') or f.name.startswith('add_') or f.name.startswith('update_')]
        
        if not migration_files:
            logger.info("ℹ️ No migration files found")
            return True
        
        # Get executed migrations
        executed = self.get_executed_migrations()
        
        # Run pending migrations
        pending = [f for f in migration_files if f.stem not in executed]
        
        if not pending:
            logger.info("✅ All migrations are up to date")
            return True
        
        logger.info(f"📋 Found {len(pending)} pending migrations")
        
        success_count = 0
        for migration_file in pending:
            if self.run_migration(migration_file):
                success_count += 1
            else:
                logger.error(f"❌ Stopping due to migration failure: {migration_file}")
                break
        
        total_migrations = len(pending)
        if success_count == total_migrations:
            logger.info(f"🎉 All {total_migrations} migrations completed successfully!")
            return True
        else:
            logger.error(f"❌ Only {success_count}/{total_migrations} migrations completed")
            return False
    
    def rollback_migration(self, migration_name):
        """Rollback a specific migration (if rollback is supported)"""
        logger.warning(f"⚠️ Rollback not implemented for {migration_name}")
        return False
    
    def get_migration_status(self):
        """Get the status of all migrations"""
        migration_files = sorted(self.migrations_dir.glob("*.py"))
        migration_files = [f for f in migration_files if f.name.startswith('create_') or f.name.startswith('add_') or f.name.startswith('update_')]
        
        executed = self.get_executed_migrations()
        
        print("\n📊 Migration Status:")
        print("=" * 80)
        print(f"{'Migration':<40} {'Status':<15} {'Executed At':<20}")
        print("-" * 80)
        
        for migration_file in migration_files:
            migration_name = migration_file.stem
            if migration_name in executed:
                print(f"{migration_name:<40} {'✅ Executed':<15} {executed[migration_name]:<20}")
            else:
                print(f"{migration_name:<40} {'⏳ Pending':<15} {'-':<20}")
        
        print("-" * 80)
        print(f"Total: {len(migration_files)} migrations, {len(executed)} executed, {len(migration_files) - len(executed)} pending")

def main():
    """Main migration runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Trading System Migration Manager")
    parser.add_argument('command', choices=['up', 'status', 'reset'], help='Migration command')
    parser.add_argument('--migration', help='Specific migration to run')
    
    args = parser.parse_args()
    
    manager = MigrationManager()
    
    if args.command == 'up':
        if args.migration:
            # Run specific migration
            migration_file = manager.migrations_dir / f"{args.migration}.py"
            if migration_file.exists():
                success = manager.run_migration(migration_file)
                sys.exit(0 if success else 1)
            else:
                logger.error(f"❌ Migration file not found: {args.migration}")
                sys.exit(1)
        else:
            # Run all pending migrations
            success = manager.run_all_migrations()
            sys.exit(0 if success else 1)
    
    elif args.command == 'status':
        manager.get_migration_status()
    
    elif args.command == 'reset':
        logger.warning("⚠️ Reset not implemented yet")
        sys.exit(1)

if __name__ == "__main__":
    main()
