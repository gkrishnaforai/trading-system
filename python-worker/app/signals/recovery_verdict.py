"""Recovery Verdict — Phase-1 read-only composition layer.

Reconciles what six engines see independently into one journaled
answer: current state, what must happen next, what invalidates it,
and where the engines DISAGREE. It does not average scores — it
reconciles evidence families (one underlying observation = one vote)
and surfaces conflicts. Phase 1 advises; nothing here moves money.

State machine (hysteresis: promotion needs evidence across sessions;
demotion is one-session — protecting capital beats elegance):
  NORMAL → EXHAUSTION → STABILIZATION → RETEST/RECOVERY
  any → STRUCTURAL_IMPAIRMENT (thesis broken/deteriorating)
  demotions fire immediately; stabilization idles ~10d → NORMAL
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional

from app.signals.recovery_snapshots import Snap

logger = logging.getLogger(__name__)

ENGINE_VERSION = "recovery_verdict_v1"
PILOT = ["COHR", "CRDO", "VRT", "ALAB", "NBIS", "IREN", "INTC", "MU",
         "NVDA", "AMD", "AVGO", "UBER", "SE", "UPST", "NOW", "ZS",
         "NET", "APLD", "UAL", "PEP"]          # PEP = negative control

S = {"NORMAL", "EXHAUSTION", "STABILIZATION", "RETEST", "RECOVERY",
     "STRUCTURAL_IMPAIRMENT"}
_DECAY_DAYS = 10


def _evidence_families(reg: Snap, sel: Snap, tape: Snap,
                       intra: Snap, fund: Snap) -> dict:
    """One underlying observation = one vote, no matter how many
    engines observed it (the derive_confirmations rollup pattern,
    applied cross-engine)."""
    r, sl, t, i, f = (reg.data, sel.data, tape.data,
                    intra.data, fund.data)
    frag = r.get("fragility")
    return {
        "volatility_stress": bool(
            r.get("regime") in ("risk_off", "stress")
            or (frag is not None and frag >= 50)),
        "breadth_weak": bool(
            (r.get("permissions") or {}).get("normal_long") is False),
        "relative_strength": bool(
            (i.get("detail") or {}).get("rel_strength") is True
            or "outperform" in str(t.get("why") or "").lower()),
        "volume_exhaustion": bool(
            sl.get("event_type") in ("capitulation", "macro_panic",
                                     "positioning_unwind")
            or (i.get("detail") or {}).get("exhaustion") is True),
        "thesis_intact": bool(
            f.get("thesis_status") not in
            ("broken", "severely_deteriorating", "deteriorating")),
    }


def _conflicts(fams: dict, intra: Snap, reg: Snap) -> list[dict]:
    """Surface disagreements — never average them away."""
    out = []
    i, r = intra.data, reg.data
    if fams["volume_exhaustion"] and not fams["relative_strength"]:
        out.append({"layers": ["volume_exhaustion", "relative_strength"],
                    "note": "selling exhaustion but no demand proof yet"})
    if (i.get("signal") in ("sustained_buying", "recovery")
            and fams["volatility_stress"]):
        out.append({"layers": ["intraday", "market_regime"],
                    "note": "buyers returning intraday while market "
                            "still under stress"})
    if (reg.data.get("dip_character") == "broad_deleveraging"
            and fams["relative_strength"]):
        out.append({"layers": ["dip_character", "relative_strength"],
                    "note": "broad liquidation but name outperforming "
                            "— idiosyncratic demand"})
    return out


def build_recovery_verdict(ticker: str, as_of: datetime,
                           regime: Snap, selloff: Snap, tape: Snap,
                           intraday: Snap, permission: Snap,
                           fundamental: Snap,
                           prev_state: Optional[str] = None,
                           prev_state_at: Optional[str] = None,
                           ) -> dict:
    """Pure composer — testable with injected snapshots."""
    snaps = {"regime": regime, "selloff": selloff, "tape": tape,
             "intraday": intraday, "permission": permission,
             "fundamental": fundamental}
    missing = [k for k, s in snaps.items() if not s.available]
    ev_refs = [{"engine": k, "as_of": s.as_of, "ref": s.source_ref}
               for k, s in snaps.items() if s.available]

    r, sl, i, f = (regime.data, selloff.data,
                   intraday.data, fundamental.data)
    fams = _evidence_families(regime, selloff, tape, intraday, fundamental)
    conflicts = _conflicts(fams, intraday, regime)

    # ---- hard gates ----
    thesis_bad = f.get("thesis_status") in (
        "broken", "severely_deteriorating")
    liquidation = (r.get("dip_character") == "broad_deleveraging"
                   and r.get("stress_direction") == "worsening")
    gates = {
        "thesis_intact": not thesis_bad,
        "market_liquidation_inactive": not liquidation,
        "fundamental_snapshot_present": fundamental.available,
    }

    # ---- candidate next state ----
    sig = i.get("signal")
    held_lows = bool((i.get("detail") or {}).get("higher_lows"))
    reclaim = bool((i.get("detail") or {}).get("vwap_reclaim")
                   or sig == "sustained_buying")
    if thesis_bad:
        nxt = "STRUCTURAL_IMPAIRMENT"
    elif prev_state == "STRUCTURAL_IMPAIRMENT":
        nxt = ("STRUCTURAL_IMPAIRMENT"      # stays until thesis clears
               if f.get("thesis_status") == "deteriorating"
               else "NORMAL")
    elif sig in ("failed_rebound", "selling_accelerating") or liquidation:
        nxt = "EXHAUSTION"
    elif sl.get("event_type") or fams["volume_exhaustion"]:
        nxt = "EXHAUSTION"
    elif reclaim and held_lows and fams["relative_strength"]:
        nxt = "RECOVERY"
    elif reclaim or held_lows or sig in ("recovery", "stabilizing"):
        nxt = "STABILIZATION"
    else:
        nxt = "NORMAL"

    # ---- hysteresis: promote at most one stage per eval; demote freely
    order = ["NORMAL", "EXHAUSTION", "STABILIZATION", "RETEST",
             "RECOVERY"]
    if prev_state in order and nxt in order \
            and order.index(nxt) > order.index(prev_state) + 1:
        nxt = order[order.index(prev_state) + 1]
    # retest: bounce then pullback that holds, from STAB/RECOVERY
    if prev_state in ("STABILIZATION", "RECOVERY") and nxt == "STABILIZATION" \
            and sl.get("event_type") is None and fams["relative_strength"]:
        nxt = "RETEST"
    # decay: stabilization idles ~10 sessions → NORMAL-watch
    days_in_state = None
    if prev_state == nxt and prev_state_at:
        try:
            days_in_state = (as_of.date() -
                             datetime.fromisoformat(
                                 str(prev_state_at)[:10]).date()).days
        except Exception:
            days_in_state = None
    if nxt == "STABILIZATION" and prev_state == "STABILIZATION" \
            and (days_in_state or 0) >= _DECAY_DAYS:
        nxt = "NORMAL"

    # ---- advisory decision (Phase 1: journaled, never executed) ----
    if nxt == "STRUCTURAL_IMPAIRMENT":
        action = "AVOID" if f.get("thesis_status") == "broken" else "TRIM"
    elif not gates["market_liquidation_inactive"]:
        action = "WATCH"
    elif nxt == "EXHAUSTION":
        action = "WATCH"
    elif nxt in ("STABILIZATION", "RETEST"):
        action = "STARTER" if all(gates.values()) else "WATCH"
    elif nxt == "RECOVERY":
        action = "ADD" if all(gates.values()) else "STARTER"
    else:
        action = "WATCH" if fams["volume_exhaustion"] else "HOLD"
    if missing and "fundamental" in missing:
        action = "WATCH" if action in ("STARTER", "ADD") else action

    req_conf, inval = [], []
    if nxt in ("EXHAUSTION", "STABILIZATION", "RETEST"):
        req_conf += ["hold the recent swing low",
                     "reclaim and sustain VWAP",
                     "outperform the peer basket on red days"]
        inval += ["break below the recent swing low",
                  "company-specific negative guidance",
                  "market stress re-accelerates"]
    if nxt == "RECOVERY":
        req_conf += ["daily structure confirms across sessions"]
        inval += ["recovery loses momentum on rising volume"]

    return {
        "ticker": ticker, "as_of": as_of.isoformat(),
        "engine_version": ENGINE_VERSION, "state": nxt,
        "prev_state": prev_state,
        "state_changed": nxt != prev_state,
        "event": {"type": sl.get("event_type"),
                  "severity": ("high" if sl.get("score") and
                               sl["score"] >= 70 else "medium")
                  if sl.get("event_type") else None},
        "market": {"regime": r.get("regime"),
                   "dip_character": r.get("dip_character"),
                   "fragility": r.get("fragility"),
                   "stress_direction": r.get("stress_direction")},
        "stock": {"attribution": tape.data.get("attribution"),
                  "why": tape.data.get("why")},
        "recovery": {"intraday_signal": sig,
                     "vwap_reclaim": reclaim,
                     "higher_lows": held_lows},
        "decision": {"action": action,
                     "confidence": ("low" if missing else
                                    "provisional" if conflicts
                                    else "normal"),
                     "gates": gates, "conflicts": conflicts},
        "evidence_families": fams,
        "required_confirmation": req_conf,
        "invalidation_conditions": inval,
        "evidence_refs": ev_refs,
        "missing_inputs": missing,
    }


def evaluate(sym: str) -> dict:
    """Gather snapshots, compose, journal — Phase-1 read-only."""
    from app.database import db
    from app.signals import recovery_snapshots as rs
    sym = sym.upper()
    prev = db.execute_query(
        "SELECT state, as_of FROM recovery_verdicts WHERE symbol=:s"
        " ORDER BY as_of DESC, id DESC LIMIT 1", {"s": sym})
    prev_state = prev[0]["state"] if prev else None
    prev_at = str(prev[0]["as_of"]) if prev else None

    now = datetime.now()
    v = build_recovery_verdict(
        sym, now,
        rs.regime_snapshot(), rs.selloff_snapshot(sym),
        rs.tape_snapshot(sym), rs.intraday_snapshot(sym),
        Snap(), rs.fundamental_snapshot(sym), prev_state, prev_at)

    db.execute_update(
        "INSERT INTO recovery_verdicts (symbol, as_of, engine_version,"
        " state, prev_state, state_changed, transition_reason,"
        " event_type, market, stock, recovery, decision,"
        " decision_confidence, gates, conflicts,"
        " required_confirmation, invalidation_conditions,"
        " evidence_refs, missing_inputs, detail)"
        " VALUES (:s,:d,:v,:st,:ps,:sc,:tr,:et,CAST(:m AS jsonb),"
        " CAST(:sk AS jsonb),CAST(:rc AS jsonb),:dc,:dcf,"
        " CAST(:g AS jsonb),CAST(:cf AS jsonb),CAST(:rq AS jsonb),"
        " CAST(:iv AS jsonb),CAST(:er AS jsonb),CAST(:mi AS jsonb),"
        " CAST(:dt AS jsonb))"
        " ON CONFLICT (symbol, as_of, engine_version) DO UPDATE SET"
        " state=EXCLUDED.state, prev_state=EXCLUDED.prev_state,"
        " state_changed=EXCLUDED.state_changed,"
        " transition_reason=EXCLUDED.transition_reason,"
        " detail=EXCLUDED.detail",
        {"s": sym, "d": now.date().isoformat(), "v": ENGINE_VERSION,
         "st": v["state"], "ps": prev_state,
         "sc": v["state_changed"],
         "tr": (" → ".join(filter(None, [prev_state, v["state"]]))
                if v["state_changed"] else None),
         "et": v["event"]["type"],
         "m": json.dumps(v["market"], default=str),
         "sk": json.dumps(v["stock"], default=str),
         "rc": json.dumps(v["recovery"], default=str),
         "dc": v["decision"]["action"],
         "dcf": v["decision"]["confidence"],
         "g": json.dumps(v["decision"]["gates"], default=str),
         "cf": json.dumps(v["decision"]["conflicts"], default=str),
         "rq": json.dumps(v["required_confirmation"], default=str),
         "iv": json.dumps(v["invalidation_conditions"], default=str),
         "er": json.dumps(v["evidence_refs"], default=str),
         "mi": json.dumps(v["missing_inputs"], default=str),
         "dt": json.dumps(v, default=str)})
    return v


def run(symbols: Optional[list[str]] = None) -> dict:
    syms = symbols or PILOT
    out, errs = {}, []
    for s in syms:
        try:
            v = evaluate(s)
            out[s] = v["state"]
        except Exception as exc:
            errs.append(f"{s}: {exc}")
    return {"symbols": len(syms), "evaluated": len(out),
            "states": out, "errors": errs}
