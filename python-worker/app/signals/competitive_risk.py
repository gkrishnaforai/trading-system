"""Competitive Disruption & Substitution Engine — CRS.

Answers "does this name capture the industry's growth, or lose share
inside it" — a different question from the cycle composite ("how good
is the business") and FDCS ("can it capture future demand"). Six
resilience legs, uniform direction (100 = protected), scored over an
APPROVED threat-claims journal:

    substitution_resist   20   how much revenue can be replaced
    competitive_position  20   incumbent wins vs rival progress
    insourcing_resist     15   can customers build it themselves
    technology_moat       15   how hard to replicate
    ecosystem_switching   15   how hard to migrate away
    value_capture         15   can economics survive pressure

Honesty rules:
- every leg that can't be evaluated is UNKNOWN — excluded from the
  composite, never zeroed; coverage reports the answered share
- announcements are not production: stage multipliers scale every
  threat's exposure, and pre-production evidence alone can push a leg
  no lower than 60
- opportunity-direction threats (AVGO/MRVL insourcing benefit) never
  touch risk — they accumulate into opportunity_credit
- displacement_confirmed is deliberately hard to reach: production+
  stage AND share floor AND even odds — the only state that can move
  a cycle decision
- every leg journals inputs + evidence refs so any displayed number
  expands to the exact claims behind it
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from app.signals.pulse_engine import _cond, _eval_when

logger = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).parent / "competitive_risk.yaml"

_DURAB = {"contracted": 4, "recurring": 3, "usage_based": 2,
          "replacement_cycle": 1, "discretionary": 0.5,
          "speculative": 0}
_MTREND = {"improving": 2, "flat": 1, "declining": 0}
_BOTTLENECK_MECHS = {"design_win_lock", "hyperscaler_qualification",
                     "capacity_reservation", "process_technology",
                     "regulatory_moat"}
_STALE_AFTER = timedelta(days=200)     # ~2 quarters


@lru_cache(maxsize=2)
def _spec() -> dict:
    return yaml.safe_load(_SPEC_PATH.read_text())


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _quarter_label(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _stage_mult(stage: str) -> float:
    return float((_spec().get("stage_multiplier") or {}).get(
        stage, 0.10))


# ---------------------------------------------------------------------
# threat journal
# ---------------------------------------------------------------------

def _approved_threats(sym: str) -> list[dict]:
    """Approved, non-stale claims. Claims older than ~2 quarters with
    no refresh decay to 'stale' — a seed can't quietly persist."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT id, competitor, threat_type, segment, stage,"
            " direction, share_at_risk_lo, share_at_risk_hi,"
            " probability, displacement_lo, displacement_hi, claim,"
            " source, source_ref, source_date, confidence, status"
            " FROM competitive_threats WHERE symbol=:s"
            " AND status='approved' ORDER BY id", {"s": sym})
    except Exception as exc:
        logger.debug("threats %s: %s", sym, exc)
        return []
    out, stale_ids = [], []
    cutoff = datetime.now(timezone.utc) - _STALE_AFTER
    for r in rows:
        sd = r.get("source_date")
        if sd is not None and getattr(sd, "tzinfo", None) is None:
            sd = sd.replace(tzinfo=timezone.utc)
        if r.get("source") == "framework_doc" and sd \
                and sd < cutoff:
            stale_ids.append(r["id"])
            continue
        r["share_at_risk_lo"] = _f(r["share_at_risk_lo"])
        r["share_at_risk_hi"] = _f(r["share_at_risk_hi"])
        r["probability"] = _f(r["probability"])
        out.append(r)
    if stale_ids:                          # mark stale, don't delete
        try:
            db.execute_update(
                "UPDATE competitive_threats SET status='stale',"
                " updated_at=now() WHERE id = ANY(:ids)",
                {"ids": stale_ids})
        except Exception:
            pass
    return out


