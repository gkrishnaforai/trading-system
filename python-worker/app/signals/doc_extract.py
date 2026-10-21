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
             "\"channel\"|\"mechanism\"|\"fact\"|\"risk\"|\"watch\"|"
             "\"driver\", "
             "\"text\": what is claimed, \"quote\": verbatim substring, "
             "\"channel\": short_snake_name (channel type only), "
             "\"direction\": \"tailwind\"|\"headwind\" (channel/risk), "
             "\"tier\": \"rumor\"|\"announced\"|\"shipping\"|\"revenue\" "
             "(channel/risk — 'revenue' only if text says money is "
             "already being made), \"metric\": e.g. 'revenue growth' "
             "(fact/watch/driver — short_snake e.g. 'ad_revenue', "
             "'op_margin'), \"value\": number (fact/driver — raw units, "
             "2.7e9 not '2.7B'), \"prior_value\": number (driver — the "
             "previously stated figure when text compares, e.g. 'vs "
             "$3B previously' → 3.0e9), \"period\": e.g. "
             "'FY27 Q1' (fact), \"threshold\": e.g. '>5% of revenue' "
             "(watch), \"horizon\": e.g. 'FY28' (watch), \"novelty\": "
             "\"under_appreciated\"|\"consensus\"|\"priced_in\"}]}. "
             "channel = a NEW revenue channel (product/service not yet "
             "material in quarterly numbers). mechanism = WHY demand "
             "grows (causal chain). fact = a NUMBERED claim. watch = "
             "a falsifiable future check. risk = counter-thesis. "
             "driver = a NAMED GROWTH ENGINE or FORWARD NUMERIC "
             "COMMITMENT — guidance targets ('expect FY26 ad revenue "
             "~$2.7B'), capacity plans ('6,000 racks/mo'), investment "
             "programs ('capex $15B') — anything management promised "
             "a number for. ALWAYS extract prior_value when the text "
             "revises an earlier figure. REVISED GUIDANCE is the "
             "highest-value claim in the document — a figure stated "
             "against a previously stated figure ('$2.7B vs ~$3B "
             "previously') MUST appear as a driver, never dropped "
             "for space. "
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


# --- deterministic revised-guidance safety net -----------------------
# 'expect X of ~$2.7B vs ~$3B previously' — the LLM is bounded to 10
# claims and may drop a revision; the pattern is regex-catchable so
# a named-driver guide cut can never silently miss the journal.
_MONEY = r"\$?\s*([\d.,]+)\s*([BbMm]|[Bb]illion|[Mm]illion)?"
_REV_RE = None
_METRIC_HINTS = [
    (r"ad(vertis\w*)? rev", "ad_revenue"),
    (r"(?:total )?revenue|sales", "revenue"),
    (r"op(erating)?[ -]?(income|margin)", "op_margin"),
    (r"gross margin", "gm"),
    (r"capex|capital expend", "capex"),
    (r"free cash|fcf", "fcf"),
    (r"eps|earnings per share|net income", "eps"),
    (r"member|subscriber|sub\b", "members"),
    (r"backlog|orders", "backlog"),
    (r"guid\w+|forecast|expect|project", "guidance"),
]


def _num(num: str, unit: str):
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    u = (unit or "").lower()
    if u.startswith("b"):
        v *= 1e9
    elif u.startswith("m"):
        v *= 1e6
    return v


def _revision_scan(text: str, covered: set) -> list:
    """Sentences of the form 'figure vs ~$X previously' → synthetic
    driver claims for revisions the LLM didn't claim. covered = the
    normalized quotes already claimed (don't duplicate)."""
    global _REV_RE
    if _REV_RE is None:
        _REV_RE = re.compile(
            r"([^.]*?(?:expect|forecast|anticipate|project|guid|now "
            r"see|estimate)[^.]*?" + _MONEY + r"[^.]*?(?:vs\.?|versus|"
            r"compared to|down from|up from|from)[^.]*?" + _MONEY +
            r"[^.]*?(?:previous|prior|earlier|forecast)[^.]*\.)",
            re.I | re.S)
    out = []
    for m in _REV_RE.finditer(text):
        sent = re.sub(r"\s+", " ", m.group(1)).strip()
        new_v, prior_v = _num(m.group(2), m.group(3)), \
            _num(m.group(4), m.group(5))
        if new_v is None or prior_v is None or new_v == prior_v:
            continue
        if _norm(sent) in covered:
            continue
        sl = sent.lower()
        metric = next((name for pat, name in _METRIC_HINTS
                       if re.search(pat, sl)), "guidance")
        per = re.search(r"\b(20\d\d|fy\s*'?20?\d\d|q[1-4]\b)", sl)
        out.append({"type": "driver", "text": sent[:200],
                    "quote": sent[:400], "metric": metric,
                    "value": new_v, "prior_value": prior_v,
                    "period": (per.group(0).upper().replace(" ", "")
                               if per else "FY"),
                    "synthetic": True})
    return out


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
                                 "risk", "watch", "driver"):
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

    # revised-guidance safety net — regex the doc for '$X vs ~$Y
    # previously' sentences the LLM didn't claim; a named-driver cut
    # is the single most important signal in an earnings doc
    covered = {_norm(c.get("quote") or "") for c in valid}
    covered |= {_norm(c.get("text") or "") for c in valid}
    for s in _revision_scan(text, covered):
        sn = _norm(s["quote"])
        if any(cov and (cov in sn or sn in cov) for cov in covered):
            continue
        s["symbol"] = sym
        valid.append(s)

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

    drivers = []
    for c in valid:
        if c["type"] == "driver":
            d = _journal_driver(sym, c, url or title or "pasted doc")
            if d:
                drivers.append(d)

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
            "drivers": drivers,
            "fact_checks": [{k: f.get(k) for k in
                             ("metric", "value", "period", "check",
                              "stored_value")} for f in facts]}


