"""Meta learner — the nightly self-training engine.

Every night it grades our own signals on REAL outcomes and writes
bounded corrections into engine_weights — the same keys the board
already reads (dip:*, gate:*). This is the piece that makes the system
get measurably better each day instead of running frozen heuristics.

What it measures:
  signal lift     per signal (dip phase, prior present, catalysts,
                  focus events, screen-ready): 10d hit-rate + median
                  return WITH the signal vs WITHOUT it — the marginal
                  contribution, not the raw pattern stats
  pilot lift      closed swing_pilot_trades by pattern_key — the
                  trade-management verdict on the same setups
  calibration     composite score decile → realized return — is a 90
                  really better than a 70? (report-only: a non-monotonic
                  curve means the WEIGHTS are wrong, surfaced for the
                  human rather than silently rewritten)

Writes (bounded — meta can adjust, never rewrite):
  engine_weights['dip:{phase}']   adj in [-12, +8]  (board reads it)
  engine_weights['gate:{key}']    {enabled:false} when a pattern proves
                                  net-negative over ≥10 closed samples
  engine_weights['meta:report']   the full measurement for the UI

Minimum sample before any write: 20 outcomes per cohort. Until then it
logs 'collecting' — honesty over false precision.
"""
from __future__ import annotations

import logging
import statistics as st
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_MIN = 20           # cohort size before a weight write is allowed

# signal name → evidence-substring matchers (the 'why' lines the board
# writes into decision evidence)
_SIGNALS = {
    "dip_turning_up":  ["dip turning up"],
    "dip_stabilizing": ["dip stabilizing"],
    "dip_falling":     ["dip still falling"],
    "prior_good":      ["prior:"],            # refined below by hit-rate
    "alert_neg":       ["NEGATIVE catalyst"],
    "alert_pos":       ["positive catalyst"],
    "screen_ready":    ["swing"],
    "focus_event":     ["focus"],
    "fund_accel":      ["accelerating"],
}


def _lift(rows: list[dict], pred) -> dict[str, Any] | None:
    """hit-rate + median return, cohorts with vs without `pred`."""
    w = [r["ret_pct"] for r in rows if pred(r)]
    wo = [r["ret_pct"] for r in rows if not pred(r)]
    if len(w) < _MIN or len(wo) < _MIN:
        return None
    return {"with": {"n": len(w),
                     "hit": round(sum(1 for x in w if x > 0) / len(w), 3),
                     "med": round(st.median(w), 4)},
            "without": {"n": len(wo),
                        "hit": round(sum(1 for x in wo if x > 0)
                                     / len(wo), 3),
                        "med": round(st.median(wo), 4)}}


def _has(ev: Any, needles: list[str]) -> bool:
    txt = " | ".join(ev) if isinstance(ev, list) else str(ev or "")
    return any(n in txt for n in needles)


