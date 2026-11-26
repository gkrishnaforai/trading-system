"""Intraday Recovery & VWAP Confirmation — deterministic 5-minute
session engine.

Answers one question: after a selloff, which watched names show
SUSTAINED buying — VWAP hold + relative strength + time-adjusted
volume + sector participation — vs a relief rally vs a failed
rebound. Up 8% is not a signal.

Data flow (one producer, one journal):

    intraday-recovery job (*/5 RTH)
      ├─ refresh_bars() — batched 5m fetch, RTH-only upsert →
      │    intraday_bars (symbol, bar_ts, o/h/l/c/v)
      └─ evaluate_session() — features + YAML thresholds → signal,
           journaled per completed bar → intraday_recovery_evals

Overlay contract (same as tape_live/swing_live): this is session
context — it annotates, never rewrites the canonical daily checklist.
Missing data BLOCKS (no bar, no benchmark, no history → DATA_BLOCKED)
rather than scoring on guesses. LLM surfaces may narrate legs;
nothing here calls one.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import yaml

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
CFG_PATH = Path(__file__).parent / "intraday_recovery.yaml"
ENGINE_VERSION = "1.1"
_cfg: Optional[dict] = None


def _cfg_get() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = yaml.safe_load(CFG_PATH.read_text())
    return _cfg


def _eng() -> dict:
    return _cfg_get().get("engine") or {}


def rules_version() -> str:
    from app.signals.pulse_engine import spec_version
    return spec_version("rules", CFG_PATH, _cfg_get())


# ---------------- universe -------------------------------------------------

def universe() -> list[str]:
    """ai_infra.yaml canonical universe — the watch scope is a
    market-structure gauge, so it covers the whole sector scope:
    a leader we don't hold still drives the sector tape. Book
    membership never gates evaluation (same discipline as
    fragility's fixed _AI_BASKET)."""
    cfg = yaml.safe_load(
        (Path(__file__).parent.parent
         / "research" / "sectors" / "ai_infra.yaml").read_text())
    return sorted(s for s in
                  (cfg.get("universe") or {}).get("symbols") or []
                  if isinstance(s, str))


def benchmarks() -> list[str]:
    b = list((_eng().get("universe") or {}).get("benchmarks")
             or ["SMH", "QQQ", "SPY"])
    vix = (_eng().get("universe") or {}).get("vix")
    return [*b, *([vix] if vix else [])]


# ---------------- tables ---------------------------------------------------

def ensure_tables() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS intraday_bars ("
        " symbol TEXT NOT NULL, bar_ts TIMESTAMPTZ NOT NULL,"
        " open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,"
        " volume NUMERIC, PRIMARY KEY (symbol, bar_ts))")
    db.execute_update(
        "CREATE INDEX IF NOT EXISTS idx_ibars_sym_ts"
        " ON intraday_bars (symbol, bar_ts DESC)")
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS intraday_recovery_evals ("
        " id bigserial PRIMARY KEY,"
        " symbol TEXT NOT NULL, as_of DATE NOT NULL,"
        " bar_ts TIMESTAMPTZ NOT NULL,"
        " signal TEXT NOT NULL, score NUMERIC,"
        " legs JSONB,"
        " rules_version TEXT NOT NULL, engine_version TEXT NOT NULL,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " UNIQUE (symbol, bar_ts))")
    db.execute_update(
        "CREATE INDEX IF NOT EXISTS idx_ire_sym_asof"
        " ON intraday_recovery_evals (symbol, as_of DESC)")
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS intraday_recovery_daily ("
        " symbol TEXT NOT NULL, as_of DATE NOT NULL,"
        " final_signal TEXT, final_score NUMERIC,"
        " recovery_score NUMERIC, accumulation_score NUMERIC,"
        " max_vwap_hold_min INT, confirmed_minutes INT,"
        " end_delta_vol NUMERIC, end_rvol NUMERIC,"
        " n_evals INT, n_transitions INT, signals JSONB,"
        " first_eval TIMESTAMPTZ, last_eval TIMESTAMPTZ,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " PRIMARY KEY (symbol, as_of))")


# ---------------- bar ingest ------------------------------------------------

def refresh_bars(symbols: list[str]) -> dict[str, Any]:
    """Batched 5m fetch → RTH-only upsert. Symbol-keyed reads —
    positional indexing misaligns when a ticker fails (same bug class
    as live_overlay; SPY must never take a neighbor's price)."""
    import yfinance as yf
    from app.database import db
    ensure_tables()
    if not symbols:
        return {"updated": 0}
    df = yf.download(" ".join(symbols), period="5d", interval="5m",
                     group_by="ticker", threads=True, progress=False,
                     auto_adjust=True, timeout=30)
    if df is None or df.empty:
        return {"updated": 0, "note": "no intraday data"}
    kept = 0
    for sym in symbols:
        try:
            try:
                sub = df[sym]
            except (KeyError, TypeError):
                continue
            sub = sub.dropna(subset=["Close"])
            if sub.empty:
                continue
            rows = []
            for ts, r in sub.iterrows():
                et = ts.tz_convert(_ET) if ts.tzinfo else ts.tz_localize(
                    "UTC").tz_convert(_ET)
                if not (dtime(9, 30) <= et.time() <= dtime(16, 0)):
                    continue                      # RTH only
                rows.append({
                    "s": sym, "t": et.to_pydatetime(),
                    "o": float(r["Open"]) if r["Open"] == r["Open"] else None,
                    "h": float(r["High"]) if r["High"] == r["High"] else None,
                    "l": float(r["Low"]) if r["Low"] == r["Low"] else None,
                    "c": float(r["Close"]),
                    "v": float(r["Volume"]) if r["Volume"] == r["Volume"] else 0})
            if not rows:
                continue
            db.execute_many(
                "INSERT INTO intraday_bars"
                " (symbol, bar_ts, open, high, low, close, volume)"
                " VALUES (:s,:t,:o,:h,:l,:c,:v)"
                " ON CONFLICT (symbol, bar_ts) DO UPDATE SET"
                " open=EXCLUDED.open, high=EXCLUDED.high,"
                " low=EXCLUDED.low, close=EXCLUDED.close,"
                " volume=EXCLUDED.volume",
                rows)
            kept += 1
        except Exception as exc:
            logger.debug("ibars %s: %s", sym, exc)
    # retention — bars only exist for RVOL baselines (20 sessions) and
    # same-day replay: 35 days covers ~25 sessions with holiday slack.
    # Raw evals keep 10 days for session stories; the durable record
    # lives in intraday_recovery_daily (rollup, kept forever).
    try:
        db.execute_update(
            "DELETE FROM intraday_bars"
            " WHERE bar_ts < now() - interval '35 days'")
        db.execute_update(
            "DELETE FROM intraday_recovery_evals"
            " WHERE as_of < CURRENT_DATE - 10")
    except Exception:
        pass
    return {"updated": kept}


def _load_bars(sym: str, days: int = 30) -> list[dict]:
    """Stored 5m bars oldest→newest for one symbol. Postgres NUMERIC
    returns Decimal — coerce to float here so every feature
    (vwap/rs/rvol) sees plain floats."""
    from app.database import db
    out = []
    for r in db.execute_query(
            "SELECT bar_ts, open, high, low, close, volume"
            " FROM intraday_bars WHERE symbol=:s"
            " AND bar_ts > now() - (:d || ' days')::interval"
            " ORDER BY bar_ts", {"s": sym, "d": days}):
        d = dict(r)
        for k in ("open", "high", "low", "close", "volume"):
            d[k] = float(d[k]) if d[k] is not None else None
        out.append(d)
    return out


# ---------------- features --------------------------------------------------

def _vwap(bars: list[dict]) -> list[float]:
    """Session cumulative VWAP over typical price."""
    tpv, vol, out = 0.0, 0.0, []
    for b in bars:
        tp = ((b["high"] or b["close"]) + (b["low"] or b["close"])
              + b["close"]) / 3
        v = b["volume"] or 0
        tpv += tp * v
        vol += v
        out.append(tpv / vol if vol else b["close"])
    return out


def _above_vwap(bars: list[dict]) -> Optional[bool]:
    """Latest close vs session VWAP for a benchmark — None when the
    feed is missing (missing never passes)."""
    vw = _vwap(bars) if bars else None
    return (bars[-1]["close"] > vw[-1]) if vw else None


def _delta_vol(bars: list[dict]) -> Optional[float]:
    """Directional volume — close-location-value per bar,
    volume-weighted across the session, ∈ [-1, +1].
    + = closes near bar highs on volume (accumulation signature),
    − = closes near bar lows on volume (distribution signature).
    RVOL says how MUCH traded; this says WHO was in control."""
    pv = tv = 0.0
    for b in bars:
        v = b["volume"] or 0
        h, l, c = b.get("high"), b.get("low"), b.get("close")
        if v <= 0 or h is None or l is None or c is None or h <= l:
            continue
        pv += ((c - l) - (h - c)) / (h - l) * v
        tv += v
    return round(pv / tv, 3) if tv else None


def _consec(closes: list[float], vw: list[float], above: bool) -> int:
    n = 0
    for c, v in zip(reversed(closes), reversed(vw)):
        if (c > v) == above:
            n += 1
        else:
            break
    return n


def _rs(closes: list[float], bench: list[float], bars_back: int) -> Optional[float]:
    """Return spread vs benchmark over the last `bars_back` bars, pp."""
    if len(closes) <= bars_back or len(bench) <= bars_back:
        return None
    a = closes[-1] / closes[-1 - bars_back] - 1
    b = bench[-1] / bench[-1 - bars_back] - 1
    return (a - b) * 100


def _rvol(today: list[dict], hist_sessions: list[list[dict]]) -> Optional[float]:
    """Time-of-day RVOL — today's cumulative volume at this bar vs the
    average cumulative volume at the same bar index over prior
    sessions. Comparing 10:30 volume to the full-day average is the
    classic lie; this compares like-for-like."""
    if not today or len(hist_sessions) < 1:
        return None
    idx = len(today) - 1
    cum = sum(b["volume"] or 0 for b in today)
    refs = []
    for sess in hist_sessions:
        if len(sess) > idx:
            refs.append(sum(b["volume"] or 0 for b in sess[:idx + 1]))
    if not refs:
        return None
    avg = sum(refs) / len(refs)
    return round(cum / avg, 2) if avg else None


def _opening_range(bars: list[dict], cfg: dict) -> dict:
    n = max(1, int(cfg.get("duration_minutes", 30) / 5))
    rng = bars[:n]
    if len(rng) < n or len(bars) <= n:
        return {}
    hi = max(b["high"] for b in rng)
    lo = min(b["low"] for b in rng)
    last = bars[-1]["close"]
    buf = cfg.get("breakout_buffer_pct", 0.10) / 100
    breakout = last > hi * (1 + buf)
    broke_below = last < lo
    # retest: dipped back to within tolerance of the OR high after a
    # breakout and held for retest_hold_bars closes
    tol = cfg.get("retest_tolerance_pct", 0.20) / 100
    hold_n = int(cfg.get("retest_hold_bars", 2))
    closes = [b["close"] for b in bars[n:]]
    retest = False
    for i in range(len(closes)):
        if closes[i] > hi * (1 + buf):          # broke out
            for j in range(i + 1, len(closes)):
                if abs(closes[j] / hi - 1) <= tol:      # touched the line
                    retest = all(c >= hi * (1 - tol)
                                 for c in closes[j:j + hold_n])
            if retest:
                break
    return {"or_high": round(hi, 2), "or_low": round(lo, 2),
            "breakout": breakout, "broke_below": broke_below,
            "retest_hold": retest,
            "in_range": not breakout and not broke_below}


def _higher_low(bars: list[dict], lookback: int) -> Optional[bool]:
    if len(bars) < lookback * 2:
        return None
    recent = min(b["low"] for b in bars[-lookback:])
    prior = min(b["low"] for b in bars[-2 * lookback:-lookback])
    return recent > prior


def _recovery_ctx(sym: str, cfg: dict) -> dict:
    """Daily-bar context — how deep the selloff and how much has been
    recovered. Annotation + the recovery_quality score leg."""
    try:
        from app.market_data import bars as bars_mod
        books = bars_mod.load([sym], days=cfg.get("selloff_lookback_days", 10) + 5)
        bars = books.get(sym) or []
        if len(bars) < 5:
            return {}
        closes = [b.close for b in bars]
        win = closes[-cfg.get("selloff_lookback_days", 10):]
        hi, lo = max(win), min(win)
        last = closes[-1]
        dd = (lo / hi - 1) * 100 if hi else None
        rec = ((last - lo) / (hi - lo) * 100) if hi and lo and hi != lo else None
        return {"selloff_dd_pct": round(dd, 1) if dd is not None else None,
                "pct_recovered": round(rec, 1) if rec is not None else None}
    except Exception:
        return {}


# ---------------- evaluation ------------------------------------------------

def _score_leg(points: float, weight: int, note: str,
               missing: bool = False) -> dict:
    return {"pts": round(points, 1), "wt": weight, "note": note,
            "missing": missing}


def _eval_symbol(sym: str, sess: list[dict], bench: dict[str, list],
                 participation: float, smh_vwap_ok: Optional[bool],
                 qqq_vwap_ok: Optional[bool],
                 vix: Optional[float], cfg: dict) -> dict:
    """One symbol's session bars → score legs + signal."""
    eng = _eng()
    dq = eng.get("data_quality") or {}
    vc = (eng.get("vwap") or {}).get("confirmation") or {}
    vf = (eng.get("vwap") or {}).get("failure") or {}
    wts = (eng.get("scoring") or {}).get("weights") or {}
    ths = (eng.get("scoring") or {}).get("thresholds") or {}

    min_bars = int(dq.get("minimum_intraday_bars", 6))
    if len(sess) < min_bars:
        return {"symbol": sym, "signal": "DATA_BLOCKED", "score": None,
                "legs": {"blocked": f"{len(sess)} bars < {min_bars}"}}

    closes = [b["close"] for b in sess]
    vw = _vwap(sess)
    if not vw or not bench.get("SMH"):
        return {"symbol": sym, "signal": "DATA_BLOCKED", "score": None,
                "legs": {"blocked": "missing vwap/benchmark"}}

    b5, b6, b12 = 1, 2, 6     # 5/10/30-minute bar counts (15m=3, 30m=6, 60m=12)
    slope_lb = int(vc.get("slope_lookback_bars", 3))

    consec_up = _consec(closes, vw, True)
    consec_dn = _consec(closes, vw, False)
    slope_ok = (vw[-1] > vw[-1 - slope_lb]) if len(vw) > slope_lb else None
    ext_pct = (closes[-1] / vw[-1] - 1) * 100 if vw[-1] else None
    dist_below = (vw[-1] / closes[-1] - 1) * 100 if closes[-1] else None
    hold_min = consec_up * 5

    rs15 = {bn: _rs(closes, bench.get(bn) or [], 3)
            for bn in ("SMH", "QQQ")}
    rs30 = {bn: _rs(closes, bench.get(bn) or [], 6)
            for bn in ("SMH", "QQQ")}
    rs30_prev = {bn: _rs(closes[:-6], (bench.get(bn) or [])[:-6], 6)
                 for bn in ("SMH", "QQQ")}
    rs_imp = (rs30["SMH"] is not None and rs30_prev["SMH"] is not None
              and rs30["SMH"] > rs30_prev["SMH"])

    orng = _opening_range(sess, (eng.get("opening_range") or {}))
    hl = _higher_low(sess, int(
        (eng.get("recovery") or {}).get("higher_low_lookback_bars", 6)))
    rctx = _recovery_ctx(sym, eng.get("recovery") or {})

    # --- score legs ---
    legs: dict[str, dict] = {}

    # vwap_confirmation (20)
    if consec_up >= int(vc.get("strong_consecutive_closes_above", 6)) \
            and slope_ok:
        legs["vwap"] = _score_leg(20, wts.get("vwap_confirmation", 20),
                                  f"hold {hold_min}m, slope up")
    elif consec_up >= int(vc.get("minimum_consecutive_closes_above", 3)) \
            and slope_ok:
        legs["vwap"] = _score_leg(16, wts.get("vwap_confirmation", 20),
                                  f"hold {hold_min}m, slope up")
    elif consec_up >= 3:
        legs["vwap"] = _score_leg(12, wts.get("vwap_confirmation", 20),
                                  f"hold {hold_min}m, slope flat")
    elif consec_up >= 1:
        legs["vwap"] = _score_leg(6, wts.get("vwap_confirmation", 20),
                                  "above vwap, unconfirmed")
    else:
        legs["vwap"] = _score_leg(0, wts.get("vwap_confirmation", 20),
                                  f"below vwap ({consec_dn} closes)")

    # relative_strength (20) — vs SMH and QQQ over 30m
    mn = (eng.get("relative_strength") or {}).get(
        "minimum_positive_rs_pct") or {}
    st = (eng.get("relative_strength") or {}).get("strong_rs_pct") or {}
    smh30, qqq30 = rs30.get("SMH"), rs30.get("QQQ")
    if smh30 is None or qqq30 is None:
        legs["rs"] = _score_leg(0, wts.get("relative_strength", 20),
                                "rs unavailable", missing=True)
    else:
        both_strong = (smh30 >= st.get("versus_smh", 1.0)
                       and qqq30 >= st.get("versus_qqq", 0.75))
        both_pos = (smh30 >= mn.get("versus_smh", 0.25)
                    and qqq30 >= mn.get("versus_qqq", 0.25))
        pts = 20 if both_strong else 15 if both_pos else \
            8 if (smh30 >= mn.get("versus_smh", 0.25)
                  or qqq30 >= mn.get("versus_qqq", 0.25)) else 0
        legs["rs"] = _score_leg(
            pts, wts.get("relative_strength", 20),
            f"30m vs SMH {smh30:+.2f}pp · QQQ {qqq30:+.2f}pp")

    # relative_volume (10) — filled in by caller (needs history)
    legs["rvol"] = _score_leg(0, wts.get("relative_volume", 10),
                              "rvol pending", missing=True)

    # volume_quality (15) — directional volume: CLV × volume across
    # the session. Accumulation vs distribution — the axis % gain
    # and rvol both miss.
    dv = _delta_vol(sess)
    vqc = eng.get("volume_quality") or {}
    if dv is None:
        legs["vol_q"] = _score_leg(0, wts.get("volume_quality", 15),
                                   "no volume bars", missing=True)
    else:
        legs["vol_q"] = _score_leg(
            (15 if dv >= vqc.get("strong_accumulation", 0.35)
             else 12 if dv >= vqc.get("accumulation", 0.15)
             else 7 if dv > vqc.get("distribution", -0.15)
             else 3 if dv > vqc.get("strong_distribution", -0.35)
             else 0),
            wts.get("volume_quality", 15),
            f"delta_vol {dv:+.2f} — "
            + ("accumulation" if dv >= vqc.get("accumulation", 0.15)
               else "distribution" if dv <= vqc.get("distribution", -0.15)
               else "neutral"))

    # price_structure (15) — intraday higher low
    if hl is None:
        legs["structure"] = _score_leg(
            6, wts.get("price_structure", 15),
            "too few bars for higher-low read", missing=True)
    else:
        legs["structure"] = _score_leg(
            15 if hl else 0, wts.get("price_structure", 15),
            "higher low" if hl else "no higher low")

    # opening_range (10)
    if orng.get("retest_hold"):
        legs["or"] = _score_leg(10, wts.get("opening_range", 10),
                                "OR retest held")
    elif orng.get("breakout"):
        legs["or"] = _score_leg(8, wts.get("opening_range", 10),
                                "OR breakout, no retest yet")
    elif orng.get("in_range"):
        legs["or"] = _score_leg(3, wts.get("opening_range", 10),
                                "inside opening range")
    elif orng.get("broke_below"):
        legs["or"] = _score_leg(0, wts.get("opening_range", 10),
                                "below opening range")
    else:
        legs["or"] = _score_leg(0, wts.get("opening_range", 10),
                                "OR unresolved", missing=True)

    # market_breadth (5) — sector participation (0-3) + benchmark
    # VWAP confirmation (1 each: SMH, QQQ). An index-led rally where
    # the benchmarks themselves can't hold VWAP isn't confirmed.
    mc = eng.get("market_confirmation") or {}
    part = participation
    part_pts = (3 if part >= mc.get("strong_sector_participation_pct", 65)
                else 2 if part >= mc.get("minimum_sector_participation_pct", 50)
                else 1 if part >= 35 else 0)
    bench_pts = ((1 if smh_vwap_ok else 0) +
                 (1 if qqq_vwap_ok else 0))
    _vw = lambda v: ("above" if v else
                     "missing" if v is None else "below")
    legs["breadth"] = _score_leg(
        min(5, part_pts + bench_pts),
        wts.get("market_breadth", 5),
        f"sector {part:.0f}% above vwap · SMH {_vw(smh_vwap_ok)}"
        f" · QQQ {_vw(qqq_vwap_ok)}")

    # recovery_quality (5)
    pr = rctx.get("pct_recovered")
    legs["recovery"] = _score_leg(
        (5 if pr is not None and pr >= 50 else
         3 if pr is not None and pr >= 30 else
         1 if pr is not None and pr >= 15 else 0),
        wts.get("recovery_quality", 5),
        f"recovered {pr}%" if pr is not None else "no ctx",
        missing=pr is None)

    return {"symbol": sym, "legs": legs,
            "_ctx": {"consec_up": consec_up, "consec_dn": consec_dn,
                     "hold_min": hold_min, "slope_ok": slope_ok,
                     "above_vwap": closes[-1] > vw[-1],
                     "ext_pct": ext_pct, "dist_below": dist_below,
                     "rs15": rs15, "rs30": rs30, "rs_imp": rs_imp,
                     "delta_vol": dv,
                     "or": orng, "higher_low": hl,
                     "smh_vwap_ok": smh_vwap_ok,
                     "qqq_vwap_ok": qqq_vwap_ok,
                     "participation": participation, "vix": vix,
                     **rctx, "last": closes[-1],
                     "vwap": round(vw[-1], 2)}}


def _apply_rvol(res: dict, rvol: Optional[float], cfg: dict) -> None:
    th = ((_eng().get("relative_volume") or {}).get("thresholds") or {})
    w = (_eng().get("scoring") or {}).get("weights") or {}
    if rvol is None:
        res["legs"]["rvol"] = _score_leg(
            0, w.get("relative_volume", 10),
            "insufficient session history", missing=True)
        res["_ctx"]["rvol"] = None
        return
    pts = (10 if rvol >= th.get("exceptional", 2.0)
           else 8 if rvol >= th.get("strong", 1.5)
           else 5 if rvol >= th.get("normal", 1.0)
           else 3 if rvol >= th.get("weak", 0.75) else 0)
    res["legs"]["rvol"] = _score_leg(
        pts, w.get("relative_volume", 10), f"rvol {rvol}x")
    res["_ctx"]["rvol"] = rvol


# two-axis split — price recovery (did the stock recover?) vs demand
# (did institutions accumulate?). Each axis maxes at its legs' total.
_PRICE_LEGS = ("vwap", "structure", "or", "recovery")
_DEMAND_LEGS = ("rs", "vol_q", "rvol", "breadth")


def _signal(res: dict) -> dict:
    eng = _eng()
    vc = (eng.get("vwap") or {}).get("confirmation") or {}
    vf = (eng.get("vwap") or {}).get("failure") or {}
    dg = eng.get("distribution") or {}
    mc = eng.get("market_confirmation") or {}
    th = (eng.get("scoring") or {}).get("thresholds") or {}
    c = res["_ctx"]

    score = sum(l["pts"] for l in res["legs"].values())
    res["score"] = round(score, 1)
    c["recovery_score"] = round(
        2 * sum(res["legs"][k]["pts"] for k in _PRICE_LEGS
                if k in res["legs"]))
    c["accumulation_score"] = round(
        2 * sum(res["legs"][k]["pts"] for k in _DEMAND_LEGS
                if k in res["legs"]))

    sig, why = "WATCH", "no confirmation yet"
    # DISTRIBUTION — below vwap, lagging the sector, on heavy
    # sell-side volume. Worse than a failed rebound: someone is
    # actively using the strength to exit.
    if (c["consec_dn"] >= int(dg.get("consecutive_closes_below", 2))
            and (c["rs30"].get("SMH") or 0) < 0
            and (c.get("rvol") or 0) >= float(dg.get("min_rvol", 1.2))
            and (c.get("delta_vol") or 0)
            <= float(dg.get("max_delta_vol", -0.15))):
        sig, why = "DISTRIBUTION", "below vwap on heavy sell-side volume"
    # FAILED_REBOUND — below vwap + negative RS + broken opening range,
    # or a deep breach of the failure distance
    elif ((c["consec_dn"] >= int(vf.get("consecutive_closes_below", 2))
         and (c["rs30"].get("SMH") or 0) < 0
         and c["or"].get("broke_below"))
            or (c["dist_below"] or 0)
            > vf.get("maximum_distance_below_pct", 0.20)):
        sig, why = "FAILED_REBOUND", "below vwap + weak rs + broken OR"
    elif (score >= th.get("strong", 85)
          and c["consec_up"] >= int(vc.get("strong_consecutive_closes_above", 6))
          and c["slope_ok"]
          and (c["rs30"].get("SMH") or 0) > 0
          and (c.get("rvol") or 0) >= 1.5
          and (c["or"].get("breakout") or c["or"].get("retest_hold"))
          and c["smh_vwap_ok"]
          and (c.get("qqq_vwap_ok")
               or not mc.get("require_qqq_above_vwap"))
          and c["participation"] >= mc.get(
              "minimum_sector_participation_pct", 50)):
        sig, why = "STRONG_RECOVERY", "vwap 30m + rs + rvol + breadth"
    elif (score >= th.get("confirmed", 70)
          and c["consec_up"] >= int(vc.get("minimum_consecutive_closes_above", 3))
          and c["slope_ok"]
          and (c["rs30"].get("SMH") or 0) > 0
          and (c.get("rvol") is None or c["rvol"] >= 0.75)
          and c["higher_low"]):
        sig, why = "CONFIRMED_RECOVERY", "vwap 15m + rs + higher low"
    elif (score >= th.get("improving", 55)
          and c["rs_imp"]
          and not c["or"].get("broke_below")):
        sig, why = "IMPROVING", "rs improving, structure intact"

    # extension cap — far above vwap is a chase, not an entry. The
    # flag journals on every signal tier so the UI can warn even
    # when the label looks calm.
    max_ext = vc.get("maximum_extension_above_vwap_pct", 3.0)
    c["overextended"] = (c["ext_pct"] or 0) > max_ext
    if c["overextended"] \
            and sig in ("CONFIRMED_RECOVERY", "STRONG_RECOVERY"):
        sig, why = "IMPROVING", f"{c['ext_pct']:.1f}% above vwap — extended"

    res["signal"], res["why"] = sig, why
    return res


def evaluate_session() -> dict[str, Any]:
    """The job's second half — evaluate the latest completed bar for
    every universe symbol, journal per (symbol, bar_ts)."""
    from app.database import db
    ensure_tables()
    eng = _eng()
    bench_names = [b for b in benchmarks() if not b.startswith("^")]
    syms = universe()
    today = date.today()

    books = {s: _load_bars(s, days=45) for s in [*(bench_names),
                                                 *( ["^VIX"] ), *syms]}
    # session partition — today's RTH bars vs prior-session history
    def _today(bars):
        return [b for b in bars
                if b["bar_ts"].astimezone(_ET).date() == today
                and b["bar_ts"].astimezone(_ET).time() < dtime(16, 0)]

    def _prior_sessions(bars, n):
        by_day: dict[date, list] = {}
        for b in bars:
            d = b["bar_ts"].astimezone(_ET).date()
            if d != today:
                by_day.setdefault(d, []).append(b)
        days = sorted(by_day, reverse=True)[:n]
        return [by_day[d] for d in days]

    bench_today = {bn: _today(books.get(bn) or []) for bn in bench_names}
    bench_close = {bn: [b["close"] for b in bars]
                   for bn, bars in bench_today.items()}

    # sector participation + SMH vwap + vix — the breadth ctx all
    # symbols share
    vix = None
    try:
        vbars = _today(books.get("^VIX") or [])
        vix = vbars[-1]["close"] if vbars else None
    except Exception:
        pass
    smh_ok = _above_vwap(bench_today.get("SMH") or [])
    qqq_ok = _above_vwap(bench_today.get("QQQ") or [])

    above = 0
    counted = 0
    for s in syms:
        tb = _today(books.get(s) or [])
        if len(tb) >= 3:
            counted += 1
            vw = _vwap(tb)
            if tb[-1]["close"] > vw[-1]:
                above += 1
    participation = (above / counted * 100) if counted else 0.0

    rvol_days = int((_eng().get("relative_volume") or {})
                    .get("baseline_days", 20))
    rv, en = rules_version(), ENGINE_VERSION
    out: dict[str, Any] = {}
    journaled = 0
    for s in syms:
        try:
            all_b = books.get(s) or []
            sess = _today(all_b)
            res = _eval_symbol(s, sess, bench_close, participation,
                               smh_ok, qqq_ok, vix, eng)
            if res.get("signal") != "DATA_BLOCKED":
                hist = _prior_sessions(all_b, rvol_days)
                _apply_rvol(res, _rvol(sess, hist), eng)
            res = _signal(res) if res.get("signal") != "DATA_BLOCKED" \
                else res
            res["as_of"] = (sess[-1]["bar_ts"].isoformat()
                            if sess else None)
            out[s] = res
            if sess:
                db.execute_update(
                    "INSERT INTO intraday_recovery_evals"
                    " (symbol, as_of, bar_ts, signal, score, legs,"
                    " rules_version, engine_version)"
                    " VALUES (:s, :d, :t, :sig, :sc,"
                    " CAST(:l AS jsonb), :rv, :en)"
                    " ON CONFLICT (symbol, bar_ts) DO NOTHING",
                    {"s": s, "d": today,
                     "t": sess[-1]["bar_ts"], "sig": res["signal"],
                     "sc": res.get("score"),
                     "l": json.dumps(
                         {"legs": {k: v for k, v in
                                   res["legs"].items()},
                          "ctx": res["_ctx"]},
                         default=str),
                     "rv": rv, "en": en})
                journaled += 1
        except Exception as exc:
            logger.debug("ireval %s: %s", s, exc)
            out[s] = {"symbol": s, "signal": "DATA_BLOCKED",
                      "score": None,
                      "legs": {"blocked": str(exc)[:120]}}
    return {"evaluated": len(out), "journaled": journaled,
            "participation": round(participation, 1),
            "signals": out}


# ---------------- read paths ------------------------------------------------

def current() -> dict[str, dict]:
    """Latest eval per symbol — the readiness/section read."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, bar_ts, signal,"
            " score, legs FROM intraday_recovery_evals"
            " WHERE as_of = CURRENT_DATE"
            " ORDER BY symbol, bar_ts DESC")
    except Exception:
        return {}
    out = {}
    for r in rows:
        legs = r.get("legs")
        if isinstance(legs, str):
            legs = json.loads(legs)
        ctx = (legs or {}).get("ctx") or {}
        out[r["symbol"]] = {
            "symbol": r["symbol"],
            "signal": r["signal"], "score": r["score"],
            "bar_ts": str(r["bar_ts"]),
            "vwap_hold_min": ctx.get("hold_min"),
            "rs30_smh": ctx.get("rs30", {}).get("SMH")
                        if isinstance(ctx.get("rs30"), dict)
                        else None,
            "rvol": ctx.get("rvol"),
            "delta_vol": ctx.get("delta_vol"),
            "recovery_score": ctx.get("recovery_score"),
            "accumulation_score": ctx.get("accumulation_score"),
            "overextended": ctx.get("overextended"),
            "vwap": ctx.get("vwap"), "last": ctx.get("last"),
            "ext_pct": ctx.get("ext_pct")}
    return out


def rollup_day(d: Optional[date] = None) -> int:
    """Day-summary rollup — the durable record after raw 5m evals
    age out (kept 10d). One row per (symbol, as_of): the facts that
    matter for grading — final state, best/worst of the day, time
    spent confirmed, signal-transition count, signal histogram."""
    from app.database import db
    day = d or date.today()
    rows = db.execute_query(
        "SELECT symbol, signal, score, legs, bar_ts"
        " FROM intraday_recovery_evals WHERE as_of=:d"
        " ORDER BY symbol, bar_ts", {"d": day})
    by_sym: dict[str, list] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
    n = 0
    for sym, evs in by_sym.items():
        try:
            ctx_of = lambda e: ((e.get("legs") or {}).get("ctx") or {}) \
                if isinstance(e.get("legs"), dict) else \
                ((json.loads(e["legs"]) or {}).get("ctx") or {})
            hist: dict[str, int] = {}
            for e in evs:
                hist[e["signal"]] = hist.get(e["signal"], 0) + 1
            transitions = sum(
                1 for a, b in zip(evs, evs[1:])
                if a["signal"] != b["signal"])
            last = ctx_of(evs[-1])
            confirmed = sum(
                5 for e in evs
                if e["signal"] in ("CONFIRMED_RECOVERY",
                                   "STRONG_RECOVERY"))
            max_hold = max(
                ((ctx_of(e).get("hold_min") or 0) for e in evs),
                default=0)
            db.execute_update(
                "INSERT INTO intraday_recovery_daily"
                " (symbol, as_of, final_signal, final_score,"
                " recovery_score, accumulation_score,"
                " max_vwap_hold_min, confirmed_minutes,"
                " end_delta_vol, end_rvol, n_evals,"
                " n_transitions, signals, first_eval, last_eval)"
                " VALUES (:s,:d,:fs,:fsc,:rs,:as,:mh,:cm,:dv,:rv,"
                " :ne,:nt,CAST(:sig AS jsonb),:fe,:le)"
                " ON CONFLICT (symbol, as_of) DO UPDATE SET"
                " final_signal=EXCLUDED.final_signal,"
                " final_score=EXCLUDED.final_score,"
                " recovery_score=EXCLUDED.recovery_score,"
                " accumulation_score=EXCLUDED.accumulation_score,"
                " max_vwap_hold_min=EXCLUDED.max_vwap_hold_min,"
                " confirmed_minutes=EXCLUDED.confirmed_minutes,"
                " end_delta_vol=EXCLUDED.end_delta_vol,"
                " end_rvol=EXCLUDED.end_rvol,"
                " n_evals=EXCLUDED.n_evals,"
                " n_transitions=EXCLUDED.n_transitions,"
                " signals=EXCLUDED.signals,"
                " first_eval=EXCLUDED.first_eval,"
                " last_eval=EXCLUDED.last_eval",
                {"s": sym, "d": day,
                 "fs": evs[-1]["signal"], "fsc": evs[-1]["score"],
                 "rs": last.get("recovery_score"),
                 "as": last.get("accumulation_score"),
                 "mh": max_hold, "cm": confirmed,
                 "dv": last.get("delta_vol"), "rv": last.get("rvol"),
                 "ne": len(evs), "nt": transitions,
                 "sig": json.dumps(hist),
                 "fe": evs[0]["bar_ts"], "le": evs[-1]["bar_ts"]})
            n += 1
        except Exception as exc:
            logger.debug("rollup %s: %s", sym, exc)
    return n


def session(symbol: str) -> dict[str, Any]:
    """One symbol's session story — today's 5m bars + vwap path +
    journaled eval timeline + signal transitions + the overnight gap.
    Read-only over stored rows; nothing recomputes the signal."""
    from app.database import db
    sym = symbol.upper()
    bars = _load_bars(sym, days=1)
    today = date.today()
    bars = [b for b in bars
            if b["bar_ts"].astimezone(_ET).date() == today]
    vw = _vwap(bars)
    smh = _load_bars("SMH", days=1)
    smh = [b["close"] for b in smh
           if b["bar_ts"].astimezone(_ET).date() == today]
    try:
        prev = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " AND date < :d ORDER BY date DESC LIMIT 1",
            {"s": sym, "d": today})
        prev_close = float(prev[0]["close"]) if prev else None
    except Exception:
        prev_close = None
    gap = (round((bars[0]["open"] / prev_close - 1) * 100, 2)
           if bars and prev_close else None)

    evals = []
    try:
        for r in db.execute_query(
                "SELECT bar_ts, signal, score, legs"
                " FROM intraday_recovery_evals"
                " WHERE symbol=:s AND as_of=:d ORDER BY bar_ts",
                {"s": sym, "d": today}):
            legs = r.get("legs")
            if isinstance(legs, str):
                legs = json.loads(legs)
            ctx = (legs or {}).get("ctx") or {}
            evals.append({
                "ts": str(r["bar_ts"]), "signal": r["signal"],
                "score": (float(r["score"])
                          if r["score"] is not None else None),
                "rec": ctx.get("recovery_score"),
                "accum": ctx.get("accumulation_score"),
                "dvol": ctx.get("delta_vol"),
                "rvol": ctx.get("rvol"),
                "hold_min": ctx.get("hold_min")})
    except Exception:
        pass
    transitions = [{"ts": b["ts"], "from": a["signal"],
                    "to": b["signal"]}
                   for a, b in zip(evals, evals[1:])
                   if a["signal"] != b["signal"]]
    return {"symbol": sym, "as_of": str(today), "gap_pct": gap,
            "prev_close": prev_close,
            "bars": [{"ts": str(b["bar_ts"]),
                      "o": b["open"], "h": b["high"], "l": b["low"],
                      "c": b["close"], "v": b["volume"]}
                     for b in bars],
            "vwap": [round(v, 3) for v in vw],
            "smh": smh,
            "evals": evals, "transitions": transitions}


def run() -> dict[str, Any]:
    """The job — fetch this cycle's bars, then evaluate."""
    syms = sorted(set(universe()) | set(benchmarks()))
    fetched = refresh_bars(syms)
    ev = evaluate_session()
    try:
        rolled = rollup_day()
    except Exception as exc:
        logger.debug("rollup failed: %s", exc)
        rolled = 0
    return {"bars": fetched, "evaluated": ev["evaluated"],
            "journaled": ev["journaled"], "rolled": rolled,
            "participation": ev["participation"],
            "signals": {s: r["signal"]
                        for s, r in ev["signals"].items()}}
