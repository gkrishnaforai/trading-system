"""Earnings-release extraction — 8-K item 2.02 → doc_extract.

Every tracked symbol's recent 8-K filings are checked for item 2.02
(results of operations — the earnings release). The EX-99 press
release text goes through the existing doc_extract pipeline: claims
must carry verbatim quotes, guidance statements become falsifiable
thesis_watches ("expects FY27 subscription revenue >$X" gets graded
later), channels/risks journal into tailwinds.

Deduped on accession number — each release is analyzed exactly once.
LLM spend is bounded: only tracked symbols, only new filings, max 3
releases per symbol per run.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run(symbols: list[str], days: int = 120) -> dict[str, Any]:
    from app.database import db
    from app.providers import sec_edgar
    from app.signals import doc_extract, sec_fundamentals

    sec_fundamentals.ensure_table()
    done = {r["accession"] for r in db.execute_query(
        "SELECT accession FROM sec_filings_processed")}

    filings = analyzed = claims = 0
    errors: list[str] = []
    for sym in symbols:
        try:
            rels = sec_edgar.recent_8k_releases(sym, days=days)
        except Exception as exc:
            errors.append(f"{sym}: {exc}")
            continue
        for rel in rels:
            filings += 1
            if rel["accession"] in done:
                continue
            try:
                res = doc_extract.analyze(
                    sym, text=rel["text"], url=rel["url"],
                    title=f"{sym} 8-K earnings release "
                          f"{rel['filed']}")
                n = len(res.get("claims") or [])
                db.execute_update(
                    "INSERT INTO sec_filings_processed "
                    "(accession, symbol, form, filed, url, claims) "
                    "VALUES (:a,:s,'8-K',:f,:u,:c) "
                    "ON CONFLICT (accession) DO NOTHING",
                    {"a": rel["accession"], "s": sym,
                     "f": rel["filed"], "u": rel["url"], "c": n})
                analyzed += 1
                claims += n
            except Exception as exc:
                errors.append(f"{sym} {rel['accession']}: {exc}")
                if len(errors) >= 10:
                    break
    return {"symbols": len(symbols), "filings_seen": filings,
            "analyzed": analyzed, "claims": claims, "errors": errors}