def _exposure(threats: list[dict], types: Optional[set] = None,
              direction: str = "threat") -> float:
    """Σ share_mid x probability x stage_mult over matching claims."""
    tot = 0.0
    for t in threats:
        if t.get("direction") != direction:
            continue
        if types is not None and t.get("threat_type") not in types:
            continue
        lo, hi = t.get("share_at_risk_lo"), t.get("share_at_risk_hi")
        if lo is None:
            continue
        mid = (lo + (hi if hi is not None else lo)) / 2
        tot += mid * (t.get("probability") or 0.5) * \
            _stage_mult(t.get("stage") or "announced")
    return round(tot, 4)


def _threat_ctx(threats: list[dict]) -> dict:
    spec = _spec()
    sub_types = set((spec.get("exposure_types") or {})
                    .get("substitution_resist") or [])
    ins_types = set((spec.get("exposure_types") or {})
                    .get("insourcing_resist") or [])
    thr = [t for t in threats if t.get("direction") == "threat"]
    prod_st = set((spec.get("groups") or {})
                  .get("production_stages") or [])
    qual_st = prod_st | {"qualification"}
    c: dict[str, Any] = {
        "threats_n": len(thr),
        "threat_exposure": _exposure(thr, sub_types) if thr else None,
        "insource_exposure": _exposure(thr, ins_types)
        if any(t["threat_type"] in ins_types for t in thr) else 0.0,
        "insource_threats_n": sum(
            1 for t in thr if t["threat_type"] in ins_types),
        "competitor_prod_n": sum(
            1 for t in thr if t["stage"] in prod_st),
        "competitor_qual_n": sum(
            1 for t in thr if t["stage"] in qual_st),
        "platform_threat_prod": any(
            t["threat_type"] == "platform" and t["stage"] in prod_st
            for t in thr),
        "pricing_threat_prod": any(
            t["threat_type"] == "pricing" and t["stage"] in prod_st
            for t in thr),
    }
    if c["insource_threats_n"] == 0:
        c["insource_exposure"] = None
    # displacement_confirmed — production+ sized threat at even odds
    dw = spec.get("displacement_when") or {}
    c["displacement_confirmed"] = any(
        t.get("direction") == "threat"
        and t.get("stage") in set(
            dw.get("stage_in") if isinstance(dw.get("stage_in"), list)
            else (spec.get("groups") or {}).get(
                dw.get("stage_in", ""), []))
        and (t.get("share_at_risk_lo") or 0)
            >= float(dw.get("share_lo_gte", 0.15))
        and (t.get("probability") or 0)
            >= float(dw.get("probability_gte", 0.5))
        for t in thr)
    return c


# ---------------------------------------------------------------------
# ctx — journaled inputs only
# ---------------------------------------------------------------------

def _ctx(sym: str) -> dict:
    from app.database import db
    c: dict[str, Any] = {"symbol": sym}
    threats = _approved_threats(sym)
    c.update(_threat_ctx(threats))
    c["_threats"] = threats
    c["opportunity_credit"] = round(min(
        _exposure(threats, None, "opportunity") * 100, 15), 1)
    try:
        r = db.execute_query(
            "SELECT om_now, om_slope, gm_slope, fcf_margin, fcf_ttm,"
            " rd_rev FROM symbol_flywheel WHERE symbol=:s", {"s": sym})
        if r:
            c.update({k: _f(r[0].get(k)) for k in
                      ("om_now", "om_slope", "gm_slope", "fcf_margin",
                       "fcf_ttm", "rd_rev")})
    except Exception as exc:
        logger.debug("crs ctx flywheel %s: %s", sym, exc)
    try:
        from app.signals.customer_conc import customer_conc
        cc = customer_conc(sym)
        c["top1_pct"] = cc["top1_pct"]
        c["cust_conc_drift"] = cc["drift_pp"]
        c["cust_conc_flag"] = cc["flag"]
    except Exception:
        c["top1_pct"] = c["cust_conc_drift"] = \
            c["cust_conc_flag"] = None
    try:
        r = db.execute_query(
            "SELECT crpo_share FROM symbol_sec_facts WHERE symbol=:s",
            {"s": sym})
        c["crpo_share"] = _f(r[0]["crpo_share"]) if r else None
    except Exception:
        c["crpo_share"] = None
    try:
        r = db.execute_query(
            "SELECT demand_durability FROM company_demand_profile"
            " WHERE symbol=:s", {"s": sym})
        c["durability_rank"] = _DURAB.get(
            r[0].get("demand_durability") or "") if r else None
    except Exception:
        c["durability_rank"] = None
    try:
        from app.research import quarter
        qt = quarter.trends(quarter.quarters(sym, 8))
        mt = qt.get("margin_trend")
        c["margin_trend"] = _MTREND.get(mt) if mt else None
    except Exception:
        c["margin_trend"] = None
    try:
        r = db.execute_query(
            "SELECT count(*) AS n FROM design_wins WHERE symbol=:s",
            {"s": sym})
        c["design_wins_n"] = int(r[0]["n"]) if r else 0
    except Exception:
        c["design_wins_n"] = 0
    try:
        mechs: set = set()
        for row in db.execute_query(
                "SELECT evidence FROM product_initiatives"
                " WHERE symbol=:s AND status='active'", {"s": sym}):
            ev = row.get("evidence") or {}
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = {}
            mechs |= set(ev.get("moat") or [])
        c["moat_mechs"] = len(mechs)
        c["bottleneck_mechs"] = len(mechs & _BOTTLENECK_MECHS)
    except Exception:
        c["moat_mechs"] = None
        c["bottleneck_mechs"] = None
    return c


