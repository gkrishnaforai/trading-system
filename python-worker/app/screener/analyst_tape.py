"""Analyst tape — event-level upgrades/downgrades/PT changes, for early
swing catches.

FMP's stable analyst endpoints (/analyst-grades) are 404 on this plan,
but the news-flavored feeds work: /grades-latest-news and
/price-target-latest-news are market-wide firehoses — two calls cover
~8h of tape, filtered to our universe. Every scoped row persists to
analyst_actions (fingerprint-deduped); grade+PT rows from the same firm
on the same symbol+hour merge into one alert — "BNP upgraded to
Outperform AND set PT $399" is one event, not two.

Direction: grades rows carry an `action` field (upgrade/downgrade/
initiated/hold). PT rows infer direction from the title verb and from
target-vs-price gap. Held-name downgrades alert HIGH — that's risk, not
noise.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_state: dict[str, Any] = {
    "running": False, "last_run_at": None, "captured": 0, "error": None}

_PT_VERBS = (
    (re.compile(r"\braised|\bboosted|\blifted|\bhiked|\bincreased|\bupped", re.I), "raise"),
    (re.compile(r"\blowered|\bcut|\btrimmed|\breduced|\bslashed", re.I), "lower"),
    (re.compile(r"\binitiated", re.I), "initiated"),
    (re.compile(r"\breiterat|\bmaintain|\bkeep", re.I), "maintained"),
)

_ACTION_DIR = {
    "upgrade": "POSITIVE", "raise": "POSITIVE",
    "initiated": "POSITIVE",
    "downgrade": "NEGATIVE", "lower": "NEGATIVE",
}

# Grade rows say "Exane BNP Paribas", PT rows say "BNP Paribas" — same
# firm, same event. Normalize for the merge key.
_FIRM_NOISE = {"exane", "llc", "inc", "co", "company", "capital",
               "securities", "financial", "group", "partners", "research",
               "markets", "lp", "ltd", "and", "the", "w"}

ALERT_RECENCY_H = 36   # older events persist to the tape but don't alert


def _firm_key(firm: str) -> str:
    toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", (firm or "").lower())
            .split() if t not in _FIRM_NOISE]
    return " ".join(sorted(toks))


def analyst_tape_status() -> dict[str, Any]:
    return dict(_state)


def _fp(sym: str, published: str, firm: str, kind: str) -> str:
    return ("atape:" + hashlib.sha1(
        f"{sym}|{published}|{firm}|{kind}".encode()).hexdigest()[:20])


def _pt_action(title: str) -> str:
    for rx, act in _PT_VERBS:
        if rx.search(title or ""):
            return act
    return "pt"


def _grade_row(r: dict) -> dict:
    from app.catalyst_intelligence.engine import grade_direction
    action = (r.get("action") or "").lower() or "grade"
    ranked = grade_direction(r.get("previousGrade"), r.get("newGrade"))
    if ranked and ranked != action:
        # the observed transition beats the feed label — Underperform→Hold
        # arriving as "downgrade" is an upgrade
        action = ranked
    return {
        "kind": "grade", "action": action,
        "firm": r.get("gradingCompany"),
        "analyst": None,
        "prev_grade": r.get("previousGrade"),
        "new_grade": r.get("newGrade"),
        "price_target": None,
        "priceWhenPosted": r.get("priceWhenPosted"),
        "title": r.get("newsTitle"),
        "url": r.get("newsURL"),
    }


def _pt_row(r: dict) -> dict:
    title = r.get("newsTitle") or ""
    return {
        "kind": "pt", "action": _pt_action(title),
        "firm": r.get("analystCompany"),
        "analyst": r.get("analystName") or None,
        "prev_grade": None, "new_grade": None,
        "price_target": r.get("priceTarget"),
        "priceWhenPosted": r.get("priceWhenPosted"),
        "title": title, "url": r.get("newsURL"),
    }


def _merge(group: list[dict]) -> dict:
    """Same firm+symbol+hour across the two feeds = one event."""
    grade = next((g for g in group if g["kind"] == "grade"), None)
    pt = next((g for g in group if g["kind"] == "pt"), None)
    base = dict(grade or pt or group[0])
    if grade and pt:
        base["price_target"] = pt.get("price_target")
        base["analyst"] = pt.get("analyst")
        if pt.get("action") in ("raise", "lower"):
            base["pt_action"] = pt["action"]
    return base


def _persist_rows(rows: list[dict]) -> int:
    """Insert tape rows; mark is_new on ones that weren't deduped."""
    from app.database import db
    captured = 0
    for row in rows:
        firm = row.get("firm") or ""
        res = db.execute_update(
            """
            INSERT INTO analyst_actions
                (symbol, published_at, kind, firm, analyst_name, action,
                 prev_grade, new_grade, price_target, price_when_posted,
                 title, url, fingerprint)
            VALUES (:s,:ts,:k,:f,:an,:a,:pg,:ng,:pt,:pw,:t,:u,:fp)
            ON CONFLICT (fingerprint) DO NOTHING
            """,
            {"s": row["symbol"], "ts": row["published"],
             "k": row["kind"], "f": firm, "an": row.get("analyst"),
             "a": row["action"], "pg": row.get("prev_grade"),
             "ng": row.get("new_grade"), "pt": row.get("price_target"),
             "pw": row.get("priceWhenPosted"), "t": row.get("title"),
             "u": row.get("url"),
             "fp": _fp(row["symbol"], row["published"], firm, row["kind"])})
        if res:
            row["is_new"] = True
            captured += 1
    return captured


