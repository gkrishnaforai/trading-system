"""inference_ladder — the AI-cycle theme ladder: where the cycle is
today and where it is moving next (6-12mo horizon).

The reviewer's rotation ("who sells equipment when hyperscalers
build" → "who earns recurring revenue when models are used") is a
ladder, not a switch. Each rung is one business-model cohort ordered
by when its revenue shows up in the cycle:

    build      hyperscalers spend -> semi_equipment, accelerators,
               networking, memory, power
    deploy     neoclouds rent energized capacity
    utilize    data_layer + software monetize workloads running

Every rung journals four independent legs so the rotation claim is
checkable, not asserted:

    tape       median member return vs SPY (5d/20d) — what price says
    growth     median FY27+28 weighted growth + PEG from
               growth_compare_daily — what consensus expects
    evidence   approved demand_evidence axes for member symbols —
               what disclosures actually show (utilization,
               monetization, capex, durability)
    funding    worst capital_funding_risk among members

rotation_state is the honest verdict: evidence_led (disclosures
improving while tape lags — the forward-looking divergence),
tape_led (price moving without confirmed disclosures — unconfirmed
momentum), leading (both agree), fading (both negative), or
unknown (no evidence yet — priors only, never a favorable default).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# cycle order — earlier rungs earn revenue earlier in the build cycle.
# members come from demand_profile ingest_groups + the ai_infra yaml
# so the ladder stays in sync with the evidence feed.
_STAGES = [
    ("hyperscalers",   "build",    "capex spenders — the demand source"),
    ("semi_equipment", "build",    "foundry + tools — earliest revenue"),
    ("accelerators",   "build",    "compute silicon"),
    ("networking",     "build",    "connectivity + optics"),
    ("memory",         "build",    "HBM/DRAM/storage bits"),
    ("power",          "build",    "power + cooling delivery"),
    ("neoclouds",      "deploy",   "capacity rental — rents energized compute"),
    ("data_layer",     "utilize",  "data/ops platforms — monetize running workloads"),
    ("software",       "utilize",  "recurring software/security"),
]


def _members(group: str) -> list[str]:
    try:
        from app.fair_value_v2.demand_ingest import ingest_groups
        return list(ingest_groups().get(group) or [])
    except Exception:
        return []


def _tape(db, members: list[str]) -> dict:
    """Median member return vs SPY over 5d/20d."""
    if not members:
        return {}
    try:
        rows = db.execute_query(
            "SELECT symbol, date, close FROM daily_bars"
            " WHERE symbol = ANY(:s) AND date > current_date - 45"
            " ORDER BY symbol, date", {"s": members + ["SPY"]}) or []
        px: dict[str, list] = {}
        for r in rows:
            px.setdefault(r["symbol"], []).append((r["date"], float(r["close"])))
        spy = px.get("SPY") or []

        def rel(syms) -> dict:
            out = {}
            for w in (5, 20):
                rets = []
                spy_r = None
                if len(spy) > w:
                    spy_r = spy[-1][1] / spy[-1 - w][1] - 1
                for s in syms:
                    b = px.get(s) or []
                    if len(b) > w and spy_r is not None:
                        rets.append(b[-1][1] / b[-1 - w][1] - 1 - spy_r)
                if rets:
                    rets.sort()
                    out[f"rel_{w}d"] = round(rets[len(rets) // 2], 4)
            return out
        return rel(members)
    except Exception as exc:
        logger.debug("ladder tape: %s", exc)
        return {}


def _growth(db, members: list[str]) -> dict:
    """Median forward weighted-growth + PEG from the journaled
    growth_compare_daily payload — what consensus expects next."""
    try:
        r = db.execute_query(
            "SELECT payload FROM growth_compare_daily"
            " ORDER BY as_of DESC LIMIT 1")
        if not r:
            return {}
        payload = r[0]["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        names = (payload or {}).get("names") or {}
        wgs = [names[s]["weighted_growth"] for s in members
               if s in names and names[s].get("weighted_growth") is not None]
        pegs = [names[s]["peg_cagr"] for s in members
                if s in names and names[s].get("peg_cagr") is not None]
        out = {}
        if wgs:
            wgs.sort()
            out["med_weighted_growth"] = round(wgs[len(wgs) // 2], 3)
        if pegs:
            pegs.sort()
            out["med_peg_cagr"] = round(pegs[len(pegs) // 2], 2)
        out["n_growth"] = len(wgs)
        return out
    except Exception as exc:
        logger.debug("ladder growth: %s", exc)
        return {}


def _evidence(db, members: list[str]) -> dict:
    """Approved demand_evidence for member symbols → per-axis
    directions. Missing evidence stays unknown — never promoted."""
    try:
        from app.fair_value_v2.demand_evidence import derive_axes
        claims = db.execute_query(
            "SELECT symbol, axis, signal, source, source_date,"
            " confidence, status, value FROM demand_evidence"
            " WHERE status='approved' AND symbol = ANY(:s)",
            {"s": members}) or []
        axes = derive_axes(claims) if claims else {}
        out = {"n_claims": len(claims), "axes": {}}
        up = down = 0
        for axis, v in (axes or {}).items():
            pos = float(v.get("pos_score") or 0)
            neg = float(v.get("neg_score") or 0)
            direction = ("conflict" if pos > 0 and neg > 0
                         else "up" if pos > neg
                         else "down" if neg > pos
                         else "flat")
            out["axes"][axis] = {
                "value": v.get("value"), "direction": direction,
                "confidence": v.get("confidence"),
                "n": v.get("n_claims"),
                "conflict": v.get("conflict", False)}
            if direction == "up":
                up += 1
            elif direction == "down":
                down += 1
        out["axes_up"] = up
        out["axes_down"] = down
        return out
    except Exception as exc:
        logger.debug("ladder evidence: %s", exc)
        return {"n_claims": 0, "axes": {}, "axes_up": 0, "axes_down": 0}


def _profile(db, members: list[str]) -> dict:
    """Demand-model + monetization + funding distribution from the
    journaled company_demand_profile priors/evidence."""
    try:
        rows = db.execute_query(
            "SELECT symbol, demand_model, ai_monetization,"
            " capital_funding_risk, utilization_health,"
            " demand_durability FROM company_demand_profile"
            " WHERE symbol = ANY(:s)", {"s": members}) or []
        out: dict[str, Any] = {"models": {}, "monetization": {},
                               "funding_worst": "low"}
        rank = {"low": 0, "moderate": 1, "high": 2, "critical": 3,
                "unknown": -1}
        for r in rows:
            for k, key in (("demand_model", "models"),
                           ("ai_monetization", "monetization")):
                v = r.get(k) or "unknown"
                out[key][v] = out[key].get(v, 0) + 1
            fr = r.get("capital_funding_risk") or "unknown"
            if rank.get(fr, -1) > rank.get(out["funding_worst"], 0):
                out["funding_worst"] = fr
        return out
    except Exception as exc:
        logger.debug("ladder profile: %s", exc)
        return {}


def _rotation_state(tape: dict, ev: dict) -> str:
    """The honest verdict. evidence_led = disclosures improving while
    tape lags — the forward-looking divergence that IS the rotation
    signal. tape_led = price moving without confirmed disclosures —
    unconfirmed momentum."""
    rel20 = tape.get("rel_20d")
    up, down = ev.get("axes_up", 0), ev.get("axes_down", 0)
    tape_up = rel20 is not None and rel20 > 0.02
    tape_down = rel20 is not None and rel20 < -0.02
    ev_up = up > down and up > 0
    ev_down = down > up and down > 0
    if ev_up and not tape_up:
        return "evidence_led"
    if tape_up and not ev_up and not ev_down:
        return "tape_led"
    if tape_up and ev_up:
        return "leading"
    if tape_down and ev_down:
        return "fading"
    if tape_down:
        return "lagging"
    if ev_down:
        return "evidence_weak"
    return "unknown"


def compute() -> dict:
    from app.database import db
    rungs: dict[str, dict] = {}
    for group, stage, desc in _STAGES:
        members = _members(group)
        tape = _tape(db, members)
        growth = _growth(db, members)
        ev = _evidence(db, members)
        prof = _profile(db, members)
        rungs[group] = {
            "stage": stage, "description": desc, "members": members,
            "tape": tape, "growth": growth, "evidence": ev,
            "profile": prof,
            "rotation_state": _rotation_state(tape, ev)}
    # market regime — the consensus read across all approved claims
    try:
        from app.fair_value_v2.demand_evidence import market_claims
        from app.fair_value_v2.demand_score import (
            ai_capex_regime, cycle_warning_score)
        mc = market_claims()
        regime = ai_capex_regime(mc)
        warning = cycle_warning_score(mc)
    except Exception as exc:
        logger.debug("ladder regime: %s", exc)
        regime, warning = {}, {}
    return {"as_of": str(date.today()), "regime": regime,
            "warning": warning, "rungs": rungs}


def run(persist: bool = True) -> dict:
    out = compute()
    if persist:
        from app.database import db
        db.execute_update(
            "INSERT INTO ai_cycle_ladder_daily (as_of, payload)"
            " VALUES (current_date, CAST(:p AS jsonb))"
            " ON CONFLICT (as_of) DO UPDATE SET payload=EXCLUDED.payload",
            {"p": json.dumps(out, default=str)})
    return out


def latest() -> Optional[dict]:
    from app.database import db
    r = db.execute_query(
        "SELECT payload FROM ai_cycle_ladder_daily"
        " ORDER BY as_of DESC LIMIT 1")
    if not r:
        return None
    p = r[0]["payload"]
    return json.loads(p) if isinstance(p, str) else p