# ---------------------------------------------------------------------
# scoring — banded first-match, unknown legs excluded, caps last
# ---------------------------------------------------------------------

_PRE_PROD_CAP = 60      # announcements can't sink a moat


def _score(ctx: dict, threats: list[dict]) -> dict:
    spec = _spec()
    comps, missing = {}, []
    ev_by_type: dict[str, list] = {}
    for t in threats:
        if t.get("direction") == "threat":
            ev_by_type.setdefault(t["threat_type"], []).append(t["id"])
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
        # pre-production evidence can warn but not sink: only
        # production-stage threats may push a leg below the cap
        prod_types = set((spec.get("groups") or {})
                         .get("production_stages") or [])
        if sc is not None and sc < _PRE_PROD_CAP and not any(
                t.get("direction") == "threat"
                and t.get("stage") in prod_types for t in threats):
            sc = max(sc, _PRE_PROD_CAP)
            note = (note or "") + " (capped — pre-production only)"
        comps[comp] = {"score": sc, "weight": float(
            cfg.get("weight", 0)), "note": note,
            **({"unknown": True} if unk else {})}
    answered = sum(c["weight"] for c in comps.values()
                   if not c.get("unknown"))
    total_w = sum(c["weight"] for c in comps.values())
    crs = (sum(c["score"] * c["weight"] for c in comps.values()
               if not c.get("unknown")) / answered
           if answered else None)
    capped = None
    for cap in spec.get("caps") or []:
        matched, log = _eval_when(ctx, cap.get("when") or {},
                                  spec.get("groups") or {})
        missing.extend(log.get("missing") or [])
        if matched and crs is not None and crs > cap["cap"]:
            crs, capped = cap["cap"], cap.get("note")
            break
    return {"crs": round(crs, 1) if crs is not None else None,
            "components": comps, "capped": capped,
            "missing": sorted(set(missing)),
            "coverage_pct": round(answered / total_w, 2)
            if total_w else None}


# ---------------------------------------------------------------------
# trend + snapshots
# ---------------------------------------------------------------------

def _prior(sym: str, qlabel: str) -> Optional[dict]:
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT crs FROM competitive_scores WHERE symbol=:s"
            " AND quarter_label<>:q ORDER BY as_of DESC LIMIT 1",
            {"s": sym, "q": qlabel})
        return {"crs": _f(r[0]["crs"])} if r else None
    except Exception:
        return None


