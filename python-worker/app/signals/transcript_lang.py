"""Management-language layer — the qualitative evidence behind the
capex-cycle numbers.

FMP reports the numbers (revenue, capex). It does NOT report the
language shift that precedes them:

    Q1 "demand exceeds supply"         demand_score +2
    Q3 "disciplined in deployment"     demand_score +0.5 → deteriorating

Sources (in preference order):
    1. FMP earning-call transcripts — if the subscription ever exposes
       them (currently 402 on this plan)
    2. SEC EDGAR 8-K Item 2.02 exhibits — the earnings press releases
       companies actually file: management quotes, guidance language,
       demand/capacity phrasing. Free, authoritative, quarterly cadence.

Design:
- each document is immutable once filed → scored exactly once,
  persisted in transcript_scores keyed (symbol, doc_period)
- per-role lenses: hyperscalers get demand + capex-guidance language;
  equipment names get orders/backlog/cancellation language
- output contract: verbatim quotes required for every claim, null over
  invention, confidence disclosed — same provenance rules as
  ai_research
- aggregate feeds capex_cycle as a 30% blend on the `capex` and
  `equipment` components — language confirms or softens what reported
  numbers imply; it never replaces them

Cadence: refreshed inside the capex fundamentals pass (~weekly);
a new quarter's filing gets scored on the first refresh after it posts.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# hyperscalers → demand + capex-guidance language
# equipment    → orders / backlog / cancellation language
ROLES = {
    "hyperscaler": ["MSFT", "AMZN", "GOOGL", "META", "ORCL"],
    "equipment": ["VRT", "ETN", "CRDO", "ALAB", "ONTO",
                  "NVDA", "AVGO", "MRVL", "MU"],
}
_DOCS_BACK = 4                           # drift needs a QoQ sequence
_SEC_UA = {"User-Agent": "TradingSystem research@tradingsystem.local",
           "Accept-Encoding": "gzip, deflate"}

SYSTEM_ROLE = """You are a forensic earnings analyst reading for EARLY
evidence of an AI/datacenter capex cycle turn. Management changes its
wording quarters before the numbers move.

Score the earnings-release text. Return JSON exactly:

{
  "demand_score": float,        // -2.0 collapsing → +2.0 demand
                                // exceeds supply. Judge WORDS:
                                // "capacity constrained"=+2,
                                // "strong demand"=+1.5,
                                // "healthy demand"=+1,
                                // "normalizing"=+0.5,
                                // "optimizing deployment"=+0 to -0.5,
                                // "digestion"/"moderating"=-1
  "capex_guidance": {
     "direction": "accelerate|flat|decelerate|cut|null",
     "stated": "verbatim phrase or null"
  },
  "orders_language": "accelerating|stable|decelerating|contracting"
                     "|not_mentioned",   // backlog/bookings language
  "key_quotes": ["verbatim quote 1", "verbatim quote 2"],  // <=3, REAL
  "confidence": 0.0-1.0,
  "note": "one line — the tell vs typical management language"
}

RULES:
- quotes must be verbatim from the text; if unsure, omit them
- never invent numbers; no capex language → direction=null
- forward-looking language counts MORE than trailing results
- hedge words matter: "continue to see" < "expect", "monitoring" <
  "committed to"