def _rows_for_symbol(fmp, symbol: str) -> list[dict]:
    """Per-symbol deep pull — both feeds' full per-symbol history."""
    rows: list[dict] = []
    for r in fmp.get_grades_news(symbol) or []:
        if r.get("publishedDate"):
            rows.append({**_grade_row(r), "symbol": symbol,
                         "published": r["publishedDate"]})
    for r in fmp.get_price_target_news(symbol) or []:
        if r.get("publishedDate"):
            rows.append({**_pt_row(r), "symbol": symbol,
                         "published": r["publishedDate"]})
    return rows


async def run_analyst_tape(symbol: Optional[str] = None) -> dict[str, Any]:
    """Poll the two firehoses, persist scoped rows, alert on events.
    With `symbol`, deep-pull that name's full per-symbol history instead
    (backfill / drill-down)."""
    from app.alerts import scanner as alert_scanner
    from app.alerts.models import AlertItem
    from app.providers.financial_modeling_prep.client import EnhancedFMPClient
    from app.screener.pt_watch import _universe_symbols

    if _state["running"]:
        return {"status": "already_running"}
    _state.update(running=True, error=None)
    try:
        fmp = EnhancedFMPClient.from_settings()
        scope = _universe_symbols()
        if symbol:
            scope.setdefault(symbol, {})
            rows = await asyncio.to_thread(_rows_for_symbol, fmp, symbol)
        else:
            grades, pts = await asyncio.gather(
                asyncio.to_thread(fmp.get_grades_latest_news, 100),
                asyncio.to_thread(fmp.get_price_target_latest_news, 100))
            rows = []
            for r in grades or []:
                sym = r.get("symbol")
                if sym and sym in scope and r.get("publishedDate"):
                    rows.append({**_grade_row(r), "symbol": sym,
                                 "published": r["publishedDate"]})
            for r in pts or []:
                sym = r.get("symbol")
                if sym and sym in scope and r.get("publishedDate"):
                    rows.append({**_pt_row(r), "symbol": sym,
                                 "published": r["publishedDate"]})

        captured = _persist_rows(rows)

        # roundup detection — a single article emitting actions for ≥2
        # distinct firms on the same symbol is a recap (TheFly's daily
        # "top analyst calls" lists boilerplate ratings: "KeyBanc OW→UW"
        # rows that aren't fresh events). They persist to the tape for
        # history but must not alert — a fake downgrade vetoes real ones.
        url_firms: dict[tuple, set] = {}
        for row in rows:
            if row.get("url"):
                url_firms.setdefault(
                    (row["symbol"], row["url"]), set()
                ).add(_firm_key(row.get("firm") or ""))
        for row in rows:
            row["roundup"] = len(url_firms.get(
                (row["symbol"], row.get("url") or "")) or set()) >= 2

        # merge same firm+symbol+hour into single alert events; only
        # recent events alert — backfilled history stays on the tape
        groups: dict[tuple, list[dict]] = {}
        now_ts = datetime.now(timezone.utc).timestamp()
        for row in rows:
            if not row.get("is_new") or row.get("roundup"):
                continue
            try:
                pub_ts = datetime.fromisoformat(
                    row["published"].replace("Z", "+00:00")).timestamp()
            except Exception:
                pub_ts = now_ts
            if now_ts - pub_ts > ALERT_RECENCY_H * 3600:
                continue
            hour = (row["published"] or "")[:13]
            key = (row["symbol"], _firm_key(row.get("firm") or ""), hour)
            groups.setdefault(key, []).append(row)

        alerts: list[AlertItem] = []
        for (sym, _firm, _h), grp in groups.items():
            ev = _merge(grp)
            action = ev.get("action") or "pt"
            direction = _ACTION_DIR.get(action, "NEUTRAL")
            flags = scope.get(sym) or {}
            held = bool(flags.get("in_portfolio"))
            watched = bool(flags.get("in_watchlist"))
            firm = ev.get("firm") or "?"
            bits = []
            if ev.get("new_grade"):
                bits.append(f"{ev.get('prev_grade') or '?'} → "
                            f"{ev['new_grade']}")
            if ev.get("price_target"):
                bits.append(f"PT ${ev['price_target']:g}")
            gap = (ev["price_target"] / ev["priceWhenPosted"] - 1
                   if ev.get("price_target") and ev.get("priceWhenPosted")
                   else None)
            if gap is not None:
                bits.append(f"({gap:+.0%} vs px)")
            high = (held or watched or direction != "NEUTRAL") and bool(
                ev.get("new_grade") or ev.get("price_target"))
            alerts.append(AlertItem(
                symbol=sym, event_type="analyst_action",
                direction=direction,
                materiality=("HIGH" if held else "MODERATE" if watched
                             else "MODERATE") if high else "LOW",
                title=f"{sym}: {firm} {action} — " + ", ".join(bits)
                      if bits else f"{sym}: {firm} {action} — {ev.get('title') or ''}",
                detail={
                    "bucket": "actionable", "kind": "analyst",
                    "firm": firm, "analyst": ev.get("analyst"),
                    "action": action, "prev_grade": ev.get("prev_grade"),
                    "new_grade": ev.get("new_grade"),
                    "price_target": ev.get("price_target"),
                    "price_when_posted": ev.get("priceWhenPosted"),
                    "target_gap_pct": round(gap * 100, 1)
                    if gap is not None else None,
                    "published": ev.get("published") or grp[0]["published"],
                    "title": ev.get("title"), "url": ev.get("url"),
                },
                fingerprint=("atape:" + hashlib.sha1(
                    f"{sym}|{firm}|{grp[0]['published']}".encode()
                ).hexdigest()[:20]),
                source="analyst_tape",
                source_timestamp=datetime.now(timezone.utc),
                in_portfolio=held, in_watchlist=watched,
                priority_score=None,
            ))

        for a in alerts:
            a.priority_score = alert_scanner.priority_score(a)
        inserted, skipped = alert_scanner.persist(alerts)
        _state.update(captured=captured,
                      last_run_at=datetime.now(timezone.utc).isoformat())
        return {"status": "completed", "feed_rows": len(rows),
                "captured": captured, "alerts": inserted,
                "skipped": skipped}
    except Exception as exc:
        logger.error("analyst tape failed: %s", exc, exc_info=True)
        _state["error"] = str(exc)
        return {"status": "error", "error": str(exc)}
    finally:
        _state["running"] = False


