"""AI Cycle Rotation Tracker — quarterly business-cycle composite.

Answers "where does this name stand in the AI cycle" per evidence
quarter — not "is the sector slowing" (capex_cycle) and not "is this
a good company" (research_runs). Eight weighted legs scored from
journaled evidence only, a three-peak detector (orders → estimates →
reported revenue; the sell zone sits between peak 1 and 2), a
demand-peak window stored as a year RANGE, and a first-match policy
decision journaled with the fired rule.

Honesty rules:
- every leg that can't be evaluated is UNKNOWN — excluded from the
  composite, never a silent zero; coverage reports how much of the
  spec was answerable
- seeded demand-peak windows are PRIORS (cohort_seed) — they move
  quarters_to_peak and show the peak_window_unsourced flag but can
  never trigger a TRIM alone; only claim-backed peaks can
- peak detectors are heuristics over journaled trends — journaled with
  their basis so each True/False/None is auditable
- rows append per (symbol, quarter_label, as_of) — prior quarters are
  never overwritten; movement compares across quarter_label
"""
from __future__ import annotations

import json
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from app.signals.pulse_engine import _cond, _eval_when

logger = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).parent / "cycle_tracker.yaml"

# demand_profile text axes → ranks so banded specs can compare them
_UTIL = {"rising": 3, "stable_high": 2, "stable": 1, "falling": 0}
_FUND = {"low": 3, "moderate": 2, "high": 1, "critical": 0}
_MONET = {"proven": 3, "scaling": 2, "early": 1, "unproven": 0}
_DURAB = {"contracted": 4, "recurring": 3, "usage_based": 2,
          "replacement_cycle": 1, "discretionary": 0.5,
          "speculative": 0}
_MTREND = {"improving": 2, "flat": 1, "declining": 0}


@lru_cache(maxsize=2)
def _spec() -> dict:
    return yaml.safe_load(_SPEC_PATH.read_text())


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def universe() -> dict[str, str]:
    """symbol -> cohort, from the spec."""
    return {s: c for c, cfg in (_spec().get("cohorts") or {}).items()
            for s in cfg.get("symbols") or []}