def _top_threats(threats: list[dict], n: int = 4) -> list[dict]:
    ranked = sorted(
        (t for t in threats if t.get("direction") == "threat"),
        key=lambda t: ((t.get("share_at_risk_lo") or 0)
                       + (t.get("share_at_risk_hi") or 0)) / 2
                      * (t.get("probability") or 0.5)
                      * _stage_mult(t.get("stage") or "announced"),
        reverse=True)[:n]
    return [{"competitor": t["competitor"], "segment": t["segment"],
             "type": t["threat_type"], "stage": t["stage"],
             "share": [t.get("share_at_risk_lo"),
                      t.get("share_at_risk_hi")],
             "probability": t.get("probability"),
             "claim": t["claim"], "source": t["source"],
             "source_date": str(t["source_date"])[:10]
             if t.get("source_date") else None}
            for t in ranked]


def evaluate_symbol(sym: str, as_of: Optional[date] = None) -> dict:
    as_of = as_of or date.today()
    qlabel = _quarter_label(as_of)
    ctx = _ctx(sym.upper())
    threats = ctx.pop("_threats", [])
    scored = _score(ctx, threats)
    prior = _prior(sym.upper(), qlabel)
    crs = scored["crs"]
    if prior is None or prior.get("crs") is None or crs is None:
        trend = "new"
    elif crs - prior["crs"] >= 10:
        trend = "improving"
    elif prior["crs"] - crs >= 10:
        trend = "deteriorating"
    else:
        trend = "stable"
    if ctx.get("displacement_confirmed") and trend != "new":
        trend = "deteriorating" if trend == "stable" else trend
    flags = []
    if ctx.get("displacement_confirmed"):
        flags.append("displacement_confirmed")
    if (ctx.get("opportunity_credit") or 0) >= 8:
        flags.append("insourcing_beneficiary")
    if any(t.get("source") == "framework_doc" for t in threats):
        flags.append("seed_claims")
    risk_lo = _exposure(threats, None, "threat")
    risk_hi = round(sum(
        ((t.get("share_at_risk_hi") if t.get("share_at_risk_hi")
          is not None else t.get("share_at_risk_lo")) or 0)
        * (t.get("probability") or 0.5)
        * _stage_mult(t.get("stage") or "announced")
        for t in threats if t.get("direction") == "threat"), 4) \
        if threats else None
    return {
        "symbol": sym.upper(), "quarter_label": qlabel,
        "as_of": str(as_of), "crs": crs,
        "coverage_pct": scored["coverage_pct"],
        "legs": {k: v["score"] for k, v in
                 scored["components"].items()},
        "components": scored["components"],
        "capped": scored["capped"],
        "opportunity_credit": ctx.get("opportunity_credit"),
        "revenue_at_risk_lo": risk_lo,
        "revenue_at_risk_hi": risk_hi,
        "displacement_confirmed": bool(
            ctx.get("displacement_confirmed")),
        "risk_trend": trend,
        "top_threats": _top_threats(threats),
        "flags": flags,
        "rules_version": f"competitive@{_spec().get('version', 0)}",
    }


def lookup(sym: str) -> Optional[dict]:
    """Canonical cross-engine interface — latest snapshot for one
    symbol or None. Any engine (cycle, fv2, thesis, invest) reads
    competitive state through here."""
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT crs, coverage_pct, opportunity_credit,"
            " revenue_at_risk_lo, revenue_at_risk_hi,"
            " displacement_confirmed, risk_trend, top_threats, flags"
            " FROM competitive_scores WHERE symbol=:s"
            " ORDER BY as_of DESC, id DESC LIMIT 1",
            {"s": sym.upper()})
        if not r:
            return None
        out = dict(r[0])
        for k in ("crs", "coverage_pct", "opportunity_credit",
                  "revenue_at_risk_lo", "revenue_at_risk_hi"):
            out[k] = _f(out[k])
        for j in ("top_threats", "flags"):
            if isinstance(out.get(j), str):
                out[j] = json.loads(out[j])
        return out
    except Exception as exc:
        logger.debug("crs lookup %s: %s", sym, exc)
        return None


