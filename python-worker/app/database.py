"""Database connection and utilities (Postgres-only)."""
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from pathlib import Path
import os
import re

import asyncpg
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager"""
    
    def __init__(self):
        self.engine = None
        self.async_engine = None
        self.session_factory = None
        
    def initialize(self):
        """Initialize database connection"""
        db_url = settings.database_url

        if db_url.startswith("sqlite") or db_url.startswith("file:"):
            raise ValueError("SQLite is no longer supported. Configure DATABASE_URL for PostgreSQL.")

        self.engine = create_engine(db_url, echo=False)
        async_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
        self.async_engine = create_async_engine(async_url, echo=False)
        logger.info("✅ Connected to PostgreSQL database")
        
        self.session_factory = sessionmaker(bind=self.engine)
    
    @contextmanager
    def get_session(self):
        """Get database session (context manager)"""
        if self.session_factory is None:
            self.initialize()
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results"""
        with self.get_session() as session:
            result = session.execute(text(query), params or {})
            rows = result.fetchall()
            # Convert to list of dicts
            if rows:
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
            return []

    def execute_query_positional(self, query: str, params: List[Any]) -> List[Dict[str, Any]]:
        """Execute a SELECT query using $1/$2 positional placeholders."""
        sql, named = self._convert_positional_sql(query, params)
        return self.execute_query(sql, named)
    
    def execute_update(self, query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query"""
        with self.get_session() as session:
            result = session.execute(text(query), params or {})
            session.commit()
            return result.rowcount

    def execute_update_positional(self, query: str, params: List[Any]) -> int:
        """Execute an INSERT/UPDATE/DELETE using $1/$2 positional placeholders."""
        sql, named = self._convert_positional_sql(query, params)
        return self.execute_update(sql, named)
    
    def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> int:
        """Execute multiple queries with different parameters"""
        # Validate that all items are dictionaries
        if not isinstance(params_list, list):
            raise ValueError(f"params_list must be a list, got {type(params_list)}")
        
        for i, item in enumerate(params_list):
            if not isinstance(item, dict):
                raise ValueError(f"List argument must consist only of dictionaries. Item {i} is {type(item)}: {item}")
        
        with self.get_session() as session:
            result = session.execute(text(query), params_list)
            session.commit()
            return result.rowcount
    
    def close(self):
        """Close database connections"""
        if self.engine:
            self.engine.dispose()
        if self.async_engine:
            # Async engine cleanup would be done with async context
            pass
        logger.info("Database connections closed")

    def _convert_positional_sql(self, query: str, params: List[Any]) -> (str, Dict[str, Any]):
        """Convert a SQL query using $1/$2 positional placeholders to SQLAlchemy bind params."""
        named_params = {}
        for i, param in enumerate(params, start=1):
            named_params[f"param_{i}"] = param
            query = re.sub(rf"\${i}", f":param_{i}", query)
        return query, named_params


# Global database instance
db = Database()


def run_migrations():
    """Run database migrations from SQL files"""
    project_root = Path(__file__).parent.parent.parent
    migrations_dir = project_root / "supabase" / "migrations"
    if not migrations_dir.exists():
        migrations_dir = project_root / "db" / "migrations_postgres"

    if not migrations_dir.exists():
        logger.warning(f"Postgres migrations directory not found: {migrations_dir}")
        return

    migration_files = sorted([p.name for p in migrations_dir.glob("*.sql")])
    if not migration_files:
        logger.info("No Postgres migrations found")
        return

    # Ensure migration tracking table exists
    db.execute_update(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          migration_name TEXT PRIMARY KEY,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    try:
        applied = db.execute_query("SELECT migration_name FROM schema_migrations")
    except Exception as e:
        # If a legacy/incompatible schema_migrations table exists, reset it.
        # This is safe for non-production environments and avoids crashing startup.
        logger.warning(f"schema_migrations table incompatible, resetting: {e}")
        db.execute_update("DROP TABLE IF EXISTS schema_migrations")
        db.execute_update(
            """
            CREATE TABLE schema_migrations (
              migration_name TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        applied = []

    applied_set = {row["migration_name"] for row in applied}

    logger.info("📝 Running Postgres migrations...")
    for migration_file in migration_files:
        if migration_file in applied_set:
            logger.debug(f"Skipping already applied migration {migration_file}")
            continue
        migration_path = migrations_dir / migration_file
        try:
            with open(migration_path, "r") as f:
                sql = f.read()

            connection = db.engine.raw_connection()
            try:
                cursor = connection.cursor()
                for stmt in _split_sql_statements(sql):
                    cursor.execute(stmt)
                connection.commit()
                logger.info(f"✅ Applied migration {migration_file}")

                # Record as applied
                db.execute_update(
                    """
                    INSERT INTO schema_migrations (migration_name)
                    VALUES (:migration_name)
                    ON CONFLICT (migration_name) DO NOTHING
                    """,
                    {"migration_name": migration_file},
                )
            finally:
                connection.close()
        except Exception as e:
            logger.warning(f"Error applying migration {migration_file}: {e}")


def _split_sql_statements(sql: str) -> List[str]:
    """Split a SQL migration file into executable statements.

    This is intentionally conservative: it removes line comments and splits on semicolons.
    It is sufficient for our Postgres migrations which should avoid procedural blocks.
    """
    cleaned_lines: List[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("--"):
            continue
        cleaned_lines.append(line)

    cleaned_sql = "\n".join(cleaned_lines)
    statements = []
    for part in cleaned_sql.split(";"):
        stmt = part.strip()
        if stmt:
            statements.append(stmt)
    return statements


def init_database():
    """Initialize database connection and run migrations"""
    db.initialize()
    run_migrations()
    return db