def _journal_driver(sym: str, c: dict, src: str) -> Optional[dict]:
    """A 'driver' claim — a named growth engine / forward numeric
    commitment — lands in driver_commitments AND the thesis_watches
    journal (metric 'driver:{metric}:{period}'), so review surfaces
    and the grader see it like any other watch. The delta vs the
    standing commitment for the same metric+period is arithmetic:
    raised | cut | reaffirmed — the NFLX 'ad revenue $3B→$2.7B'
    red flag is exactly this."""
    from app.database import db
    metric = _norm(c.get("metric") or "")[:60]
    period = str(c.get("period") or c.get("horizon")
                 or "standing")[:30]
    val = c.get("value")
    if not metric:
        return None
    try:
        val = float(val) if val is not None else None
    except (TypeError, ValueError):
        val = None
    prior_v = c.get("prior_value")
    try:
        prior_v = float(prior_v) if prior_v is not None else None
    except (TypeError, ValueError):
        prior_v = None

    # standing open commitment for the same metric+period → the
    # baseline this one is compared against (superseded after)
    quote = str(c.get("quote") or "")[:400]
    standing = db.execute_query(
        "SELECT id, value, quote FROM driver_commitments"
        " WHERE symbol=:s AND metric=:m AND period=:p"
        " AND status='open' ORDER BY created_at DESC LIMIT 1",
        {"s": sym, "m": metric, "p": period})
    # same commitment re-journaled (same quote) — not a revision
    if standing and standing[0].get("quote") == quote:
        standing = []
    base = prior_v if prior_v is not None else (
        float(standing[0]["value"]) if standing
        and standing[0]["value"] is not None else None)
    if base and val is not None:
        d_pct = (val - base) / abs(base)
        delta = "raised" if d_pct > 0.005 else \
                "cut" if d_pct < -0.005 else "reaffirmed"
    else:
        d_pct, delta = None, "new"

    if standing and (standing[0]["value"] != val
                     or delta in ("raised", "cut")):
        db.execute_update(
            "UPDATE driver_commitments SET status='superseded',"
            " check_note=:n, checked_at=now() WHERE id=:i",
            {"n": f"revised {base}→{val} ({delta}) on {src[:60]}",
             "i": standing[0]["id"]})
    db.execute_update(
        "INSERT INTO driver_commitments (symbol, metric, period,"
        " value, value_text, direction, prior_value, delta_dir,"
        " delta_pct, quote, source) VALUES"
        " (:s,:m,:p,:v,:vt,:di,:pv,:dd,:dp,:q,:src)"
        " ON CONFLICT (symbol, metric, period, quote) DO NOTHING",
        {"s": sym, "m": metric, "p": period, "v": val,
         "vt": str(c.get("text") or "")[:120],
         "di": str(c.get("guidance_dir") or "approx"),
         "pv": base, "dd": delta, "dp": d_pct, "q": quote,
         "src": src[:200]})
    # same journal as every other watch — never a parallel tracker
    thr = f">={val:g}" if val is not None else \
        str(c.get("threshold") or "")[:80]
    db.execute_update(
        "INSERT INTO thesis_watches (symbol, metric, threshold,"
        " horizon, direction, source, expected_direction) VALUES"
        " (:s,:m,:t,:h,'confirm',:src,'>=')"
        " ON CONFLICT (symbol, metric, horizon) DO UPDATE SET"
        " threshold=EXCLUDED.threshold, source=EXCLUDED.source",
        {"s": sym, "m": f"driver:{metric}:{period}"[:80],
         "t": thr[:80], "h": period[:30], "src": src[:200]})
    # a material named-driver revision is itself the event — SMCI's
    # +28% revenue guide raise came through a prelim update, not an
    # earnings print, so check_symbol never saw it. Alert on the
    # delta directly (fingerprint-deduped).
    if delta in ("raised", "cut") and d_pct is not None \
            and abs(d_pct) >= 0.10:
        pv_s = (f"{base/1e9:.1f}B" if base and abs(base) >= 1e9
                else f"{base}") if base is not None else "prior"
        v_s = f"{val/1e9:.1f}B" if val and abs(val) >= 1e9 else f"{val}"
        db.execute_update(
            "INSERT INTO alert_items (symbol, event_type, direction,"
            " materiality, title, detail, fingerprint, source,"
            " source_timestamp, status, priority_score) VALUES"
            " (:s,'guidance',:di,'HIGH',:t,CAST(:de AS jsonb),:fp,"
            " 'driver_commitments', now(),'new',140)"
            " ON CONFLICT (fingerprint) DO NOTHING",
            {"s": sym,
             "di": "UP" if delta == "raised" else "DOWN",
             "t": (f"{sym} guidance {delta}: {metric} {period} "
                   f"{d_pct:+.0%} ({pv_s}→{v_s})"),
             "de": json.dumps({"metric": metric, "period": period,
                               "value": val, "prior": base,
                               "delta_pct": d_pct, "quote": quote,
                               "source": src}, default=str),
             "fp": f"driver:{sym}:{metric}:{period}:{quote[:60]}"})
    return {"metric": metric, "period": period, "value": val,
            "prior": base, "delta": delta, "delta_pct": d_pct}


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
