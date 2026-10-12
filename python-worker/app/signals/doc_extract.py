"""Curated-document extraction — user pastes an article/note, the LLM
answers a fixed question set, deterministic validation decides what
lands. Never scores, never recommends — claims only.

The six questions:
  Q1 channel claims   → tailwinds journal (existing machinery)
  Q2 mechanism        → returned + stored in doc_analyses
  Q3 numbered facts   → cross-checked vs stored fundamentals
  Q4 counter/risk     → headwind claims → tailwinds journal
  Q5 watch items      → thesis_watches (graded on fundamental refresh)
  Q6 novelty          → under_appreciated | consensus | priced_in

The grounding rule that makes it trustworthy: every claim must carry a
VERBATIM quote that is a literal substring of the pasted text —
hallucinated evidence dies in validation.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MAX_CHARS = 24000          # ~6k tokens — bound spend per doc

_FACT_MAP = {               # metric words → symbol_flywheel columns
    "revenue growth": "rev_growth", "rev growth": "rev_growth",
    "eps growth": "eps_growth", "earnings growth": "eps_growth",
    "forward p/e": "fwd_pe", "fwd pe": "fwd_pe", "fwd p/e": "fwd_pe",
    "gross margin": "gm_now", "estimate revision": "est_revision_pct",
    "beat streak": "beat_streak",
}


def _fetch(url: str) -> tuple[str, str]:
    """Best-effort article fetch → (text, title). Paywalled sources
    often refuse — the caller falls back to pasted text."""
    import re as _re
    try:
        import requests
        html = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0"}).text
        title = ""
        m = _re.search(r"<title[^>]*>(.*?)</title>", html,
                       _re.S | _re.I)
        if m:
            title = _re.sub(r"\s+", " ", m.group(1)).strip()
        body = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                       flags=_re.S | _re.I)
        body = _re.sub(r"<[^>]+>", " ", body)
        body = _re.sub(r"\s+", " ", body).strip()
        return body[:_MAX_CHARS], title
    except Exception as exc:
        logger.info("doc fetch %s failed: %s", url, exc)
        return "", ""


def _llm(sym: str, text: str, model: Optional[str] = None) -> dict:
    from litellm import completion
    from app.config import settings
    mdl = model or getattr(settings, "litellm_model", None) \
        or "gpt-4o-mini"
    resp = completion(
        model=mdl, temperature=0.1, max_tokens=1600, timeout=60,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content":
             "You analyze one document about a stock and return STRICT "
             "JSON. You extract claims only — never scores, ratings, "
             "price targets, or trade recommendations. Every claim MUST "
             "carry `quote`: a VERBATIM substring copied from the text "
             "(validation checks this literally — paraphrase dies). "
             "Schema: {\"thesis\": one line, \"claims\": [{\"type\": "
             "\"channel\"|\"mechanism\"|\"fact\"|\"risk\"|\"watch\", "
             "\"text\": what is claimed, \"quote\": verbatim substring, "
             "\"channel\": short_snake_name (channel type only), "
             "\"direction\": \"tailwind\"|\"headwind\" (channel/risk), "
             "\"tier\": \"rumor\"|\"announced\"|\"shipping\"|\"revenue\" "
             "(channel/risk — 'revenue' only if text says money is "
             "already being made), \"metric\": e.g. 'revenue growth' "
             "(fact/watch), \"value\": number (fact), \"period\": e.g. "
             "'FY27 Q1' (fact), \"threshold\": e.g. '>5% of revenue' "
             "(watch), \"horizon\": e.g. 'FY28' (watch), \"novelty\": "
             "\"under_appreciated\"|\"consensus\"|\"priced_in\"}]}. "
             "channel = a NEW revenue channel (product/service not yet "
             "material in quarterly numbers). mechanism = WHY demand "
             "grows (causal chain). fact = a NUMBERED claim. watch = "
             "a falsifiable future check. risk = counter-thesis. "
             "Return fewer, better claims — max 10."},
            {"role": "user", "content":
             f"Symbol: {sym}\n\nDocument:\n{text}"}])
    return json.loads(resp.choices[0].message.content)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _grounded(quote: str, text: str) -> bool:
    """Literal-substring grounding (whitespace/case normalized)."""
    q, t = _norm(quote), _norm(text)
    return bool(q) and q in t


def _fact_check(claim: dict) -> dict:
    """Numbered claims get checked against stored fundamentals —
    consistent | conflict | unverifiable."""
    from app.database import db
    metric = _norm(claim.get("metric"))
    val = claim.get("value")
    col = next((v for k, v in _FACT_MAP.items() if k in metric), None)
    claim["check"] = "unverifiable"
    if col and isinstance(val, (int, float)) and claim.get("symbol"):
        r = db.execute_query(
            f"SELECT {col} v FROM symbol_flywheel WHERE symbol=:s",
            {"s": claim["symbol"]})
        if r and r[0]["v"] is not None:
            got = float(r[0]["v"])
            # article values arrive as % or ratio — normalize
            want = val / 100 if abs(val) > 3 else val
            claim["check"] = ("consistent"
                              if abs(got - want) < max(0.05, abs(want) * 0.2)
                              else f"conflict — stored {got:.2f}")
            claim["stored_value"] = got
    return claim


def analyze(symbol: str, text: str = "", url: str = "",
            title: str = "") -> dict[str, Any]:
    """Extract → validate → journal → return the analysis."""
    from app.database import db
    sym = symbol.upper().strip()
    if not text and url:
        text, fetched_title = _fetch(url)
        title = title or fetched_title
    if not text or len(text) < 200:
        return {"error": "no document text — paste the article body "
                "(paywalled sources can't be fetched)"}
    raw = _llm(sym, text[:_MAX_CHARS])

    valid, dropped = [], []
    for c in (raw.get("claims") or [])[:10]:
        c["symbol"] = sym
        quote = c.get("quote") or ""
        if not _grounded(quote, text):
            c["drop_reason"] = "quote not verbatim in document"
            dropped.append(c)
            continue
        if c.get("type") not in ("channel", "mechanism", "fact",
                                 "risk", "watch"):
            c["drop_reason"] = "unknown claim type"
            dropped.append(c)
            continue
        if c.get("type") in ("channel", "risk"):
            # channel name: LLM-provided, else slugify the claim text
            if not c.get("channel"):
                c["channel"] = "risk:" + re.sub(
                    r"[^a-z0-9]+", "_",
                    str(c.get("text") or "").lower())[:45].strip("_")
            c["channel"] = re.sub(r"[^a-z0-9_:-]", "",
                                  str(c["channel"]).lower())[:60]
        valid.append(c)

    # ---- journal: channels + risks → tailwinds; watches → table ----
    from app.signals import tailwinds as tw
    tw_claims = []
    for c in valid:
        if c["type"] in ("channel", "risk") and c.get("channel"):
            tw_claims.append({
                "channel": c["channel"],
                "direction": ("headwind" if c["type"] == "risk"
                              or c.get("direction") == "headwind"
                              else "tailwind"),
                "tier": c.get("tier") if c.get("tier") in
                        tw._TIER_RANK else "announced",
                "why": str(c.get("text") or "")[:200],
                "confidence": 0.75,   # curated doc — stronger than one
                                       # headline, still human-reviewed
                "sources": [{"title": title or url or "pasted doc",
                             "at": str(date.today()),
                             "src": url or "pasted"}]})
    journaled = tw._upsert(sym, tw_claims) if tw_claims else 0

    watches = []
    for c in valid:
        if c["type"] == "watch":
            metric = str(c.get("metric") or c.get("text") or "")[:80]
            if not metric:
                continue
            db.execute_update(
                "INSERT INTO thesis_watches (symbol, metric, threshold,"
                " horizon, direction, source) VALUES"
                " (:s,:m,:t,:h,:d,:src) ON CONFLICT (symbol, metric,"
                " horizon) DO UPDATE SET source=:src",
                {"s": sym, "m": metric,
                 "t": str(c.get("threshold") or "")[:80],
                 "h": str(c.get("horizon") or "")[:30],
                 "d": "confirm" if c.get("direction") != "headwind"
                     else "refute",
                 "src": (url or title or "pasted doc")[:200]})
            watches.append(metric)

    facts = [_fact_check(dict(c)) for c in valid if c["type"] == "fact"]

    db.execute_update(
        "INSERT INTO doc_analyses (symbol, url, title, thesis, claims,"
        " dropped) VALUES (:s,:u,:t,:th,CAST(:c AS jsonb),"
        " CAST(:d AS jsonb))",
        {"s": sym, "u": url or None, "t": title or None,
         "th": str(raw.get("thesis") or "")[:300],
         "c": json.dumps(valid), "d": json.dumps(dropped)})

    return {"symbol": sym, "thesis": raw.get("thesis"),
            "title": title, "claims": valid, "dropped": dropped,
            "journaled_channels": journaled, "watches": watches,
            "fact_checks": [{k: f.get(k) for k in
                             ("metric", "value", "period", "check",
                              "stored_value")} for f in facts]}


def check_watches() -> dict[str, int]:
    """Grade open thesis_watches against stored fundamentals.
    Mappable metrics (rev growth, fwd PE…) get auto-graded; free-text
    ones ('optical segment revenue') stay open for human review —
    never fake a verdict."""
    from app.database import db
    stats = {"confirmed": 0, "refuted": 0, "still_open": 0}
    rows = db.execute_query(
        "SELECT w.id, w.symbol, w.metric, w.threshold, w.direction"
        " FROM thesis_watches w WHERE w.status='open'")
    fly = {r["symbol"]: dict(r) for r in db.execute_query(
        "SELECT * FROM symbol_flywheel")}
    for w in rows:
        metric, thr = _norm(w["metric"]), w["threshold"] or ""
        col = next((v for k, v in _FACT_MAP.items() if k in metric),
                   None)
        m = re.match(r"\s*(>=|<=|>|<)\s*\$?([\d.]+)\s*(%|m|b)?",
                     thr, re.I)
        row = fly.get(w["symbol"])
        if not (col and m and row and row.get(col) is not None):
            stats["still_open"] += 1
            continue
        op, num, unit = m.group(1), float(m.group(2)), (m.group(3) or "")
        want = num / 100 if unit == "%" or abs(num) > 3 else num
        got = float(row[col])
        met = ((got > want) if op == ">" else (got >= want) if op == ">="
               else (got < want) if op == "<" else (got <= want))
        status = ("confirmed" if met else "refuted") \
            if w["direction"] == "confirm" else \
            ("refuted" if met else "confirmed")
        db.execute_update(
            "UPDATE thesis_watches SET status=:st, check_note=:n,"
            " checked_at=now() WHERE id=:i",
            {"st": status,
             "n": f"stored {col}={got:.3f} vs threshold '{thr}'",
             "i": w["id"]})
        stats["confirmed" if status == "confirmed"
              else "refuted"] += 1
    return stats
