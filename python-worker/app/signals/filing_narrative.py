"""Filing narrative — Phase C of the public-data spine.

10-Q/10-K MD&A + Risk Factors (EDGAR text only) → grounded claims.

The contract, same as doc_extract: every claim carries a VERBATIM
quote — a literal substring of the section text. Paraphrase dies in
validation; unsupported claims never reach the ledger. Each landed
claim gets a claim_evidence row (filing/section/quote), optional
claim_metric_links, and a lineage edge back to the filing — public
eligibility is proven, not assumed.

Per filing: filing_narratives row = the extraction journal
(idempotent on accession). Claims land in narrative_claims via the
existing emit() dedupe — re-running a filing confirms, never dupes.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PARSER = "filing_narrative_v1"
_MAX_SECTION_CHARS = 24000      # ~6k tokens — bound spend per section
_MAX_CLAIMS = 8

# item headers — the TOC lists them first, the body repeats them;
# the LAST match is the section body
_HEADERS = {
    "10-Q": {
        "mda": r"item\s*2\.?\s+management.{0,5}discussion",
        "risk_factors": r"item\s*1a\.?\s+risk\s*factors",
    },
    "10-K": {
        "mda": r"item\s*7\.?\s+management.{0,5}discussion",
        "risk_factors": r"item\s*1a\.?\s+risk\s*factors",
    },
}
_NEXT_ITEM = re.compile(r"item\s*\d+[a-z]?\s*\.", re.I)


def _split_sections(text: str, form: str) -> dict[str, str]:
    """Filing text → {section: body}. Header names appear in the TOC
    and the body — take the last occurrence, slice to the next Item."""
    heads = _HEADERS.get(form, {})
    out: dict[str, str] = {}
    for name, pat in heads.items():
        matches = list(re.finditer(pat, text, re.I))
        if not matches:
            continue
        start = matches[-1].end()
        nxt = _NEXT_ITEM.search(text, pos=start)
        body = text[start:nxt.start() if nxt else None]
        body = body.strip()
        if len(body) > 400:          # stub matches aren't sections
            out[name] = body[:_MAX_SECTION_CHARS]
    return out


def _llm_extract(symbol: str, form: str, section: str,
                 text: str) -> tuple[list[dict], str]:
    """LLM extracts claims — verbatim-quote grounded, classified,
    metric-linked. Returns (claims, model). The model never invents:
    validation drops anything whose quote isn't a literal substring."""
    from app.llm.client import llm_completion
    from app.config import settings
    import json as _json
    model = getattr(settings, "litellm_model", None) or "gpt-4o-mini"
    resp = llm_completion(
        model=model, temperature=0.1, max_tokens=1800,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content":
             "You extract claims from a SEC filing section and return "
             "STRICT JSON. Extract only what the text says — never "
             "infer, never score, never recommend. Every claim MUST "
             "carry `quote`: a VERBATIM substring copied from the text "
             "(validation checks literally — paraphrase dies). "
             "Schema: {\"claims\": [{\"type\": \"risk_factor\"|"
             "\"management_view\"|\"forward_looking\"|\"liquidity\"|"
             "\"critical_estimate\"|\"operating_trend\", "
             "\"text\": what is claimed (1-2 lines), \"quote\": "
             "verbatim substring, \"direction\": \"tailwind\"|"
             "\"headwind\"|\"neutral\", \"metric\": short_snake name "
             "when the claim quantifies something (e.g. 'revenue', "
             "'capex', 'op_margin', 'cash_on_hand') else null, "
             "\"value\": number in raw units (2.7e9 not '2.7B') or "
             "null, \"prior_value\": number when the text compares "
             "against a previously stated figure else null, "
             "\"period\": e.g. 'FY26 Q3' or 'FY27' else null}]}. "
             "risk_factor = a stated risk. management_view = how "
             "management explains results. forward_looking = a stated "
             "expectation/plan (guidance, capacity, investment). "
             "liquidity = cash/debt/going-concern content. "
             "critical_estimate = disclosed accounting judgment. "
             "operating_trend = stated demand/segment/mix movement. "
             f"Section: {section.replace('_',' ')}. "
             f"Return the { _MAX_CLAIMS } most material claims only."},
            {"role": "user", "content":
             f"Symbol: {symbol}\nForm: {form}\n\nSection text:\n{text}"}])
    raw = _json.loads(resp.choices[0].message.content)
    return (raw.get("claims") or [])[:_MAX_CLAIMS], model


