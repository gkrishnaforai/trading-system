"""Tailwind extraction — 'pre-revenue revenue channels'.

Reads `alert_items` (the live catalyst pipeline — same ingestion the
alerts job feeds), LLM-extracts structured channel claims per symbol
('meta glasses', 'robotaxi', 'CPO wins'), validates deterministically,
and journals to `tailwinds`.

Rules consistent with the system: the LLM only EXTRACTS claims; the
deterministic layer decides whether they count — a channel must recur
across distinct headlines to corroborate, and tiers only promote
upward (rumor → announced → shipping → revenue). Negative claims land
as headwinds. When quarterly numbers confirm a channel the row is
promotable to 'confirmed'; when it dies, 'dead'.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TIER_RANK = {"rumor": 0, "announced": 1, "shipping": 2, "revenue": 3}
_TIER_BONUS = {"announced": 2, "shipping": 4, "revenue": 6}
# evidence-ledger schema — LLM proposes, deterministic code validates
_STAGES = {"concept", "development", "qualification", "ramp",
           "production"}
_HORIZONS = {"this_year", "1_to_3_years", "3_plus_years"}


def _items(sym: str, days: int = 45) -> list[dict]:
    """A symbol's recent catalyst/analyst headlines — the live corpus."""
    from app.database import db
    return [dict(r) for r in db.execute_query(
        "SELECT title, detail, direction, materiality, source,"
        " source_timestamp, created_at FROM alert_items"
        " WHERE symbol=:s AND event_type IN"
        "   ('catalyst','analyst_action','eps_revision')"
        " AND created_at > :c ORDER BY created_at DESC LIMIT 25",
        {"s": sym.upper(), "c": date.today() - timedelta(days=days)})]


