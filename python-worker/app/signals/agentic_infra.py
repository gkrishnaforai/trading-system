"""Agentic Infrastructure Engine — AIS.

"Who sells the software base layer every agent needs?" — the
software-sector analog of CRDO/VRT/NVDA. Not applications: the
plumbing — data plane, streaming, edge runtime, AI gateways,
non-human identity, agent security, observability.

    role_strength        30   core | adjacent | watch | candidate
    sublayer_diversity   15   agent primitives covered
    monetization_fit     20   agents buy usage, not seats
    growth_durability    20   journaled revenue growth only
    ai_evidence          15   documented AI/agent claims in evidence

Honesty rules:
- seed priors (yaml seed map) are flagged `seeded`; a name upgrades to
  `evidence_backed` only on journaled AI evidence, never narrative
- registry candidates land at `candidate` — visible, low-scored,
  review-gated; they can never silently outrank a reviewed name
- unknown legs excluded + coverage reported; growth unknown never
  becomes zero
- lookup() is the canonical cross-engine read — same contract as
  competitive_risk.lookup
"""
from __future__ import annotations

import json
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from app.signals.pulse_engine import _cond

logger = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).with_name("agentic_infra.yaml")


@lru_cache(maxsize=2)
def _spec() -> dict:
    return yaml.safe_load(_SPEC_PATH.read_text())


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def seeds() -> dict:
    return _spec().get("seeds") or {}


def universe() -> dict[str, dict]:
    """symbol → seed spec; includes discovered candidates."""
    out = dict(seeds())
    out.update({s: {"role": "candidate", "sublayers": [],
                    "monetization": None,
                    "note": "registry candidate — unreviewed"}
                for s in _candidates() if s not in out})
    return out


def _candidates() -> list[str]:
    """Tracked software-infra names with no seed — review queue, not
    a claim that they belong."""
    from app.database import db
    from app.signals import symbol_tiers
    try:
        pats = _spec().get("candidate_industries") or []
        if not pats:
            return []
        likes = " OR ".join(f"COALESCE(s.industry,'') ILIKE '{p}'"
                            for p in pats)
        rows = db.execute_query(
            f"SELECT DISTINCT s.symbol FROM stocks s"
            f" JOIN ({symbol_tiers._active_sql()}) t"
            f"   ON t.symbol = s.symbol WHERE {likes}")
        return [r["symbol"] for r in rows]
    except Exception as exc:
        logger.debug("agentic candidates: %s", exc)
        return []


# ---------------------------------------------------------------------
# ctx — seeds are priors; evidence legs come from journaled data only
# ---------------------------------------------------------------------

def _ai_evidence_count(sym: str) -> int:
    """Documented AI/agent claims across the evidence tables — the
    leg that can upgrade a seed to evidence_backed."""
    from app.database import db
    n = 0
    try:
        r = db.execute_query(
            "SELECT count(*) AS n FROM demand_evidence WHERE symbol=:s"
            " AND status='approved' AND (claim ILIKE '%ai%'"
            "  OR claim ILIKE '%agent%' OR claim ILIKE '%llm%'"
            "  OR claim ILIKE '%inference%' OR signal ILIKE '%ai%')",
            {"s": sym})
        n += int(r[0]["n"]) if r else 0
    except Exception:
        pass
    try:
        r = db.execute_query(
            "SELECT count(*) AS n FROM product_initiatives"
            " WHERE symbol=:s AND status='active'"
            " AND (name ILIKE '%ai%' OR name ILIKE '%agent%'"
            "   OR name ILIKE '%copilot%' OR name ILIKE '%llm%'"
            "   OR channel ILIKE '%ai%')",
            {"s": sym})
        n += int(r[0]["n"]) if r else 0
    except Exception:
        pass
    return n


def _ctx(sym: str) -> dict:
    from app.database import db
    seed = universe().get(sym) or {}
    c: dict[str, Any] = {
        "symbol": sym,
        "role": seed.get("role"),
        "monetization": seed.get("monetization"),
        "sublayers_n": len(seed.get("sublayers") or []),
        "evidence_n": _ai_evidence_count(sym),
    }
    try:
        r = db.execute_query(
            "SELECT rev_growth, est_revision_pct FROM symbol_flywheel"
            " WHERE symbol=:s", {"s": sym})
        c["rev_growth"] = _f(r[0]["rev_growth"]) if r else None
        c["est_revision_pct"] = (_f(r[0]["est_revision_pct"])
                                 if r else None)
    except Exception:
        c["rev_growth"] = None
        c["est_revision_pct"] = None
    return c


# ---------------------------------------------------------------------
# scoring — banded, unknown excluded, candidates capped at watch
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
    ais = (sum(c["score"] * c["weight"] for c in comps.values()
               if not c.get("unknown")) / answered
           if answered else None)
    # candidates can never tier above 'watch' — review gate, not a ban
    tier = "watch"
    if ais is not None:
        for t in spec.get("tiers") or []:
            if ais >= float(t.get("ais_gte", 0)):
                tier = t["tier"]
                break
    if ctx.get("role") == "candidate":
        tier = "candidate"
    return {"ais": round(ais, 1) if ais is not None else None,
            "tier": tier, "components": comps,
            "missing": sorted(set(missing)),
            "coverage_pct": round(answered / total_w, 2)
            if total_w else None}


