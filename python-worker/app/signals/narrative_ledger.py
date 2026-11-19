"""Narrative claims ledger — what the market believes about a company,
with provenance. Spec docs/specs/expectations-value-engine.md Phase 1.

Two dimensions, never one: claim_type is immutable provenance
(guidance stays guidance even when later data supports it); status is
the mutable evidentiary state that only journaled evidence may move.
Transitions append a versioned row (supersedes) + a claim_reviews row
carrying the evidence id — an LLM repeating a claim never confirms it.

collect() gathers claims from journaled engine outputs — earnings_watch
guidance claims, earnings-quality flags, driver commitments, flywheel
revision swings — so the ledger grows on evidence the system already
journals, not on a research agent's say-so.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    """Time-ordered 26-char id — sortable like ULID without the dep."""
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    chars = []
    for _ in range(10):
        chars.append(_ULID_ALPHABET[ts & 31])
        ts >>= 5
    import secrets
    return "".join(reversed(chars)) + "".join(
        secrets.choice(_ULID_ALPHABET) for _ in range(16))


def _hash(text: str) -> str:
    return hashlib.sha1(
        re.sub(r"\s+", " ", text.lower()).strip().encode()).hexdigest()[:16]


def _j(o) -> Any:
    return json.loads(o) if isinstance(o, str) else o


# ── write paths ─────────────────────────────────────────────────────

def emit(symbol: str, claim: str, direction: Optional[str],
         claim_type: str, source: Optional[str] = None,
         source_date: Optional[str] = None,
         evidence_confidence: Optional[float] = None,
         outcome_confidence: Optional[float] = None,
         status: str = "proposed", created_by: str = "collector",
         evidence_refs: Optional[list] = None,
         valid_until: Optional[str] = None) -> Optional[str]:
    """Propose a claim — deduped on (symbol, type, claim-hash,
    source-date): re-collecting the same claim is a no-op, never a
    duplicate row."""
    from app.database import db
    sym = symbol.upper()
    dk = f"{claim_type}|{_hash(claim)}|{source_date or ''}"
    try:
        ex = db.execute_query(
            "SELECT claim_id FROM narrative_claims"
            " WHERE symbol=:s AND dedupe_key=:d AND version=1",
            {"s": sym, "d": dk})
        if ex:
            return ex[0]["claim_id"]
        cid = f"nc_{_ulid()}"
        db.execute_update(
            "INSERT INTO narrative_claims (claim_id, version, symbol,"
            " claim, direction, claim_type, status, source,"
            " source_date, evidence_confidence, outcome_confidence,"
            " valid_until, evidence_refs, created_by, dedupe_key)"
            " VALUES (:c,1,:s,:cl,:di,:ty,:st,:so,"
            " COALESCE(:sd::date, current_date),:ec,:oc,"
            " COALESCE(:vu::timestamptz, now() + interval '180 days'),"
            " CAST(:er AS jsonb),:cb,:dk)",
            {"c": cid, "s": sym, "cl": claim[:500], "di": direction,
             "ty": claim_type, "st": status, "so": source,
             "sd": source_date, "ec": evidence_confidence,
             "oc": outcome_confidence, "vu": valid_until,
             "er": json.dumps(evidence_refs or [], default=str),
             "cb": created_by, "dk": dk})
        db.execute_update(
            "INSERT INTO claim_reviews (claim_id, review_kind, actor,"
            " verdict, evidence_refs, note) VALUES"
            " (:c,'transition',:a,:v,CAST(:e AS jsonb),:n)",
            {"c": cid, "a": created_by, "v": status,
             "e": json.dumps(evidence_refs or [], default=str),
             "n": f"claim proposed ({claim_type})"})
        return cid
    except Exception as exc:
        logger.debug("claim emit %s: %s", sym, exc)
        return None


def transition(claim_id: str, new_status: str,
               evidence_refs: Optional[list] = None,
               actor: str = "collector",
               note: Optional[str] = None) -> bool:
    """Move a claim's evidentiary state — appends version n+1 (the old
    version's valid_until closes) and journals the evidence. The only
    sanctioned way a status changes."""
    from app.database import db
    try:
        cur = db.execute_query(
            "SELECT * FROM narrative_claims WHERE claim_id=:c"
            " ORDER BY version DESC LIMIT 1", {"c": claim_id})
        if not cur:
            return False
        row = dict(cur[0])
        if row["status"] == new_status:
            return True
        db.execute_update(
            "UPDATE narrative_claims SET valid_until=now()"
            " WHERE claim_id=:c AND version=:v",
            {"c": claim_id, "v": row["version"]})
        refs = evidence_refs or []
        db.execute_update(
            "INSERT INTO narrative_claims (claim_id, version, symbol,"
            " entity, claim, direction, claim_type, status, source,"
            " source_date, evidence_confidence, outcome_confidence,"
            " valid_until, evidence_refs, first_seen, last_confirmed,"
            " created_by, supersedes, dedupe_key)"
            " VALUES (:c,:v,:s,:en,:cl,:di,:ty,:st,:so,:sd,:ec,:oc,"
            " now() + interval '180 days',CAST(:er AS jsonb),:fs,"
            " CASE WHEN :st2='confirmed' THEN now() ELSE NULL END,"
            " :cb,:sup,:dk)",
            {"c": claim_id, "v": row["version"] + 1, "s": row["symbol"],
             "en": row.get("entity"), "cl": row["claim"],
             "di": row.get("direction"), "ty": row["claim_type"],
             "st": new_status, "so": row.get("source"),
             "sd": row.get("source_date"),
             "ec": row.get("evidence_confidence"),
             "oc": row.get("outcome_confidence"),
             "er": json.dumps(refs, default=str),
             "fs": row.get("first_seen"), "st2": new_status,
             "cb": actor, "sup": claim_id if row["version"] > 1
             else None, "dk": row["dedupe_key"]})
        db.execute_update(
            "INSERT INTO claim_reviews (claim_id, review_kind, actor,"
            " verdict, evidence_refs, note) VALUES"
            " (:c,'transition',:a,:v,CAST(:e AS jsonb),:n)",
            {"c": claim_id, "a": actor, "v": new_status,
             "e": json.dumps(refs, default=str),
             "n": note or f"{row['status']} → {new_status}"})
        return True
    except Exception as exc:
        logger.debug("claim transition %s: %s", claim_id, exc)
        return False


# ── deterministic collectors — claims from journaled evidence ────────

def collect(symbol: str) -> int:
    """Emit claims from the system's own journals. Each writer is
    idempotent (dedupe_key) — reruns add evidence, not duplicates."""
    from app.database import db
    sym = symbol.upper()
    n = 0
    try:    # guidance claims extracted on the last print
        ew = db.execute_query(
            "SELECT detail, earnings_date FROM earnings_watch"
            " WHERE symbol=:s ORDER BY earnings_date DESC LIMIT 1",
            {"s": sym})
        if ew:
            det = _j(ew[0].get("detail")) or {}
            rel = det.get("release") or {}
            for c in (rel.get("claims") or [])[:6]:
                txt = c.get("claim") if isinstance(c, dict) else str(c)
                if not txt:
                    continue
                n += bool(emit(
                    sym, txt, "positive" if (c.get("sentiment") or "")
                    .startswith("pos") else
                    "negative" if (c.get("sentiment") or "")
                    .startswith("neg") else "mixed",
                    "management_guidance",
                    source="earnings_call",
                    source_date=str(ew[0]["earnings_date"]),
                    evidence_confidence=0.8, outcome_confidence=0.6,
                    status="supported",
                    evidence_refs=[{"table": "earnings_watch",
                                    "date": str(ew[0]["earnings_date"])}]))
    except Exception:
        pass
    try:    # accounting/quality flags — reported facts, negative
        eq = db.execute_query(
            "SELECT flags, as_of FROM symbol_earnings_quality"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        for fl in ((_j(eq[0]["flags"]) if eq else None) or []):
            name = fl if isinstance(fl, str) else str(fl.get("flag", ""))
            if not name:
                continue
            n += bool(emit(
                sym, f"earnings-quality flag: {name.replace('_',' ')}",
                "negative", "reported_fact",
                source="earnings_quality",
                source_date=str(eq[0]["as_of"]),
                evidence_confidence=0.7, status="supported",
                evidence_refs=[{"table": "symbol_earnings_quality",
                                "as_of": str(eq[0]["as_of"])}]))
    except Exception:
        pass
    try:    # management's own forward commitments
        for d in db.execute_query(
                "SELECT metric, period, value, delta_dir, as_of, id"
                " FROM driver_commitments WHERE symbol=:s"
                " AND status='open' ORDER BY as_of DESC LIMIT 6",
                {"s": sym}) or []:
            n += bool(emit(
                sym, f"{d['metric']} {d['period']} guided "
                     f"{d['delta_dir']} to {d['value']}",
                "positive" if d["delta_dir"] == "raised" else "negative",
                "management_guidance", source="guidance",
                source_date=str(d.get("as_of")),
                evidence_confidence=0.85, outcome_confidence=0.65,
                status="supported",
                evidence_refs=[{"table": "driver_commitments",
                                "id": d["id"]}]))
    except Exception:
        pass
    try:    # street revision swings — analyst beliefs, not facts
        fw = db.execute_query(
            "SELECT est_revision_pct, as_of FROM symbol_flywheel"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if fw:
            er = fw[0].get("est_revision_pct")
            if er is not None and abs(float(er)) >= 0.05:
                up = float(er) > 0
                n += bool(emit(
                    sym, f"street revising fwd estimates "
                         f"{'up' if up else 'down'} {abs(float(er))*100:.0f}%",
                    "positive" if up else "negative",
                    "analyst_estimate", source="consensus_revisions",
                    source_date=str(fw[0]["as_of"]),
                    evidence_confidence=0.75, status="supported",
                    evidence_refs=[{"table": "symbol_flywheel",
                                    "as_of": str(fw[0]["as_of"])}]))
    except Exception:
        pass
    return n


def run(symbols: Optional[list[str]] = None) -> dict:
    from app.database import db
    if symbols is None:
        rows = db.execute_query(
            "SELECT DISTINCT symbol FROM symbol_flywheel")
        symbols = [r["symbol"] for r in rows]
    n = sum(collect(s) for s in symbols)
    return {"symbols": len(symbols), "claims_emitted": n}


def read(symbol: str, history: bool = False) -> list[dict]:
    from app.database import db
    try:
        if history:
            return db.execute_query(
                "SELECT * FROM narrative_claims WHERE symbol=:s"
                " ORDER BY claim_id, version DESC", {"s": symbol.upper()})
        return db.execute_query(
            "SELECT c.* FROM narrative_claims c JOIN ("
            " SELECT claim_id, max(version) v FROM narrative_claims"
            " WHERE symbol=:s GROUP BY claim_id) l"
            " ON c.claim_id=l.claim_id AND c.version=l.v"
            " WHERE c.status != 'expired'"
            " ORDER BY c.source_date DESC NULLS LAST",
            {"s": symbol.upper()})
    except Exception:
        return []
