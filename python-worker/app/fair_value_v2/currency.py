"""Statement-currency normalization for fair_value_v2.

FMP reports foreign listers' fundamentals in REPORTED currency
(e.g. TSM statements are TWD) while their ADR shares + price are USD.
The DSL consumed raw statement values → DCF divided TWD cash flow by
ADR share count, producing ~5x-inflated fair values (TSM fv read
$2,133 vs spot $425; 2133 ≈ the unconverted number, not a real fv).

Fix at extraction: when the enclosing statement row declares
`reportedCurrency` != USD, scale money leaf values by the FX rate.
Share counts, ratios, margins and dates are never scaled.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# keys whose numeric leaf must NOT be FX-scaled — share counts,
# ratios, identifiers, dates. Substring match on the lowered key.
# NOTE: per-share money keys (revenuePerShare, bookValuePerShareTTM,
# eps…) DO scale — only share *counts* are excluded.
_NO_SCALE_SUBSTR = (
    "shsout", "outstanding", "issued", "currency",
    "date", "symbol", "period", "year", "quarter", "link", "cik",
    "ratio", "margin", "growth", "percent", "yield", "days",
    "count", "number", "rank", "score",
)
_NO_SCALE_EXACT = {"id", "uuid", "index", "pe", "pettm", "trailingpe",
                   "peratio", "priceearningsratio", "roe", "roettm",
                   "returnonequity", "returnonequityttm"}

# Money keys that may lack a reportedCurrency marker in their row
# (e.g. fmp_key_metrics_ttm.marketCap is TWD for TSM but carries no
# currency field). Only these get the symbol-level fallback scale.
KNOWN_MONEY_KEYS = {
    "marketcap", "marketcapttm", "enterprisevalue", "enterprisevaluettm",
    "eps", "epsforward", "epsforwardttm", "epsnextyear",
    "epsestimatednextyear", "epsttm", "epsdiluted", "epsdilutedttm",
    "netincomepershare", "netincomepersharettm", "bookvaluepershare",
    "bookvaluepersharettm", "tangiblebookvaluepersharettm",
    "revenuepersharettm", "freecashflowpersharettm",
    "operatingcashflowpersharettm", "capexpersharettm",
    "dividendpersharettm", "cashpersharettm",
    "ebitdattm", "netincomettm", "freecashflowttm",
    "operatingcashflowttm", "revenuettm", "grossprofitttm",
    "capittm", "dividendpaidttm",
}

_fx_cache: dict[tuple, tuple[float, float]] = {}  # (ccy, date|'live') -> (rate, ts)
_FX_TTL = 12 * 3600


def usd_per_unit(ccy: str, as_of=None) -> Optional[float]:
    """USD value of 1 unit of `ccy` (TWD -> ~0.031) via yfinance FX.

    With `as_of` given, returns the last close on/before that date —
    point-in-time FX, consistent with the rest of the feature store.
    Without it, returns the current rate. Historical fetch falls back
    to the latest quote if the pair has no pre-as_of history."""
    c = (ccy or "").upper().strip()
    if not c or c == "USD":
        return 1.0 if c == "USD" else None
    day = None
    if as_of is not None:
        try:
            day = as_of.date() if hasattr(as_of, "date") else as_of
        except Exception:
            day = None
    key = (c, day.isoformat() if day else "live")
    hit = _fx_cache.get(key)
    if hit and time.time() - hit[1] < _FX_TTL:
        return hit[0]
    rate = None
    try:
        import yfinance as yf
        t = yf.Ticker(f"{c}USD=X")
        if day is not None:
            from datetime import timedelta
            h = t.history(start=day - timedelta(days=10),
                          end=day + timedelta(days=1))
            if h is not None and not h.empty:
                rate = float(h["Close"].iloc[-1])
        if not rate:
            rate = (t.fast_info or {}).get("last_price") \
                or (t.fast_info or {}).get("lastPrice")
            if not rate:
                h = t.history(period="5d")
                if h is not None and not h.empty:
                    rate = float(h["Close"].iloc[-1])
    except Exception as exc:
        logger.debug("fx fetch %sUSD failed: %s", c, exc)
    if rate:
        rate = float(rate)
        _fx_cache[key] = (rate, time.time())
    return rate


def is_money_key(key: object) -> bool:
    """Numeric leaf is money if its name isn't a share-count /
    ratio / identifier / date field."""
    k = str(key or "").lower()
    if not k or k in _NO_SCALE_EXACT:
        return False
    return not any(s in k for s in _NO_SCALE_SUBSTR)


def scale(key: object, value: Optional[float],
          currency: Optional[str],
          require_known: bool = False,
          as_of=None) -> Tuple[Optional[float], Optional[str]]:
    """(possibly-scaled value, fx_note). Returns (value, None) when
    USD/unknown; (scaled, 'TWD@0.0312@2026-10-05') on success; (None,
    'TWD:no_fx') when the rate can't be fetched — a missing number is
    honest, a TWD-as-USD number is not.

    require_known=True is the unmarked-payload fallback: only keys in
    KNOWN_MONEY_KEYS scale (a ratio in an unmarked row stays put)."""
    c = (currency or "").upper().strip()
    if value is None or not c or c == "USD":
        return value, None
    if require_known and str(key or "").lower() not in KNOWN_MONEY_KEYS:
        return value, None
    if not is_money_key(key):
        return value, f"{c}:unscaled_key"
    rate = usd_per_unit(c, as_of=as_of)
    if not rate:
        return None, f"{c}:no_fx"
    day = ""
    try:
        day = f"@{as_of.date().isoformat()}" if as_of is not None else ""
    except Exception:
        day = ""
    return value * rate, f"{c}@{rate:.4f}{day}"
