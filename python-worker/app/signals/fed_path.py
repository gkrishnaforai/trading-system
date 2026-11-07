"""Fed path engine — hike/hold/cut probabilities + rate direction.

Deterministic three-layer model (matching the architecture):

  data      ^IRX (13w bill ≈ front-end pricing), ^TNX, oil, FRED
            series (DFF/DGS2/DGS10/UNRATE/ICSA/CPIAUCSL) when present,
            macro_snapshots module scores, FOMC calendar
  scoring   market baseline (yield pricing) + bounded economic
            pressure shift — a score is never a probability
  journal   fed_predictions rows carry rules_version; meta_learn
            grades them against realized decisions — calibration is
            earned, not declared

Honesty contract: no FRED key → the econ legs degrade to market-only
and confidence drops; no futures feed → ^IRX is the explicit proxy;
a scheduled meeting is never priced to certainty.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).with_name("fed_path.yaml")
_spec_cache: Optional[dict] = None


def spec() -> dict:
    global _spec_cache
    if _spec_cache is None:
        _spec_cache = yaml.safe_load(_SPEC_PATH.read_text())
    return _spec_cache


def rules_version() -> str:
    from app.signals.pulse_engine import spec_version
    return spec_version("fed_path", _SPEC_PATH, spec())


# ------------------------------------------------------------------
# inputs — every leg optional; missing legs degrade, never invent
# ------------------------------------------------------------------

def _series_latest(sid: str, lookback_days: int = 120
                   ) -> tuple[Optional[float], Optional[int]]:
    """(latest value, age_days) for a FRED series, else (None, None)."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT observation_date, value FROM macro_series_points"
            " WHERE series_id=:s AND value IS NOT NULL"
            " ORDER BY observation_date DESC LIMIT 1",
            {"s": sid})
        if not rows:
            return None, None
        r = rows[0]
        d = r["observation_date"]
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        return float(r["value"]), (date.today() - d).days
    except Exception:
        return None, None


