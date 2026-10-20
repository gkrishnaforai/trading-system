"""Short-data loader — Massive (Polygon) → short_interest /
short_volume / share_float.

Data contract (FINRA semantics matter — do not blur these):

- short_interest = biweekly POSITION snapshot at settlement_date.
  Stale by design (up to ~2w lag). It says how crowded the short
  trade WAS, not what it is right now.
- short_volume = daily FLOW of short-sale orders — NOT positions.
  A high ratio alone is routine (market-making); the signal lives
  in the TREND during a rally. Covering buys are not marked short,
  so a FALLING ratio while price rises is the covering signature;
  a RISING ratio is new shorts pressing into strength.
- short_percent = short_interest / shares_outstanding. We lack a
  true free-float feed, so this is % of shares outstanding — a
  usable but slightly conservative proxy (% float reads higher).

Rate budget: the Massive key is ~5 req/min SHARED across every job
using it. This loader therefore (a) only pulls stale symbols,
(b) paces calls through a token bucket, (c) never hammers 429s —
one backoff then it moves on. A partial run is success; the next
run picks up the rest.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any, Optional

import requests

from app.config import settings
from app.observability.logging import get_logger

logger = get_logger("short_data")

_BASE = "https://api.massive.com"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "trading-system/short-data"})

# token bucket shared within a process; conservative under the
# shared-key free tier
_MIN_INTERVAL_S = 26.0      # ~2.3 calls/min
_last_call = [0.0]


def _pace() -> None:
    wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()


def _get(path: str, params: dict) -> Optional[dict]:
    """One request with a single 429 backoff. None on failure."""
    if not settings.massive_api_key:
        return None
    params = {**params, "apiKey": settings.massive_api_key}
    for attempt in (0, 1):
        _pace()
        try:
            r = _SESSION.get(f"{_BASE}{path}", params=params, timeout=30)
            if r.status_code == 429:
                if attempt == 0:
                    time.sleep(30)
                    continue
                return None
            if r.status_code != 200:
                logger.warning("massive %s → %s", path, r.status_code)
                return None
            return r.json()
        except Exception as e:                          # noqa: BLE001
            logger.warning("massive %s error: %s", path, e)
            return None
    return None


# ------------------------------ universe ------------------------------

def _universe() -> list[str]:
    from app.database import db
    return [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM stocks"
        " WHERE is_active AND momentum_state IS NOT NULL"
        " ORDER BY symbol")]


def _stale(table: str, date_col: str, symbols: list[str],
           max_age_days: int) -> list[str]:
    """Symbols whose newest row is older than max_age_days (or missing)."""
    from app.database import db
    if not symbols:
        return []
    rows = db.execute_query(
        f"SELECT symbol, max({date_col}) AS mx FROM {table}"
        " WHERE symbol = ANY(:syms) GROUP BY symbol",
        {"syms": symbols})
    have = {r["symbol"]: r["mx"] for r in rows}
    out = []
    for s in symbols:
        mx = have.get(s)
        if mx is None or (date.today() - mx).days > max_age_days:
            out.append(s)
    return out


# ------------------------------ loaders -------------------------------

def refresh_float(symbol: str) -> bool:
    """ticker details → share_float + stocks.float_shares."""
    from app.database import db
    j = _get("/v3/reference/tickers/" + symbol, {})
    res = (j or {}).get("results") or {}
    shares = res.get("share_class_shares_outstanding") \
        or res.get("weighted_shares_outstanding")
    if not shares:
        return False
    db.execute_update(
        "INSERT INTO share_float (symbol, float_date,"
        " shares_outstanding, share_float)"
        " VALUES (:s, CURRENT_DATE, :so, :so)"
        " ON CONFLICT (symbol, float_date) DO UPDATE SET"
        " shares_outstanding=EXCLUDED.shares_outstanding,"
        " share_float=EXCLUDED.share_float,"
        " updated_at=now()",
        {"s": symbol, "so": shares})
    db.execute_update(
        "UPDATE stocks SET float_shares=:f WHERE symbol=:s",
        {"f": shares, "s": symbol})
    return True


def refresh_short_interest(symbol: str, limit: int = 8) -> int:
    """Biweekly SI snapshots → short_interest. Returns rows written."""
    from app.database import db
    j = _get("/stocks/v1/short-interest",
             {"ticker": symbol, "limit": limit,
              "sort": "settlement_date.desc"})
    rows = (j or {}).get("results") or []
    if not rows:
        return 0
    fl = db.execute_query(
        "SELECT float_shares FROM stocks WHERE symbol=:s",
        {"s": symbol})
    shares = fl[0]["float_shares"] if fl else None
    n = 0
    for r in rows:
        si = r.get("short_interest")
        sd = r.get("settlement_date")
        if not si or not sd:
            continue
        pct = round(si / shares * 100, 2) if shares else None
        db.execute_update(
            "INSERT INTO short_interest (symbol, short_interest_date,"
            " short_interest, short_percent, days_to_cover,"
            " avg_daily_share_volume)"
            " VALUES (:s,:d,:si,:pct,:dtc,:adv)"
            " ON CONFLICT (symbol, short_interest_date) DO UPDATE SET"
            " short_interest=EXCLUDED.short_interest,"
            " short_percent=EXCLUDED.short_percent,"
            " days_to_cover=EXCLUDED.days_to_cover,"
            " avg_daily_share_volume=EXCLUDED.avg_daily_share_volume,"
            " updated_at=now()",
            {"s": symbol, "d": sd, "si": si, "pct": pct,
             "dtc": r.get("days_to_cover"),
             "adv": r.get("avg_daily_volume")})
        n += 1
    return n


def refresh_short_volume(symbol: str, limit: int = 15) -> int:
    """Daily short-sale volume → short_volume. Returns rows written."""
    from app.database import db
    j = _get("/stocks/v1/short-volume",
             {"ticker": symbol, "limit": limit, "sort": "date.desc"})
    rows = (j or {}).get("results") or []
    n = 0
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        db.execute_update(
            "INSERT INTO short_volume (symbol, short_volume_date,"
            " short_volume, total_volume, short_volume_percent)"
            " VALUES (:s,:d,:sv,:tv,:pct)"
            " ON CONFLICT (symbol, short_volume_date) DO UPDATE SET"
            " short_volume=EXCLUDED.short_volume,"
            " total_volume=EXCLUDED.total_volume,"
            " short_volume_percent=EXCLUDED.short_volume_percent,"
            " updated_at=now()",
            {"s": symbol, "d": d, "sv": r.get("short_volume"),
             "tv": r.get("total_volume"),
             "pct": r.get("short_volume_ratio")})
        n += 1
    return n


# ------------------------------ driver --------------------------------

def refresh(symbols: Optional[list[str]] = None,
            max_float: int = 25, max_si: int = 40,
            max_sv: int = 80) -> dict[str, Any]:
    """Staleness-aware nightly pull. Budgets keep the shared key alive:
    float >30d stale, SI >10d (biweekly feed), SV >2d (daily feed).
    SV priority goes to names currently moving — covering evidence is
    perishable."""
    from app.database import db
    symbols = symbols or _universe()
    stats = {"symbols": len(symbols), "float": 0, "si": 0, "sv": 0,
             "calls": 0, "errors": 0}

    for sym in _stale("share_float", "float_date", symbols, 30)[:max_float]:
        stats["calls"] += 1
        try:
            if refresh_float(sym):
                stats["float"] += 1
        except Exception as e:                          # noqa: BLE001
            stats["errors"] += 1
            logger.warning("float %s: %s", sym, e)

    for sym in _stale("short_interest", "short_interest_date",
                      symbols, 10)[:max_si]:
        stats["calls"] += 1
        try:
            stats["si"] += refresh_short_interest(sym)
        except Exception as e:                          # noqa: BLE001
            stats["errors"] += 1
            logger.warning("si %s: %s", sym, e)

    sv_stale = _stale("short_volume", "short_volume_date", symbols, 2)
    if len(sv_stale) > max_sv:
        movers = {r["symbol"] for r in db.execute_query(
            "SELECT DISTINCT symbol FROM ("
            "  SELECT symbol, close / NULLIF(lag(close,5) OVER"
            "    (PARTITION BY symbol ORDER BY date),0) - 1 AS r5"
            "  FROM daily_bars"
            "  WHERE symbol = ANY(:syms) AND date > CURRENT_DATE - 12"
            ") t WHERE abs(r5) > 0.07", {"syms": sv_stale})}
        sv_stale.sort(key=lambda s: (s not in movers, s))
        sv_stale = sv_stale[:max_sv]
    for sym in sv_stale:
        stats["calls"] += 1
        try:
            stats["sv"] += refresh_short_volume(sym)
        except Exception as e:                          # noqa: BLE001
            stats["errors"] += 1
            logger.warning("sv %s: %s", sym, e)

    logger.info("short-data refresh: %s", stats)
    return stats


if __name__ == "__main__":
    import sys
    syms = sys.argv[1:] or None
    print(refresh(syms))
