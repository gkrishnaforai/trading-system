"""Focus book intelligence — per-symbol development tracking for the
conviction bucket (focus_members).

The generic board only surfaces a name when today's screens bless it.
The focus book watches its members on their own merits: press/news for
contracts, design wins, product/roadmap and capacity events, analyst
grade + price-target moves, and SEC filings (8-Ks carry material
agreements by law). Each item is classified deterministically into an
event_type with a 1-5 materiality score — 4-5 = move-thesis events the
user should see the same day.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --- deterministic materiality taxonomy --------------------------------------
# (event_type, [patterns], materiality) — first strongest match wins
_BULL: list[tuple[str, list[str], int]] = [
    ("contract",    [r"contract", r"\baward", r"selected", r"design[- ]win",
                     r"purchase order", r"\bPO\b", r"supply agreement",
                     r"deployment", r"secures?", r"\bwins?\b"], 5),
    ("backlog",     [r"backlog", r"record orders?", r"bookings?", r"\bRPO\b",
                     r"remaining performance"], 5),
    ("guidance",    [r"rais\w* (?:its )?(?:\w+ )?guidance",
                     r"guidance (?:raised|above|boost|strong)",
                     r"prelim\w*", r"above (?:prior |previous )?guidance"], 5),
    ("product",     [r"launch", r"introduc", r"unveil", r"sampl(?:e|ing)",
                     r"production ramp", r"volume production",
                     r"mass production", r"new product", r"general availab"],
                    4),
    ("partnership", [r"partner\w*", r"collaborat", r"ecosystem",
                     r"joint develop"], 4),
    ("capacity",    [r"capacity", r"expansion", r"new facility", r"fab\b",
                     r"capex", r"manufacturing"], 3),
    ("ai_infra",    [r"hyperscaler", r"\bAI\b", r"cluster", r"data ?cent",
                     r"nvidia", r"1\.6 ?T", r"800 ?G", r"\bCPO\b",
                     r"co-?packaged", r"retimer", r"\bAEC\b", r"\bDSP\b",
                     r"\bCXL\b", r"PCIe", r"optical", r"connectivity"], 3),
]
_BEAR = [r"downgrade", r"lowers?", r"cut(?:s|ting)?", r"miss(?:es|ed)?",
         r"delay", r"cancel", r"lawsuit", r"probe", r"resign", r"depart",
         r"weak guidance", r"loss of", r"loses", r"inventory correction",
         r"push-?out"]
_HI_RE = [(t, [re.compile(p, re.I) for p in pats], m) for t, pats, m in _BULL]
_NEG_RE = [re.compile(p, re.I) for p in _BEAR]


def _classify(title: str, text: str = "") -> tuple[str, int, str]:
    """→ (event_type, materiality, direction). Deterministic keywords."""
    hay = f"{title} {text or ''}"
    neg = any(p.search(hay) for p in _NEG_RE)
    best_type, best_mat = "other", 1
    for t, pats, m in _HI_RE:
        if any(p.search(hay) for p in pats):
            best_type, best_mat = t, m
            break
    if neg and best_mat < 5:
        return "risk", 4, "NEG"
    return best_type, best_mat, ("NEG" if neg else "POS")


def _eid(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:24]


def _ts(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def members() -> list[str]:
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol FROM focus_members WHERE active ORDER BY symbol")
    return [r["symbol"] for r in rows]


def _insert(ev: dict) -> bool:
    """INSERT ... ON CONFLICT DO NOTHING → True when new."""
    from app.database import db
    n = db.execute_query(
        "INSERT INTO focus_events "
        "(symbol, source, external_id, event_type, materiality, title,"
        " summary, url, published_at, raw) "
        "VALUES (:sym,:src,:eid,:etype,:mat,:title,:summary,:url,:pub,"
        " CAST(:raw AS jsonb)) "
        "ON CONFLICT (symbol, source, external_id) DO NOTHING "
        "RETURNING id",
        {"sym": ev["symbol"], "src": ev["source"], "eid": ev["eid"],
         "etype": ev["event_type"], "mat": ev["materiality"],
         "title": ev["title"][:600], "summary": (ev.get("summary") or "")[:900],
         "url": ev.get("url"), "pub": ev.get("published_at"),
         "raw": __import__("json").dumps(ev.get("raw") or {})})
    return bool(n)


# --- collectors ---------------------------------------------------------------

# content-mill publishers — commentary, not company developments;
# cap their materiality so "Why Zacks Rank #1..." never reads as an event
_COMMENTARY = {"zacks.com", "fool.com", "simplywall.st", "insidermonkey.com",
               "seekingalpha.com", "247wallst.com", "investorplace.com"}


def _collect_news(fmp, sym: str) -> list[dict]:
    out = []
    for n in (fmp.search_stock_news(sym) or []):
        title, text = n.get("title") or "", (n.get("text") or "")[:400]
        etype, mat, direc = _classify(title, text)
        if (n.get("site") or "").lower() in _COMMENTARY:
            mat = min(mat, 2)
            if etype == "risk":
                etype, direc = "other", "POS"
        out.append({
            "symbol": sym, "source": "news",
            "eid": _eid(sym, "news", n.get("url") or _eid(title,
                        n.get("publishedDate"))),
            "event_type": etype, "materiality": mat,
            "title": title, "summary": text, "url": n.get("url"),
            "published_at": _ts(n.get("publishedDate")),
            "raw": {"publisher": n.get("publisher"), "dir": direc}})
    return out


def _collect_grades(fmp, sym: str) -> list[dict]:
    out = []
    for g in (fmp.get_grades_news(sym) or []):
        title = g.get("newsTitle") or f"{g.get('gradingCompany')}: " \
            f"{g.get('previousGrade')} → {g.get('newGrade')}"
        t = title.lower()
        if "downgrade" in t or "lowered" in t or "cut" in t:
            etype, mat = "analyst_down", 4
        elif "upgrade" in t or "raised" in t or "initiat" in t:
            etype, mat = "analyst_up", 3
        else:
            etype, mat = "analyst", 2
        out.append({
            "symbol": sym, "source": "grade",
            "eid": _eid(sym, "grade", g.get("newsURL") or _eid(
                title, g.get("publishedDate"))),
            "event_type": etype, "materiality": mat, "title": title,
            "summary": f"{g.get('gradingCompany')}: "
                       f"{g.get('previousGrade')} → {g.get('newGrade')}",
            "url": g.get("newsURL"),
            "published_at": _ts(g.get("publishedDate")),
            "raw": g})
    return out


def _collect_pt(fmp, sym: str) -> list[dict]:
    out = []
    for p in (fmp.get_price_target_news(sym) or []):
        title = p.get("newsTitle") or \
            f"{p.get('analystName')}: PT ${p.get('priceTarget')}"
        t = title.lower()
        etype = "pt_cut" if ("lower" in t or "cut" in t) else "pt_raise"
        out.append({
            "symbol": sym, "source": "price_target",
            "eid": _eid(sym, "pt", p.get("newsURL") or _eid(
                title, p.get("publishedDate"))),
            "event_type": etype, "materiality": 3 if etype == "pt_cut" else 2,
            "title": title,
            "summary": f"PT ${p.get('priceTarget')} "
                       f"(px ${p.get('priceWhenPosted')})",
            "url": p.get("newsURL"),
            "published_at": _ts(p.get("publishedDate")), "raw": p})
    return out


_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBM_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# SEC rejects bot-looking agents — needs a real contact format
_UA = {"User-Agent": "ResearchAgent/1.0 contact@example.com"}
_FORMS = {"8-K": 4, "8-K/A": 4, "10-Q": 3, "10-K": 3, "SC 13D": 4,
          "SC 13D/A": 4, "SC 13G": 2, "SC 13G/A": 2}
_cik_cache: dict[str, int] = {}


def _edgar_cik(sym: str) -> Optional[int]:
    if not _cik_cache:
        try:
            import requests
            rows = requests.get(_TICKERS_URL, headers=_UA, timeout=20).json()
            for v in rows.values():
                _cik_cache[str(v["ticker"]).upper()] = int(v["cik_str"])
        except Exception as exc:
            logger.debug("edgar tickers: %s", exc)
    return _cik_cache.get(sym)


def _collect_filings(sym: str, days: int = 21) -> list[dict]:
    cik = _edgar_cik(sym)
    if not cik:
        return []
    try:
        import requests
        sub = requests.get(_SUBM_URL.format(cik=cik), headers=_UA,
                           timeout=20).json()
    except Exception as exc:
        logger.debug("edgar submissions %s: %s", sym, exc)
        return []
    rec = (sub.get("filings") or {}).get("recent") or {}
    forms, dates, accs = (rec.get("form") or [], rec.get("filingDate") or [],
                          rec.get("accessionNumber") or [])
    docs, descs = (rec.get("primaryDocument") or [],
                   rec.get("primaryDocDescription") or [])
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    out = []
    for i, form in enumerate(forms):
        try:
            fd = datetime.fromisoformat(str(dates[i])).date()
        except Exception:
            continue
        if fd < cutoff or form not in _FORMS:
            continue
        acc = (accs[i] if i < len(accs) else "").replace("-", "")
        doc = docs[i] if i < len(docs) else ""
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
               if acc and doc else None)
        desc = descs[i] if i < len(descs) else ""
        out.append({
            "symbol": sym, "source": "sec_filing",
            "eid": acc or _eid(sym, form, str(fd)),
            "event_type": "filing_8k" if form.startswith("8-K") else
                          ("holder_13d" if "13D" in form else "filing"),
            "materiality": _FORMS[form],
            "title": f"{form} filed {fd} — {desc or 'SEC submission'}",
            "summary": desc, "url": url,
            "published_at": datetime(fd.year, fd.month, fd.day,
                                     tzinfo=timezone.utc),
            "raw": {"form": form, "acc": accs[i] if i < len(accs) else None}})
    return out


# --- scan ---------------------------------------------------------------------

def scan_symbol(sym: str, fmp=None) -> dict:
    if fmp is None:
        from app.providers.financial_modeling_prep.client import (
            EnhancedFMPClient)
        fmp = EnhancedFMPClient.from_settings()
    sym = sym.upper().strip()
    events: list[dict] = []
    for fn in (_collect_news, _collect_grades, _collect_pt):
        try:
            events += fn(fmp, sym)
        except Exception as exc:
            logger.debug("focus %s %s: %s", sym, fn.__name__, exc)
    try:
        events += _collect_filings(sym)
    except Exception as exc:
        logger.debug("focus filings %s: %s", sym, exc)
    new = sum(1 for e in events if _insert(e))
    return {"symbol": sym, "seen": len(events), "new": new}


def scan_all(symbols: list[str] = None) -> dict:
    from app.providers.financial_modeling_prep.client import (
        EnhancedFMPClient)
    fmp = EnhancedFMPClient.from_settings()
    syms = symbols or members()
    per = [scan_symbol(s, fmp) for s in syms]
    return {"symbols": len(syms), "seen": sum(p["seen"] for p in per),
            "new": sum(p["new"] for p in per), "per_symbol": per}


# --- board read-out -----------------------------------------------------------

def recent_events(days: int = 5, min_mat: int = 3) -> list[dict]:
    from app.database import db
    return db.execute_query(
        "SELECT symbol, source, event_type, materiality, title, summary,"
        " url, published_at::text AS published_at "
        "FROM focus_events "
        "WHERE published_at >= now() - (:d || ' days')::interval"
        "  AND materiality >= :m "
        "ORDER BY published_at DESC, materiality DESC LIMIT 40",
        {"d": days, "m": min_mat})


def fresh_boosts(hours: int = 72) -> dict[str, dict]:
    """symbol → strongest fresh (≤hours) material event — board boost."""
    from app.database import db
    rows = db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, event_type, materiality,"
        " title, published_at::text AS published_at "
        "FROM focus_events "
        "WHERE published_at >= now() - (:h || ' hours')::interval"
        "  AND event_type NOT LIKE 'pt%' "
        "  AND event_type NOT IN ('analyst','other','filing') "
        "ORDER BY symbol, materiality DESC, published_at DESC",
        {"h": hours})
    return {r["symbol"]: r for r in rows}
