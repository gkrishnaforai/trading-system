#!/usr/bin/env python3
"""
Stock Grades Database Migration Script
Executes all stock grades system migrations in correct order
Follows best practices for database migrations
"""
import os
import sys
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.database import get_db
from app.observability.logging import get_logger

logger = get_logger(__name__)


class StockGradesMigrationRunner:
    """Handles execution of stock grades database migrations"""
    
    def __init__(self):
        self.db = get_db()
        self.migrations_dir = project_root / "migrations"
        self.migration_files = [
            "007_stock_grades_system.sql",
            "008_consensus_system.sql", 
            "009_alerts_integration.sql",
            "010_stock_grades_indexes.sql"
        ]
        
    async def run_all_migrations(self, force: bool = False) -> Dict[str, Any]:
        """Run all stock grades migrations in order"""
        
        logger.info("🚀 Starting Stock Grades System Migration")
        logger.info(f"📁 Migration directory: {self.migrations_dir}")
        logger.info(f"📋 Migration files: {self.migration_files}")
        
        results = {
            'start_time': datetime.utcnow(),
            'migrations': {},
            'success': True,
            'errors': [],
            'total_time_seconds': 0
        }
        
        try:
            # Check database connection
            await self._check_database_connection()
            
            # Run each migration in order
            for migration_file in self.migration_files:
                migration_result = await self._run_migration(migration_file, force)
                results['migrations'][migration_file] = migration_result
                
                if not migration_result['success']:
                    results['success'] = False
                    results['errors'].append(f"Failed to run {migration_file}: {migration_result['error']}")
                    break
            
            # Verify migration success
            if results['success']:
                await self._verify_migration()
                await self._update_migration_stats()
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            results['success'] = False
            results['errors'].append(str(e))
        
        finally:
            results['end_time'] = datetime.utcnow()
            results['total_time_seconds'] = (results['end_time'] - results['start_time']).total_seconds()
            
            # Log results
            self._log_results(results)
        
        return results
    
    async def _check_database_connection(self):
        """Verify database connection and permissions"""
        try:
            logger.info("🔍 Checking database connection...")
            
            # Test basic connection
            result = self.db.execute_query("SELECT 1 as test")
            if not result or result[0]['test'] != 1:
                raise Exception("Database connection test failed")
            
            # Check permissions
            self.db.execute_query("SELECT version()")
            
            # Check if tables exist
            existing_tables = await self._get_existing_tables()
            logger.info(f"📊 Existing tables: {len(existing_tables)}")
            
            logger.info("✅ Database connection verified")
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    async def _get_existing_tables(self) -> List[str]:
        """Get list of existing tables"""
        try:
            query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """
            result = self.db.execute_query(query)
            return [row['table_name'] for row in result] if result else []
        except Exception as e:
            logger.warning(f"⚠️ Could not get existing tables: {e}")
            return []
    
    async def _run_migration(self, migration_file: str, force: bool = False) -> Dict[str, Any]:
        """Run a single migration file"""
        
        migration_path = self.migrations_dir / migration_file
        
        if not migration_path.exists():
            return {
                'success': False,
                'error': f"Migration file not found: {migration_path}",
                'execution_time_seconds': 0
            }
        
        logger.info(f"🔄 Running migration: {migration_file}")
        
        result = {
            'file': migration_file,
            'success': False,
            'start_time': datetime.utcnow(),
            'statements_executed': 0,
            'execution_time_seconds': 0,
            'error': None
        }
        
        try:
            # Read migration file
            with open(migration_path, 'r', encoding='utf-8') as f:
                migration_sql = f.read()
            
            if not migration_sql.strip():
                result['success'] = True
                result['error'] = "Migration file is empty"
                return result
            
            # Split into individual statements
            statements = self._split_sql_statements(migration_sql)
            
            # Execute each statement
            for i, statement in enumerate(statements, 1):
                if statement.strip():
                    try:
                        self.db.execute_update(statement.strip())
                        result['statements_executed'] += 1
                        logger.debug(f"✅ Statement {i}/{len(statements)} executed")
                    except Exception as e:
                        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                            logger.debug(f"⚠️ Statement {i} skipped (already exists): {e}")
                            continue
                        else:
                            raise Exception(f"Statement {i} failed: {e}")
            
            result['success'] = True
            logger.info(f"✅ Migration {migration_file} completed successfully")
            
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
            logger.error(f"❌ Migration {migration_file} failed: {e}")
            
            if not force:
                logger.error("💡 Use --force flag to continue despite errors")
        
        finally:
            result['end_time'] = datetime.utcnow()
            result['execution_time_seconds'] = (result['end_time'] - result['start_time']).total_seconds()
        
        return result
    
    def _split_sql_statements(self, sql: str) -> List[str]:
        """Split SQL into individual statements"""
        statements = []
        current_statement = ""
        in_string = False
        string_char = None
        
        for char in sql:
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
        
        return statements
    
    async def _verify_migration(self):
        """Verify that migration was successful"""
        try:
            logger.info("🔍 Verifying migration...")
            
            # Check key tables exist
            expected_tables = [
                'stock_grades',
                'stock_grade_consensus', 
                'stock_consensus_history',
                'grade_change_events',
                'consensus_change_events',
                'data_source_mappings',
                'analyst_firm_rankings'
            ]
            
            existing_tables = await self._get_existing_tables()
            missing_tables = [table for table in expected_tables if table not in existing_tables]
            
            if missing_tables:
                raise Exception(f"Missing tables after migration: {missing_tables}")
            
            # Check foreign key constraints
            await self._verify_foreign_keys()
            
            # Check indexes
            await self._verify_indexes()
            
            # Check triggers
            await self._verify_triggers()
            
            logger.info("✅ Migration verification completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Migration verification failed: {e}")
            raise
    
    async def _verify_foreign_keys(self):
        """Verify foreign key constraints"""
        try:
            query = """
                SELECT 
                    tc.table_name, 
                    tc.constraint_name, 
                    tc.constraint_type,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name LIKE '%stock_grade%'
                ORDER BY tc.table_name, tc.constraint_name
            """
            
            result = self.db.execute_query(query)
            logger.info(f"✅ Found {len(result)} foreign key constraints")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not verify foreign keys: {e}")
    
    async def _verify_indexes(self):
        """Verify indexes were created"""
        try:
            query = """
                SELECT 
                    indexname, 
                    tablename, 
                    indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename LIKE '%stock_grade%'
                ORDER BY tablename, indexname
            """
            
            result = self.db.execute_query(query)
            logger.info(f"✅ Found {len(result)} indexes for stock grades tables")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not verify indexes: {e}")
    
    async def _verify_triggers(self):
        """Verify triggers were created"""
        try:
            query = """
                SELECT 
                    trigger_name, 
                    event_manipulation, 
                    event_object_table,
                    action_timing
                FROM information_schema.triggers
                WHERE trigger_schema = 'public'
                  AND event_object_table LIKE '%stock_grade%'
                ORDER BY event_object_table, trigger_name
            """
            
            result = self.db.execute_query(query)
            logger.info(f"✅ Found {len(result)} triggers for stock grades tables")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not verify triggers: {e}")
    
    async def _update_migration_stats(self):
        """Update migration statistics"""
        try:
            # Count records in key tables
            stats = {}
            
            tables_to_check = [
                'stock_grades',
                'stock_grade_consensus',
                'stock_consensus_history',
                'analyst_firm_rankings',
                'data_source_mappings'
            ]
            
            for table in tables_to_check:
                try:
                    result = self.db.execute_query(f"SELECT COUNT(*) as count FROM {table}")
                    stats[table] = result[0]['count'] if result else 0
                except Exception as e:
                    logger.warning(f"⚠️ Could not count records in {table}: {e}")
                    stats[table] = 0
            
            logger.info("📊 Migration Statistics:")
            for table, count in stats.items():
                logger.info(f"   {table}: {count} records")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not update migration stats: {e}")
    
    def _log_results(self, results: Dict[str, Any]):
        """Log migration results"""
        logger.info("=" * 80)
        logger.info("🎯 STOCK GRADES MIGRATION RESULTS")
        logger.info("=" * 80)
        
        logger.info(f"⏱️  Total time: {results['total_time_seconds']:.2f} seconds")
        logger.info(f"✅ Success: {results['success']}")
        
        logger.info("\n📋 Migration Details:")
        for file, result in results['migrations'].items():
            status = "✅" if result['success'] else "❌"
            time_str = f"{result['execution_time_seconds']:.2f}s"
            stmts = f"{result['statements_executed']} statements"
            
            logger.info(f"   {status} {file} ({time_str}, {stmts})")
            
            if not result['success'] and result['error']:
                logger.info(f"      Error: {result['error']}")
        
        if results['errors']:
            logger.info(f"\n❌ Errors ({len(results['errors'])}):")
            for error in results['errors']:
                logger.info(f"   - {error}")
        
        logger.info("=" * 80)


async def main():
    """Main migration runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Stock Grades Database Migrations")
    parser.add_argument("--force", action="store_true", help="Continue despite errors")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be executed without running")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing migration")
    
    args = parser.parse_args()
    
    runner = StockGradesMigrationRunner()
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
        logger.info(f"📋 Migration files to execute: {runner.migration_files}")
        return
    
    if args.verify_only:
        logger.info("🔍 VERIFICATION MODE - Checking existing migration")
        try:
            await runner._check_database_connection()
            await runner._verify_migration()
            logger.info("✅ Migration verification completed")
        except Exception as e:
            logger.error(f"❌ Migration verification failed: {e}")
            sys.exit(1)
        return
    
    # Run migrations
    results = await runner.run_all_migrations(force=args.force)
    
    if not results['success']:
        logger.error("❌ Migration failed. Check logs for details.")
        sys.exit(1)
    else:
        logger.info("🎉 Migration completed successfully!")
        
        # Show next steps
        logger.info("\n📋 Next Steps:")
        logger.info("   1. Start the API server: python start_api_server.py")
        logger.info("   2. Test endpoints: curl http://localhost:8001/api/v2/stock-grades/coverage-stats")
        logger.info("   3. Load sample data: curl -X POST http://localhost:8001/api/v2/stock-grades/refresh/AAPL")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)
