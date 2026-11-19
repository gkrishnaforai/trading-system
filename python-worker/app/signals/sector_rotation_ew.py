"""Sector Rotation Early Warning — leadership deterioration journal.

Answers "is the leader getting weaker, and where is strength
building?" BEFORE the sector ETF breaks — breadth and relative
strength roll over inside the cohort days before the headline
index moves. Read-only Phase 1: legs journaled daily, advisory
states — flow-dependent states stay unreachable until a real ETF-
flow source exists (missing ≠ zero).

One code path for live + replay: evaluate(source, as_of) reads
only bars <= as_of, so June-2026 backtests can't leak forward.
"""
from __future__ import annotations

import json
import logging
import statistics as st
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# sectors to watch — pilot is SMH; the SECTORS map is reused from
# sector_timing so breadth uses the same tracked-subset lists
from app.signals.sector_timing import SECTORS

BENCH = ["QQQ", "SPY", "IWM"]
DESTINATIONS = ["XLE", "XLI", "XLU", "XLF", "XLB", "XLV", "XLY",
                "XLP", "XLRE", "XLC", "IGV", "XBI", "KRE", "ITA",
                "ARKK", "TAN", "XRT"]
WATCHED = {"SMH": "semiconductors"}           # pilot

_WEIGHTS = {"pairwise_rs": 0.30, "constituent_breadth": 0.25,
            "distribution": 0.20, "etf_flows": 0.15,
            "destination_leadership": 0.10}


def _bars(sym: str, n: int, as_of: date) -> list[dict]:
    from app.database import db
    rows = db.execute_query(
        "SELECT date, open, close, high, low, volume FROM daily_bars"
        " WHERE symbol=:s AND date<=:d ORDER BY date DESC LIMIT :n",
        {"s": sym, "d": as_of, "n": n})
    return list(reversed(rows)) if rows else []


def _cl(bars: list[dict]) -> list[float]:
    return [float(b["close"]) for b in bars if b.get("close") is not None]


