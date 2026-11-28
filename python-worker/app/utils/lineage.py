"""Data lineage + public-eligibility gate — A3 of the spine.

Every derived output records its inputs as edges in data_lineage.
Public eligibility is decided by walking those edges to leaves and
classifying each leaf's source through SOURCE_LICENSE — recursively,
so a licensed input can't reach a public output through a derived
middle layer no matter how many hops it travels.

Read path is materialized: compute_eligibility writes
output_eligibility at derivation time (O(1) API reads); audit walks
the graph again to prove it. If an upstream fact is restated or a
source reclassified, invalidate_downstream marks the affected
outputs for recomputation — a cached TRUE never outlives its inputs.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# single source of truth for "can this reach a public user" —
# government/public-domain vs commercial/third-party. A source not
# listed here defaults to LICENSED (fail closed).
SOURCE_LICENSE: dict[str, str] = {
    "sec_edgar":       "public",   # filings, companyfacts, submissions
    "sec":             "public",
    "fred":            "public",   # government series — see note: ICE/Cboe series on FRED are third-party
    "cftc":            "public",
    "bls":             "public",
    "bea":             "public",
    "federal_reserve": "public",
    "fmp":             "licensed",
    "financial_modeling_prep": "licensed",
    "yahoo":           "licensed",
    "yahoo_finance":   "licensed",
    "finnhub":         "licensed",
    "alphavantage":    "licensed",
    "alpha_vantage":   "licensed",
    "massive":         "licensed",
    "polygon":         "licensed",
    "cboe":            "licensed",
    "nowflation":      "licensed",
    "farside":         "licensed",
    "binance":         "licensed",
    "kraken":          "licensed",
    "defillama":       "licensed",
    "stooq":           "licensed",
}

_POLICY_VERSION = "1.0"
_MAX_WALK = 10_000          # runaway-graph guard


def license_class(source: Optional[str]) -> str:
    """public|licensed — unknown sources are licensed (fail closed)."""
    return SOURCE_LICENSE.get(str(source or "").strip().lower(),
                              "licensed")


def record_edge(output_type: str, output_id: str, input_type: str,
                input_id: str, data_source: str,
                transform_version: Optional[str] = None) -> None:
    """One lineage edge. Idempotent — re-derivation can re-record."""
    from app.database import db
    db.execute_update(
        "INSERT INTO data_lineage (output_type, output_id, input_type,"
        " input_id, data_source, license_class,"
        " transformation_version)"
        " VALUES (:ot,:oid,:it,:iid,:ds,:lc,:tv)"
        " ON CONFLICT (output_type, output_id, input_type, input_id)"
        " DO NOTHING",
        {"ot": output_type, "oid": str(output_id), "it": input_type,
         "iid": str(input_id), "ds": data_source,
         "lc": license_class(data_source), "tv": transform_version})


def _walk_leaves(output_type: str, output_id: str) -> tuple[list, list, bool]:
    """BFS to leaf nodes — returns (public_leaves, restricted_leaves,
    complete). A leaf = an edge endpoint with no downstream edges of
    its own. complete=False means the walk hit the guard or an edge
    referenced a node type we can't verify."""
    from app.database import db
    public: list[str] = []
    restricted: list[str] = []
    seen = {(output_type, str(output_id))}
    frontier = [(output_type, str(output_id))]
    steps = 0
    complete = True
    while frontier and steps < _MAX_WALK:
        ot, oid = frontier.pop()
        steps += 1
        rows = db.execute_query(
            "SELECT input_type, input_id, license_class"
            " FROM data_lineage"
            " WHERE output_type=:ot AND output_id=:oid",
            {"ot": ot, "oid": oid})
        if not rows:
            continue            # no recorded inputs — a terminal node
        for r in rows:
            key = (r["input_type"], str(r["input_id"]))
            leaf_id = f"{r['input_type']}:{r['input_id']}"
            # leaf = endpoint without recorded downstream edges
            has_children = db.execute_query(
                "SELECT 1 FROM data_lineage"
                " WHERE output_type=:it AND output_id=:iid LIMIT 1",
                {"it": r["input_type"], "iid": str(r["input_id"])})
            if not has_children:
                (public if r["license_class"] == "public"
                 else restricted).append(leaf_id)
            elif key not in seen:
                seen.add(key)
                frontier.append(key)
    if steps >= _MAX_WALK:
        complete = False
        logger.warning("lineage walk guard hit for %s:%s",
                       output_type, output_id)
    return public, restricted, complete


def compute_eligibility(output_type: str, output_id: str) -> dict[str, Any]:
    """Walk leaves → materialize the eligibility verdict. Call this at
    derivation time; API reads stay O(1) off output_eligibility."""
    from app.database import db
    public, restricted, complete = _walk_leaves(output_type, output_id)
    eligible = complete and not restricted
    leaf_set = sorted(public + restricted)
    lh = hashlib.sha1("|".join(leaf_set).encode()).hexdigest()
    db.execute_update(
        "INSERT INTO output_eligibility (output_type, output_id,"
        " public_eligible, lineage_complete, public_leaf_count,"
        " restricted_leaf_count, lineage_hash,"
        " eligibility_checked_at, eligibility_policy_version)"
        " VALUES (:ot,:oid,:pe,:lc,:pc,:rc,:lh,now(),:pv)"
        " ON CONFLICT (output_type, output_id) DO UPDATE SET"
        " public_eligible=:pe, lineage_complete=:lc,"
        " public_leaf_count=:pc, restricted_leaf_count=:rc,"
        " lineage_hash=:lh, eligibility_checked_at=now(),"
        " eligibility_policy_version=:pv",
        {"ot": output_type, "oid": str(output_id), "pe": eligible,
         "lc": complete, "pc": len(public), "rc": len(restricted),
         "lh": lh, "pv": _POLICY_VERSION})
    return {"output": f"{output_type}:{output_id}",
            "public_eligible": eligible, "lineage_complete": complete,
            "public_leaves": len(public),
            "restricted_leaves": len(restricted)}


def is_public_eligible(output_type: str, output_id: str) -> bool:
    """The API-read gate — materialized verdict only; absence of a
    verdict is NOT eligible (fail closed)."""
    from app.database import db
    rows = db.execute_query(
        "SELECT public_eligible, lineage_complete"
        " FROM output_eligibility"
        " WHERE output_type=:ot AND output_id=:oid",
        {"ot": output_type, "oid": str(output_id)})
    return bool(rows and rows[0]["public_eligible"]
                and rows[0]["lineage_complete"])


def invalidate_downstream(input_type: str, input_id: str) -> int:
    """An input changed (restatement, source reclassify) — every
    output reachable FROM this input needs eligibility recomputed.
    Returns outputs marked stale via eligibility deletion; the next
    compute_eligibility pass rebuilds them."""
    from app.database import db
    # walk the edge graph FORWARD from the changed input
    affected: set[tuple[str, str]] = set()
    frontier = [(input_type, str(input_id))]
    steps = 0
    while frontier and steps < _MAX_WALK:
        it, iid = frontier.pop()
        steps += 1
        rows = db.execute_query(
            "SELECT output_type, output_id FROM data_lineage"
            " WHERE input_type=:it AND input_id=:iid",
            {"it": it, "iid": iid})
        for r in rows:
            key = (r["output_type"], str(r["output_id"]))
            if key not in affected:
                affected.add(key)
                frontier.append(key)
    for ot, oid in affected:
        db.execute_update(
            "DELETE FROM output_eligibility"
            " WHERE output_type=:ot AND output_id=:oid",
            {"ot": ot, "oid": oid})
    return len(affected)
