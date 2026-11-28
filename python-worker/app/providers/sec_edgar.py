"""SEC EDGAR provider — free, authoritative US-filings data.

Three reads we need:
  company_tickers.json  ticker → CIK (cached in-process for the run)
  companyfacts          all XBRL facts ever filed (RPO, goodwill,
                        acquisition cash, share counts — things FMP
                        doesn't carry)
  submissions           recent filing index → 8-K exhibit documents

Fair-use: SEC asks for a declared User-Agent and ≤10 req/s. We send a
project UA and self-throttle to ~4 req/s — this job is patient, not
fast. Everything here is read-only public data; no auth.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

import os

# SEC rejects UAs with placeholder contacts (admin@localhost → 403)
# — the address doesn't need to be yours, but it must parse like one.
_UA = os.getenv("SEC_USER_AGENT",
                "OspreyDesk/1.0 research@ospreydesk.dev")
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_DOC_URL = ("https://www.sec.gov/Archives/edgar/data/{cik}/"
            "{acc_nodash}/{name}")

_session = requests.Session()
_session.headers.update({"User-Agent": _UA,
                         "Accept-Encoding": "gzip, deflate"})

_lock = threading.Lock()
_last_req = 0.0
_MIN_GAP = 0.25                    # ~4 req/s, well under the 10/s cap

_cik_cache: dict[str, str] = {}


def _get(url: str, timeout: int = 30) -> Optional[requests.Response]:
    global _last_req
    with _lock:
        wait = _MIN_GAP - (time.monotonic() - _last_req)
        if wait > 0:
            time.sleep(wait)
        _last_req = time.monotonic()
    try:
        r = _session.get(url, timeout=timeout)
        if r.status_code == 200:
            return r
        logger.debug("edgar %s → %s", url, r.status_code)
    except Exception as exc:
        logger.debug("edgar %s failed: %s", url, exc)
    return None


def cik_for(symbol: str) -> Optional[str]:
    """Ticker → zero-padded 10-digit CIK. The ticker map is ~2MB and
    changes rarely — one fetch per process."""
    sym = symbol.upper().strip()
    if sym in _cik_cache:
        return _cik_cache[sym]
    if not _cik_cache:
        r = _get(_TICKERS_URL, timeout=60)
        if not r:
            return None
        try:
            for row in r.json().values():
                t = str(row.get("ticker") or "").upper()
                cik = str(row.get("cik_str") or "").zfill(10)
                if t and cik:
                    _cik_cache[t] = cik
        except Exception as exc:
            logger.debug("edgar ticker map parse: %s", exc)
            return None
    return _cik_cache.get(sym)


def company_facts(symbol: str) -> Optional[dict]:
    """Full XBRL companyfacts blob (us-gaap + dei namespaces)."""
    cik = cik_for(symbol)
    if not cik:
        return None
    r = _get(_FACTS_URL.format(cik=cik), timeout=60)
    try:
        return r.json() if r else None
    except Exception:
        return None


def submissions(symbol: str, include_older: bool = False) -> Optional[dict]:
    """Full filings index for one issuer — the event log the spine
    keys off. Returns {cik, events: [...]} where each event carries
    accession, form, filing/acceptance dates, report period, primary
    doc and items. include_older pulls the paginated `filings.files`
    chunks for issuers whose `recent` (>1000 rows) doesn't reach back
    far enough — almost every filer's 2y window lives in `recent`."""
    cik = cik_for(symbol)
    if not cik:
        return None
    r = _get(_SUBS_URL.format(cik=cik), timeout=60)
    if not r:
        return None
    try:
        subs = r.json()
    except Exception:
        return None
    events: list[dict] = []

    def _emit(block: dict) -> None:
        forms = block.get("form", [])
        accs = block.get("accessionNumber", [])
        fdates = block.get("filingDate", [])
        adts = block.get("acceptanceDateTime", [])
        rdates = block.get("reportDate", [])
        pdocs = block.get("primaryDocument", [])
        items_l = block.get("items", [])
        for i, form in enumerate(forms):
            acc = str(accs[i]) if i < len(accs) else None
            if not acc:
                continue
            events.append({
                "accession_number": acc,
                "form": form,
                "filing_date": fdates[i] if i < len(fdates) else None,
                "acceptance_datetime": adts[i] if i < len(adts) else None,
                "report_period": rdates[i] if i < len(rdates) else None,
                "primary_document": (pdocs[i] if i < len(pdocs) else None),
                "items": items_l[i] if i < len(items_l) else None,
            })

    filings = subs.get("filings", {})
    _emit(filings.get("recent", {}) or {})
    if include_older:
        for f in filings.get("files", []) or []:
            name = f.get("name")
            if not name:
                continue
            fr = _get(f"https://data.sec.gov/submissions/{name}",
                      timeout=60)
            if fr:
                try:
                    _emit(fr.json())
                except Exception:
                    pass
    # entity-level identity — SIC is the cohort key for Phase D
    entity = {"name": subs.get("name"),
              "sic": subs.get("sic"),
              "sic_description": subs.get("sicDescription"),
              "fy_end": subs.get("fiscalYearEnd"),
              "entity_type": subs.get("entityType")}
    return {"cik": cik, "events": events, "entity": entity}


