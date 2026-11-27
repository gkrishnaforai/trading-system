"""Brain intake — the admin lane for feeding the intelligence layer.

Admin submits a doc/news/URL on the /brain page. The submission runs
through the SAME pipeline as every other source — doc_extract's
verbatim-quote grounding + deterministic validation — and the queue
row journals the verdict with the canonical why block:

  accepted   claims survived validation and landed in the stores
  partial    some survived, some dropped — both sides journaled
  rejected   nothing usable — no text, no resolvable symbol, or
             every claim failed grounding. The why says exactly why.

The brain never silently ingests: a doc that can't be grounded to a
tracked symbol or verbatim evidence is rejected with the reason, not
parsed into narrative.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MAX_SYMBOLS = 5     # bound LLM spend per submission
_MIN_CHARS = 200     # same floor doc_extract enforces


def _tracked() -> tuple[set[str], dict[str, str]]:
    """The working universe: tickers + {lower company name → ticker}."""
    from app.database import db
    from app.signals import symbol_tiers
    syms = {r["symbol"] for r in db.execute_query(
        f"SELECT symbol FROM ({symbol_tiers._active_sql()}) x")}
    names = {str(r["company_name"]).lower(): r["symbol"]
             for r in db.execute_query(
                 "SELECT symbol, company_name FROM stocks"
                 " WHERE company_name IS NOT NULL")
             if r.get("symbol") in syms and r.get("company_name")}
    return syms, names


def _detect_symbols(text: str, title: str = "") -> list[str]:
    """Resolve the doc to tracked symbols — ticker tokens + company
    names. Deterministic only; the LLM never picks symbols."""
    syms, names = _tracked()
    hay = f"{title}\n{text}".lower()
    found: list[str] = []
    # ticker tokens — require word-boundary match on the RAW text so
    # case matters ('ON' the word doesn't tag ON Semiconductor)
    for tok in set(re.findall(r"\b([A-Z]{2,5})\b", f"{title} {text}")):
        if tok in syms and tok not in found:
            found.append(tok)
    # company names — longest-name-first so 'Applied Materials' beats
    # 'Applied'; probe on the name minus Inc/Corp suffixes since docs
    # write 'Nvidia', not 'Nvidia Corporation'
    for name in sorted(names, key=len, reverse=True):
        first = name.split(",")[0].split(" inc")[0].split(" corp")[0].strip()
        probe = first if len(first) >= 4 else name
        if len(probe) >= 4 and probe in hay and names[name] not in found:
            found.append(names[name])
    return found[:_MAX_SYMBOLS]


def _sha(text: str, url: str) -> str:
    return hashlib.sha1(
        f"{url}|{re.sub(r' +', ' ', text.lower().strip())}".encode()
    ).hexdigest()[:24]


def submit(text: str = "", url: str = "", title: str = "",
           symbols: Optional[list[str]] = None, by: str = "admin",
           kind: str = "doc") -> dict:
    """Enqueue a submission. Dedupes on content hash — resubmitting
    the same doc returns the existing queue row."""
    from app.database import db
    sha = _sha(text or url, url)
    existing = db.execute_query(
        "SELECT id, status, verdict FROM brain_intake WHERE text_sha=:s",
        {"s": sha})
    if existing:
        return {"id": existing[0]["id"], "deduped": True,
                "status": existing[0]["status"]}
    row = db.execute_query(
        "INSERT INTO brain_intake (submitted_by, kind, title, url,"
        " text_sha, symbols) VALUES (:b,:k,:t,:u,:s,CAST(:sy AS jsonb))"
        " RETURNING id",
        {"b": by, "k": kind, "t": (title or "")[:200] or None,
         "u": (url or "")[:400] or None, "s": sha,
         "sy": json.dumps([s.upper() for s in (symbols or [])])})
    return {"id": row[0]["id"], "deduped": False, "status": "queued"}


def process(intake_id: int, text: str = "", url: str = "",
            title: str = "", symbols: Optional[list[str]] = None) -> dict:
    """Run one queued submission through the extraction pipeline and
    journal the verdict. Synchronous — the POST handler wraps it in
    to_thread; one doc_extract call per resolved symbol."""
    from app.database import db
    from app.signals import doc_extract
    from app.support.why import explain

    def _finish(status: str, why: dict, syms: list[str],
                landed: dict, dropped: list) -> dict:
        db.execute_update(
            "UPDATE brain_intake SET status=:st, verdict=CAST(:v AS jsonb),"
            " symbols=CAST(:sy AS jsonb), landed=CAST(:l AS jsonb),"
            " dropped=CAST(:d AS jsonb) WHERE id=:i",
            {"st": status, "v": json.dumps(why), "sy": json.dumps(syms),
             "l": json.dumps(landed), "d": json.dumps(dropped),
             "i": intake_id})
        return {"id": intake_id, "status": status, "verdict": why,
                "symbols": syms, "landed": landed, "dropped": dropped}

    db.execute_update(
        "UPDATE brain_intake SET status='processing' WHERE id=:i",
        {"i": intake_id})

    # fetch-by-url needs text on hand for symbol detection —
    # doc_extract refetches for its own analysis
    probe_text = text
    if not probe_text and url:
        probe_text, fetched = doc_extract._fetch(url)
        title = title or fetched

    if len(probe_text or "") < _MIN_CHARS:
        return _finish("rejected", explain(
            "rejected",
            counter=["no usable document text — paywalled source or"
                     " paste under 200 chars; paste the article body"],
            rule="text ≥200 chars required before extraction"),
            [], {}, [])

    syms = [s.upper() for s in (symbols or [])][: _MAX_SYMBOLS]
    if not syms:
        syms = _detect_symbols(probe_text, title)
    if not syms:
        return _finish("rejected", explain(
            "rejected",
            counter=["no tracked symbol resolved — the brain only"
                     " grounds claims to coverage names; tag symbols"
                     " explicitly or mention the ticker/company name"],
            rule="explicit symbols, else ticker/company-name detection"
                 " vs tracked universe"),
            [], {}, [])

    landed = {"symbols_analyzed": 0, "claims": 0, "channels": 0,
              "watches": 0, "drivers": 0, "doc_analyses": 0}
    dropped: list = []
    errors: list = []
    for sym in syms:
        try:
            r = doc_extract.analyze(sym, text=probe_text,
                                    url=url, title=title)
            if r.get("error"):
                errors.append(f"{sym}: {r['error']}")
                continue
            landed["symbols_analyzed"] += 1
            landed["claims"] += len(r.get("claims") or [])
            landed["channels"] += int(r.get("journaled_channels") or 0)
            landed["watches"] += len(r.get("watches") or [])
            landed["drivers"] += len(r.get("drivers") or [])
            landed["doc_analyses"] += 1
            for d in (r.get("dropped") or []):
                dropped.append({"symbol": sym,
                                "reason": d.get("drop_reason") or "validation",
                                "claim": str(d.get("text") or "")[:120]})
        except Exception as exc:                       # noqa: BLE001
            logger.warning("brain intake %s %s failed: %s",
                           intake_id, sym, exc)
            errors.append(f"{sym}: {str(exc)[:120]}")

    stored = (landed["claims"] or landed["doc_analyses"]
              or landed["channels"] or landed["watches"])
    if errors and not stored:
        status = "error"
    elif dropped and stored:
        status = "partial"
    elif stored:
        status = "accepted"
    else:
        status = "rejected"

    counter = ([f"{len(dropped)} claims failed validation"]
               + [d["reason"] for d in dropped[:3]]
               + errors[:3])
    if status == "rejected" and not counter:
        counter = ["no extractable claims — doc carried no"
                   " channel/fact/watch/driver content for the"
                   " resolved symbols"]
    dests = [f"{v} {k}" for k, v in
             (("channel", landed["channels"]), ("watch", landed["watches"]),
              ("driver", landed["drivers"])) if v]
    why = explain(
        status,
        summary=(
            f"{landed['claims']} claims journaled for "
            f"{', '.join(syms[:3])}"
            + (f" ({', '.join(dests)})" if dests else "")
            + (f" — {len(dropped)} dropped by validation" if dropped
               else "")),
        basis=[{"name": k, "value": v} for k, v in landed.items() if v],
        drivers=[f"{sym} → {landed['doc_analyses']} doc row(s) "
                 f"journaled" for sym in syms[:1]] if stored else [],
        counter=counter,
        refs=[{"table": "brain_intake", "id": intake_id}],
        rule="verbatim-quote grounding + claim-type whitelist"
             " (doc_extract); ≥1 journaled claim → accepted/partial")
    return _finish(status, why, syms, landed, dropped)


def list_recent(limit: int = 25) -> list[dict]:
    """The intake queue for the /brain page — newest first."""
    from app.database import db
    rows = db.execute_query(
        "SELECT id, submitted_at, submitted_by, kind, title, url,"
        " symbols, status, verdict, landed, dropped"
        " FROM brain_intake ORDER BY submitted_at DESC LIMIT :n",
        {"n": limit})
    return rows