def _extract(sym: str, items: list[dict],
             model: Optional[str] = None) -> list[dict]:
    """One LLM pass → structured channel claims. Extraction only —
    scoring happens deterministically downstream."""
    # dedupe syndicated re-prints — one story, one evidence line
    seen_t, uniq = set(), []
    for r in items:
        t = (r.get("title") or "").strip().lower()
        if t and t not in seen_t:
            seen_t.add(t)
            uniq.append(r)
    items = uniq
    if len(items) < 2:
        return []
    def _det(r):
        d = r.get("detail")
        if isinstance(d, dict):
            return "; ".join(str(x) for x in (d.get("reasons") or []))[:120]
        return str(d or "")[:120]
    lines = [f"{i+1}. [{r.get('direction') or '?'}] {r['title']}"
             + (f" — {d}" if (d := _det(r)) else "")
             for i, r in enumerate(items)]
    existing = [r["channel"] for r in for_symbol(sym)]
    try:
        from litellm import completion
        from app.config import settings
        mdl = model or getattr(settings, "litellm_model", None) \
            or "gpt-4o-mini"
        resp = completion(
            model=mdl, temperature=0.1, max_tokens=900, timeout=45,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content":
                 "You extract NEW REVENUE CHANNEL claims from stock "
                 "headlines — products/services not yet material in "
                 "quarterly numbers (e.g. 'Ray-Ban AI glasses', "
                 "'robotaxi', 'CPO orders', 'new cloud contract'). "
                 "Also extract HEADWINDS — a channel dying, a major "
                 "customer lost, a regulatory block. Return JSON: "
                 "{\"claims\": [{\"channel\": short snake/kebab name, "
                 "\"direction\": \"tailwind\"|\"headwind\", "
                 "\"tier\": \"rumor\"|\"announced\"|\"shipping\"|"
                 "\"revenue\", \"why\": one line, "
                 "\"confidence\": 0-1, \"src\": [item numbers], "
                 "\"commercial_stage\": \"concept\"|\"development\"|"
                 "\"qualification\"|\"ramp\"|\"production\", "
                 "\"financial_horizon\": \"this_year\"|\"1_to_3_years\"|"
                 "\"3_plus_years\", \"expected_impact\": {\"revenue\": "
                 "\"pos\"|\"neg\"|\"uncertain\"|\"unknown\", "
                 "\"gross_margin\": same, \"eps\": same}, "
                 "\"next_milestone\": the next proof point (one line)}. "
                 "Tier discipline: 'announced' = company announced it; "
                 "'shipping' = product actually selling/shipping; "
                 "'revenue' = headline says revenue is being generated. "
                 "Skip generic news (price moves, earnings dates, "
                 "analyst ratings) — only channel-level claims. "
                 "IMPORTANT: if a claim refers to a product/channel "
                 "already in the KNOWN list, reuse that exact channel "
                 "name so corroboration accrues to it."
                 + (f" KNOWN: {', '.join(existing)}." if existing else "")
                 + " Return {\"claims\": []} if nothing qualifies."},
                {"role": "user", "content":
                 f"Symbol: {sym}\n\nHeadlines:\n" + "\n".join(lines)}])
        raw = json.loads(resp.choices[0].message.content)
        claims = raw.get("claims") or []
    except Exception as exc:
        logger.warning("tailwind extract %s failed: %s", sym, exc)
        return []

    # deterministic validation — grounded in real headlines only
    out = []
    for c in claims[:6]:
        ch = re.sub(r"[^a-z0-9 \-_/]", "",
                    str(c.get("channel") or "").lower()).strip()[:60]
        if not ch or len(ch) < 3:
            continue
        src = [int(i) - 1 for i in (c.get("src") or [])
               if str(i).isdigit() and 1 <= int(i) <= len(items)]
        if not src:
            continue                        # ungrounded claim — drop
        imp = c.get("expected_impact") or {}
        impact = {k: imp.get(k) if imp.get(k) in
                  ("pos", "neg", "uncertain", "unknown") else "unknown"
                  for k in ("revenue", "gross_margin", "eps")}
        out.append({
            "channel": ch,
            "direction": "headwind" if c.get("direction") == "headwind"
                         else "tailwind",
            "tier": c.get("tier") if c.get("tier") in _TIER_RANK
                    else "rumor",
            "why": str(c.get("why") or "")[:200],
            "confidence": min(max(float(c.get("confidence") or 0.5),
                                  0.0), 1.0),
            "sources": [{"title": items[i]["title"],
                         "at": str(items[i].get("source_timestamp")
                                  or items[i].get("created_at"))[:19]}
                        for i in src[:4]],
            "commercial_stage":
                c.get("commercial_stage") if c.get("commercial_stage")
                in _STAGES else None,
            "financial_horizon":
                c.get("financial_horizon") if c.get("financial_horizon")
                in _HORIZONS else None,
            "expected_impact": impact,
            "next_milestone": str(c.get("next_milestone") or "")[:120]
                              or None,
        })
    return out


def _canon(sym: str, channel: str,
           existing: list[str]) -> str:
    """Deterministic channel merge — 'muse_ai' and 'meta_muse' are the
    same product; fold variants that share a distinctive token (≥4
    chars, not the ticker/company token) into the first-seen name."""
    toks = {t for t in channel.split("_") if len(t) >= 4
            and t != sym.lower()}
    for e in existing:
        etoks = {t for t in e.split("_") if len(t) >= 4
                 and t != sym.lower()}
        if toks & etoks:
            return e
    return channel