def _valid(c: dict, section_text: str) -> Optional[str]:
    """One claim → drop reason or None (same grounding rule as
    doc_extract: the quote must be a literal substring)."""
    from app.signals.doc_extract import _grounded
    if c.get("type") not in ("risk_factor", "management_view",
                             "forward_looking", "liquidity",
                             "critical_estimate", "operating_trend"):
        return "unknown claim type"
    if not (c.get("text") or "").strip():
        return "empty claim text"
    if not _grounded(c.get("quote") or "", section_text):
        return "quote not verbatim in section"
    return None


_CLAIM_TYPE = {
    "risk_factor": "reported_fact",
    "management_view": "reported_fact",
    "forward_looking": "management_guidance",
    "liquidity": "reported_fact",
    "critical_estimate": "reported_fact",
    "operating_trend": "reported_fact",
}
_DIRECTION = {"tailwind": "positive", "headwind": "negative"}


def extract_filing(db, filing: dict) -> dict[str, Any]:
    """One 10-Q/10-K → sections → grounded claims → ledger +
    evidence + metric links + lineage. Idempotent on accession."""
    from app.providers import sec_edgar
    from app.signals import narrative_ledger
    from app.utils import lineage as lin

    accn, sym = filing["accession_number"], filing["symbol"]
    cik, form = filing.get("cik"), filing.get("form")
    status = "error"
    try:
        text = sec_edgar.filing_document(cik, accn,
                                         filing.get("primary_document"))
        if not text or len(text) < 2000:
            status = "no_doc"
            _journal(db, filing, None, 0, 0, status=status)
            return {"accession": accn, "status": status}
        sections = _split_sections(text, form)
        if not sections:
            status = "no_sections"
            _journal(db, filing, None, 0, 0, status=status)
            return {"accession": accn, "status": status}

        emitted = dropped = 0
        model = None
        for section, body in sections.items():
            claims, model = _llm_extract(sym, form, section, body)
            for c in claims:
                reason = _valid(c, body)
                if reason:
                    dropped += 1
                    continue
                cid = narrative_ledger.emit(
                    sym, str(c["text"])[:450],
                    _DIRECTION.get(c.get("direction"), "mixed"),
                    _CLAIM_TYPE.get(c["type"], "reported_fact"),
                    source=f"edgar_{form}_{section}",
                    source_date=str(filing.get("filing_date") or ""),
                    evidence_confidence=0.8, status="supported",
                    created_by="filing_narrative",
                    evidence_refs=[{"table": "edgar_filings",
                                    "accession": accn,
                                    "section": section}])
                if not cid:
                    continue          # deduped — already ledgered
                emitted += 1
                db.execute_update(
                    "INSERT INTO claim_evidence (claim_id,"
                    " accession_number, symbol, section, quote,"
                    " source_url, filed_at, parser_version) VALUES"
                    " (:c,:a,:s,:sec,:q,:u,:f,:p)"
                    " ON CONFLICT (claim_id, accession_number,"
                    " md5(quote)) DO NOTHING",
                    {"c": cid, "a": accn, "s": sym, "sec": section,
                     "q": str(c.get("quote") or "")[:2000],
                     "u": filing.get("document_url"),
                     "f": str(filing.get("filing_date") or ""),
                     "p": _PARSER})
                if c.get("metric"):
                    db.execute_update(
                        "INSERT INTO claim_metric_links (claim_id,"
                        " symbol, metric, value, prior_value, period,"
                        " direction) VALUES (:c,:s,:m,:v,:pv,:p,:d)"
                        " ON CONFLICT (claim_id, metric, period)"
                        " DO NOTHING",
                        {"c": cid, "s": sym,
                         "m": str(c["metric"])[:60],
                         "v": _num(c.get("value")),
                         "pv": _num(c.get("prior_value")),
                         "p": str(c.get("period") or "")[:30],
                         "d": _DIRECTION.get(c.get("direction"))})
                # provenance: claim ← filing (sec_edgar = public leaf)
                lin.record_edge("narrative_claim", cid,
                                "edgar_filing", accn, "sec_edgar",
                                transform_version=_PARSER)
        status = "done"
        _journal(db, filing, sections, emitted, dropped,
                 model=model, status=status)
        return {"accession": accn, "status": status,
                "sections": list(sections), "emitted": emitted,
                "dropped": dropped}
    except Exception as exc:
        logger.warning("narrative extract %s %s failed: %s",
                       sym, accn, exc)
        _journal(db, filing, None, 0, 0, status="error")
        return {"accession": accn, "status": "error",
                "error": str(exc)[:200]}