def evaluate_symbol(sym: str, as_of: Optional[date] = None) -> dict:
    as_of = as_of or date.today()
    sym = sym.upper()
    seed = universe().get(sym) or {}
    ctx = _ctx(sym)
    scored = _score(ctx)
    flags = []
    if seed.get("role") != "candidate" and (ctx.get("evidence_n") or 0) == 0:
        flags.append("seed_only")
    status = ("candidate" if seed.get("role") == "candidate"
              else "evidence_backed" if (ctx.get("evidence_n") or 0) >= 2
              else "seeded")
    if status == "candidate":
        flags.append("unreviewed")
    return {
        "symbol": sym, "as_of": str(as_of),
        "ais": scored["ais"], "tier": scored["tier"],
        "sublayers": seed.get("sublayers") or [],
        "monetization": seed.get("monetization"),
        "evidence_n": ctx.get("evidence_n"),
        "coverage_pct": scored["coverage_pct"],
        "legs": {k: v["score"] for k, v in
                 scored["components"].items()},
        "components": scored["components"],
        "flags": flags, "status": status,
        "note": seed.get("note"),
        "rules_version": f"agentic_infra@{_spec().get('version', 0)}",
    }


# ---------------------------------------------------------------------
# journal + reads
# ---------------------------------------------------------------------

def _ensure() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS agentic_infra_snapshots ("
        " id bigserial PRIMARY KEY, symbol text NOT NULL,"
        " as_of date NOT NULL, ais numeric, tier text,"
        " sublayers jsonb NOT NULL DEFAULT '[]',"
        " monetization text, evidence_n integer,"
        " coverage_pct numeric,"
        " legs jsonb NOT NULL DEFAULT '{}',"
        " components jsonb NOT NULL DEFAULT '{}',"
        " flags jsonb NOT NULL DEFAULT '[]',"
        " status text NOT NULL DEFAULT 'seeded',"
        " rules_version text,"
        " created_at timestamptz NOT NULL DEFAULT now(),"
        " UNIQUE (symbol, as_of))", {})


def refresh() -> dict:
    from app.database import db
    _ensure()
    done, errors = 0, []
    for sym in sorted(universe()):
        try:
            r = evaluate_symbol(sym)
            db.execute_update(
                "INSERT INTO agentic_infra_snapshots (symbol, as_of,"
                " ais, tier, sublayers, monetization, evidence_n,"
                " coverage_pct, legs, components, flags, status,"
                " rules_version) VALUES (:s,:d,:a,:t,CAST(:sl AS jsonb),"
                " :m,:en,:cv,CAST(:l AS jsonb),CAST(:c AS jsonb),"
                " CAST(:f AS jsonb),:st,:rv)"
                " ON CONFLICT (symbol, as_of) DO UPDATE SET"
                " ais=excluded.ais, tier=excluded.tier,"
                " sublayers=excluded.sublayers,"
                " monetization=excluded.monetization,"
                " evidence_n=excluded.evidence_n,"
                " coverage_pct=excluded.coverage_pct,"
                " legs=excluded.legs, components=excluded.components,"
                " flags=excluded.flags, status=excluded.status,"
                " rules_version=excluded.rules_version",
                {"s": sym, "d": r["as_of"], "a": r["ais"],
                 "t": r["tier"], "sl": json.dumps(r["sublayers"]),
                 "m": r["monetization"], "en": r["evidence_n"],
                 "cv": r["coverage_pct"], "l": json.dumps(r["legs"]),
                 "c": json.dumps(r["components"]),
                 "f": json.dumps(r["flags"]), "st": r["status"],
                 "rv": r["rules_version"]})
            done += 1
        except Exception as exc:
            logger.warning("agentic_infra %s: %s", sym, exc)
            errors.append(sym)
    return {"evaluated": done, "errors": errors,
            "candidates": len(_candidates())}


def lookup(sym: str) -> Optional[dict]:
    """Canonical cross-engine read — latest snapshot or None."""
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT ais, tier, sublayers, monetization, evidence_n,"
            " coverage_pct, flags, status, as_of"
            " FROM agentic_infra_snapshots WHERE symbol=:s"
            " ORDER BY as_of DESC, id DESC LIMIT 1",
            {"s": sym.upper()})
        if not r:
            return None
        out = dict(r[0])
        for k in ("ais", "coverage_pct"):
            out[k] = _f(out[k])
        for j in ("sublayers", "flags"):
            if isinstance(out.get(j), str):
                out[j] = json.loads(out[j])
        return out
    except Exception as exc:
        logger.debug("agentic lookup %s: %s", sym, exc)
        return None


def current() -> dict:
    """The board — latest snapshot per symbol grouped by tier."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, as_of, ais, tier,"
            " sublayers, monetization, evidence_n, coverage_pct,"
            " flags, status FROM agentic_infra_snapshots"
            " ORDER BY symbol, as_of DESC, id DESC")
    except Exception as exc:
        logger.warning("agentic current: %s", exc)
        return {"rows": [], "tiers": {}}
    sub = _spec().get("sublayers") or {}
    for r in rows:
        r["ais"] = _f(r.get("ais"))
        r["coverage_pct"] = _f(r.get("coverage_pct"))
        for j in ("sublayers", "flags"):
            if isinstance(r.get(j), str):
                r[j] = json.loads(r[j])
        r["sublayer_labels"] = [sub.get(s, s)
                                for s in (r.get("sublayers") or [])]
    tiers: dict[str, list] = {}
    for r in rows:
        tiers.setdefault(r.get("tier") or "watch", []).append(
            r["symbol"])
    return {"as_of": str(rows[0]["as_of"]) if rows else None,
            "n": len(rows), "rows": rows, "tiers": tiers}