def analyst_tape_board(hours: int = 48, limit: int = 60) -> dict[str, Any]:
    """Recent analyst actions on universe symbols, newest first."""
    from app.database import db
    from app.screener.pt_watch import _universe_symbols
    try:
        scope = _universe_symbols()
    except Exception:
        scope = {}
    rows = db.execute_query(
        """
        SELECT symbol, published_at, kind, firm, analyst_name, action,
               prev_grade, new_grade, price_target, price_when_posted,
               title, url
        FROM analyst_actions
        WHERE published_at > now() - make_interval(hours => :h)
          AND symbol = ANY(:syms)
        ORDER BY published_at DESC LIMIT :n
        """,
        {"h": hours, "syms": list(scope) or ["__none__"], "n": limit})
    out = []
    for r in rows:
        pt, pw = r.get("price_target"), r.get("price_when_posted")
        gap = float(pt) / float(pw) - 1 if pt and pw else None
        flags = scope.get(r["symbol"]) or {}
        out.append({
            "symbol": r["symbol"], "published": str(r["published_at"]),
            "kind": r["kind"], "firm": r.get("firm"),
            "analyst": r.get("analyst_name"), "action": r.get("action"),
            "prev_grade": r.get("prev_grade"), "new_grade": r.get("new_grade"),
            "price_target": float(pt) if pt else None,
            "target_gap_pct": round(gap * 100, 1) if gap is not None else None,
            "title": r.get("title"), "url": r.get("url"),
            "in_portfolio": bool(flags.get("in_portfolio")),
            "in_watchlist": bool(flags.get("in_watchlist")),
        })
    return {"actions": out, "count": len(out), "hours": hours}
