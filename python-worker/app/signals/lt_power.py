"""Long-duration earnings-power repricing lens (deterministic).

Why this exists — the AMD lesson: the market repriced AMD from ~$460 to
~$655 by capitalizing CY2030 consensus EPS (~$45 avg / $57 high) at a
mature multiple (~15x), while our 1-year-forward fair-value engine's
explosive ceiling was $337. The engine was "right" about near-term value
and blind to the actual repricing mechanism.

This module answers two questions deterministically:

  1. Is a long-duration repricing setup present?  — a checklist of
     OBSERVABLE conditions (not a probability guess):

       a. lt_curve_exists  — street publishes an annual EPS estimate
          >= LT_MIN_YEARS out (the market can only capitalize a number
          it can see)
       b. back_loaded      — eps_lt / eps_near >= BACK_LOADED_MIN —
          earnings power is back-loaded; a 1y-forward lens structurally
          underprices the name
       c. coverage         — LT estimate has >= MIN_ANALYSTS analysts
          (a real modeled curve, not one outlier)
       d. revisions_up     — the LT (or nearest fwd) estimate is rising
          vs our own stored snapshots — repricings are preceded by
          out-year estimate upgrades
       e. tailwind_evidence — TAM-expanding channels journaled at
          announced/shipping/revenue tier (the narrative that justifies
          the duration trade)
       f. tape_confirm     — price above its 50d MA — the market is
          already voting; repricing without tape confirmation is a
          value thesis, not a repricing setup

  2. If it reprices, how far can it go?  — the LT implied band:
       bear      = eps_lt_low  × EXIT_BEAR
       base      = eps_lt_avg  × EXIT_BASE
       bull      = eps_lt_high × EXIT_BULL
       explosive = eps_lt_high × EXIT_EXPLOSIVE

     Exit multiples are the mature-state band for a growth business
     that has delivered its out-year earnings power — deliberately
     conservative constants (versioned), because the whole point is
     that the market only awards ~12-22x on realized 4-5y-out EPS.

Everything derives from stored rows (symbol_estimate_snapshots,
daily_bars, tailwinds, symbol_flywheel). No LLM, no analyst PRICE
TARGETS — consensus EPS *estimates* are a data input (same as
eps_forward already is in the FV engine); price targets remain
context-only. Runs journal append-only to lt_power_runs for the
training/backtest record.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MODEL_VERSION = "lt_power.v1"

# --- versioned, explicit constants -------------------------------------
LT_MIN_DAYS = 540              # an annual estimate ~18mo+ out = "long duration"
BACK_LOADED_MIN = 2.0          # eps_lt / eps_near >= 2x → back-loaded power
MIN_ANALYSTS = 4               # LT estimate needs real street coverage
REVISION_LOOKBACK_DAYS = 90    # compare LT estimate vs >=90d-old snapshot
REVISION_MIN_PCT = 0.05        # +5% counts as "revising up"
EXIT_BEAR = 12.0               # mature-state exit multiple band (on LT EPS)
EXIT_BASE = 15.0
EXIT_BULL = 18.0
EXIT_EXPLOSIVE = 22.0
# implied_lt_pe bands for "how much is already priced"
PRICED_LOW, PRICED_MID, PRICED_HIGH = 12.0, 18.0, 25.0


def _f(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _latest_estimate_curve(sym: str, as_of: date) -> list[dict]:
    """Newest snapshot of each forward annual period, point-in-time."""
    from app.database import db
    return db.execute_query(
        """
        SELECT DISTINCT ON (period_end)
               period_end, eps_avg, eps_low, eps_high, rev_avg,
               num_analysts, as_of
        FROM symbol_estimate_snapshots
        WHERE symbol = :s AND as_of <= :a
        ORDER BY period_end, as_of DESC
        """,
        {"s": sym, "a": as_of},
    ) or []


def _lt_revision(sym: str, period_end: Any, as_of: date,
                 cur_eps: Optional[float]) -> Optional[float]:
    """LT eps revision vs a >=90d-old snapshot of the same period."""
    from app.database import db
    if cur_eps is None:
        return None
    prev = db.execute_query(
        """
        SELECT eps_avg FROM symbol_estimate_snapshots
        WHERE symbol = :s AND period_end = :p
          AND as_of <= :cut
        ORDER BY as_of DESC LIMIT 1
        """,
        {"s": sym, "p": period_end,
         "cut": as_of - timedelta(days=REVISION_LOOKBACK_DAYS)},
    )
    if not prev or _f(prev[0].get("eps_avg")) in (None, 0):
        return None
    p = _f(prev[0]["eps_avg"])
    if abs(p) < 0.25 or (p > 0) != (cur_eps > 0):
        return None  # same base-sanity rule as the flywheel revision check
    return cur_eps / p - 1


def _spot_and_tape(sym: str, as_of: date) -> Dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        """
        SELECT date, close FROM daily_bars
        WHERE symbol = :s AND date <= :a
        ORDER BY date DESC LIMIT 60
        """,
        {"s": sym, "a": as_of},
    ) or []
    if not rows:
        return {"spot": None, "sma50": None, "tape_confirm": None}
    spot = _f(rows[0]["close"])
    closes = [_f(r["close"]) for r in rows[:50]]
    sma50 = (sum(closes) / len(closes)) if closes and all(
        c is not None for c in closes) else None
    tape = (spot > sma50) if (spot and sma50) else None
    return {"spot": spot, "sma50": sma50, "tape_confirm": tape,
            "spot_date": str(rows[0]["date"])}


def _tailwind_evidence(sym: str) -> Dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        """
        SELECT channel, tier, direction FROM tailwinds
        WHERE symbol = :s AND status IS DISTINCT FROM 'dead'
        """,
        {"s": sym},
    ) or []
    tiers = ("announced", "shipping", "revenue")
    supporting = [r for r in rows
                  if r.get("direction") == "tailwind"
                  and r.get("tier") in tiers]
    opposing = [r for r in rows
                if r.get("direction") == "headwind"
                and r.get("tier") in tiers]
    return {"tailwind_channels": sorted({r["channel"] for r in supporting}),
            "headwind_channels": sorted({r["channel"] for r in opposing}),
            "has_evidence": bool(supporting)}


def compute_lt_power(sym: str, as_of: Optional[date] = None) -> Dict[str, Any]:
    """Deterministic long-duration repricing read for one symbol."""
    as_of = as_of or date.today()
    curve = _latest_estimate_curve(sym, as_of)
    tape = _spot_and_tape(sym, as_of)
    tw = _tailwind_evidence(sym)
    spot = tape.get("spot")

    # nearest forward period (~+1y) and the furthest (LT) period —
    # near must be a DIFFERENT, earlier period or the duration ratio
    # is meaningless
    fwd_cut = as_of + timedelta(days=60)
    fwd_rows = [r for r in curve if r["period_end"] > fwd_cut]
    lt = next((r for r in reversed(curve)
               if (r["period_end"] - as_of).days >= LT_MIN_DAYS), None)
    near = next((r for r in fwd_rows
                 if not lt or r["period_end"] < lt["period_end"]),
                None)

    out: Dict[str, Any] = {
        "symbol": sym, "as_of": str(as_of), "model_version": MODEL_VERSION,
        "spot": spot, "spot_date": tape.get("spot_date"),
        "lt_period": str(lt["period_end"]) if lt else None,
        "near_period": str(near["period_end"]) if near else None,
        "eps_near": _f(near["eps_avg"]) if near else None,
        "eps_lt_avg": _f(lt["eps_avg"]) if lt else None,
        "eps_lt_low": _f(lt["eps_low"]) if lt else None,
        "eps_lt_high": _f(lt["eps_high"]) if lt else None,
        "lt_analysts": _f(lt["num_analysts"]) if lt else None,
        "curve_periods": len(fwd_rows),
        "tailwind_channels": tw["tailwind_channels"],
        "headwind_channels": tw["headwind_channels"],
    }

    eps_lt, eps_near = out["eps_lt_avg"], out["eps_near"]

    # --- the band: "if it reprices to LT power, how far can it go"
    if lt and eps_lt and eps_lt > 0:
        out["lt_band"] = {
            "bear":      round((out["eps_lt_low"] or eps_lt) * EXIT_BEAR, 2),
            "base":      round(eps_lt * EXIT_BASE, 2),
            "bull":      round((out["eps_lt_high"] or eps_lt) * EXIT_BULL, 2),
            "explosive": round((out["eps_lt_high"] or eps_lt) * EXIT_EXPLOSIVE, 2),
            "exit_multiples": {"bear": EXIT_BEAR, "base": EXIT_BASE,
                               "bull": EXIT_BULL, "explosive": EXIT_EXPLOSIVE},
        }
        if spot:
            out["lt_gap_pct"] = round(out["lt_band"]["base"] / spot - 1, 4)
            out["implied_lt_pe"] = round(spot / eps_lt, 1)
            ilp = spot / eps_lt
            # implied LT PE under ~4x is almost always a currency unit
            # bug on ADRs (native-ccy EPS vs USD price — NVO/TSM class)
            # rather than a genuinely unpriced name — flag, don't trust
            out["already_priced"] = (
                "fx_suspect" if ilp < 4.0 else
                "beyond_lt_avg" if ilp > PRICED_HIGH else
                "substantial" if ilp > PRICED_MID else
                "partial" if ilp > PRICED_LOW else
                "not_priced")
            out["fx_suspect"] = ilp < 4.0
    else:
        out["lt_band"] = None
        out["lt_gap_pct"] = None
        out["implied_lt_pe"] = None
        out["already_priced"] = None

    # --- the checklist: "is a long-duration repricing setup present"
    duration_ratio = (eps_lt / eps_near) if (
        lt and near and eps_lt and eps_near and eps_near > 0) else None
    lt_rev = _lt_revision(sym, lt["period_end"], as_of, eps_lt) if lt else None
    out["duration_ratio"] = round(duration_ratio, 2) if duration_ratio else None
    out["lt_revision_pct"] = round(lt_rev, 4) if lt_rev is not None else None

    checklist = {
        "lt_curve_exists": bool(lt),
        "back_loaded": (duration_ratio >= BACK_LOADED_MIN)
                       if duration_ratio is not None else None,
        "coverage": bool(out["lt_analysts"] and out["lt_analysts"] >= MIN_ANALYSTS),
        "revisions_up": (lt_rev is not None and lt_rev >= REVISION_MIN_PCT)
                        if lt_rev is not None else None,
        "tailwind_evidence": tw["has_evidence"],
        "tape_confirm": tape.get("tape_confirm"),
    }
    out["checklist"] = checklist
    # score over items that could actually be evaluated (None = no data)
    scored = [k for k, v in checklist.items() if v is not None]
    hits = sum(1 for k in scored if checklist[k])
    out["repricing_score"] = f"{hits}/{len(scored)}"
    out["repricing_setup"] = (
        "high" if scored and hits >= len(scored) - 1 and hits >= 4 else
        "moderate" if hits >= 3 else
        "low" if hits >= 1 else
        "none")
    return out


def journal_run(res: Dict[str, Any]) -> None:
    """Append-only journal — skip if identical inputs already stored
    today (the page can call this on every view without spamming)."""
    from app.database import db
    payload = {k: res.get(k) for k in
               ("eps_near", "eps_lt_avg", "eps_lt_low", "eps_lt_high",
                "lt_analysts", "lt_period", "near_period", "spot",
                "duration_ratio", "lt_revision_pct")}
    inputs_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    try:
        dup = db.execute_query(
            "SELECT 1 FROM lt_power_runs WHERE symbol=:s "
            "AND as_of=:a AND inputs_hash=:h LIMIT 1",
            {"s": res["symbol"], "a": res["as_of"], "h": inputs_hash})
        if dup:
            return
        db.execute_query(
            """
            INSERT INTO lt_power_runs
              (symbol, as_of, spot, lt_period, eps_near, eps_lt_avg,
               eps_lt_low, eps_lt_high, lt_analysts, lt_band, checklist,
               repricing_setup, implied_lt_pe, lt_gap_pct, inputs_hash,
               model_version)
            VALUES (:s, :a, :spot, :lp, :en, :ea, :el, :eh, :la,
                    CAST(:band AS jsonb), CAST(:cl AS jsonb),
                    :setup, :ilpe, :gap, :h, :mv)
            """,
            {"s": res["symbol"], "a": res["as_of"], "spot": res.get("spot"),
             "lp": res.get("lt_period"), "en": res.get("eps_near"),
             "ea": res.get("eps_lt_avg"), "el": res.get("eps_lt_low"),
             "eh": res.get("eps_lt_high"), "la": res.get("lt_analysts"),
             "band": json.dumps(res.get("lt_band")),
             "cl": json.dumps(res.get("checklist")),
             "setup": res.get("repricing_setup"),
             "ilpe": res.get("implied_lt_pe"),
             "gap": res.get("lt_gap_pct"), "h": inputs_hash,
             "mv": res.get("model_version")})
    except Exception as exc:
        logger.debug("lt_power journal %s failed: %s", res.get("symbol"), exc)


def lt_power_for_card(sym: str) -> Optional[Dict[str, Any]]:
    """Compute + journal for the Stock page; None-safe."""
    try:
        res = compute_lt_power(sym)
        journal_run(res)
        return res
    except Exception as exc:
        logger.debug("lt_power %s failed: %s", sym, exc)
        return None


# --- priced_status batch ----------------------------------------------------
# The loss-avoidance flag: how much forward growth the current price already
# capitalizes. LT estimate curve is the honest source when it exists
# (implied_lt_pe = spot / LT EPS avg); the FV engine's expected-value upside
# is the fallback when it doesn't. Persisted on stocks so every screener
# reads the same flag rather than recomputing.

_PRICED_MAP = {"not_priced": "not_priced", "partial": "partial",
             "substantial": "substantial", "beyond_lt_avg": "full",
             "fx_suspect": "fx_suspect"}


def _fv_priced_fallback(sym: str) -> Optional[dict]:
    """Latest FV run's expected/scenario blend vs spot → priced status.
    >+30% expected upside = growth not priced; <0% = fully priced."""
    from app.database import db
    r = db.execute_query(
        "SELECT expected_fair_value, fair_value, spot_at_run"
        " FROM fair_value_v2_runs WHERE symbol=:s"
        " ORDER BY as_of DESC, run_id DESC LIMIT 1", {"s": sym})
    if not r:
        return None
    row = dict(r[0])
    spot = _f(row.get("spot_at_run"))
    exp = (_f(row.get("expected_fair_value"))
           or _f(row.get("fair_value")))
    if not spot or not exp or spot <= 0:
        return None
    upside = exp / spot - 1
    status = ("not_priced" if upside > 0.30 else
              "partial" if upside > 0.0 else "full")
    return {"status": status, "source": "fv",
            "fv_expected": exp, "fv_upside": round(upside, 4)}


def priced_status_for(sym: str, res: Optional[Dict] = None) -> dict:
    """Unified flag for one symbol. res = precomputed lt_power result."""
    if res is None:
        res = compute_lt_power(sym)
    ap = res.get("already_priced")
    if ap in _PRICED_MAP:
        return {"status": _PRICED_MAP[ap], "source": "lt_curve",
                "implied_lt_pe": res.get("implied_lt_pe"),
                "lt_gap_pct": res.get("lt_gap_pct"),
                "eps_lt_avg": res.get("eps_lt_avg")}
    fb = _fv_priced_fallback(sym)
    if fb:
        return fb
    return {"status": "unknown", "source": "none"}


def refresh_priced_status(symbols: Optional[list] = None) -> dict:
    """Universe pass — compute + persist stocks.priced_status and merge
    the inputs into stocks.fwd_detail. Run at the tail of the daily
    flywheel/board job; each symbol's full result also journals to
    lt_power_runs (deduped on inputs hash)."""
    from app.database import db
    syms = symbols or [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM stocks WHERE momentum_state IS NOT NULL")]
    done = {"lt_curve": 0, "fv": 0, "unknown": 0, "err": 0}
    for s in syms:
        try:
            res = compute_lt_power(s)
            journal_run(res)
            ps = priced_status_for(s, res)
            done[ps["source"]] = done.get(ps["source"], 0) + 1
            db.execute_update(
                "UPDATE stocks SET priced_status=:p,"
                " fwd_detail = COALESCE(fwd_detail,'{}'::jsonb)"
                " || CAST(:d AS jsonb) WHERE symbol=:s",
                {"s": s, "p": ps["status"],
                 "d": json.dumps({"priced": ps})})
        except Exception as exc:
            logger.debug("priced_status %s: %s", s, exc)
            done["err"] += 1
    return {"symbols": len(syms), **done}