def _alert(sym: str, channel: str, direction: str, tier: str,
           summary: str, hits: int):
    """A tier promotion or fresh revenue/shipping claim is a discrete
    'make a move' event — emit it into the live alert feed."""
    from app.database import db
    watch = db.execute_query(
        "SELECT EXISTS(SELECT 1 FROM portfolio_positions pp"
        "  JOIN stocks s2 ON s2.id=pp.stock_id WHERE s2.symbol=:s) pf,"
        " EXISTS(SELECT 1 FROM watchlist_stocks ws"
        "  JOIN stocks s3 ON s3.id=ws.stock_id WHERE s3.symbol=:s) wl",
        {"s": sym})
    pf, wl = (watch[0]["pf"], watch[0]["wl"]) if watch else (False, False)
    sign = "POSITIVE" if direction == "tailwind" else "NEGATIVE"
    mat = "HIGH" if tier == "revenue" else "MODERATE"
    arrow = "▲" if direction == "tailwind" else "▼"
    db.execute_update(
        "INSERT INTO alert_items (symbol, event_type, direction,"
        " materiality, title, detail, fingerprint, source,"
        " source_timestamp, in_portfolio, in_watchlist, priority_score)"
        " VALUES (:s,'tailwind',:dir,:m,:t,CAST(:d AS jsonb),:f,"
        " 'tailwinds',now(),:pf,:wl,:p)"
        " ON CONFLICT (fingerprint) DO NOTHING",
        {"s": sym, "dir": sign, "m": mat,
         "t": f"{arrow} {sym}: channel '{channel}' → {tier} tier"
              f" ({hits} corroborating)",
         "d": json.dumps({"channel": channel, "tier": tier,
                          "hits": hits, "summary": summary,
                          "kind": "tailwind_promotion"}),
         "f": f"tailwind:{sym}:{channel}:{direction}:{tier}",
         "pf": pf, "wl": wl,
         "p": {"revenue": 75, "shipping": 65}.get(tier, 50)})


def _upsert(sym: str, claims: list[dict]) -> int:
    """Journal + promote. Tiers only move up; hit_count = distinct
    corroborating headlines (new titles add, old ones don't recount)."""
    from app.database import db
    existing = {r["channel"]: r["direction"] for r in for_symbol(sym)}
    n = 0
    for c in claims:
        # same-direction channels only — a Muse launch tailwind and a
        # Muse doxing headwind are two different claims on one product
        same_dir = [k for k, d in existing.items()
                    if d == c["direction"]]
        c["channel"] = _canon(sym, c["channel"], same_dir)
        existing.setdefault(c["channel"], c["direction"])
        row = db.execute_query(
            "SELECT id, tier, hit_count, sources, status"
            " FROM tailwinds WHERE symbol=:s AND channel=:c",
            {"s": sym, "c": c["channel"]})
        if row:
            row = row[0]
            seen = {s["title"] for s in (row["sources"] or [])}
            new_src = [s for s in c["sources"] if s["title"] not in seen]
            hits = (row["hit_count"] or 1) + len(new_src)
            promoted = _TIER_RANK[c["tier"]] > _TIER_RANK[row["tier"]]
            tier = c["tier"] if promoted else row["tier"]
            # fresh evidence resurrects a noise/dead channel — the
            # reviewer was wrong, or the channel came back to life
            resurrect = row["status"] != "active"
            if promoted and not resurrect:
                _alert(sym, c["channel"], c["direction"], tier,
                       c["why"], hits)
            db.execute_update(
                "UPDATE tailwinds SET tier=:t, hit_count=:h,"
                " sources=CAST(:src AS jsonb), last_seen=now(),"
                " summary=:w, confidence=:cf,"
                " commercial_stage=COALESCE(CAST(:cs AS text),"
                " commercial_stage),"
                " financial_horizon=COALESCE(CAST(:fh AS text),"
                " financial_horizon),"
                " expected_impact=COALESCE(CAST(:ei AS jsonb),"
                " expected_impact),"
                " next_milestone=COALESCE(CAST(:nm AS text),"
                " next_milestone),"
                " verification_status=CASE"
                "   WHEN tier='revenue' THEN 'confirmed'"
                "   WHEN :h >= 3 THEN 'corroborated'"
                "   ELSE verification_status END,"
                " status='active', review_note=NULL, updated_at=now()"
                " WHERE id=:i",
                {"t": tier, "h": hits,
                 "src": json.dumps((row["sources"] or []) + new_src),
                 "w": c["why"], "cf": c["confidence"], "i": row["id"],
                 "cs": c.get("commercial_stage"),
                 "fh": c.get("financial_horizon"),
                 "ei": (json.dumps(c["expected_impact"])
                        if c.get("expected_impact") else None),
                 "nm": c.get("next_milestone")})
            n += bool(new_src)
        else:
            db.execute_update(
                "INSERT INTO tailwinds (symbol, channel, direction,"
                " tier, summary, confidence, sources, hit_count,"
                " commercial_stage, financial_horizon, expected_impact,"
                " next_milestone, verification_status,"
                " first_seen, last_seen) VALUES"
                " (:s,:c,:d,:t,:w,:cf,CAST(:src AS jsonb),1,:cs,:fh,"
                " CAST(:ei AS jsonb),:nm,:vs,now(),now())",
                {"s": sym, "c": c["channel"], "d": c["direction"],
                 "t": c["tier"], "w": c["why"], "cf": c["confidence"],
                 "src": json.dumps(c["sources"]),
                 "cs": c.get("commercial_stage"),
                 "fh": c.get("financial_horizon"),
                 "ei": (json.dumps(c["expected_impact"])
                        if c.get("expected_impact") else None),
                 "nm": c.get("next_milestone"),
                 "vs": ("confirmed" if c["tier"] == "revenue"
                        else "unverified")})
            if _TIER_RANK[c["tier"]] >= _TIER_RANK["shipping"]:
                _alert(sym, c["channel"], c["direction"], c["tier"],
                       c["why"], 1)
            n += 1
    return n


