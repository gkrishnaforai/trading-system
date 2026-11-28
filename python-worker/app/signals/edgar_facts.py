"""EDGAR fact-observation loader — A2 of the public-data spine.

companyfacts → fact_observations: every reported XBRL fact preserved
verbatim — value, period bounds and fiscal metadata exactly as filed,
never normalized in place. Restatements and amendments arrive as new
observations under their own accession; which observation "wins" is
the resolver's call, not this table's.

Dedup is a deterministic content hash (source_fact_id) so re-runs are
idempotent — no duplicate observations ever land twice. Scope is
bounded to ~3 years of period-ends: the product serves 8 quarters and
YoY legs need one comparison year of history. Derived observations
(is_derived) are written by the resolver, not here.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PARSER = "a2_v1"
# observation horizon — display serves ~8 quarters; one extra year
# covers YoY legs on the earliest shown period
_HORIZON_DAYS = 3 * 366


def _fact_id(cik: str, accn: str, tax: str, tag: str, unit: str,
             start: Optional[str], end: Optional[str], val) -> str:
    raw = f"{cik}|{accn}|{tax}|{tag}|{unit}|{start}|{end}|{val}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _row(cik: str, tax: str, tag: str, unit: str, o: dict,
         horizon: date) -> Optional[dict]:
    end = o.get("end")
    if not end:
        return None
    try:
        if date.fromisoformat(str(end)) < horizon:
            return None
    except Exception:
        return None
    start = o.get("start") or None
    accn = str(o.get("accn") or "")
    if not accn:
        return None
    form = str(o.get("form") or "")
    filed = o.get("filed")
    return {
        "cik": cik, "accn": accn, "tax": tax, "tag": tag,
        "unit": unit, "val": o.get("val"), "dec": o.get("decimals"),
        "start": start, "end": end, "instant": start is None,
        "fy": o.get("fy"), "fp": o.get("fp"), "frame": o.get("frame"),
        "form": form,
        "filed": f"{filed} 00:00:00+00" if filed and
                 len(str(filed)) == 10 else filed,
        "amend": form.strip().upper().endswith("/A"),
        "src": "https://data.sec.gov/api/xbrl/companyfacts/"
               f"CIK{cik}.json",
        "sfid": _fact_id(cik, accn, tax, tag, unit, start, end,
                         o.get("val")),
    }


def load_symbol(db, symbol: str) -> dict[str, Any]:
    """One issuer's companyfacts → fact_observations. Idempotent."""
    from app.providers import sec_edgar
    blob = sec_edgar.company_facts(symbol)
    cik = sec_edgar.cik_for(symbol)
    if not blob or not cik:
        return {"symbol": symbol, "cik": cik, "inserted": 0}
    horizon = date.today() - timedelta(days=_HORIZON_DAYS)
    rows: list[dict] = []
    facts = blob.get("facts") or {}
    for tax, tags in facts.items():
        if not isinstance(tags, dict):
            continue
        for tag, obj in tags.items():
            for unit, obs in ((obj.get("units") or {}).items()):
                for o in obs:
                    r = _row(cik, tax, tag, unit, o, horizon)
                    if r:
                        rows.append(r)
    if not rows:
        db.execute_update(
            "INSERT INTO edgar_ingest_state (symbol, cik,"
            " facts_pulled_at, updated_at) VALUES (:s,:cik,now(),now())"
            " ON CONFLICT (symbol) DO UPDATE SET cik=:cik,"
            " facts_pulled_at=now(), updated_at=now()",
            {"s": symbol, "cik": cik})
        return {"symbol": symbol, "cik": cik, "inserted": 0}
    inserted = db.execute_many(
        "INSERT INTO fact_observations (cik, accn, taxonomy, tag,"
        " unit, value, decimals, period_start, period_end, instant,"
        " fy, fp, frame, form, filed_at, is_amendment, source_url,"
        " parser_version, source_fact_id)"
        " VALUES (:cik,:accn,:tax,:tag,:unit,:val,:dec,:start,:end,"
        " :instant,:fy,:fp,:frame,:form,:filed,:amend,:src,:p,:sfid)"
        " ON CONFLICT (source_fact_id) DO NOTHING",
        [{**r, "p": _PARSER} for r in rows])
    db.execute_update(
        "INSERT INTO edgar_ingest_state (symbol, cik,"
        " facts_pulled_at, updated_at) VALUES (:s,:cik,now(),now())"
        " ON CONFLICT (symbol) DO UPDATE SET cik=:cik,"
        " facts_pulled_at=now(), updated_at=now()",
        {"s": symbol, "cik": cik})
    return {"symbol": symbol, "cik": cik, "observed": len(rows),
            "inserted": inserted}


def run(symbols: list[str], chunk: int = 25) -> dict[str, Any]:
    """Weekend backfill pass — chunked; each symbol's ingest_state
    tick is the resume point, so a kill mid-run restarts cleanly.
    Sequential by design: EDGAR stays at ~4 req/s, this job is
    patient."""
    from app.database import db
    # issuers not yet backfilled run first — resumable ordering
    pending = db.execute_query(
        "SELECT symbol FROM edgar_ingest_state"
        " WHERE facts_pulled_at IS NULL OR"
        "       facts_pulled_at < now() - interval '30 days'")
    done = {r["symbol"] for r in pending} if pending else set()
    ordered = [s for s in symbols if s in done] + \
              [s for s in symbols if s not in done]
    totals = {"symbols": 0, "no_cik": 0, "observations": 0,
              "inserted": 0, "errors": []}
    for i in range(0, len(ordered), chunk):
        for sym in ordered[i:i + chunk]:
            try:
                r = load_symbol(db, sym)
                totals["symbols"] += 1
                if not r["cik"]:
                    totals["no_cik"] += 1
                totals["observations"] += r.get("observed", 0)
                totals["inserted"] += r["inserted"]
            except Exception as exc:
                logger.warning("edgar facts %s failed: %s", sym, exc)
                totals["errors"].append(f"{sym}: {exc}")
    return totals