"""


# ------------------------------------------------------------------
# SEC EDGAR fetch — earnings-release exhibits (Item 2.02 / EX-99.1)
# ------------------------------------------------------------------

def _sec_get(url: str) -> Any:
    import requests
    r = requests.get(url, headers=_SEC_UA, timeout=20)
    if r.status_code != 200:
        return None
    return r.json() if url.endswith(".json") else r.text


def _cik_map() -> dict[str, int]:
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM engine_weights WHERE key='sec:cik_map'")
    if rows:
        return rows[0]["value"] or {}
    data = _sec_get("https://www.sec.gov/files/company_tickers.json")
    out = {v["ticker"].upper(): int(v["cik_str"])
           for v in (data or {}).values()}
    if out:
        db.execute_query(
            "INSERT INTO engine_weights(key, value, updated_at)"
            " VALUES ('sec:cik_map', CAST(:v AS jsonb), now())"
            " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,"
            " updated_at=now()", {"v": json.dumps(out)})
    return out


def _html_text(doc: str) -> str:
    doc = re.sub(r"(?is)<(script|style).*?</\1>", " ", doc)
    doc = re.sub(r"(?s)<[^>]+>", " ", doc)
    doc = re.sub(r"&nbsp;?|&amp;", " ", doc)
    return re.sub(r"\s+", " ", doc).strip()


def _recent_earnings_docs(sym: str, n: int = _DOCS_BACK) -> list[dict]:
    """Latest n earnings-release filings: {period, text}."""
    cik = _cik_map().get(sym.upper())
    if not cik:
        return []
    subs = _sec_get(
        f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    recent = (((subs or {}).get("filings") or {}).get("recent")) or {}
    forms = recent.get("form") or []
    items = recent.get("items") or []
    accs = recent.get("accessionNumber") or []
    dates = recent.get("reportDate") or recent.get("filingDate") or []
    hits = []
    for i, f in enumerate(forms):
        if f != "8-K" or i >= len(accs):
            continue
        it = str(items[i] if i < len(items) else "")
        if "2.02" not in it and "2.02" not in it.replace(" ", ""):
            continue                            # earnings-release 8-Ks
        hits.append({"acc": accs[i].replace("-", ""),
                     "date": str(dates[i])[:10]})
        if len(hits) >= n + 1:
            break
    docs = []
    for h in hits[:n]:
        idx = _sec_get(
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{h['acc']}/index.json")
        names = [it["name"] for it in
                 ((idx or {}).get("directory") or {})
                 .get("item") or []]
        # prefer the exhibit (EX-99.1 = the press release), else the
        # largest .htm document
        cands = [nm for nm in names if nm.lower().endswith(".htm")]
        ex = [nm for nm in cands if re.search(r"(ex|x)99|press|earn|release",
                                             nm, re.I)]
        target = (ex or cands or [None])[0]
        if not target:
            continue
        raw = _sec_get(f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                       f"{h['acc']}/{target}")
        if not raw:
            continue
        text = _html_text(str(raw))
        if len(text) < 1500:
            continue
        d = h["date"]
        q = (int(d[5:7]) - 1) // 3 + 1          # quarter of report date
        docs.append({"period": f"{d[:4]}Q{q}", "text": text})
    return docs


def _fmp_transcript_docs(sym: str, n: int) -> list[dict]:
    """FMP transcripts — currently 402 on this plan; kept so an upgrade
    lights the path with zero code change."""
    try:
        from app.providers.financial_modeling_prep.client import (
            EnhancedFMPClient)
        c = EnhancedFMPClient.from_settings()
        dates = c.get_transcript_dates_by_symbol(sym) or []
    except Exception:
        return []
    out = []
    for d in sorted(dates, key=lambda x: (x.get("year", 0),
                                          x.get("quarter", 0)))[-n:]:
        try:
            t = c.get_earning_transcript(sym, year=int(d["year"]),
                                         quarter=int(d["quarter"])) or []
            text = (t[0].get("content") if isinstance(t, list) and t
                    else (t or {}).get("content")) or ""
            if len(text) > 2000:
                out.append({"period": f"{d['year']}Q{d['quarter']}",
                            "text": text, "source": "fmp_transcript"})
        except Exception:
            continue
    return out


def _docs(sym: str, n: int) -> list[dict]:
    docs = _fmp_transcript_docs(sym, n)
    if docs:
        return docs
    return [{**d, "source": "sec_8k"}
            for d in _recent_earnings_docs(sym, n)]


def _slice(text: str, limit: int = 16000) -> str:
    """Keep the front matter + keyword neighborhoods where the tell
    lives — full docs run 20-80k chars."""
    if len(text) <= limit:
        return text
    head = text[:8000]
    windows = []
    for kw in ("capital expenditure", "capex", "backlog", "bookings",
               "orders", "capacity constrained", "demand",
               "guidance", "deployment", "outlook"):
        for m in re.finditer(re.escape(kw), text.lower()):
            windows.append((max(0, m.start() - 600), m.start() + 900))
            if len(windows) > 12:
                break
    windows.sort()
    merged, cur = [], None
    for a, b in windows:
        if cur and a <= cur[1]:
            cur = (cur[0], max(cur[1], b))
        else:
            if cur:
                merged.append(cur)
            cur = (a, b)
    if cur:
        merged.append(cur)
    tail = "\n[...]\n".join(text[a:b] for a, b in merged)
    return (head + "\n[...]\n" + tail)[:limit]


def _score_llm(sym: str, role: str, period: str, text: str) -> dict | None:
    from litellm import completion
    lens = ("demand trajectory + capex guidance" if role == "hyperscaler"
            else "orders/backlog/cancellation language + demand tone")
    user = {"task": f"Score the {period} earnings release for {sym}. "
                    f"Lens: {lens}. Return the JSON schema exactly.",
            "document": text}
    try:
        resp = completion(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_ROLE},
                      {"role": "user", "content": json.dumps(user)}],
            temperature=0.1, max_tokens=700,
            response_format={"type": "json_object"})
        raw = re.sub(r"^```(?:json)?|```$", "",
                     (resp.choices[0].message.content or "").strip())
        return json.loads(raw)
    except Exception as exc:
        logger.warning("language LLM %s %s: %s", sym, period, exc)
        return None


def _scored_periods() -> set[tuple]:
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, doc_period FROM transcript_scores")
    return {(r["symbol"], r["doc_period"]) for r in rows}


def _persist(sym: str, role: str, period: str, source: str, res: dict):
    from app.database import db
    db.execute_query(
        "INSERT INTO transcript_scores"
        " (symbol, doc_period, role, source, demand_score, capex_dir,"
        "  orders_language, key_quotes, confidence, note, model)"
        " VALUES (:s,:p,:r,:src,:d,:c,:o,CAST(:k AS jsonb),:cf,:n,:m)"
        " ON CONFLICT (symbol, doc_period) DO NOTHING",
        {"s": sym, "p": period, "r": role, "src": source,
         "d": res.get("demand_score"),
         "c": (res.get("capex_guidance") or {}).get("direction"),
         "o": res.get("orders_language"),
         "k": json.dumps(res.get("key_quotes") or []),
         "cf": res.get("confidence"),
         "n": (res.get("note") or "")[:300],
         "m": "gpt-4o-mini"})


def _load_scores() -> dict[str, list[dict]]:
    """Per-symbol scored periods, oldest→newest."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, doc_period, demand_score, capex_dir,"
        " orders_language, key_quotes, confidence, note, source"
        " FROM transcript_scores"
        " ORDER BY symbol, doc_period")
    out: dict[str, list] = {}
    for r in rows:
        r = dict(r)
        for k in ("demand_score", "confidence"):
            if r.get(k) is not None:
                r[k] = float(r[k])
        if isinstance(r.get("key_quotes"), str):
            try:
                r["key_quotes"] = json.loads(r["key_quotes"])
            except Exception:
                r["key_quotes"] = []
        out.setdefault(r["symbol"], []).append(r)
    return out