def _ensure_bars(symbols: list[str], as_of: date) -> None:
    """Top-up thin history once per evaluate — daily_bars only carries
    symbols a refresh job has touched, so ETFs may have no rows until
    the first read. One count pass + ONE batched refresh (the bars
    module's own dedup); failures leave legs unavailable, never fake."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT symbol, count(*) n FROM daily_bars"
            " WHERE symbol = ANY(:s) AND date <= :d GROUP BY symbol",
            {"s": list(dict.fromkeys(symbols)), "d": as_of})
        have = {r["symbol"]: int(r["n"]) for r in rows}
        thin = [s for s in symbols if have.get(s, 0) < 25]
        if thin:
            from app.market_data import bars as bars_mod
            bars_mod.refresh(thin, period="1y")
    except Exception as exc:
        logger.debug("sector_ew ensure_bars: %s", exc)


def _ret(c: list[float], n: int) -> Optional[float]:
    return (c[-1] / c[-1 - n] - 1) if len(c) > n else None


def _leg(score, **kw):
    return {"score": score, "available": True, **kw}


# ── leg 1: pairwise relative strength (30%) ──────────────────────────

def _pairwise_rs(src: str, dests: list[str], as_of: date) -> dict:
    sc = _cl(_bars(src, 26, as_of))
    if len(sc) < 21:
        return {"score": 0, "available": False}
    det = 0.0; n_pair = 0; deltas = {}
    for b in BENCH + dests:
        bc = _cl(_bars(b, 26, as_of))
        if len(bc) < 21:
            continue
        for h in (5, 10, 20):
            d = (_ret(sc, h) or 0) - (_ret(bc, h) or 0)
            if h == 20:
                deltas[b] = round(d * 100, 1)
            det -= max(0.0, -d)     # only underperformance counts
            n_pair += 1
    if not n_pair:
        return {"score": 0, "available": False}
    # det is negative-ish; normalize: each pair-horizon can
    # contribute -1 → score 0..100 deterioration
    score = min(100.0, max(0.0, -det / n_pair * 100 * 3))
    return _leg(round(score, 1), deltas_20d=deltas, pairs=n_pair)


# ── leg 2: constituent breadth (25%) — TRACKED SUBSET ────────────────

def _breadth(sector_key: str, as_of: date) -> dict:
    theme = (SECTORS.get(sector_key) or {}).get("theme") or []
    if not theme:
        return {"score": 0, "available": False, "coverage": 0}
    above20 = above50 = pos5 = pos20 = nh = nl = 0
    have = 0
    mean_ret20 = []
    for sym in theme:
        c = _cl(_bars(sym, 60, as_of))
        if len(c) < 55:
            continue
        have += 1
        sma20 = sum(c[-20:]) / 20
        sma50 = sum(c[-50:]) / 50
        above20 += c[-1] > sma20
        above50 += c[-1] > sma50
        pos5 += (c[-1] / c[-6] - 1) > 0
        pos20 += (c[-1] / c[-21] - 1) > 0
        hi20, lo20 = max(c[-20:]), min(c[-20:])
        nh += c[-1] >= hi20 * 0.999
        nl += c[-1] <= lo20 * 1.001
        mean_ret20.append(c[-1] / c[-21] - 1)
    if not have:
        return {"score": 0, "available": False, "coverage": 0}
    det = ((1 - above20 / have) * 45 + (1 - above50 / have) * 25
           + (1 - pos20 / have) * 20 + min(1, nl / max(1, nh + nl)) * 10)
    return _leg(round(det, 1), pct_above20=round(above20 / have * 100),
                pct_above50=round(above50 / have * 100),
                pct_pos20=round(pos20 / have * 100),
                net_hi_lo=nh - nl, coverage=have,
                expected=len(theme),
                equal_vs_cap=round(
                    (st.mean(mean_ret20) if mean_ret20 else 0) * 100, 1))


# ── leg 3: distribution pressure (20%) ───────────────────────────────

def _distribution(src: str, as_of: date) -> dict:
    bars = _bars(src, 15, as_of)
    if len(bars) < 10:
        return {"score": 0, "available": False}
    up_v = down_v = 0.0; loc = []; obv = 0.0
    for b in bars[1:]:
        c, o, v = (float(b.get("close") or 0),
                   float(b.get("open") or 0), float(b.get("volume") or 0))
        h, l = float(b.get("high") or c), float(b.get("low") or c)
        if c >= o:
            up_v += v; obv += v
        else:
            down_v += v; obv -= v
        loc.append((c - l) / (h - l) if h > l else 0.5)
    ratio = down_v / up_v if up_v else None
    mean_loc = sum(loc) / len(loc) if loc else 0.5
    score = 0.0
    if ratio and ratio > 1.2:
        score += min(50, (ratio - 1) * 100)
    if mean_loc < 0.35:
        score += 30
    if obv < 0:
        score += 20
    return _leg(round(min(100, score), 1), down_up_ratio=
                round(ratio, 2) if ratio else None,
                close_loc=round(mean_loc, 2), obv_sign="neg" if obv < 0
                else "pos")


# ── leg 4: destination leadership (10%) ──────────────────────────────

def _destinations(src: str, as_of: date) -> dict:
    spy = _cl(_bars("SPY", 26, as_of))
    out = []
    for d in DESTINATIONS:
        if d == src:
            continue
        c = _cl(_bars(d, 26, as_of))
        if len(c) < 21 or len(spy) < 21:
            continue
        rs5 = (_ret(c, 5) or 0) - (_ret(spy, 5) or 0)
        rs20 = (_ret(c, 20) or 0) - (_ret(spy, 20) or 0)
        score = max(0.0, rs20 * 100 * 8 + rs5 * 100 * 4)
        out.append({"etf": d, "score": round(score, 1),
                    "rs_20d": round(rs20 * 100, 1)})
    out.sort(key=lambda x: -x["score"])
    return _leg(round(out[0]["score"], 1) if out else 0,
                leaderboard=out[:5])


# ── compose ──────────────────────────────────────────────────────────

def evaluate(source_etf: str, as_of: date,
             destinations: Optional[list[str]] = None) -> dict:
    sector_key = next((k for k, v in SECTORS.items()
                       if v.get("etf") == source_etf), None)
    dests = destinations or [d for d in DESTINATIONS if d != source_etf]
    theme = (SECTORS.get(sector_key or "") or {}).get("theme") or []
    _ensure_bars([source_etf] + BENCH + dests + theme, as_of)
    legs = {
        "pairwise_rs": _pairwise_rs(source_etf, dests, as_of),
        "constituent_breadth": _breadth(sector_key or "", as_of),
        "distribution": _distribution(source_etf, as_of),
        "etf_flows": {"score": None, "available": False,
                      "status": "unavailable"},
        "destination_leadership": _destinations(source_etf, as_of),
    }
    # renormalize over available legs — missing never counts as zero
    num = den = 0.0
    for k, w in _WEIGHTS.items():
        l = legs[k]
        if l.get("available") and l.get("score") is not None:
            num += l["score"] * w
            den += w
    risk = round(num / den, 1) if den else None
    if risk is None:
        state = "unknown"
    elif risk < 25:
        state = "healthy"
    elif risk < 40:
        state = "early_deterioration"
    elif risk < 55:
        state = "rotation_developing"
    else:
        state = "rotation_probable"   # capped: confirmed needs flows
    br = legs["constituent_breadth"]
    return {"sector": source_etf, "as_of": str(as_of),
            "state": state, "risk_score": risk,
            "flow_status": "unavailable",
            "dest_scores": (legs["destination_leadership"]
                            .get("leaderboard") or []),
            "legs": legs,
            "breadth_coverage": (br.get("coverage"), br.get("expected")),
            "missing_inputs": [k for k, l in legs.items()
                               if not l.get("available")]}


def run(sources: Optional[list[str]] = None) -> dict:
    """Daily journal — watched leaders (pilot: SMH)."""
    from app.database import db
    out, errs = {}, []
    for src in (sources or list(WATCHED)):
        try:
            v = evaluate(src, date.today())
            db.execute_update(
                "INSERT INTO sector_rotation_daily (sector, as_of,"
                " state, risk_score, dest_scores, legs, flow_status,"
                " breadth_coverage, missing_inputs, detail) VALUES"
                " (:s,:d,:st,:rs,CAST(:ds AS jsonb),CAST(:lg AS jsonb),"
                " :fs,:bc,CAST(:mi AS jsonb),CAST(:dt AS jsonb))"
                " ON CONFLICT (sector, as_of) DO UPDATE SET"
                " state=EXCLUDED.state, risk_score=EXCLUDED.risk_score,"
                " dest_scores=EXCLUDED.dest_scores,"
                " legs=EXCLUDED.legs, detail=EXCLUDED.detail",
                {"s": src, "d": str(date.today()), "st": v["state"],
                 "rs": v["risk_score"],
                 "ds": json.dumps(v["dest_scores"], default=str),
                 "lg": json.dumps(v["legs"], default=str),
                 "fs": v["flow_status"],
                 "bc": (v["breadth_coverage"][0]
                        if v["breadth_coverage"][0] is not None else 0),
                 "mi": json.dumps(v["missing_inputs"]),
                 "dt": json.dumps(v, default=str)})
            out[src] = v["state"]
        except Exception as exc:
            errs.append(f"{src}: {exc}")
    return {"evaluated": len(out), "states": out, "errors": errs}


def replay(source_etf: str, start: date, end: date) -> list[dict]:
    """evaluate() for every trading day in [start,end] — the
    June-2026 acceptance harness."""
    from app.database import db
    days = [r["date"] for r in db.execute_query(
        "SELECT DISTINCT date FROM daily_bars WHERE symbol=:s"
        " AND date BETWEEN :a AND :b ORDER BY date",
        {"s": source_etf, "a": start, "b": end})]
    return [evaluate(source_etf, d) for d in days]


def read(sector: str, days: int = 30) -> list[dict]:
    from app.database import db
    try:
        return db.execute_query(
            "SELECT sector, as_of, state, risk_score, dest_scores,"
            " legs, flow_status, breadth_coverage, missing_inputs"
            " FROM sector_rotation_daily WHERE sector=:s"
            " ORDER BY as_of DESC LIMIT :n",
            {"s": sector, "n": days})
    except Exception:
        return []