def _series_delta(sid: str, days: int) -> Optional[float]:
    """latest minus the closest point `days` back."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT observation_date, value FROM macro_series_points"
            " WHERE series_id=:s AND value IS NOT NULL"
            " ORDER BY observation_date DESC LIMIT 40",
            {"s": sid})
        if len(rows) < 2:
            return None
        target = date.today() - timedelta(days=days)
        best = min(rows, key=lambda r: abs(
            (r["observation_date"] if not isinstance(
                r["observation_date"], str)
             else date.fromisoformat(str(r["observation_date"])[:10]))
            - target))
        cur = float(rows[0]["value"])
        return (cur - float(best["value"])) * 100.0   # bp for rates
    except Exception:
        return None


def _instrument_bars(sym: str) -> Optional[list]:
    """3mo of daily bars via the canonical service."""
    import asyncio
    try:
        from app.market_data import MarketDataService
        svc = MarketDataService()
        bars = asyncio.run(
            svc.get_ohlcv(sym, period="3mo", interval="1d"))
        return bars or None
    except Exception as exc:
        logger.debug("fed_path: %s fetch failed: %s", sym, exc)
        return None


def _close_at(bars: list, back: int) -> Optional[float]:
    try:
        if bars and len(bars) > back:
            v = bars[-1 - back]
            c = getattr(v, "close", None)
            if c is None and isinstance(v, dict):
                c = v.get("close")
            return float(c) if c is not None else None
    except Exception:
        pass
    return None


def _ctx() -> dict[str, Any]:
    """Gather all inputs; every leg flags its own freshness."""
    from app.database import db
    ctx: dict[str, Any] = {"as_of": date.today().isoformat()}

    # --- market legs -------------------------------------------------
    irx = _instrument_bars("^IRX")
    tnx = _instrument_bars("^TNX")
    oil = _instrument_bars("CL=F")
    ctx["irx"] = _close_at(irx, 0)
    ctx["irx_1m_bp"] = ((_close_at(irx, 0) - _close_at(irx, 21)) * 100
                        if _close_at(irx, 0) and _close_at(irx, 21)
                        else None)
    ctx["irx_3m_bp"] = ((_close_at(irx, 0) - _close_at(irx, 60)) * 100
                        if _close_at(irx, 0) and _close_at(irx, 60)
                        else None)
    ctx["tnx_1m_bp"] = ((_close_at(tnx, 0) - _close_at(tnx, 21)) * 100
                        if _close_at(tnx, 0) and _close_at(tnx, 21)
                        else None)
    o0, o21 = _close_at(oil, 0), _close_at(oil, 21)
    ctx["oil_1m_pct"] = ((o0 / o21 - 1) * 100
                         if o0 and o21 else None)

    # --- FRED legs ---------------------------------------------------
    dff, dff_age = _series_latest("DFF")
    ctx["policy_rate"] = dff
    ctx["policy_rate_age"] = dff_age
    if dff is None and ctx["irx"] is not None:
        # front-end bill yield stands in for the policy rate — flagged
        ctx["policy_rate"] = ctx["irx"]
        ctx["policy_rate_source"] = "irx_proxy"
    else:
        ctx["policy_rate_source"] = "dff" if dff else None

    ctx["dgs2"] = _series_latest("DGS2")[0]
    ctx["unrate"] = _series_latest("UNRATE")[0]

    # macro module z-scores (0-100; high inflation.score = LOW cpi)
    try:
        ms = db.execute_query(
            "SELECT as_of_date, module_scores FROM macro_snapshots"
            " ORDER BY as_of_date DESC LIMIT 1")
        if ms:
            row = ms[0]
            ctx["modules"] = row.get("module_scores") or {}
            d = row["as_of_date"]
            if isinstance(d, str):
                d = date.fromisoformat(d[:10])
            ctx["modules_age"] = (date.today() - d).days
    except Exception:
        pass

    # --- calendar ----------------------------------------------------
    try:
        from app.market_events.calendar import upcoming_macro_events
        fomc = [e for e in upcoming_macro_events(120)
                if e["kind"] == "fomc" and e["days_away"] >= 0]
        if fomc:
            ctx["fomc_date"] = fomc[0]["date"]
            ctx["fomc_days"] = fomc[0]["days_away"]
        if len(fomc) > 1:
            ctx["fomc2_date"] = fomc[1]["date"]
            ctx["fomc2_days"] = fomc[1]["days_away"]
    except Exception:
        pass
    return ctx


# ------------------------------------------------------------------
# scoring — pure function over ctx (eval-suite callable, no DB)
# ------------------------------------------------------------------

def _band(table: list[dict], v: float, key: str) -> dict:
    for row in table:
        if v <= row["max_bp"]:
            return row
    return table[-1]


def _pressure(ctx: dict, spec: dict) -> tuple[Optional[float], list]:
    """Hawkish pressure −100..+100 from FRED modules + oil."""
    w = spec["pressure"]["weights"]
    mods = ctx.get("modules") or {}
    parts, notes, used = [], [], 0

    def mod(name):
        v = (mods.get(name) or {}).get("score")
        return float(v) if isinstance(v, (int, float)) else None

    lab, inf, gro = mod("labor"), mod("inflation"), mod("growth")
    p = 0.0
    if lab is not None:
        p += (lab - 50) * w["labor_dovish_gap"]; used += 1
        if lab >= 60:
            notes.append("tight labor")
        elif lab <= 40:
            notes.append("labor loosening")
    if inf is not None:
        p += (inf - 50) * w["inflation_dovish"]; used += 1
        if inf <= 40:
            notes.append("inflation still hot")
        elif inf >= 65:
            notes.append("disinflation")
    if gro is not None:
        p += (gro - 50) * w["growth"]; used += 1
        if gro <= 40:
            notes.append("growth weakening")
    if ctx.get("oil_1m_pct") is not None:
        p += max(-15.0, min(15.0,
                          ctx["oil_1m_pct"])) * w["oil_1m_pct"]
        used += 1
        if ctx["oil_1m_pct"] > 8:
            notes.append(f"oil +{ctx['oil_1m_pct']:.0f}%/1m")

    if not used:
        return None, notes
    lo, hi = spec["pressure"]["clamp"]
    return max(lo, min(hi, p)), notes


def compute(ctx: dict, sp: Optional[dict] = None) -> dict[str, Any]:
    """ctx → probabilities + plain-English. Pure — no DB, no fetch."""
    sp = sp or spec()
    out: dict[str, Any] = {"as_of": ctx.get("as_of"),
                           "policy_rate": ctx.get("policy_rate"),
                           "policy_rate_source":
                               ctx.get("policy_rate_source")}
    drivers: list[str] = []
    dq = {"fred": "missing" if not ctx.get("modules") else "ok",
          "market": "missing", "confidence": "low"}

    # ---- market baseline -------------------------------------------
    spread = None
    if ctx.get("policy_rate") is not None and ctx.get("irx") is not None:
        spread = (ctx["irx"] - ctx["policy_rate"]) * 100.0
    baseline = None
    base_read = None
    mode = None
    if spread is not None and ctx.get("policy_rate_source") == "dff":
        row = _band(sp["spread_baseline"], spread, "max_bp")
        baseline, base_read, mode = row["probs"], row["read"], "spread"
        drivers.append(
            f"IRX {spread:+.0f}bp vs policy — {base_read}")
        dq["market"] = "ok"
    elif ctx.get("irx_3m_bp") is not None:
        row = _band(sp["delta_baseline"], ctx["irx_3m_bp"], "max_bp")
        baseline, base_read, mode = row["probs"], row["read"], "delta"
        drivers.append(
            f"IRX {ctx['irx_3m_bp']:+.0f}bp/3m — {base_read}"
            " (front-end repricing; no DFF so direction-only)")
        dq["market"] = "ok"
    elif ctx.get("irx_1m_bp") is not None:
        row = _band(sp["delta_baseline"], ctx["irx_1m_bp"], "max_bp")
        baseline, base_read, mode = row["probs"], row["read"], "delta"
        drivers.append(f"IRX {ctx['irx_1m_bp']:+.0f}bp/1m — {base_read}")
        dq["market"] = "ok"
    else:
        # nothing priced — flat, honest
        baseline = {"hike": 33, "hold": 34, "cut": 33}
        mode = "none"
        drivers.append("no front-end pricing data — flat baseline")

    # ---- economic pressure shift ------------------------------------
    pres, pnotes = _pressure(ctx, sp)
    drivers += pnotes
    days = ctx.get("fomc_days")
    prox_w = 0.55
    for row in sp["proximity"]:
        if days is None or days <= row["max_days"]:
            prox_w = row["baseline_weight"]
            break

    probs = dict(baseline)
    if pres is not None:
        shift = (pres / 100.0) * sp["pressure_shift_pp"] * (1 - prox_w) * 2
        src = "hold"
        dst = "hike" if pres > 0 else "cut"
        moved = min(abs(shift), probs.get(src, 0))
        probs[src] = round(probs.get(src, 0) - moved)
        probs[dst] = round(probs.get(dst, 0) + moved)
        drivers.append(
            f"econ pressure {pres:+.0f} ({'hawkish' if pres > 0 else 'dovish'})"
            f" → {src}→{dst} {moved:.0f}pp")

    lo, hi = sp["prob_clamp"]
    for k in probs:
        probs[k] = max(lo, min(hi, probs[k]))
    tot = sum(probs.values())
    probs = {k: round(v / tot * 100) for k, v in probs.items()}
    drift = 100 - sum(probs.values())
    probs["hold"] = probs.get("hold", 0) + drift     # residual → hold

    expected = round((probs["hike"] - probs["cut"])
                     * sp["engine"]["decision_step_bps"] / 100, 1)

    # ---- confidence --------------------------------------------------
    conf = 0.0
    if mode == "spread":
        conf += 0.5
    elif mode == "delta":
        conf += 0.35
    if pres is not None:
        conf += 0.25
    if ctx.get("modules"):
        conf += 0.15
    if dq["fred"] == "missing":
        conf -= 0.15
    conf = max(0.0, min(1.0, conf))
    confidence = ("moderate" if conf >= 0.6 else
                  "low" if conf >= 0.35 else "very_low")
    dq["confidence"] = confidence

    # ---- horizons ----------------------------------------------------
    out["next_fomc"] = {
        "date": ctx.get("fomc_date"),
        "days_away": days,
        "p_hike": probs["hike"], "p_hold": probs["hold"],
        "p_cut": probs["cut"],
        "expected_bps": expected,
    }
    # 1m: same distribution — a meeting inside ~30d is this one or none
    out["path_1m"] = {
        "lean": ("hike" if probs["hike"] >= max(probs["hold"],
                                                probs["cut"])
                 else "cut" if probs["cut"] >= probs["hold"]
                 else "hold"),
        "expected_bps": expected,
        "note": f"next decision {ctx.get('fomc_date') or 'unknown'}"
                f" — {probs['hold']}% hold / "
                f"{probs['cut']}% cut / {probs['hike']}% hike",
    }
    # 3-6m: the front-end spread IS the implied move (~13w window) —
    # but only when the policy rate is real DFF; an IRX-proxy rate
    # makes the spread identically 0 and hides the repricing.
    exp_bps = None
    lean = "hold"
    if spread is not None and ctx.get("policy_rate_source") == "dff":
        exp_bps = max(sp["path"]["expected_bps_clamp"][0],
                      min(sp["path"]["expected_bps_clamp"][1],
                          round(spread)))
    elif ctx.get("irx_3m_bp") is not None:
        exp_bps = max(sp["path"]["expected_bps_clamp"][0],
                      min(sp["path"]["expected_bps_clamp"][1],
                          round(ctx["irx_3m_bp"])))
    if exp_bps is not None:
        for row in sp["path"]["lean_bands"]:
            if exp_bps <= row["max_bps"]:
                lean = row["lean"]
                break
        drivers.append(f"3-6m: front end implies {exp_bps:+d}bp"
                       f" → {lean.replace('_', ' ')}")
    # pressure can tilt the lean one notch when market is neutral
    if lean == "hold" and pres is not None and abs(pres) >= 40:
        lean = "tightening_bias" if pres > 0 else "easing_bias"

    out["path_3_6m"] = {"lean": lean, "expected_bps": exp_bps}

    # ---- second meeting --------------------------------------------
    # The front-end window (~13w) prices BOTH meetings. Meeting-2's
    # distribution is the residual expected move after meeting-1's
    # share — weaker by construction, labeled and clamped, never
    # presented with meeting-1's confidence.
    step = sp["engine"]["decision_step_bps"]
    m2 = {"date": ctx.get("fomc2_date"),
          "days_away": ctx.get("fomc2_days")}
    if exp_bps is not None:
        resid = round(exp_bps - expected, 1)
        p_move = min(0.85, max(0.05, abs(resid) / step))
        direction = "hike" if resid > 0 else "cut"
        m2.update({"p_hike": round(p_move * 100) if direction == "hike"
                                else 0,
                   "p_cut": round(p_move * 100) if direction == "cut"
                                else 0,
                   "p_hold": round(100 - p_move * 100),
                   "expected_bps": resid,
                   "basis": "window_residual"})
        if ctx.get("fomc2_date"):
            drivers.append(
                f"{ctx['fomc2_date']} FOMC: window residual "
                f"{resid:+.0f}bp → {direction} {round(p_move*100)}% / "
                f"hold {round(100-p_move*100)}%")
    else:
        # nothing priced — decay meeting-1 toward hold, honest basis
        m2.update({"p_hike": round(probs["hike"] * 0.5),
                   "p_cut": round(probs["cut"] * 0.5),
                   "p_hold": round(100 - (probs["hike"]
                                          + probs["cut"]) * 0.5),
                   "expected_bps": None,
                   "basis": "extrapolated_low_confidence"})
    out["fomc_2"] = m2

    out["drivers"] = drivers
    out["components"] = {
        "baseline_mode": mode, "baseline_weight": prox_w,
        "market_spread_bp": (round(spread, 1)
                             if spread is not None
                             and ctx.get("policy_rate_source") == "dff"
                             else None),
        "pressure": round(pres, 1) if pres is not None else None,
    }
    out["data_quality"] = dq

    # ---- conclusion — deterministic plain English --------------------
    top = max(probs, key=probs.get)
    conv = []
    if ctx.get("fomc_date"):
        conv.append(
            f"Into the {ctx['fomc_date']} FOMC ({days}d), pricing reads "
            f"{top} at {probs[top]}% "
            f"(hike {probs['hike']} / hold {probs['hold']} / "
            f"cut {probs['cut']}).")
    else:
        conv.append(
            f"Rate odds read {top} at {probs[top]}% — "
            "no FOMC date on the calendar.")
    if pres is not None and abs(pres) >= 30:
        conv.append(
            f"Economic pressure is {'hawkish' if pres > 0 else 'dovish'} "
            f"({pres:+.0f}) — pulls odds {'toward hikes' if pres > 0 else 'toward cuts'}.")
    if exp_bps is not None:
        conv.append(
            f"Over 3-6 months the front end implies "
            f"{exp_bps:+d}bp — {lean.replace('_', ' ')}.")
    if dq["fred"] == "missing":
        conv.append("FRED macro legs unavailable — market pricing only,"
                    " confidence capped.")
    out["conclusion"] = " ".join(conv)
    return out


# ------------------------------------------------------------------
# journal + read
# ------------------------------------------------------------------

def run() -> dict[str, Any]:
    """Daily compute + journal. Idempotent per day."""
    from app.database import db
    import json
    ctx = _ctx()
    res = compute(ctx)
    res["rules_version"] = rules_version()
    db.execute_update(
        """INSERT INTO fed_predictions
             (as_of, meeting_date, p_hike, p_hold, p_cut,
              expected_bps, lean_3_6m, expected_bps_3_6m,
              confidence, payload, rules_version)
           VALUES (:d,:m,:h,:hd,:c,:e,:l,:e6,:cf,:p,:rv)
           ON CONFLICT (as_of) DO UPDATE SET
             meeting_date=:m, p_hike=:h, p_hold=:hd, p_cut=:c,
             expected_bps=:e, lean_3_6m=:l, expected_bps_3_6m=:e6,
             confidence=:cf, payload=:p, rules_version=:rv""",
        {"d": date.today(), "m": (res["next_fomc"] or {}).get("date"),
         "h": res["next_fomc"]["p_hike"],
         "hd": res["next_fomc"]["p_hold"],
         "c": res["next_fomc"]["p_cut"],
         "e": res["next_fomc"]["expected_bps"],
         "l": res["path_3_6m"]["lean"],
         "e6": res["path_3_6m"]["expected_bps"],
         "cf": res["data_quality"]["confidence"],
         "p": json.dumps(res, default=str),
         "rv": res["rules_version"]})
    return res


def read() -> Optional[dict[str, Any]]:
    """Latest journaled prediction — the fast read for regime card."""
    from app.database import db
    import json
    try:
        rows = db.execute_query(
            "SELECT as_of, payload FROM fed_predictions"
            " ORDER BY as_of DESC LIMIT 1")
        if not rows:
            return None
        p = rows[0].get("payload")
        if isinstance(p, str):
            p = json.loads(p)
        p = p or {}
        p["as_of"] = str(rows[0]["as_of"])
        d = rows[0]["as_of"]
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        p["age_days"] = (date.today() - d).days
        return p
    except Exception:
        return None