def run(max_symbols: int = 80, days: int = 45) -> dict[str, Any]:
    """Daily pass — symbols with enough fresh catalyst flow to extract
    from (≥3 items), capped to bound spend."""
    from app.database import db
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol, count(*) n FROM alert_items"
        " WHERE event_type IN ('catalyst','analyst_action',"
        "   'eps_revision') AND created_at > :c"
        " GROUP BY symbol HAVING count(*) >= 3"
        " ORDER BY n DESC LIMIT :m",
        {"c": date.today() - timedelta(days=7), "m": max_symbols})]
    stats = {"symbols": len(syms), "claims_new": 0, "errors": 0}
    for sym in syms:
        try:
            items = _items(sym, days)
            claims = _extract(sym, items)
            stats["claims_new"] += _upsert(sym, claims)
        except Exception as exc:
            logger.debug("tailwind %s: %s", sym, exc)
            stats["errors"] += 1
    return stats


def _review_symbol(sym: str, rows: list[dict],
                   model: Optional[str] = None) -> list[dict]:
    """One LLM pass: does each journaled channel still plausibly move
    revenue? Extraction-style discipline — verdicts only, applied
    deterministically."""
    lines = []
    for r in rows:
        srcs = " | ".join(s["title"][:80]
                          for s in (r.get("sources") or [])[:3])
        lines.append(
            f"- channel={r['channel']} | dir={r['direction']} | "
            f"tier={r['tier']} | hits={r['hit_count']} | "
            f"summary={r.get('summary') or '—'} | evidence: {srcs}")
    try:
        from litellm import completion
        from app.config import settings
        mdl = model or getattr(settings, "litellm_model", None) \
            or "gpt-4o-mini"
        resp = completion(
            model=mdl, temperature=0.1, max_tokens=700, timeout=45,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content":
                 "You re-grade journaled 'new revenue channel' claims "
                 "the way an analyst re-checks a thesis. For each "
                 "channel return verdict: 'live' = plausibly material "
                 "to revenue within ~4 quarters (growing product, "
                 "contract, adoption); 'noise' = real news but no "
                 "credible revenue path (partnership fluff, branding, "
                 "integrations, PR); 'dead' = channel killed/cancelled/"
                 "contradicted by newer evidence. Judge ONLY revenue "
                 "relevance, not stock direction. Return JSON: "
                 "{\"reviews\": [{\"channel\": exact channel name, "
                 "\"verdict\": \"live\"|\"noise\"|\"dead\", "
                 "\"reason\": one line}]}"},
                {"role": "user", "content":
                 f"Symbol: {sym}\n\nChannels under review:\n"
                 + "\n".join(lines)}])
        raw = json.loads(resp.choices[0].message.content)
        return raw.get("reviews") or []
    except Exception as exc:
        logger.warning("tailwind review %s failed: %s", sym, exc)
        return []


