"""Update stock_insights_snapshots primary key to include source.

This prevents snapshots from different sources on the same day from overwriting each other.

Executed by migrations/migrate.py (it runs create_*, add_*, update_* python modules).
"""

from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)


def create_trading_signals_table():
    """Migration entrypoint expected by migrate.py (legacy naming)."""

    statements = [
        """
        ALTER TABLE IF EXISTS stock_insights_snapshots
          DROP CONSTRAINT IF EXISTS stock_insights_snapshots_pkey;
        """,
        """
        ALTER TABLE IF EXISTS stock_insights_snapshots
          ADD CONSTRAINT stock_insights_snapshots_pkey
          PRIMARY KEY (stock_symbol, insights_date, source);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_stock_insights_symbol_date_source
          ON stock_insights_snapshots(stock_symbol, insights_date DESC, source);
        """,
    ]

    for stmt in statements:
        db.execute_update(stmt)

    logger.info("✅ Updated stock_insights_snapshots primary key to (stock_symbol, insights_date, source)")