def _ensure() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS competitive_scores ("
        " id bigserial PRIMARY KEY, symbol text NOT NULL,"
        " quarter_label text NOT NULL, as_of date NOT NULL,"
        " crs numeric, coverage_pct numeric,"
        " substitution_resist numeric, competitive_position numeric,"
        " insourcing_resist numeric, technology_moat numeric,"
        " ecosystem_switching numeric, value_capture numeric,"
        " opportunity_credit numeric, revenue_at_risk_lo numeric,"
        " revenue_at_risk_hi numeric,"
        " displacement_confirmed boolean, risk_trend text,"
        " top_threats jsonb NOT NULL DEFAULT '[]',"
        " components jsonb NOT NULL DEFAULT '{}',"
        " flags jsonb NOT NULL DEFAULT '[]', rules_version text,"
        " created_at timestamptz NOT NULL DEFAULT now(),"
        " UNIQUE (symbol, quarter_label, as_of))", {})
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS competitive_threats ("
        " id bigserial PRIMARY KEY, symbol text NOT NULL,"
        " competitor text NOT NULL, threat_type text NOT NULL,"
        " segment text NOT NULL, stage text NOT NULL,"
        " direction text NOT NULL,"
        " share_at_risk_lo numeric, share_at_risk_hi numeric,"
        " probability numeric,"
        " displacement_lo smallint, displacement_hi smallint,"
        " claim text NOT NULL, source text NOT NULL,"
        " source_ref text, source_date timestamptz,"
        " confidence text NOT NULL DEFAULT 'medium',"
        " status text NOT NULL DEFAULT 'draft',"
        " created_at timestamptz NOT NULL DEFAULT now(),"
        " updated_at timestamptz NOT NULL DEFAULT now(),"
        " UNIQUE (symbol, competitor, segment, source_ref))", {})


def seed_threats() -> dict:
    """Journal the yaml threat_seeds — idempotent via the UNIQUE key.
    Seeds arrive approved (they are the doc's reviewed hypotheses)
    but flagged `seed_claims` and decay to stale if unrefreshed."""
    from app.database import db
    _ensure()
    inserted = 0
    for s in _spec().get("threat_seeds") or []:
        try:
            db.execute_update(
                "INSERT INTO competitive_threats (symbol, competitor,"
                " threat_type, segment, stage, direction,"
                " share_at_risk_lo, share_at_risk_hi, probability,"
                " displacement_lo, displacement_hi, claim, source,"
                " source_ref, source_date, confidence, status)"
                " VALUES (:symbol,:competitor,:tt,:seg,:stage,:dir,"
                " :lo,:hi,:p,:dlo,:dhi,:claim,'framework_doc',"
                " 'ai-rotation-framework', '2026-11-12', 'medium',"
                " 'approved') ON CONFLICT DO NOTHING",
                {"symbol": s["symbol"], "competitor": s["competitor"],
                 "tt": s["threat_type"], "seg": s["segment"],
                 "stage": s["stage"], "dir": s["direction"],
                 "lo": s.get("share_at_risk_lo"),
                 "hi": s.get("share_at_risk_hi"),
                 "p": s.get("probability"),
                 "dlo": s.get("displacement_lo"),
                 "dhi": s.get("displacement_hi"),
                 "claim": s["claim"]})
            inserted += 1
        except Exception as exc:
            logger.warning("seed %s: %s", s.get("symbol"), exc)
    return {"seeded": inserted}


