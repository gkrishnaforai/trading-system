from __future__ import annotations

from datetime import date, datetime, time
from typing import Iterable, List, Optional

import pandas as pd


def _get_xnys_calendar():
    try:
        import exchange_calendars as xcals  # type: ignore

        return xcals.get_calendar("XNYS")
    except Exception:
        return None


def expected_trading_days(start: date, end: date) -> List[date]:
    """Return expected NYSE trading sessions in [start, end] (inclusive).

    Falls back to business days if exchange calendar is not available.
    """
    cal = _get_xnys_calendar()
    if cal is None:
        return list(pd.bdate_range(start=start, end=end).date)

    sessions = cal.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    return list(sessions.date)


def expected_intraday_15m_timestamps(start: date, end: date) -> List[pd.Timestamp]:
    """Return expected 15m bar timestamps in UTC for NYSE sessions in [start, end].

    - Uses exchange_calendars when available (holiday-aware, timezone-aware)
    - Falls back to 09:30-16:00 America/New_York on business days when not available

    The timestamps returned are the bar start times (e.g., 09:30, 09:45, ..., 15:45).
    """
    cal = _get_xnys_calendar()
    if cal is None:
        days = pd.bdate_range(start=start, end=end)
        out: List[pd.Timestamp] = []
        for d in days:
            day = d.date()
            open_dt = pd.Timestamp(datetime.combine(day, time(9, 30)), tz="America/New_York")
            close_dt = pd.Timestamp(datetime.combine(day, time(16, 0)), tz="America/New_York")
            # last bar starts at 15:45
            rng = pd.date_range(open_dt, close_dt - pd.Timedelta(minutes=15), freq="15min", tz="America/New_York")
            out.extend([ts.tz_convert("UTC") for ts in rng])
        return out

    schedule = cal.schedule.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    out = []
    for _, row in schedule.iterrows():
        open_ts = row["market_open"]
        close_ts = row["market_close"]
        # timestamps are tz-aware
        rng = pd.date_range(open_ts, close_ts - pd.Timedelta(minutes=15), freq="15min", tz=open_ts.tz)
        out.extend([ts.tz_convert("UTC") for ts in rng])
    return out