def _to_slowdown(role: str, rows: list[dict]) -> float | None:
    """Latest-period language → 0-100 slowdown score for the role's
    component. QoQ drift adjusts ±10."""
    if not rows:
        return None
    latest = rows[-1]
    ds = latest.get("demand_score")
    if ds is None:
        return None
    base = max(0.0, min(100.0, (2.0 - float(ds)) * 22.5))  # +2→0, -2→90
    if role == "hyperscaler":
        base += {"accelerate": -10, "flat": 0,
                 "decelerate": 12, "cut": 25}.get(
                     latest.get("capex_dir") or "", 0)
    else:
        base += {"accelerating": -12, "stable": 0,
                 "decelerating": 14, "contracting": 28}.get(
                     latest.get("orders_language") or "", 0)
    if len(rows) >= 2 and rows[-2].get("demand_score") is not None:
        drift = float(rows[-1]["demand_score"]) - float(
            rows[-2]["demand_score"])
        base += max(-10, min(10, -drift * 8))   # language worsening ↑
    return round(max(0.0, min(100.0, base)), 1)


def refresh(limit_new: int = 14) -> dict[str, Any]:
    """Score unscored docs (incremental) → transcript_scores +
    engine_weights['capex:language']. First run scores the last
    _DOCS_BACK quarters per watch symbol."""
    done = _scored_periods()
    scored = 0
    for role, syms in ROLES.items():
        for sym in syms:
            if scored >= limit_new:
                break
            try:
                docs = _docs(sym, _DOCS_BACK)
            except Exception as exc:
                logger.debug("docs %s: %s", sym, exc)
                continue
            for d in docs:
                if (sym, d["period"]) in done or scored >= limit_new:
                    continue
                res = _score_llm(sym, role, d["period"],
                                 _slice(d["text"]))
                if res:
                    _persist(sym, role, d["period"],
                             d.get("source", "?"), res)
                    scored += 1
    scores = _load_scores()
    per_symbol = {}
    for sym, rows in scores.items():
        role = ("hyperscaler" if sym in ROLES["hyperscaler"]
                else "equipment")
        per_symbol[sym] = {
            "role": role, "slowdown": _to_slowdown(role, rows),
            "demand_score": rows[-1].get("demand_score"),
            "demand_prev": (rows[-2].get("demand_score")
                            if len(rows) > 1 else None),
            "capex_dir": rows[-1].get("capex_dir"),
            "orders_language": rows[-1].get("orders_language"),
            "period": rows[-1]["doc_period"],
            "source": rows[-1].get("source"),
            "quotes": rows[-1].get("key_quotes") or [],
            "note": rows[-1].get("note")}
    out = {"per_symbol": per_symbol, "scored_new": scored,
           "as_of": date.today().isoformat()}
    from app.database import db
    db.execute_query(
        "INSERT INTO engine_weights(key, value, updated_at)"
        " VALUES ('capex:language', CAST(:v AS jsonb), now())"
        " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,"
        " updated_at=now()", {"v": json.dumps(out)})
    return out


def language_map() -> dict[str, dict]:
    """sym → {slowdown, demand_score, ...} for component blending."""
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM engine_weights WHERE key='capex:language'")
    return (rows[0]["value"] or {}).get("per_symbol") or {} \
        if rows else {}
