"""Demand-evidence feed — validated, source-dated claims that inform
canonical demand axes.

Contract:
  - Claims are facts ("backlog grew 40%", "lease commencement delayed
    to 2027"), never conclusions. Conclusions are computed.
  - LLM extraction produces drafts only; a claim upgrades an axis
    only after human approval (status='approved') or source='manual'.
  - Opposing approved signals in one axis = conflict: preserved in
    the profile, axis falls back, confidence drops.
  - Missing evidence stays unknown — never promoted to a favorable
    state. Stale evidence is ignored for axes but kept for audit.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import yaml

from app.observability.logging import get_logger

logger = get_logger(__name__)

_POLICY_PATH = os.path.join(os.path.dirname(__file__),
                            "demand_profile.yaml")
_CONF_W = {"high": 1.0, "medium": 0.6, "low": 0.3}


def _signal_cfg() -> Dict[str, Any]:
    try:
        with open(_POLICY_PATH) as f:
            return (yaml.safe_load(f) or {}).get("signal_map") or {}
    except Exception:
        return {}


def _claim_direction(axis: str, signal: str) -> Optional[str]:
    spec = _signal_cfg().get(axis) or {}
    if signal in (spec.get("positive") or []):
        return "positive"
    if signal in (spec.get("negative") or []):
        return "negative"
    return None


def validate_claim(c: Dict[str, Any]) -> List[str]:
    """Deterministic claim validation. Returns error strings — an
    empty list means the claim is structurally sound."""
    errs = []
    axis, sig = c.get("axis"), c.get("signal")
    if axis not in (_signal_cfg() or {}):
        errs.append(f"unknown axis {axis!r}")
    elif _claim_direction(axis, sig) is None:
        errs.append(f"signal {sig!r} not in vocabulary for {axis!r}")
    if not (c.get("claim") or "").strip():
        errs.append("claim text required")
    if not (c.get("source") or "").strip():
        errs.append("source required")
    if c.get("confidence") not in _CONF_W:
        errs.append("confidence must be high|medium|low")
    sd = c.get("source_date")
    if sd is not None:
        try:
            d = (datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
                 if not isinstance(sd, datetime) else sd)
            if d > datetime.now(timezone.utc) + timedelta(days=2):
                errs.append("source_date in the future")
        except (TypeError, ValueError):
            errs.append("unparseable source_date")
    return errs


def derive_axes(claims: List[Dict[str, Any]],
                now: Optional[datetime] = None
                ) -> Dict[str, Dict[str, Any]]:
    """Fold approved claims into per-axis evidence verdicts.

    Returns {axis: {value, confidence, direction_counts, conflicts,
    stale, n_claims}} — pure function, no I/O.
    """
    now = now or datetime.now(timezone.utc)
    cfg = _signal_cfg()
    out: Dict[str, Dict[str, Any]] = {}
    for axis, spec in cfg.items():
        fresh = float(spec.get("freshness_days") or 180)
        pos = neg = 0.0
        n = stale = 0
        axis_claims = [c for c in claims
                       if c.get("axis") == axis
                       and c.get("status") == "approved"]
        for c in axis_claims:
            sd = c.get("source_date")
            if sd is not None:
                d = (sd if isinstance(sd, datetime)
                     else datetime.fromisoformat(
                         str(sd).replace("Z", "+00:00")))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                if (now - d).days > fresh:
                    stale += 1
                    continue
            direction = _claim_direction(axis, c.get("signal") or "")
            w = _CONF_W.get(c.get("confidence") or "medium", 0.6)
            if direction == "positive":
                pos += w
            elif direction == "negative":
                neg += w
            n += 1

        if not n:
            continue
        verdict: Dict[str, Any] = {
            "n_claims": n, "stale": stale,
            "pos_score": round(pos, 3), "neg_score": round(neg, 3),
        }
        if pos > 0 and neg > 0:
            verdict["conflict"] = True
            verdict["value"] = spec.get("conflict_value")
            verdict["confidence"] = "low"
        else:
            stronger = "positive" if pos > neg else "negative"
            verdict["value"] = (spec.get("axis_value") or {}).get(stronger)
            score = max(pos, neg)
            verdict["confidence"] = ("high" if score >= 1.6
                                     else "medium" if score >= 0.8
                                     else "low")
        if spec.get("evidence_can_set"):
            # claim payload value.<axis> carries the new classification
            for c in axis_claims:
                cv = (c.get("value") or {})
                if isinstance(cv, dict) and cv.get(axis):
                    verdict["model_value"] = cv[axis]
                    break
        out[axis] = verdict
    return out


# ── persistence ────────────────────────────────────────────────────

def record_claim(c: Dict[str, Any]) -> Dict[str, Any]:
    """Validate + persist one claim. LLM-derived claims always enter
    as draft; only explicit source='manual' claims may enter approved.
    Returns {ok, id?|errors}."""
    errs = validate_claim(c)
    if errs:
        return {"ok": False, "errors": errs}
    status = c.get("status") or "draft"
    if c.get("source") != "manual" and status == "approved":
        status = "draft"  # non-manual claims always need review
    from app.database import db
    from sqlalchemy import text
    try:
        with db.get_session() as session:
            res = session.execute(text(
                """
                INSERT INTO demand_evidence
                    (symbol, axis, signal, claim, value, source,
                     source_ref, source_date, confidence, status,
                     extractor_version, reviewed_by)
                VALUES (:s, :a, :sig, :cl, :v, :src, :ref, :sd,
                        :conf, :st, :xv, :rb)
                ON CONFLICT (symbol, axis, signal, source_ref) DO UPDATE
                    SET updated_at = now()
                RETURNING id
                """),
                {"s": (c.get("symbol") or "").upper(),
                 "a": c.get("axis"), "sig": c.get("signal"),
                 "cl": (c.get("claim") or "")[:2000],
                 "v": (json.dumps(c.get("value"))
                      if c.get("value") else None),
                 "src": c.get("source"),
                 "ref": (c.get("source_ref") or "")[:1000] or None,
                 "sd": c.get("source_date"),
                 "conf": c.get("confidence") or "medium",
                 "st": status,
                 "xv": c.get("extractor_version") or "demand_evidence_v1",
                 "rb": c.get("reviewed_by")})
            session.commit()
            row = res.fetchone()
        return {"ok": True, "id": row[0] if row else None,
                "status": status}
    except Exception as exc:
        logger.warning("record_claim failed: %s", exc)
        return {"ok": False, "errors": [str(exc)]}


def claims_for(symbol: str, include_drafts: bool = False
               ) -> List[Dict[str, Any]]:
    from app.database import db
    try:
        return db.execute_query(
            """
            SELECT id, symbol, axis, signal, claim, value, source,
                   source_ref, source_date, confidence, status,
                   extractor_version, created_at
            FROM demand_evidence
            WHERE symbol = :s AND status != 'rejected'
              AND (:d OR status != 'draft')
            ORDER BY source_date DESC NULLS LAST, created_at DESC
            """,
            {"s": symbol.upper(), "d": include_drafts}) or []
    except Exception as exc:
        logger.warning("claims_for %s failed: %s", symbol, exc)
        return []


def set_status(claim_id: int, status: str,
               reviewed_by: Optional[str] = None) -> bool:
    if status not in ("approved", "rejected", "stale", "draft"):
        return False
    from app.database import db
    try:
        db.execute_update(
            """
            UPDATE demand_evidence
            SET status = :st, reviewed_by = :rb, updated_at = now()
            WHERE id = :i
            """, {"st": status, "rb": reviewed_by, "i": claim_id})
        return True
    except Exception as exc:
        logger.warning("set_status %s failed: %s", claim_id, exc)
        return False