def refresh(as_of: Optional[date] = None,
            symbols: Optional[list[str]] = None) -> dict:
    """Score every symbol that has threats OR flywheel data."""
    from app.database import db
    as_of = as_of or date.today()
    _ensure()
    if symbols is None:
        try:
            rows = db.execute_query(
                "SELECT DISTINCT symbol FROM competitive_threats"
                " WHERE status='approved'")
            symbols = sorted(r["symbol"] for r in rows)
        except Exception:
            symbols = []
        if not symbols:
            from app.signals import cycle_tracker
            symbols = sorted(cycle_tracker.universe().keys())
    done, errors = 0, {}
    for sym in symbols:
        try:
            s = evaluate_symbol(sym, as_of)
            db.execute_update(
                "INSERT INTO competitive_scores (symbol, quarter_label,"
                " as_of, crs, coverage_pct, substitution_resist,"
                " competitive_position, insourcing_resist,"
                " technology_moat, ecosystem_switching, value_capture,"
                " opportunity_credit, revenue_at_risk_lo,"
                " revenue_at_risk_hi, displacement_confirmed,"
                " risk_trend, top_threats, components, flags,"
                " rules_version)"
                " VALUES (:s,:q,:ao,:crs,:cov,:sr,:cp,:ir,:tm,:es,:vc,"
                " :oc,:rl,:rh,:dc,:rt,:tt,:comps,:f,:rv)"
                " ON CONFLICT (symbol, quarter_label, as_of)"
                " DO NOTHING",
                {"s": sym, "q": s["quarter_label"], "ao": as_of,
                 "crs": s["crs"], "cov": s["coverage_pct"],
                 "sr": s["legs"]["substitution_resist"],
                 "cp": s["legs"]["competitive_position"],
                 "ir": s["legs"]["insourcing_resist"],
                 "tm": s["legs"]["technology_moat"],
                 "es": s["legs"]["ecosystem_switching"],
                 "vc": s["legs"]["value_capture"],
                 "oc": s["opportunity_credit"],
                 "rl": s["revenue_at_risk_lo"],
                 "rh": s["revenue_at_risk_hi"],
                 "dc": s["displacement_confirmed"],
                 "rt": s["risk_trend"],
                 "tt": json.dumps(s["top_threats"]),
                 "comps": json.dumps(s["components"]),
                 "f": json.dumps(s["flags"]),
                 "rv": s["rules_version"]})
            done += 1
        except Exception as exc:
            errors[sym] = str(exc)
            logger.warning("crs refresh %s: %s", sym, exc)
    return {"as_of": str(as_of), "evaluated": done,
            "errors": errors or None}


def current() -> dict:
    """Latest CRS per symbol for the board."""
    from app.database import db
    _ensure()
    rows = db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, quarter_label, as_of,"
        " crs, coverage_pct, substitution_resist,"
        " competitive_position, insourcing_resist, technology_moat,"
        " ecosystem_switching, value_capture, opportunity_credit,"
        " revenue_at_risk_lo, revenue_at_risk_hi,"
        " displacement_confirmed, risk_trend, top_threats, flags"
        " FROM competitive_scores ORDER BY symbol, as_of DESC,"
        " id DESC")
    for r in rows:
        for k in ("crs", "coverage_pct", "opportunity_credit",
                  "revenue_at_risk_lo", "revenue_at_risk_hi"):
            r[k] = _f(r[k])
        for j in ("top_threats", "flags"):
            if isinstance(r.get(j), str):
                r[j] = json.loads(r[j])
    rows.sort(key=lambda r: (r["crs"] is None, r["crs"] or 0))
    return {"as_of": str(rows[0]["as_of"]) if rows else None,
            "quarter_label": rows[0]["quarter_label"] if rows else None,
            "n": len(rows), "rows": rows}


def detail(sym: str) -> dict:
    """One name — latest score + every journaled threat claim."""
    from app.database import db
    _ensure()
    latest = lookup(sym)
    threats = db.execute_query(
        "SELECT id, competitor, threat_type, segment, stage,"
        " direction, share_at_risk_lo, share_at_risk_hi, probability,"
        " displacement_lo, displacement_hi, claim, source, source_ref,"
        " source_date, confidence, status, created_at"
        " FROM competitive_threats WHERE symbol=:s"
        " ORDER BY status='approved' DESC, id",
        {"s": sym.upper()})
    for t in threats:
        for k in ("share_at_risk_lo", "share_at_risk_hi",
                  "probability"):
            t[k] = _f(t[k])
        t["source_date"] = str(t["source_date"])[:10] \
            if t.get("source_date") else None
        t["created_at"] = str(t["created_at"])[:10]
    return {"symbol": sym.upper(), "latest": latest,
            "threats": threats}
