from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

from app.database import db


@dataclass
class NextEarningsInfo:
    earnings_date: Optional[date]
    earnings_at: Optional[datetime]
    timezone: Optional[str]
    session: Optional[str]
    earnings_id: Optional[str]
    source: Optional[str]


class EarningsIndexService:
    def get_next_earnings_for_symbol(self, symbol: str, *, today: Optional[date] = None) -> NextEarningsInfo:
        today = today or date.today()

        rows = db.execute_query(
            """
            SELECT earnings_date, earnings_at, earnings_timezone, earnings_session, earnings_id, source
            FROM earnings_data
            WHERE stock_symbol = :symbol
              AND (
                (earnings_at IS NOT NULL AND earnings_at >= NOW())
                OR (earnings_at IS NULL AND earnings_date >= :today)
              )
            ORDER BY COALESCE(earnings_at, (earnings_date::timestamp AT TIME ZONE COALESCE(earnings_timezone, 'America/New_York'))) ASC
            LIMIT 1
            """,
            {"symbol": symbol, "today": today},
        )

        if not rows:
            return NextEarningsInfo(earnings_date=None, earnings_at=None, timezone=None, session=None, earnings_id=None, source=None)

        row = rows[0]

        earnings_date = row.get("earnings_date")
        tz = row.get("earnings_timezone") or "America/New_York"
        session = row.get("earnings_session")
        earnings_at = row.get("earnings_at")

        if earnings_at is not None and getattr(earnings_at, "tzinfo", None) is None:
            earnings_at = earnings_at.replace(tzinfo=ZoneInfo("UTC"))

        if earnings_at is None and isinstance(earnings_date, date):
            local_dt = datetime.combine(earnings_date, time(0, 0), tzinfo=ZoneInfo(tz))
            earnings_at = local_dt.astimezone(ZoneInfo("UTC"))

        return NextEarningsInfo(
            earnings_date=earnings_date,
            earnings_at=earnings_at,
            timezone=tz if earnings_at is not None else None,
            session=session,
            earnings_id=row.get("earnings_id"),
            source=row.get("source"),
        )

    def update_stock_next_earnings(self, symbol: str) -> bool:
        info = self.get_next_earnings_for_symbol(symbol)

        next_earnings_time = None
        if info.earnings_at is not None and info.timezone:
            try:
                local = info.earnings_at.astimezone(ZoneInfo(info.timezone))
                next_earnings_time = local.strftime('%H:%M')
            except Exception:
                next_earnings_time = None

        db.execute_update(
            """
            UPDATE stocks
            SET next_earnings_date = :next_earnings_date,
                next_earnings_at = :next_earnings_at,
                next_earnings_timezone = :next_earnings_timezone,
                next_earnings_time = :next_earnings_time,
                next_earnings_session = :next_earnings_session,
                next_earnings_source = :next_earnings_source,
                next_earnings_earnings_id = :next_earnings_earnings_id,
                next_earnings_updated_at = NOW()
            WHERE symbol = :symbol
            """,
            {
                "symbol": symbol,
                "next_earnings_date": info.earnings_date,
                "next_earnings_at": info.earnings_at,
                "next_earnings_timezone": info.timezone,
                "next_earnings_time": next_earnings_time,
                "next_earnings_session": info.session,
                "next_earnings_source": info.source,
                "next_earnings_earnings_id": info.earnings_id,
            },
        )

        return True

    def backfill_next_earnings(self, *, limit: int = 1000) -> Dict[str, Any]:
        symbols = db.execute_query(
            """
            SELECT DISTINCT stock_symbol AS symbol
            FROM earnings_data
            ORDER BY stock_symbol
            LIMIT :limit
            """,
            {"limit": limit},
        )

        updated = 0
        for row in symbols:
            symbol = row.get("symbol")
            if not symbol:
                continue
            try:
                self.update_stock_next_earnings(symbol)
                updated += 1
            except Exception:
                continue

        return {"updated": updated, "scanned": len(symbols)}
