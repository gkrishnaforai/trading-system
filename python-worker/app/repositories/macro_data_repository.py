"""Macro Data Repository
 Stores and retrieves macro_market_data used for market regime detection
 """

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from app.exceptions import DatabaseError
from app.repositories.base_repository import BaseRepository


class MacroDataRepository(BaseRepository):
    """Repository for macro_market_data."""

    @staticmethod
    def fetch_latest() -> Optional[Dict[str, Any]]:
        try:
            rows = BaseRepository.fetch_many(
                table="macro_market_data",
                where=None,
                order_by="data_date DESC",
                limit=1,
            )
            return rows[0] if rows else None
        except Exception as e:
            raise DatabaseError(f"Failed to fetch latest macro data: {e}") from e

    @staticmethod
    def save_macro_data(payload: Dict[str, Any]) -> int:
        """Upsert macro data by data_date."""
        if "data_date" not in payload:
            payload = dict(payload)
            payload["data_date"] = date.today()

        try:
            return BaseRepository.upsert_many(
                table="macro_market_data",
                unique_columns=["data_date"],
                rows=[payload],
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to upsert macro data: {e}",
                details={"keys": list(payload.keys())},
            ) from e