def _num(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _journal(db, filing: dict, sections: Optional[dict],
             emitted: int, dropped: int, model: Optional[str] = None,
             status: str = "done") -> None:
    found = ({s: len(t) for s, t in sections.items()}
             if sections else None)
    db.execute_update(
        "INSERT INTO filing_narratives (accession_number, symbol, cik,"
        " form, report_period, filing_date, sections_found,"
        " claims_emitted, claims_dropped, llm_model, parser_version,"
        " status) VALUES (:a,:s,:c,:f,:rp,:fd,CAST(:sf AS jsonb),"
        " :ce,:cd,:m,:p,:st)"
        " ON CONFLICT (accession_number) DO UPDATE SET"
        " sections_found=CAST(:sf AS jsonb), claims_emitted=:ce,"
        " claims_dropped=:cd, status=:st, extracted_at=now()",
        {"a": filing["accession_number"], "s": filing["symbol"],
         "c": filing.get("cik"), "f": filing.get("form"),
         "rp": str(filing.get("report_period") or "") or None,
         "fd": str(filing.get("filing_date") or "") or None,
         "sf": _json(found) if found else None,
         "ce": emitted, "cd": dropped, "m": model, "p": _PARSER,
         "st": status})


def _json(o) -> Optional[str]:
    import json
    return json.dumps(o) if o is not None else None


def _pending_filings(db, symbols: list[str],
                     per_symbol: int = 2) -> list[dict]:
    """Latest N 10-Q/10-K per symbol not yet extracted. Filings are
    CIK-keyed (the stable identity — tickers get reused); symbols
    resolve to ciks first. Amendments skipped — the base filing's
    text is the narrative source."""
    from app.providers import sec_edgar
    ciks: dict[str, Optional[str]] = {
        s.upper(): sec_edgar.cik_for(s) for s in symbols}
    ciks = {s: c for s, c in ciks.items() if c}
    if not ciks:
        return []
    rows = db.execute_query(
        "SELECT accession_number, cik, form, report_period,"
        " filing_date, primary_document, document_url"
        " FROM edgar_filings"
        " WHERE cik = ANY(:ciks) AND form IN ('10-Q','10-K')"
        "   AND NOT is_amendment"
        "   AND accession_number NOT IN (SELECT accession_number"
        "        FROM filing_narratives WHERE status='done')"
        " ORDER BY cik, filing_date DESC",
        {"ciks": list(ciks.values())})
    sym_for = {c: s for s, c in ciks.items()}
    out: dict[str, list] = {}
    for r in rows:
        r["symbol"] = sym_for.get(r["cik"], r["cik"])
        out.setdefault(r["symbol"], []).append(r)
    return [r for rs in out.values() for r in rs[:per_symbol]]


def run(symbols: Optional[list[str]] = None,
        per_symbol: int = 2) -> dict[str, Any]:
    """Extract pending 10-Q/10-K narratives. Chunked + resumable —
    filing_narratives is the done-set."""
    from app.database import db
    if symbols is None:
        symbols = [r["symbol"] for r in db.execute_query(
            "SELECT DISTINCT symbol FROM income_statements"
            " WHERE data_source='sec_edgar'")]
    filings = _pending_filings(db, symbols, per_symbol)
    results = [extract_filing(db, f) for f in filings]
    return {"symbols": len(symbols), "filings": len(results),
            "done": sum(r["status"] == "done" for r in results),
            "claims": sum(r.get("emitted") or 0 for r in results),
            "dropped": sum(r.get("dropped") or 0 for r in results),
            "errors": [r for r in results if r["status"] == "error"]}
