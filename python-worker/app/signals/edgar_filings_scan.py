"""EDGAR filing-event scan — A1 of the public-data spine.

Polls the submissions index per tracked issuer and journals every
filing event into edgar_filings, keyed by accession number. The event
log is append-only: amendments (10-Q/A, 8-K/A) land as their own rows
linked back to the amended filing — a restatement is itself an event.

Resumable: edgar_ingest_state.filings_scanned_at is the cursor; the
job chunks the universe so a kill mid-run loses nothing. Submissions
is one call per issuer (~4 req/s self-throttled) — nightly is cheap;
the deep pass with paginated older-files is for backfill windows.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# how far back the event log reaches — v1 scope is ~2 years of
# quarterly history; the buffer catches late amendments/restating
# re-filings for the earliest periods we still serve.
_LOOKBACK_DAYS = 1100
# one symbol's submissions call doubles as its resume tick — chunk
# the universe so an interrupted run loses ≤1 symbol's work
_CHUNK = 50


def _doc_url(cik: str, accn: str, primary: Optional[str]) -> Optional[str]:
    if not primary:
        return None
    acc_nd = accn.replace("-", "")
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{acc_nd}/{primary}")


def _is_amendment(form: str) -> bool:
    return form.strip().upper().endswith("/A")


def _upsert_filing(db, cik: str, e: dict) -> bool:
    """Insert one filing event; False when the event already exists."""
    accn = e["accession_number"]
    form = e.get("form") or ""
    doc_url = _doc_url(cik, accn, e.get("primary_document"))
    n = db.execute_update(
        "INSERT INTO edgar_filings (cik, accession_number, form,"
        " filing_date, acceptance_datetime, report_period,"
        " primary_document, items, is_amendment, document_url)"
        " VALUES (:cik,:accn,:form,:fd,:adt,:rp,:pd,:items,:amend,:url)"
        " ON CONFLICT (accession_number) DO NOTHING",
        {"cik": cik, "accn": accn, "form": form,
         "fd": e.get("filing_date"), "adt": e.get("acceptance_datetime"),
         "rp": e.get("report_period") or None,
         "pd": e.get("primary_document"), "items": e.get("items"),
         "amend": _is_amendment(form), "url": doc_url})
    return bool(n)


def _link_amendments(db, cik: str) -> int:
    """Resolve amends_accession_number — an amendment points at the
    latest earlier filing sharing base form + report period. Runs as
    a sweep (not per-insert) so order of ingestion doesn't matter."""
    return db.execute_update(
        "UPDATE edgar_filings a SET amends_accession_number = p.ac"
        " FROM (SELECT DISTINCT ON (a2.accession_number)"
        "        a2.accession_number AS am, p2.accession_number AS ac"
        "      FROM edgar_filings a2"
        "      JOIN edgar_filings p2 ON p2.cik = a2.cik"
        "        AND replace(p2.form,'/A','') = replace(a2.form,'/A','')"
        "        AND p2.report_period = a2.report_period"
        "        AND NOT p2.is_amendment"
        "        AND p2.filing_date <= a2.filing_date"
        "      WHERE a2.cik = :cik AND a2.is_amendment"
        "      ORDER BY a2.accession_number, p2.filing_date DESC) p"
        " WHERE a.cik = :cik AND a.is_amendment"
        "   AND a.accession_number = p.am"
        "   AND a.amends_accession_number IS NULL",
        {"cik": cik})


def scan_symbol(db, symbol: str, lookback_days: int = _LOOKBACK_DAYS,
                deep: bool = False) -> dict[str, Any]:
    """Submissions → edgar_filings for one issuer. Returns counts."""
    from app.providers import sec_edgar
    blob = sec_edgar.submissions(symbol, include_older=deep)
    if not blob:
        return {"symbol": symbol, "cik": None, "new": 0, "skipped": 0}
    cik = blob["cik"]
    cutoff = date.today() - timedelta(days=lookback_days)
    new = skipped = 0
    for e in blob["events"]:
        try:
            if date.fromisoformat(str(e.get("filing_date"))) < cutoff:
                continue
        except Exception:
            continue
        if _upsert_filing(db, cik, e):
            new += 1
        else:
            skipped += 1
    _link_amendments(db, cik)
    db.execute_update(
        "INSERT INTO edgar_ingest_state (symbol, cik,"
        " filings_scanned_at, backfill_done, updated_at)"
        " VALUES (:s,:cik,now(),:deep,now())"
        " ON CONFLICT (symbol) DO UPDATE SET cik=:cik,"
        " filings_scanned_at=now(),"
        " backfill_done = edgar_ingest_state.backfill_done OR :deep,"
        " updated_at=now()",
        {"s": symbol, "cik": cik, "deep": deep})
    return {"symbol": symbol, "cik": cik, "new": new,
            "skipped": skipped}


def run(symbols: list[str], deep: bool = False) -> dict[str, Any]:
    """Chunked pass over the tracked universe. deep=True also pulls
    the paginated older-filings chunks — the weekend backfill path."""
    from app.database import db
    totals = {"symbols": 0, "no_cik": 0, "new_filings": 0,
              "amended_events": 0, "errors": []}
    for i in range(0, len(symbols), _CHUNK):
        for sym in symbols[i:i + _CHUNK]:
            try:
                r = scan_symbol(db, sym, deep=deep)
                totals["symbols"] += 1
                if not r["cik"]:
                    totals["no_cik"] += 1
                totals["new_filings"] += r["new"]
            except Exception as exc:
                logger.warning("edgar scan %s failed: %s", sym, exc)
                totals["errors"].append(f"{sym}: {exc}")
        # chunk boundary = resume point; ingest_state rows are already
        # durable, next run skips unchanged issuers cheaply
    amendments = db.execute_query(
        "SELECT COUNT(*) AS n FROM edgar_filings WHERE is_amendment")
    totals["amended_events"] = int(amendments[0]["n"]) if amendments else 0
    return totals
