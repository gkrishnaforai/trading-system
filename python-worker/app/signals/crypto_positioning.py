"""Crypto positioning — the positioning layer behind crypto's
macro vote. The x-asset check watches BTC's 5d move; this watches
the flows, leverage, supply and trend underneath it.

Four signal groups, each a banded vote (bullish|warning|neutral),
never a fabricated composite:

  trend_leadership   BTC vs SMA200 (reclaim/hold vs breakdown) +
                     BTC-QQQ RS-20d — computable from stored bars
  stablecoin_supply  DefiLlama circulating USD + own-journal delta
  futures_leverage   Binance BTCUSDT OI 7d — "OI rising while price
                     falls" is the warning; leverage reset is bullish
  etf_flows          Farside daily table scrape — fragile, journaled
                     missing on failure (flows ≠ price, treat as
                     corroboration not signal)

Every fetch rides the shared breaker + fetch_failures ledger.
Journal first, calibrate later — same contract as the structural
layer and metals engine.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Optional

import requests

from app.utils.http_resilience import breaker, fail, ProviderDown

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "trading-system research contact@example.com"}
_LLAMA = "https://stablecoins.llama.fi"
_BINANCE = "https://fapi.binance.com/futures/data/openInterestHist"
# Binance 451s US IPs; Bybit 403s bots; Kraken futures is the
# free public fallback — point-in-time OI, trend from own journal
_KRAKEN = "https://futures.kraken.com/derivatives/api/v3/tickers"
_FARSIDE = "https://farside.co.uk/btc/"


def _get(url: str, name: str, timeout: int = 15) -> Any:
    if not breaker(name).allow():
        raise ProviderDown(f"{name} circuit open — failing fast")
    try:
        r = requests.get(url, headers=_UA, timeout=timeout)
        r.raise_for_status()
        breaker(name).success()
        return r
    except Exception as e:
        fail(name, url, e)
        raise


# ── signal 1: trend + leadership (stored bars, no provider risk) ─────

def _trend_leadership() -> dict:
    from app.market_data import bars as bars_mod
    out: dict[str, Any] = {}
    btc = bars_mod.live("BTC-USD", period="1y")
    qqq = bars_mod.live("QQQ", period="1y")
    if len(btc) >= 210:
        closes = [b.close for b in btc]
        sma200 = sum(closes[-200:]) / 200
        sma200_prev = sum(closes[-210:-10]) / 200
        out["price"] = closes[-1]
        out["sma200"] = round(sma200, 2)
        out["above_sma200"] = closes[-1] > sma200
        out["sma200_slope"] = round((sma200 - sma200_prev) / sma200_prev * 100, 3)
    if len(btc) >= 21 and len(qqq) >= 21:
        r_btc = btc[-1].close / btc[-21].close - 1
        r_qqq = qqq[-1].close / qqq[-21].close - 1
        out["rs_20d"] = round(r_btc - r_qqq, 4)
    if not out:
        return {"available": False, "vote": "neutral", "note": "no bars"}
    above = out.get("above_sma200")
    rs = out.get("rs_20d")
    slope = out.get("sma200_slope")
    if above is True and (rs or 0) > 0:
        vote = "bullish"
        note = "above 200d and outperforming QQQ — leadership returning"
    elif above is False or (rs or 0) < -0.05:
        vote = "warning"
        note = ("below 200d" if above is False else
                "underperforming QQQ by >5%/20d")
        if slope is not None and slope < -0.05:
            note += " (200d slope falling)"
    else:
        vote = "neutral"
        note = "mixed trend read"
    out.update({"available": True, "vote": vote, "note": note})
    return out


# ── signal 2: stablecoin supply (DefiLlama) ──────────────────────────

def _stablecoin_supply() -> dict:
    try:
        data = _get(f"{_LLAMA}/stablecoins?includePrices=true",
                    "defillama").json()
        total = sum(
            float((a.get("circulating") or {}).get("peggedUSD") or 0)
            for a in (data or {}).get("peggedAssets") or [])
        # trend from our own journal — no delta on day 1, honest
        from app.database import db
        try:
            prev = db.execute_query(
                "SELECT payload->'stablecoin_supply'->>'total_usd' AS t"
                " FROM crypto_positioning_daily ORDER BY as_of DESC"
                " LIMIT 1")
            prev_total = float(prev[0]["t"]) if prev and prev[0].get("t") else None
        except Exception:
            prev_total = None
        d_pct = (total / prev_total - 1) if prev_total else None
        if d_pct is not None and d_pct < -0.005:
            vote, note = "warning", "supply contracting — liquidity leaving"
        elif d_pct is not None and d_pct > 0.005:
            vote, note = "bullish", "supply expanding — dry powder returning"
        else:
            vote, note = "neutral", "supply flat"
        return {"available": True, "total_usd": round(total),
                "d_chg_pct": round(d_pct * 100, 3) if d_pct is not None else None,
                "vote": vote, "note": note}
    except Exception as e:
        logger.warning("stablecoin supply fetch failed: %s", e)
        return {"available": False, "vote": "neutral",
                "note": "supply source unavailable"}


# ── signal 3: futures leverage (Binance public) ──────────────────────

def _futures_leverage() -> dict:
    """OI rising while price falls = levered longs adding into
    weakness (warning); OI falling = leverage flushed (bullish).
    OI trend from own journal where the venue gives no history."""
    try:
        oi_now, src = None, None
        try:
            rows = _get(
                f"{_BINANCE}?symbol=BTCUSDT&period=1d&limit=7",
                "binance").json() or []
            if rows:
                oi_now = float(rows[-1]["sumOpenInterest"])
                oi_then = float(rows[0]["sumOpenInterest"])
                src = "binance"
            else:
                oi_then = None
        except Exception:
            oi_then = None          # US IP 451 — try the fallback
        if oi_now is None:
            data = _get(_KRAKEN, "kraken").json()
            t = next((x for x in (data or {}).get("tickers") or []
                      if x.get("symbol") == "PF_XBTUSD"), None)
            if not t or t.get("openInterest") is None:
                return {"available": False, "vote": "neutral",
                        "note": "OI source unavailable"}
            oi_now, src = float(t["openInterest"]), "kraken"
            oi_then = None
        # journal-based OI trend when the venue gives no history
        if oi_then is None:
            try:
                from app.database import db
                prev = db.execute_query(
                    "SELECT payload->'futures_leverage'->>'oi_btc' AS o"
                    " FROM crypto_positioning_daily"
                    " WHERE as_of >= CURRENT_DATE - INTERVAL '7 days'"
                    " ORDER BY as_of LIMIT 1")
                oi_then = (float(prev[0]["o"])
                           if prev and prev[0].get("o") else None)
            except Exception:
                oi_then = None
        oi_chg = oi_now / oi_then - 1 if oi_then else None
        # direction of BTC over the same window — from stored bars
        price_chg = None
        try:
            from app.market_data import bars as bars_mod
            btc = bars_mod.live("BTC-USD", period="1mo")
            if len(btc) >= 7:
                price_chg = btc[-1].close / btc[-7].close - 1
        except Exception:
            pass
        out = {"available": True, "source": src,
               "oi_btc": round(oi_now),
               "oi_chg_7d_pct": round(oi_chg * 100, 2)
               if oi_chg is not None else None,
               "price_chg_7d_pct": round(price_chg * 100, 2)
               if price_chg is not None else None}
        if oi_chg is None:
            out.update(vote="neutral",
                       note="OI baseline journaled — trend needs 7d "
                            "of history")
        elif oi_chg > 0.05 and (price_chg or 0) < -0.02:
            out.update(vote="warning",
                       note="OI rising while price falls — levered "
                            "longs still adding into weakness")
        elif oi_chg < -0.05:
            out.update(vote="bullish",
                       note="OI falling — leverage flushed, cleaner tape")
        else:
            out.update(vote="neutral", note="leverage stable")
        return out
    except Exception as e:
        logger.warning("binance OI fetch failed: %s", e)
        return {"available": False, "vote": "neutral",
                "note": "OI source unavailable"}


# ── signal 4: spot ETF flows (Farside scrape — fragile) ─────────────

def _etf_flows() -> dict:
    """Best-effort: Farside publishes daily net-flow tables. Parse the
    TOTAL column rows; on any shape change we journal unavailable —
    flows corroborate, never gate."""
    try:
        html = _get(_FARSIDE, "farside").text
        # rows like: <td>Total</td><td>..</td> then a $M number column
        totals = re.findall(
            r"Total</t[dh]>\s*(?:<t[dh][^>]*>[^<]*</t[dh]>\s*)*?"
            r"<t[dh][^>]*>\s*\$?\(?\$?([\d,\.]+)", html)
        if not totals:
            return {"available": False, "vote": "neutral",
                    "note": "flow table not parsed — shape changed"}
        last5 = [float(t.replace(",", "")) for t in totals[:5]]
        net5 = sum(last5)
        vote = ("bullish" if net5 > 200 else "warning" if net5 < -200
                else "neutral")
        return {"available": True, "last5_usd_m": last5,
                "net_5d_usd_m": round(net5), "vote": vote,
                "note": f"~${net5:,.0f}M net over last 5 sessions"}
    except Exception as e:
        logger.warning("farside flow fetch failed: %s", e)
        return {"available": False, "vote": "neutral",
                "note": "flow source unavailable"}


# ── compose + journal ────────────────────────────────────────────────

def evaluate() -> dict:
    """All legs, missing-is-honest. Verdict = banded rollup of the
    four votes: ≥2 bullish & 0 warning → accumulation; ≥2 warning →
    distribution; else neutral."""
    legs = {
        "trend_leadership": _trend_leadership(),
        "stablecoin_supply": _stablecoin_supply(),
        "futures_leverage": _futures_leverage(),
        "etf_flows": _etf_flows(),
    }
    votes = [v["vote"] for v in legs.values() if v.get("available")]
    bull = votes.count("bullish")
    warn = votes.count("warning")
    stance = ("accumulation" if bull >= 2 and warn == 0 else
              "distribution" if warn >= 2 else "neutral")
    return {"as_of": date.today().isoformat(), "stance": stance,
            "votes": {"bullish": bull, "warning": warn,
                      "available": len(votes)},
            "legs": legs}


def run() -> dict:
    """Daily journal — the calibration substrate. Every day's
    banded votes land so 30/60/90d forward grading can say which
    signal actually preceded crypto rallies."""
    from app.database import db
    v = evaluate()
    db.execute_update(
        "INSERT INTO crypto_positioning_daily (as_of, stance, legs,"
        " payload) VALUES (:d,:s,CAST(:l AS jsonb),CAST(:p AS jsonb))"
        " ON CONFLICT (as_of) DO UPDATE SET stance=EXCLUDED.stance,"
        " legs=EXCLUDED.legs, payload=EXCLUDED.payload",
        {"d": v["as_of"], "s": v["stance"],
         "l": json.dumps(v["legs"], default=str),
         "p": json.dumps(v, default=str)})
    return v


def read(days: int = 30) -> list[dict]:
    from app.database import db
    try:
        return db.execute_query(
            "SELECT as_of, stance, legs, payload"
            " FROM crypto_positioning_daily ORDER BY as_of DESC"
            " LIMIT :n", {"n": days})
    except Exception:
        return []
