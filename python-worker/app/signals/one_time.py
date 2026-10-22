"""One-time charge detection — the 'was the miss real' pass.

Earnings releases bury non-recurring items in expense tables and
bullet highlights: 'includes $2.40 billion of charges related to
legal proceedings' (META Q2-26), severance, settlements, impairments,
restructuring. A headline EPS miss built on one-time charges is not
business deterioration — adjusted EPS (reported + charges net of tax)
tells the market's actual read.

Deterministic regex over the release text — same contract as
doc_extract's revision scan: verbatim quote carried with every item,
no LLM, arithmetic only. Detected items + adjusted EPS persist on the
earnings_data row; the raw eps_actual is never rewritten.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MONEY = r"\$?\s*([\d.,]+)\s*([BbMm](?:illion)?)?"
_KINDS = [
    (r"legal|litigation|settlement", "legal"),
    (r"severance|headcount|layoff|workforce", "severance"),
    (r"restructur", "restructuring"),
    (r"impair|write[- ]?down|write[- ]?off|goodwill", "impairment"),
    (r"one[- ]?time|non[- ]?recurring", "one_time"),
]
# '$2.40 billion of charges related to legal proceedings'
_RE_MONEY_FIRST = re.compile(
    _MONEY + r"\s+of\s+([^.]{0,70}?"
    r"(?:charge|severance|settlement|impair|restructur|legal"
    r"|litigation|write[- ]?(?:down|off)|expense)s?)", re.I)
# 'a legal/settlement charge of $2.4 billion'
_RE_KIND_FIRST = re.compile(
    r"((?:legal|severance|restructur\w*|impair\w*|litigation|"
    r"one[- ]?time)[^.]{0,50}?"
    r"(?:charge|expense|cost|settlement|payment)s?)\s+(?:of\s+)?"
    + _MONEY, re.I)
_TAX_RE = re.compile(r"effective tax rate[^\d]{0,20}(\d+(?:\.\d+)?)\s*%", re.I)
_SHARES_RE = re.compile(r"Diluted\s+([\d,]+)", re.I)


def _num(num: str, unit: str) -> Optional[float]:
    try:
        v = float(num.replace(",", ""))
    except (ValueError, AttributeError):
        return None
    u = (unit or "").lower()
    if u.startswith("b"):
        v *= 1e9
    elif u.startswith("m") or not u:
        # bare table numbers in releases are typically thousands or
        # unitless — only trust scaled ones for charge items
        if not u:
            return None
        v *= 1e6
    return v


def _kind(sent: str) -> Optional[str]:
    sl = sent.lower()
    for pat, k in _KINDS:
        if re.search(pat, sl):
            return k
    return None


def scan_items(text: str) -> list[dict]:
    """Sentences disclosing a one-time charge amount → items with the
    verbatim quote. A single sentence can carry several charges
    ('$2.4B legal and $1.18B severance') — find every amount; the
    kind comes from each match's own descriptor. Dedupes on
    (kind, amount)."""
    out, seen = [], set()
    for sent in re.split(r"(?<=\.)\s+", text):
        s = re.sub(r"\s+", " ", sent).strip()
        if not _kind(s):
            continue
        for rx, gi, di in ((_RE_MONEY_FIRST, 1, 3),
                           (_RE_KIND_FIRST, 2, 1)):
            for m in rx.finditer(s):
                amt = _num(m.group(gi), m.group(gi + 1))
                if amt is None or amt < 25e6:   # material items only
                    continue
                kind = _kind(m.group(di)) or _kind(s)
                key = (kind, round(amt))
                if key in seen:
                    continue
                seen.add(key)
                out.append({"type": kind, "amount": amt,
                            "quote": s[:400]})
    return out


def _tax_rate(text: str) -> float:
    m = _TAX_RE.search(text)
    if m:
        try:
            r = float(m.group(1)) / 100.0
            if 0.0 < r < 0.6:
                return r
        except ValueError:
            pass
    return 0.15


def _diluted_shares(text: str, sym: str) -> Optional[float]:
    m = _SHARES_RE.search(text)
    if m:
        try:
            return float(m.group(1).replace(",", "")) * 1e6
        except ValueError:
            pass
    try:
        from app.database import db
        r = db.execute_query(
            "SELECT payload->'fundamentals'->>'shares_outstanding' sh"
            " FROM stock_insights_snapshots"
            " WHERE stock_symbol=:s AND source='fmp_fundamentals'"
            " ORDER BY generated_at DESC LIMIT 1", {"s": sym})
        if r and r[0].get("sh"):
            return float(r[0]["sh"])
    except Exception:
        pass
    return None


def _release_text(sym: str, earnings_date: date, days: int = 10) -> Optional[dict]:
    """The 8-K release nearest the print date."""
    from app.providers import sec_edgar
    try:
        rels = sec_edgar.recent_8k_releases(sym, days=days)
    except Exception as exc:
        logger.debug("one_time edgar %s: %s", sym, exc)
        return None
    if not rels:
        return None
    def _d(r):
        f = r.get("filed")
        try:
            fd = f.date() if hasattr(f, "date") else date.fromisoformat(str(f)[:10])
        except Exception:
            return 999
        return abs((fd - earnings_date).days)
    return min(rels, key=_d)


def apply(sym: str, earnings_date: date,
          days: int = 10) -> dict[str, Any]:
    """Detect one-time items for a print, compute adjusted EPS, persist
    to earnings_data. Returns {} when there's nothing to annotate."""
    from app.database import db
    sym = sym.upper()
    pr = db.execute_query(
        "SELECT eps_estimate, eps_actual FROM earnings_data"
        " WHERE stock_symbol=:s AND earnings_date=:d",
        {"s": sym, "d": earnings_date})
    if not pr or pr[0].get("eps_actual") is None:
        return {}
    eps_actual, eps_est = float(pr[0]["eps_actual"]), pr[0].get("eps_estimate")
    rel = _release_text(sym, earnings_date, days=days)
    if not rel or not rel.get("text"):
        return {}
    items = scan_items(rel["text"])
    if not items:
        return {}
    shares = _diluted_shares(rel["text"], sym)
    if not shares:
        return {"items": items, "note": "no share count — unadjusted"}
    tax = _tax_rate(rel["text"])
    charges = sum(i["amount"] for i in items)
    adj = float(eps_actual) + charges * (1.0 - tax) / shares
    adj_surp = ((adj - float(eps_est)) / float(eps_est) * 100.0
                if eps_est else None)
    db.execute_update(
        "UPDATE earnings_data SET one_time_items=:it,"
        " adjusted_eps_actual=:a, updated_at=now()"
        " WHERE stock_symbol=:s AND earnings_date=:d",
        {"s": sym, "d": earnings_date,
         "it": json.dumps(items, default=str),
         "a": round(adj, 4)})
    return {"items": items, "charges": charges, "tax_rate": tax,
            "shares": shares, "adjusted_eps": round(adj, 4),
            "adjusted_surprise": (round(adj_surp, 2)
                                  if adj_surp is not None else None)}