def _extract_text(html: str) -> str:
    """Filing HTML → readable text. Inline-XBRL tags carry the facts
    as attributes; we want the visible prose."""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
               flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&#8217;", "'").replace("&rsquo;", "'")
          .replace("&#8220;", '"').replace("&#8221;", '"')
          .replace("&ldquo;", '"').replace("&rdquo;", '"')
          .replace("&mdash;", "—").replace("&ndash;", "–"))
    return re.sub(r"\s+", " ", t).strip()


def recent_8k_releases(symbol: str, days: int = 120,
                       max_filings: int = 3) -> list[dict]:
    """Recent 8-K filings carrying item 2.02 (results of operations) —
    the earnings-release event. Returns [{accession, filed, url, text}]
    with the EX-99 press-release text extracted where findable."""
    cik = cik_for(symbol)
    if not cik:
        return []
    r = _get(_SUBS_URL.format(cik=cik))
    if not r:
        return []
    try:
        subs = r.json()
        recent = subs.get("filings", {}).get("recent", {})
    except Exception:
        return []
    forms = recent.get("form", [])
    items = recent.get("items", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])

    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=days)
    out: list[dict] = []
    for i, form in enumerate(forms):
        if len(out) >= max_filings:
            break
        if form != "8-K" or "2.02" not in str(items[i] if i < len(items)
                                            else ""):
            continue
        try:
            filed = date.fromisoformat(str(dates[i]))
        except Exception:
            continue
        if filed < cutoff:
            continue
        acc = str(accs[i]).replace("-", "")
        # the 8-K's filing index lists EX-99.1 (the actual press
        # release); fall back to the primary doc when the index
        # doesn't surface it
        idx_r = _get(_DOC_URL.format(cik=str(int(cik)), acc_nodash=acc,
                                   name="index.json"))
        exhibit = None
        primary = docs[i] if i < len(docs) else None
        if idx_r:
            try:
                # the EX-99 press release is the largest .htm in the
                # filing — excluding R*.htm (XBRL report renders),
                # index files, and the 8-K cover (primary doc)
                cands = []
                for it in idx_r.json()["directory"]["item"]:
                    n = str(it.get("name") or "")
                    if (n.endswith(".htm") and n != primary
                            and not re.match(r"R\d+\.htm", n)
                            and "index" not in n):
                        cands.append((int(it.get("size") or 0), n))
                if cands:
                    exhibit = max(cands)[1]
            except Exception:
                pass
        doc = exhibit or primary
        if not doc:
            continue
        doc_r = _get(_DOC_URL.format(cik=str(int(cik)), acc_nodash=acc,
                                     name=doc), timeout=60)
        if not doc_r:
            continue
        text = _extract_text(doc_r.text)
        if len(text) < 500:
            continue
        out.append({"accession": str(accs[i]),
                    "filed": str(filed),
                    "url": _DOC_URL.format(cik=str(int(cik)),
                                           acc_nodash=acc, name=doc),
                    "text": text})
    return out


def filing_document(cik: str, accession: str,
                    primary_doc: str) -> Optional[str]:
    """Fetch one filing's primary document → extracted text.
    MD&A / Risk Factors live in the filing body, not XBRL exhibits."""
    if not cik or not accession or not primary_doc:
        return None
    r = _get(_DOC_URL.format(cik=str(int(cik)),
                             acc_nodash=str(accession).replace("-", ""),
                             name=primary_doc),
             timeout=60)
    if not r:
        return None
    return _extract_text(r.text)


def recent_filings(symbol: str, forms: tuple = ("10-Q", "10-K"),
                   days: int = 45, max_filings: int = 5) -> list[dict]:
    """Recent filings of given forms — [{accession, form, filed,
    period_end}] — metadata only, no doc fetch. The completion
    reconciler uses this to detect when a 10-Q/10-K covering a
    reported quarter has landed on EDGAR."""
    from datetime import date, timedelta
    cik = cik_for(symbol)
    if not cik:
        return []
    r = _get(_SUBS_URL.format(cik=cik))
    if not r:
        return []
    try:
        recent = r.json().get("filings", {}).get("recent", {})
    except Exception:
        return []
    forms_l = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    periods = recent.get("reportDate", [])
    cutoff = date.today() - timedelta(days=days)
    out: list[dict] = []
    for i, form in enumerate(forms_l):
        if len(out) >= max_filings:
            break
        if form not in forms:
            continue
        try:
            filed = date.fromisoformat(str(dates[i]))
        except Exception:
            continue
        if filed < cutoff:
            continue
        out.append({"accession": str(accs[i]) if i < len(accs) else None,
                    "form": form, "filed": str(filed),
                    "period_end": (str(periods[i])
                                   if i < len(periods) else None)})
    return out