def _weight_num(key: str, default: float) -> float:
    """Current learned scalar for a key (value may wrap it in a dict)."""
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM engine_weights WHERE key=:k", {"k": key})
    if not rows:
        return default
    v = rows[0]["value"]
    if isinstance(v, dict):
        v = v.get("value", default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def run() -> dict[str, Any]:
    from app.database import db
    import json

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rep: dict[str, Any] = {"at": now, "writes": [], "notes": []}

    # --- 1. signal lift on graded board decisions (10d horizon) ------
    rows = db.execute_query(
        "SELECT d.evidence, d.momentum_state, d.score, o.ret_pct,"
        " o.mae_pct, o.mfe_pct"
        " FROM board_outcomes o"
        " JOIN board_decisions d ON d.id = o.decision_id"
        " WHERE o.horizon_days = 10 AND o.ret_pct IS NOT NULL")
    rep["outcomes_n"] = len(rows)

    if len(rows) >= _MIN:
        lifts = {}
        for sig, needles in _SIGNALS.items():
            lf = _lift(rows, lambda r, n=needles: _has(r["evidence"], n))
            if lf:
                lifts[sig] = lf
        rep["signal_lifts"] = lifts

        # dip-phase weights — measured lift → bounded adjustment
        # lift = med_return_with − med_return_without; map ±0.05 → ±6
        for phase, key in (("turning_up", "dip_turning_up"),
                           ("stabilizing", "dip_stabilizing"),
                           ("still_falling", "dip_falling")):
            lf = lifts.get(key)
            if not lf:
                continue
            delta = lf["with"]["med"] - lf["without"]["med"]
            adj = float(max(-12.0, min(8.0, round(delta * 120, 1))))
            db.execute_update(
                "INSERT INTO engine_weights (key, value, updated_at)"
                " VALUES (:k, CAST(:v AS jsonb), now())"
                " ON CONFLICT (key) DO UPDATE SET"
                " value=CAST(:v AS jsonb), updated_at=now()",
                {"k": f"dip:{phase}",
                 "v": json.dumps({"adj": adj, "n": lf["with"]["n"],
                                  "lift": float(round(delta, 4)),
                                  "by": "meta", "at": now})})
            rep["writes"].append(f"dip:{phase} → {adj:+.1f}")

        # calibration — score decile vs realized return (report-only)
        dec = {}
        for r in rows:
            b = min(9, int((r.get("score") or 0) // 10))
            dec.setdefault(b, []).append(r["ret_pct"])
        rep["calibration"] = {
            f"{b*10}-{b*10+9}": {"n": len(v), "hit": round(
                sum(1 for x in v if x > 0) / len(v), 3),
                "med": round(st.median(v), 4)}
            for b, v in sorted(dec.items()) if len(v) >= 5}
    else:
        rep["notes"].append(
            f"only {len(rows)} graded outcomes — collecting "
            f"(need {_MIN}); weights untouched")

    # --- 2. pilot pattern lift — closed trades are the cleanest data --
    tr = db.execute_query(
        "SELECT pattern_key, ret_pct FROM swing_pilot_trades"
        " WHERE status='closed' AND ret_pct IS NOT NULL")
    by_key: dict[str, list] = {}
    for t in tr:
        by_key.setdefault(t["pattern_key"], []).append(t["ret_pct"])
    rep["pilot_closed"] = len(tr)
    for key, rets in by_key.items():
        if len(rets) < 10:
            continue
        med = st.median(rets)
        if med < 0:                          # proven loser → gate OFF
            db.execute_update(
                "INSERT INTO engine_weights (key, value, updated_at)"
                " VALUES (:k, CAST(:v AS jsonb), now())"
                " ON CONFLICT (key) DO UPDATE SET"
                " value=CAST(:v AS jsonb), updated_at=now()",
                {"k": f"gate:{key}",
                 "v": json.dumps({"enabled": False, "n": len(rets),
                                  "med": float(round(med, 4)),
                                  "by": "meta", "at": now})})
            rep["writes"].append(f"gate:{key} → OFF (med {med:+.1%})")

    # --- 2.5 call plan quality — did the PLAN work, not just the pick
    # daily_call_outcomes resolves every top-3 call as target_first /
    # stop_first / expired. The learnable params in daily_calls.generate:
    #   calls:band_mult   stop distance = mult × atr_pct (default 1.5)
    #   calls:rr_target   target = entry + rr × risk (default 2.0)
    co = db.execute_query(
        "SELECT resolution, ret_eod, ret_20d, mfe, mae, days_held"
        " FROM daily_call_outcomes WHERE resolution != 'open'")
    rep["calls_graded"] = len(co)
    if len(co) >= _MIN:
        stopped = [r for r in co if r["resolution"] == "stop_first"]
        expired = [r for r in co if r["resolution"] == "expired"]
        stop_share = len(stopped) / len(co)
        exp_share = len(expired) / len(co)
        rep["calls_mix"] = {"stop_first": len(stopped),
                            "target_first": sum(1 for r in co
                                                if r["resolution"]
                                                == "target_first"),
                            "expired": len(expired)}
        # stops clipping winners: many stop-outs that still ran up ≥3%
        stopped_mfe = [r["mfe"] for r in stopped
                       if r["mfe"] is not None]
        recovered = (sum(1 for m in stopped_mfe if m > 3)
                     / len(stopped_mfe) if stopped_mfe else 0)
        cur_mult = _weight_num("calls:band_mult", 1.5)
        if stop_share > 0.45 and recovered > 0.5 and cur_mult < 2.2:
            new = round(cur_mult + 0.1, 2)
            db.execute_update(
                "INSERT INTO engine_weights (key, value, updated_at)"
                " VALUES (:k, CAST(:v AS jsonb), now())"
                " ON CONFLICT (key) DO UPDATE SET"
                " value=CAST(:v AS jsonb), updated_at=now()",
                {"k": "calls:band_mult",
                 "v": json.dumps({"value": new, "n": len(co),
                                  "stop_share": round(stop_share, 3),
                                  "recovered": round(recovered, 3),
                                  "by": "meta", "at": now})})
            rep["writes"].append(
                f"calls:band_mult {cur_mult}→{new} "
                f"({len(stopped)}/{len(co)} stopped, "
                f"{recovered:.0%} then ran ≥3%)")
        # targets unreachable: many expiries that saw ≥+6% before dying
        exp_mfe = [r["mfe"] for r in expired if r["mfe"] is not None]
        cur_rr = _weight_num("calls:rr_target", 2.0)
        if exp_share > 0.40 and exp_mfe \
                and st.median(exp_mfe) > 6 and cur_rr > 1.5:
            new = round(cur_rr - 0.15, 2)
            db.execute_update(
                "INSERT INTO engine_weights (key, value, updated_at)"
                " VALUES (:k, CAST(:v AS jsonb), now())"
                " ON CONFLICT (key) DO UPDATE SET"
                " value=CAST(:v AS jsonb), updated_at=now()",
                {"k": "calls:rr_target",
                 "v": json.dumps({"value": new, "n": len(co),
                                  "exp_share": round(exp_share, 3),
                                  "exp_med_mfe": float(round(
                                      st.median(exp_mfe), 2)),
                                  "by": "meta", "at": now})})
            rep["writes"].append(
                f"calls:rr_target {cur_rr}→{new} "
                f"({len(expired)}/{len(co)} expired, med MFE "
                f"{st.median(exp_mfe):+.1f}%)")
    elif co:
        rep["notes"].append(
            f"{len(co)} graded calls — collecting (need {_MIN}) "
            "before plan params adjust")

    # --- 2.7 crash alpha — did the scores earn their thresholds? ----
    # Graded crash_alpha_snapshots answer two calibration questions:
    #   cap_bounce: cap_score ≥ zone → SPY bounced >2% in 20d?
    #   put_hit_rate: flagged candidates actually underperformed?
    # Learnables:
    #   alpha:cap_zone    capitulation threshold (default 60)
    #   alpha:put_min     min put-entry score to surface (default 35)
    ca = db.execute_query(
        """SELECT capitulation_score cs, cap_bounce, put_hit_rate,
                  spy_ret_20d
           FROM crash_alpha_snapshots WHERE spy_ret_20d IS NOT NULL""")
    rep["alpha_graded"] = len(ca)
    if len(ca) >= _MIN:
        hot = [r for r in ca if (r["cs"] or 0) >= 60]
        if len(hot) >= 5:
            bounces = sum(1 for r in hot if r["cap_bounce"])
            bounce_rate = bounces / len(hot)
            cur_zone = _weight_num("alpha:cap_zone", 60.0)
            # firing but not bouncing → the zone is too eager; raise it
            if bounce_rate < 0.35 and cur_zone < 80:
                new = round(cur_zone + 5)
                db.execute_update(
                    "INSERT INTO engine_weights (key, value, updated_at)"
                    " VALUES (:k, CAST(:v AS jsonb), now())"
                    " ON CONFLICT (key) DO UPDATE SET"
                    " value=CAST(:v AS jsonb), updated_at=now()",
                    {"k": "alpha:cap_zone",
                     "v": json.dumps({"value": new, "n": len(hot),
                                      "bounce": round(bounce_rate, 3),
                                      "by": "meta", "at": now})})
                rep["writes"].append(
                    f"alpha:cap_zone {cur_zone:.0f}→{new} "
                    f"(fired {len(hot)}×, only "
                    f"{bounce_rate:.0%} bounced)")
            # bouncing at 60 but never firing → don't tighten it away
        hrs = [r["put_hit_rate"] for r in ca
               if r["put_hit_rate"] is not None]
        if len(hrs) >= 10:
            med_hr = st.median(hrs)
            cur_min = _weight_num("alpha:put_min", 35.0)
            # put candidates keep out-performing → the bar's too low
            if med_hr < 45 and cur_min < 60:
                new = round(cur_min + 5)
                db.execute_update(
                    "INSERT INTO engine_weights (key, value, updated_at)"
                    " VALUES (:k, CAST(:v AS jsonb), now())"
                    " ON CONFLICT (key) DO UPDATE SET"
                    " value=CAST(:v AS jsonb), updated_at=now()",
                    {"k": "alpha:put_min",
                     "v": json.dumps({"value": new, "n": len(hrs),
                                      "med_hit": float(
                                          round(med_hr, 1)),
                                      "by": "meta", "at": now})})
                rep["writes"].append(
                    f"alpha:put_min {cur_min:.0f}→{new} "
                    f"(med underperformance rate {med_hr:.0f}%)")
    elif ca:
        rep["notes"].append(
            f"{len(ca)} graded alpha snapshots — collecting "
            f"(need {_MIN}) before thresholds adjust")

    # --- 2.8 posture gate — do "no new longs" days precede weak tape?
    # Learnable: posture:thin_tape:breadth_score_lt (default 32,
    # bounded 24-38). If days the gate blocked actually did WORSE
    # forward → it has edge → allow catching a bit more. If blocked
    # days did as well or better → the gate costs opportunity →
    # lower the trigger so it fires only when truly thin.
    po = db.execute_query(
        "SELECT e.new_longs, o.fwd_20d FROM posture_outcomes o"
        " JOIN posture_evals e ON e.id = o.eval_id"
        " WHERE o.fwd_20d IS NOT NULL")
    rep["posture_graded"] = len(po)
    if len(po) >= _MIN:
        blocked = [float(r["fwd_20d"]) for r in po
                   if not r["new_longs"]]
        allowed = [float(r["fwd_20d"]) for r in po if r["new_longs"]]
        if len(blocked) >= 10 and len(allowed) >= 10:
            b_med, a_med = st.median(blocked), st.median(allowed)
            rep["posture_gate"] = {
                "blocked": {"n": len(blocked),
                            "med_20d": round(b_med, 2)},
                "allowed": {"n": len(allowed),
                            "med_20d": round(a_med, 2)},
                "edge": round(a_med - b_med, 2)}
            cur = _weight_num("posture:thin_tape:breadth_score_lt",
                              32.0)
            new = cur
            if b_med > a_med and cur > 24:
                new = cur - 2      # firing on fine days → tighten
            elif b_med < a_med - 3 and cur < 38:
                new = cur + 2      # proven protective → widen a bit
            if new != cur:
                db.execute_update(
                    "INSERT INTO engine_weights (key, value,"
                    " updated_at) VALUES (:k, CAST(:v AS jsonb),"
                    " now()) ON CONFLICT (key) DO UPDATE SET"
                    " value=CAST(:v AS jsonb), updated_at=now()",
                    {"k": "posture:thin_tape:breadth_score_lt",
                     "v": json.dumps(
                         {"value": new, "blocked_med": round(b_med, 2),
                          "allowed_med": round(a_med, 2),
                          "n": len(po), "by": "meta", "at": now})})
                rep["writes"].append(
                    f"posture:thin_tape bs<{cur:.0f}→{new:.0f} "
                    f"(blocked 20d med {b_med:+.1f}% vs allowed "
                    f"{a_med:+.1f}%)")

    # --- 2.9 rank calibration — does a higher rank actually pay? ---
    # ready-rows' rank decile vs realized 10d return. REPORT-ONLY —
    # same contract as the calibration block: a non-monotonic curve
    # means rank_weights are wrong; that call stays human.
    rk = db.execute_query(
        "SELECT e.use_case, e.rank,"
        " (SELECT close FROM daily_bars WHERE symbol=e.symbol"
        "  AND date >= e.as_of ORDER BY date LIMIT 1) AS base,"
        " (SELECT close FROM daily_bars WHERE symbol=e.symbol"
        "  AND date >= e.as_of ORDER BY date OFFSET 10 LIMIT 1)"
        "  AS fwd"
        " FROM readiness_evals e"
        " WHERE e.state='ready' AND e.rank IS NOT NULL"
        "   AND e.as_of <= CURRENT_DATE - 14")
    cal: dict[str, dict] = {}
    for r in rk or []:
        if not r.get("base") or not r.get("fwd"):
            continue
        ret = (float(r["fwd"]) / float(r["base"]) - 1) * 100
        b = min(9, int((float(r["rank"]) or 0) // 10))
        cal.setdefault(r["use_case"], {}).setdefault(
            b, []).append(ret)
    rep["rank_calibration"] = {
        uc: {f"{b*10}-{b*10+9}": {"n": len(v),
                                  "hit": round(sum(
                                      1 for x in v if x > 0)
                                      / len(v), 3),
                                  "med": round(st.median(v), 2)}
             for b, v in sorted(d.items()) if len(v) >= 5}
        for uc, d in cal.items()}
    rep["rank_rows"] = len(rk or [])

    # --- 3. the report itself is a weight row — the UI reads it ------
    db.execute_update(
        "INSERT INTO engine_weights (key, value, updated_at)"
        " VALUES ('meta:report', CAST(:v AS jsonb), now())"
        " ON CONFLICT (key) DO UPDATE SET"
        " value=CAST(:v AS jsonb), updated_at=now()",
        {"v": json.dumps(rep, default=str)})
    rep["writes"] = rep["writes"] or ["report only — no weight changes"]
    return rep