def review(max_symbols: int = 60, stale_days: int = 21) -> dict:
    """Weekly re-grade — the self-cleaning pass.

    1. Deterministic decay: a rumor-tier channel with 1 hit that hasn't
       been re-seen in `stale_days` days faded — auto-noise, no LLM.
    2. LLM relevance check on what's still active: does it plausibly
       move revenue? noise → status='noise' (audit-kept, excluded from
       card/bonus); dead → 'dead'; live → stays.
    """
    from app.database import db
    stats = {"decayed": 0, "reviewed": 0, "live": 0,
             "noise": 0, "dead": 0}
    stats["decayed"] = db.execute_update(
        "UPDATE tailwinds SET status='noise',"
        " review_note='stale single-source rumor — never corroborated',"
        " reviewed_at=now(), updated_at=now()"
        " WHERE status='active' AND tier='rumor' AND hit_count<=1"
        " AND last_seen < :c",
        {"c": date.today() - timedelta(days=stale_days)})
    rows = [dict(r) for r in db.execute_query(
        "SELECT id, symbol, channel, direction, tier, summary,"
        " hit_count, sources FROM tailwinds WHERE status='active'"
        " AND (reviewed_at IS NULL OR reviewed_at < now() - interval"
        " '7 days') ORDER BY symbol, hit_count DESC")]
    by_sym: dict[str, list] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
    for sym, rs in list(by_sym.items())[:max_symbols]:
        verdicts = _review_symbol(sym, rs)
        stats["reviewed"] += len(rs)
        vmap = {str(v.get("channel") or "").lower(): v
                for v in verdicts if isinstance(v, dict)}
        for r in rs:
            v = vmap.get(r["channel"].lower())
            verdict = (v or {}).get("verdict")
            reason = str((v or {}).get("reason") or "")[:200]
            if verdict in ("noise", "dead"):
                db.execute_update(
                    "UPDATE tailwinds SET status=:v,"
                    " review_note=:n, reviewed_at=now(),"
                    " updated_at=now() WHERE id=:i",
                    {"v": verdict, "n": reason, "i": r["id"]})
                stats[verdict] += 1
            else:
                db.execute_update(
                    "UPDATE tailwinds SET review_note=:n,"
                    " reviewed_at=now(), updated_at=now()"
                    " WHERE id=:i",
                    {"n": reason or "live — still plausible",
                     "i": r["id"]})
                stats["live"] += 1
    # grade open thesis watches against fresh fundamentals —
    # mappable metrics auto-grade, free-text stay open for humans
    try:
        from app.signals.doc_extract import check_watches
        stats["watches"] = check_watches()
    except Exception as exc:
        logger.debug("watch check skipped: %s", exc)
    return stats


def for_symbol(sym: str) -> list[dict]:
    """The card's read — active tail/headwinds, strongest first."""
    from app.database import db
    return [dict(r) for r in db.execute_query(
        "SELECT channel, direction, tier, summary, confidence,"
        " hit_count, last_seen FROM tailwinds"
        " WHERE symbol=:s AND status='active'"
        " ORDER BY CASE tier WHEN 'revenue' THEN 0"
        " WHEN 'shipping' THEN 1 WHEN 'announced' THEN 2 ELSE 3 END,"
        " hit_count DESC", {"s": sym.upper()})]


def bonus(sym: str) -> float:
    """Conviction._future's tailwind leg — tier-weighted, ±10 cap.
    Headwinds subtract."""
    try:
        rows = for_symbol(sym)
    except Exception:
        return 0.0
    s = 0.0
    for r in rows:
        w = _TIER_BONUS.get(r["tier"], 1)
        s += w if r["direction"] == "tailwind" else -w
    return max(-10.0, min(10.0, s))