def _quarter_label(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ---------------------------------------------------------------------
# ctx — every field traces to a journaled row
# ---------------------------------------------------------------------

def _ctx(sym: str) -> dict:
    from app.database import db
    c: dict[str, Any] = {"symbol": sym}
    try:
        r = db.execute_query(
            "SELECT rev_growth, rev_accel, gm_slope, eps_growth,"
            " beat_streak, est_revision_pct, fwd_pe, gap_score, roic,"
            " om_now, om_qoq, om_slope, sbc_rev, fcf_ttm, fcf_margin,"
            " net_debt_ebitda FROM symbol_flywheel WHERE symbol=:s",
            {"s": sym})
        if r:
            c.update({k: _f(r[0].get(k)) for k in
                      ("rev_growth", "rev_accel", "gm_slope",
                       "eps_growth", "est_revision_pct", "fwd_pe",
                       "gap_score", "roic", "om_now", "om_qoq",
                       "om_slope", "sbc_rev", "fcf_ttm", "fcf_margin")})
            c["beat_streak"] = r[0].get("beat_streak")
            c["nde"] = _f(r[0].get("net_debt_ebitda"))
    except Exception as exc:
        logger.debug("cycle ctx flywheel %s: %s", sym, exc)
    try:
        r = db.execute_query(
            "SELECT rpo_yoy, crpo_share, def_rev_yoy, gw_impair_fy"
            " FROM symbol_sec_facts WHERE symbol=:s", {"s": sym})
        if r:
            c.update({k: _f(r[0].get(k)) for k in
                      ("rpo_yoy", "crpo_share", "def_rev_yoy",
                       "gw_impair_fy")})
    except Exception as exc:
        logger.debug("cycle ctx sec_facts %s: %s", sym, exc)
    try:
        from app.research import quarter
        qt = quarter.trends(quarter.quarters(sym, 8))
        c["rev_qoq"] = _f(qt.get("rev_qoq"))
        c["rev_yoy_q"] = _f(qt.get("rev_yoy"))
        c["q_rev_accel"] = _f(qt.get("rev_accel"))
        mt = qt.get("margin_trend")
        c["margin_trend"] = _MTREND.get(mt) if mt else None
        c["dilution_pct"] = _f(qt.get("dilution_yoy"))
        c["fcf_conversion"] = _f(qt.get("fcf_conversion"))
        c["runway_quarters"] = _f(qt.get("runway_quarters"))
    except Exception as exc:
        logger.debug("cycle ctx quarters %s: %s", sym, exc)
    try:
        r = db.execute_query(
            "SELECT utilization_health, capital_funding_risk,"
            " ai_monetization, demand_durability"
            " FROM company_demand_profile WHERE symbol=:s", {"s": sym})
        if r:
            c["utilization_rank"] = _UTIL.get(
                r[0].get("utilization_health") or "")
            c["funding_rank"] = _FUND.get(
                r[0].get("capital_funding_risk") or "")
            c["monetization_rank"] = _MONET.get(
                r[0].get("ai_monetization") or "")
            c["durability_rank"] = _DURAB.get(
                r[0].get("demand_durability") or "")
    except Exception as exc:
        logger.debug("cycle ctx demand_profile %s: %s", sym, exc)
    try:
        r = db.execute_query(
            "SELECT status FROM symbol_thesis WHERE symbol=:s",
            {"s": sym})
        c["thesis_status"] = r[0]["status"] if r else "unknown"
        # a break is a positive detection — absent row is unverified,
        # not confirmed-broken; coverage/flags carry the caveat
        c["structural_break"] = c["thesis_status"] == "broken"
    except Exception as exc:
        logger.debug("cycle ctx thesis %s: %s", sym, exc)
        c["thesis_status"] = "unknown"
        c["structural_break"] = False
    try:
        r = db.execute_query(
            "SELECT top1_pct FROM symbol_customer_conc WHERE symbol=:s",
            {"s": sym})
        c["top1_pct"] = _f(r[0]["top1_pct"]) if r else None
    except Exception:
        c["top1_pct"] = None
    try:
        r = db.execute_query(
            "SELECT count(*) AS n FROM design_wins WHERE symbol=:s",
            {"s": sym})
        c["design_wins_n"] = int(r[0]["n"]) if r else 0
    except Exception:
        c["design_wins_n"] = 0
    try:
        r = db.execute_query(
            "SELECT scores FROM research_runs WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT 1", {"s": sym})
        sc = r[0]["scores"] if r else {}
        if isinstance(sc, str):
            sc = json.loads(sc)
        for k, fld in (("ai_tailwind", "ai_tailwind"),
                       ("business_strength", "bstrength"),
                       ("valuation_opportunity", "vo_score"),
                       ("technical_entry", "te_score")):
            v = (sc.get(k) or {}).get("score")
            c[fld] = _f(v)
    except Exception as exc:
        logger.debug("cycle ctx research %s: %s", sym, exc)
    try:
        r = db.execute_query(
            "SELECT score FROM capex_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        c["capex_score"] = _f(r[0]["score"]) if r else None
    except Exception:
        c["capex_score"] = None
    return c


# ---------------------------------------------------------------------
# component scoring — mirrors research/scores.evaluate: first-match
# bands, unknown legs excluded, composite renormalized over answered
# weight, coverage = answered share
# ---------------------------------------------------------------------

def _score(ctx: dict) -> dict:
    spec = _spec()
    comps, missing = {}, []
    for comp, cfg in (spec.get("components") or {}).items():
        sc, note, unk = None, None, False
        n0 = len(missing)
        for band in cfg.get("bands") or []:
            if "default" in band:
                sc, note = band["default"], band.get("note")
                continue
            if _cond(ctx, band.get("if") or {}, missing,
                     spec.get("groups") or {}):
                sc, note = band["score"], band.get("note")
                break
        if sc is None:
            unk, note = True, ("insufficient evidence: " + ",".join(
                sorted(set(missing[n0:]))[:4])
                if len(missing) > n0 else "no band matched")
        comps[comp] = {"score": sc, "weight": float(
            cfg.get("weight", 0)), "note": note,
            **({"unknown": True} if unk else {})}
    answered = sum(c["weight"] for c in comps.values()
                   if not c.get("unknown"))
    total_w = sum(c["weight"] for c in comps.values())
    comp = (sum(c["score"] * c["weight"] for c in comps.values()
                if not c.get("unknown")) / answered
            if answered else None)
    capped = None
    for cap in spec.get("caps") or []:
        matched, log = _eval_when(ctx, cap.get("when") or {},
                                  spec.get("groups") or {})
        missing.extend(log.get("missing") or [])
        if matched and comp is not None and comp > cap["cap"]:
            comp, capped = cap["cap"], cap.get("note")
            break
    return {"composite": round(comp, 1) if comp is not None else None,
            "components": comps, "capped": capped,
            "missing": sorted(set(missing)),
            "coverage_pct": round(answered / total_w, 2)
            if total_w else None}


# ---------------------------------------------------------------------
# three-peak detection — heuristic, journaled with basis
# ---------------------------------------------------------------------

def _detect_peaks(ctx: dict, prior: Optional[dict]) -> dict:
    """order → estimate → revenue peak booleans; None = can't tell.
    `prior` is the latest snapshot from a different quarter_label."""
    p = prior or {}
    pl = (p.get("components") or {})

    # peak 1 — orders/backlog: RPO or deferred-rev shrinkage is direct;
    # absent those, hard rev decel into a slowing sector proxies it
    order = None
    rpo, drv = ctx.get("rpo_yoy"), ctx.get("def_rev_yoy")
    if rpo is not None or drv is not None:
        order = bool((rpo is not None and rpo < -0.02)
                     or (drv is not None and drv < -0.02))
    if not order and pl.get("backlog_quality", {}).get("score") is not None:
        cur = ctx.get("_leg_backlog_quality")
        if cur is not None and pl["backlog_quality"]["score"] - cur >= 20:
            order = True
    if order is None and ctx.get("rev_accel") is not None:
        order = bool(ctx["rev_accel"] < -0.10
                     and (ctx.get("capex_score") or 0) >= 50)

    # peak 2 — expectations: revision drift negative, or the est leg
    # fell sharply quarter over quarter
    est = None
    er = ctx.get("est_revision_pct")
    if er is not None:
        est = er < -0.03
    if not est and pl.get("est_revisions", {}).get("score") is not None:
        cur = ctx.get("_leg_est_revisions")
        if cur is not None and pl["est_revisions"]["score"] - cur >= 20:
            est = True

    # peak 3 — reported growth rolled
    rev = None
    if ctx.get("rev_qoq") is not None or ctx.get("q_rev_accel") is not None:
        rev = bool((ctx.get("rev_qoq") or 0) < 0
                   or (ctx.get("q_rev_accel") or 0) < -0.15)

    return {"order_peak": order, "estimate_peak": est,
            "revenue_peak": rev}


def _rev_peak_risk(ctx: dict) -> tuple[Optional[float], list]:
    legs, basis, hit = _spec().get("rev_peak_risk", {}).get("legs") or [], [], []
    if not legs:
        return None, basis
    total = 0
    for leg in legs:
        m: list = []
        if _cond(ctx, leg.get("when") or {}, m,
                 _spec().get("groups") or {}):
            total += leg["pts"]
            hit.append(leg.get("note"))
    return min(total, 100), hit


def _peak_window(sym: str, cohort: str) -> dict:
    """Claim-backed window beats the cohort seed. Claims are approved
    demand_evidence peak_window rows: {lo,hi} | {year_lo,year_hi} |
    {window:[lo,hi]} | scalar year."""
    from app.database import db
    lo = hi = None
    src, conf = "cohort_seed", (_spec()["cohorts"].get(cohort) or {}) \
        .get("peak", {}).get("confidence", "low")
    try:
        r = db.execute_query(
            "SELECT value, confidence FROM demand_evidence"
            " WHERE symbol=:s AND axis='peak_window'"
            " AND status='approved'"
            " ORDER BY source_date DESC NULLS LAST LIMIT 1",
            {"s": sym})
        if r:
            v = r[0]["value"]
            if isinstance(v, str):
                v = json.loads(v)
            if isinstance(v, dict):
                w = v.get("window") or [v.get("lo") or v.get("year_lo"),
                                        v.get("hi") or v.get("year_hi")]
                lo, hi = w[0], w[1] if len(w) > 1 else w[0]
            elif v is not None:
                lo = hi = int(v)
            if lo:
                src, conf = "claim", r[0].get("confidence") or "medium"
    except Exception as exc:
        logger.debug("cycle peak claim %s: %s", sym, exc)
    if lo is None:
        seed = (_spec()["cohorts"].get(cohort) or {}).get("peak") or {}
        lo, hi = seed.get("lo"), seed.get("hi")
    return {"lo": lo, "hi": hi if hi is not None else lo,
            "source": src, "confidence": conf}


def _qtp(peak: dict, as_of: date) -> Optional[int]:
    """Quarters to the window MIDPOINT — the expected-peak convention.
    The lo edge stays journaled for context; midpoint is what 'peak
    >4 quarters away' means when the honest answer is a range."""
    if not peak.get("lo"):
        return None
    mid = (peak["lo"] + peak["hi"]) / 2
    cur = as_of.year * 4 + (as_of.month - 1) // 3 + 1
    return round(mid * 4 - cur)


def _movement(peak: dict, prior: Optional[dict]) -> str:
    """Range-vs-range vs the prior quarter — overlap can't produce a
    false 'moved' read."""
    if not prior or not peak.get("lo") or not prior.get("demand_peak_lo"):
        return "new"
    if peak["hi"] < prior["demand_peak_lo"]:
        return "pulled_forward"
    if peak["lo"] > prior["demand_peak_hi"]:
        return "pushed_out"
    return "unchanged"


def _decide(ctx: dict) -> tuple[str, dict, list]:
    spec = _spec()
    for rule in spec.get("decisions") or []:
        matched, log = _eval_when(ctx, rule.get("when") or {},
                                  spec.get("groups") or {})
        if matched:
            flags = [f["flag"] for f in spec.get("flags") or []
                     if _eval_when(ctx, f.get("when") or {},
                                   spec.get("groups") or {})[0]]
            return rule["action"], {"note": rule.get("note"),
                                    "conditions": log["conditions"],
                                    "missing": log["missing"]}, flags
    return "research_incomplete", {"note": "no rule matched"}, []


# ---------------------------------------------------------------------
# journal + read
# ---------------------------------------------------------------------

def _ensure() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS cycle_snapshots ("
        " id bigserial PRIMARY KEY, symbol text NOT NULL,"
        " quarter_label text NOT NULL, as_of date NOT NULL,"
        " cohort text, composite numeric, coverage_pct numeric,"
        " demand_accel numeric, backlog_quality numeric,"
        " est_revisions numeric, margin_cf numeric,"
        " capacity_util numeric, customer_adoption numeric,"
        " capital_recovery numeric, valuation_duration numeric,"
        " order_peak boolean, estimate_peak boolean,"
        " revenue_peak boolean,"
        " demand_peak_lo smallint, demand_peak_hi smallint,"
        " peak_confidence text, peak_source text, peak_movement text,"
        " quarters_to_peak smallint, rev_peak_risk numeric,"
        " decision text, structural_break boolean,"
        " valuation_blocked boolean,"
        " components jsonb NOT NULL DEFAULT '{}',"
        " peaks jsonb NOT NULL DEFAULT '{}',"
        " decision_detail jsonb NOT NULL DEFAULT '{}',"
        " flags jsonb NOT NULL DEFAULT '[]', rules_version text,"
        " created_at timestamptz NOT NULL DEFAULT now(),"
        " UNIQUE (symbol, quarter_label, as_of))", {})


def _prior_snapshot(sym: str, qlabel: str) -> Optional[dict]:
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT components, demand_peak_lo, demand_peak_hi"
            " FROM cycle_snapshots WHERE symbol=:s"
            " AND quarter_label<>:q ORDER BY as_of DESC LIMIT 1",
            {"s": sym, "q": qlabel})
        if r:
            row = dict(r[0])
            if isinstance(row.get("components"), str):
                row["components"] = json.loads(row["components"])
            return row
    except Exception as exc:
        logger.debug("cycle prior %s: %s", sym, exc)
    return None


def evaluate_symbol(sym: str, as_of: Optional[date] = None) -> dict:
    """One snapshot dict — journaled by refresh(), returnable for
    ad-hoc eval/tests without writing."""
    as_of = as_of or date.today()
    qlabel = _quarter_label(as_of)
    cohort = universe().get(sym.upper())
    ctx = _ctx(sym.upper())
    ctx["cohort"] = cohort
    prior = _prior_snapshot(sym.upper(), qlabel)

    scored = _score(ctx)
    for k, v in scored["components"].items():
        ctx[k] = v["score"]
        ctx[f"_leg_{k}"] = v["score"]
    ctx["composite"] = scored["composite"]
    ctx["coverage_pct"] = scored["coverage_pct"]

    peaks = _detect_peaks(ctx, prior)
    ctx.update(peaks)
    peak = _peak_window(sym.upper(), cohort or "")
    ctx["peak_source"] = peak["source"]
    ctx["quarters_to_peak"] = _qtp(peak, as_of)
    # seed priors inform, never trigger — only claim-backed windows can
    ctx["sourced_qtp"] = ctx["quarters_to_peak"] \
        if peak["source"] == "claim" else None
    ctx["rev_peak_risk"], risk_basis = _rev_peak_risk(ctx)
    vb_when = _spec().get("valuation_blocked_when") or {}
    ctx["valuation_blocked"], _ = _eval_when(
        ctx, vb_when, _spec().get("groups") or {})
    # accumulate/add_on_pullback read quarters_to_peak from any window
    # (seeds are the framework's map); the trim-proximity rule reads
    # sourced_qtp — claim-backed only, seeds can't auto-trim
    decision, detail, flags = _decide(ctx)

    return {
        "symbol": sym.upper(), "quarter_label": qlabel,
        "as_of": str(as_of), "cohort": cohort,
        "composite": scored["composite"],
        "coverage_pct": scored["coverage_pct"],
        "legs": {k: v["score"] for k, v in
                 scored["components"].items()},
        "components": scored["components"],
        "capped": scored["capped"],
        "peaks": {**peaks, "basis": {
            "order": "rpo/def_rev shrinkage or prior-leg collapse",
            "estimate": "revision drift < -3% or leg collapse",
            "revenue": "rev_qoq<0 or accel < -15%"}},
        "demand_peak_lo": peak["lo"], "demand_peak_hi": peak["hi"],
        "peak_confidence": peak["confidence"],
        "peak_source": peak["source"],
        "peak_movement": _movement(peak, prior),
        "quarters_to_peak": ctx["quarters_to_peak"],
        "rev_peak_risk": ctx["rev_peak_risk"],
        "rev_peak_risk_basis": risk_basis,
        "decision": decision, "decision_detail": detail,
        "structural_break": ctx["structural_break"],
        "valuation_blocked": ctx["valuation_blocked"],
        "flags": flags,
        "rules_version": f"cycle@{_spec().get('version', 0)}",
    }


def refresh(as_of: Optional[date] = None) -> dict:
    """Score the whole universe, journal one row per symbol."""
    from app.database import db
    as_of = as_of or date.today()
    _ensure()
    done, errors = 0, {}
    for sym, cohort in sorted(universe().items()):
        try:
            s = evaluate_symbol(sym, as_of)
            db.execute_update(
                "INSERT INTO cycle_snapshots (symbol, quarter_label,"
                " as_of, cohort, composite, coverage_pct,"
                " demand_accel, backlog_quality, est_revisions,"
                " margin_cf, capacity_util, customer_adoption,"
                " capital_recovery, valuation_duration,"
                " order_peak, estimate_peak, revenue_peak,"
                " demand_peak_lo, demand_peak_hi, peak_confidence,"
                " peak_source, peak_movement, quarters_to_peak,"
                " rev_peak_risk, decision, structural_break,"
                " valuation_blocked, components, peaks,"
                " decision_detail, flags, rules_version)"
                " VALUES (:symbol,:ql,:ao,:co,:comp,:cov,"
                " :da,:bq,:er,:mc,:cu,:ca,:cr,:vd,"
                " :op,:ep,:rp,:plo,:phi,:pc,:ps,:pm,:qtp,:rpr,"
                " :dec,:sb,:vb,:comps,:peaks,:dd,:flags,:rv)"
                " ON CONFLICT (symbol, quarter_label, as_of)"
                " DO NOTHING",
                {"symbol": sym, "ql": s["quarter_label"], "ao": as_of,
                 "co": cohort, "comp": s["composite"],
                 "cov": s["coverage_pct"],
                 "da": s["legs"]["demand_accel"],
                 "bq": s["legs"]["backlog_quality"],
                 "er": s["legs"]["est_revisions"],
                 "mc": s["legs"]["margin_cf"],
                 "cu": s["legs"]["capacity_util"],
                 "ca": s["legs"]["customer_adoption"],
                 "cr": s["legs"]["capital_recovery"],
                 "vd": s["legs"]["valuation_duration"],
                 "op": s["peaks"]["order_peak"],
                 "ep": s["peaks"]["estimate_peak"],
                 "rp": s["peaks"]["revenue_peak"],
                 "plo": s["demand_peak_lo"], "phi": s["demand_peak_hi"],
                 "pc": s["peak_confidence"], "ps": s["peak_source"],
                 "pm": s["peak_movement"], "qtp": s["quarters_to_peak"],
                 "rpr": s["rev_peak_risk"], "dec": s["decision"],
                 "sb": s["structural_break"],
                 "vb": s["valuation_blocked"],
                 "comps": json.dumps(s["components"]),
                 "peaks": json.dumps(s["peaks"]),
                 "dd": json.dumps(s["decision_detail"]),
                 "flags": json.dumps(s["flags"]),
                 "rv": s["rules_version"]})
            done += 1
        except Exception as exc:
            errors[sym] = str(exc)
            logger.warning("cycle refresh %s: %s", sym, exc)
    return {"as_of": str(as_of), "evaluated": done,
            "errors": errors or None}


def current() -> dict:
    """Latest snapshot per symbol + cohort aggregates for the board."""
    from app.database import db
    _ensure()
    rows = db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, quarter_label, as_of,"
        " cohort, composite, coverage_pct, demand_accel,"
        " backlog_quality, est_revisions, margin_cf, capacity_util,"
        " customer_adoption, capital_recovery, valuation_duration,"
        " order_peak, estimate_peak, revenue_peak, demand_peak_lo,"
        " demand_peak_hi, peak_confidence, peak_source,"
        " peak_movement, quarters_to_peak, rev_peak_risk, decision,"
        " structural_break, valuation_blocked, components,"
        " decision_detail, flags"
        " FROM cycle_snapshots ORDER BY symbol, as_of DESC, id DESC")
    for r in rows:
        for j in ("components", "decision_detail", "flags"):
            if isinstance(r.get(j), str):
                r[j] = json.loads(r[j])
        for k in ("composite", "coverage_pct", "rev_peak_risk"):
            r[k] = _f(r[k])
    cohorts: dict[str, dict] = {}
    for r in rows:
        c = r.get("cohort") or "unclassified"
        agg = cohorts.setdefault(c, {"n": 0, "scored": 0, "comps": [],
                                     "decisions": {}})
        agg["n"] += 1
        if r["composite"] is not None:
            agg["scored"] += 1
            agg["comps"].append(r["composite"])
        d = r.get("decision") or "unknown"
        agg["decisions"][d] = agg["decisions"].get(d, 0) + 1
    for c, agg in cohorts.items():
        cfg = (_spec().get("cohorts") or {}).get(c) or {}
        agg["label"] = cfg.get("label", c)
        agg["phase"] = cfg.get("phase")
        agg["peak"] = cfg.get("peak")
        agg["median"] = round(sorted(agg["comps"])[len(agg["comps"]) // 2], 1) \
            if agg["comps"] else None
        agg.pop("comps")
    order = {"accumulate": 0, "add_on_pullback": 1, "hold": 2,
             "trim": 3, "exit": 4, "research_incomplete": 5}
    rows.sort(key=lambda r: (order.get(r.get("decision") or "", 6),
                             -(r["composite"] or -1)))
    return {"as_of": str(rows[0]["as_of"]) if rows else None,
            "quarter_label": rows[0]["quarter_label"] if rows else None,
            "n": len(rows), "rows": rows, "cohorts": cohorts}


def history(sym: str) -> dict:
    """All quarters for one name — the movement evidence."""
    from app.database import db
    _ensure()
    rows = db.execute_query(
        "SELECT quarter_label, as_of, composite, coverage_pct,"
        " decision, rev_peak_risk, demand_peak_lo, demand_peak_hi,"
        " peak_movement, quarters_to_peak, order_peak, estimate_peak,"
        " revenue_peak, components, decision_detail, flags"
        " FROM cycle_snapshots WHERE symbol=:s"
        " ORDER BY quarter_label DESC, as_of DESC LIMIT 24",
        {"s": sym.upper()})
    for r in rows:
        for j in ("components", "decision_detail", "flags"):
            if isinstance(r.get(j), str):
                r[j] = json.loads(r[j])
        r["composite"] = _f(r["composite"])
        r["rev_peak_risk"] = _f(r["rev_peak_risk"])
    return {"symbol": sym.upper(), "rows": rows}
