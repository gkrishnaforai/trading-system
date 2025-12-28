"""
Base Repository with common upsert/query utilities (DRY).
Industry Standard: Repository Pattern; hides SQL dialect differences.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple
from datetime import date, datetime

from app.database import db
from app.exceptions import DatabaseError


class BaseRepository:
    """Shared repository utilities (SQLite vs Postgres upserts, date handling)."""

    @staticmethod
    def upsert_many(
        table: str,
        unique_columns: List[str],
        rows: Iterable[Dict[str, Any]],
        returning: Optional[str] = None,
    ) -> int:
        """Generic upsert for any table; handles dialect differences."""
        rows_list = list(rows)
        if not rows_list:
            return 0

        return BaseRepository._postgres_upsert(table, unique_columns, rows_list, returning)

    @staticmethod
    def _sqlite_upsert(table: str, rows: List[Dict[str, Any]], returning: Optional[str]) -> int:
        cols = list(rows[0].keys())
        placeholders = ", ".join(f":{c}" for c in cols)
        query = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        return db.execute_many(query, rows)

    @staticmethod
    def _postgres_upsert(
        table: str,
        unique_columns: List[str],
        rows: List[Dict[str, Any]],
        returning: Optional[str],
    ) -> int:
        cols = list(rows[0].keys())
        placeholders = ", ".join(f":{c}" for c in cols)
        unique = ", ".join(unique_columns)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in unique_columns and c != "updated_at")
        returning_clause = f" RETURNING {returning}" if returning else ""

        query = f"""
            INSERT INTO {table} ({', '.join(cols)})
            VALUES ({placeholders})
            ON CONFLICT ({unique})
            DO UPDATE SET {updates}, updated_at = NOW()
            {returning_clause}
        """
        return db.execute_many(query, rows)

    @staticmethod
    def fetch_one(
        table: str,
        where: Dict[str, Any],
        select_cols: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        cols = ", ".join(select_cols) if select_cols else "*"
        conditions = " AND ".join(f"{k} = :{k}" for k in where)
        query = f"SELECT {cols} FROM {table} WHERE {conditions} LIMIT 1"
        result = db.execute_query(query, where)
        return result[0] if result else None

    @staticmethod
    def fetch_many(
        table: str,
        where: Optional[Dict[str, Any]] = None,
        select_cols: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        cols = ", ".join(select_cols) if select_cols else "*"
        query = f"SELECT {cols} FROM {table}"
        params: Dict[str, Any] = {}
        if where:
            conditions = " AND ".join(f"{k} = :{k}" for k in where)
            query += f" WHERE {conditions}"
            params.update(where)
        if order_by:
            query += f" ORDER BY {order_by}"
        if limit:
            query += f" LIMIT {limit}"
        return db.execute_query(query, params)
