"""Post engine — deterministic content from journaled data.

Every post type is built from rows the system already journals —
regime snapshots, board decisions + graded outcomes, event-day
verdicts, stock health cards. No LLM required: the evidence is the
content. Slugs are idempotent (kind-date[-sym]) so re-runs upsert.

Post types
  daily_brief   — the morning read: posture, capex, board, calendar
  receipts      — what the board called and how it graded
  mover         — "why <sym> moved" from the health card
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _q(sql: str, params: dict | None = None) -> list[dict]:
    from app.database import db
    return db.execute_query(sql, params or {})


def _publish(slug: str, kind: str, title: str, dek: str,
             body: str, symbols: list[str], payload: dict) -> bool:
    from app.database import db
    try:
        db.execute_update(
            """
            INSERT INTO blog_posts
                (slug, kind, title, dek, body_md, symbols, payload)
            VALUES (:s, :k, :t, :d, :b, :sy, CAST(:p AS jsonb))
            ON CONFLICT (slug) DO UPDATE SET
                title=EXCLUDED.title, dek=EXCLUDED.dek,
                body_md=EXCLUDED.body_md, symbols=EXCLUDED.symbols,
                payload=EXCLUDED.payload, published_at=now()
            """,
            {"s": slug, "k": kind, "t": title, "d": dek, "b": body,
             "sy": symbols, "p": json.dumps(payload, default=str)})
        return True
    except Exception as exc:
        logger.warning("publish %s failed: %s", slug, exc)
        return False


# ---------------------------------------------------------------- daily brief

def daily_brief(today: date | None = None) -> Optional[dict]:
    """The morning read — posture, capex cycle, the board, the calendar.
    Rendered from journaled rows, not prose invented at write time."""
    today = today or date.today()
    slug = f"daily-brief-{today.isoformat()}"

    posture = _q(
        "SELECT stance, vix, spy_vs_200, payload FROM regime_snapshots"
        " WHERE as_of=:d", {"d": today})
    morning = _q(
        "SELECT regime, ai_regime, score, confidence, buckets"
        " FROM morning_regime_snapshots ORDER BY as_of DESC LIMIT 1")
    board = _q(
        "SELECT symbol, action, instrument, score FROM board_decisions"
        " WHERE as_of=:d ORDER BY score DESC", {"d": today})
    regime_row = morning[0] if morning else {}
    buckets = regime_row.get("buckets") or {}
    if isinstance(buckets, str):
        try:
            buckets = json.loads(buckets)
        except Exception:
            buckets = {}
    capex = ((buckets.get("structural") or {}).get("capex")
             if isinstance(buckets, dict) else None) or {}

    stance = (posture[0]["stance"] if posture else None) or "—"
    regime = regime_row.get("regime") or "—"
    score = regime_row.get("score")

    title = f"Market regime: {str(stance).title()} — {str(regime).replace('_', ' ')}"
    dek = (f"Today's tape read, the AI-capex cycle underneath it, and "
           f"what the board is doing about it — {today:%B %d, %Y}.")

    L: list[str] = []
    L.append(f"*Journaled at {datetime.now(timezone.utc):%H:%M} UTC. "
             "Advisory — deterministic reads, human decides.*\n")
    L.append("## The tape")
    if posture:
        p = posture[0]
        L.append(
            f"Posture is **{stance}**. VIX {p.get('vix') or '—'}, "
            f"SPY vs its 200-day {round((p.get('spy_vs_200') or 0) * 100, 1)}%. "
            f"Regime `{regime}`"
            + (f" scored {score}/100" if score is not None else "")
            + (f" with {regime_row['confidence']}% confidence."
               if regime_row.get("confidence") is not None else "."))
    else:
        L.append("No regime snapshot journaled today — the morning job "
                 "hasn't run or the tape feed is down.")

    if capex:
        L.append("\n## AI capex watch")
        L.append(
            f"The cycle sits at **{capex.get('score', '—')}/100 "
            f"({capex.get('band', '—')})**"
            + (f", {capex['n_elevated']}/8 legs elevated" if capex.get(
                "n_elevated") is not None else "") + ".")
        if capex.get("guidance"):
            L.append(str(capex["guidance"]))
        comp = capex.get("components") or {}
        if isinstance(comp, dict) and comp:
            legs = ", ".join(
                f"{k.replace('_', ' ')} {v}" for k, v in comp.items()
                if isinstance(v, (int, float)) and v >= 50)
            if legs:
                L.append(f"Elevated legs: {legs}.")

    if board:
        L.append("\n## On the board")
        exits = [r for r in board if r["action"] in ("EXIT", "TRIM")]
        puts = [r for r in board if r["action"] == "PUT"]
        buys = [r for r in board if r["action"] in ("ACCUMULATE", "BOUNCE")]
        if exits:
            L.append("**Trim/exit:** " + ", ".join(
                f"{r['symbol']} ({r['instrument'] or 'stock'})"
                for r in exits))
        if puts:
            L.append("**Puts:** " + ", ".join(r["symbol"] for r in puts))
        if buys:
            L.append("**Deploy:** " + ", ".join(
                f"{r['symbol']} ({r['action'].lower()})" for r in buys))
    else:
        L.append("\n## On the board\nNo picks journaled today — a quiet "
                 "board is itself information: the evidence didn't meet "
                 "the bar.")

    L.append("\n---\n*Every pick above is journaled and graded on the "
             "[receipts ledger](/receipts) — including the misses.*")

    payload = {"stance": stance, "regime": regime, "score": score,
               "capex": capex, "board_n": len(board)}
    if _publish(slug, "daily_brief", title, dek, "\n".join(L),
                [r["symbol"] for r in board[:10]], payload):
        return {"slug": slug, "title": title}
    return None


# ------------------------------------------------------------------ receipts

def receipts_recap(days: int = 30) -> Optional[dict]:
    """The accountability post — graded calls from the ledger."""
    rows = _q(
        """
        SELECT d.symbol, d.action, d.instrument, d.as_of, d.price,
               o.horizon_days, o.ret_pct
        FROM board_decisions d
        JOIN board_outcomes o ON o.decision_id = d.id
        WHERE d.as_of > now()::date - :days AND o.horizon_days = 20
        ORDER BY d.as_of DESC
        """, {"days": days})
    if not rows:
        return None
    wins = [r for r in rows if (r.get("ret_pct") or 0) > 0]
    losses = [r for r in rows if (r.get("ret_pct") or 0) <= 0]
    avg = sum(r["ret_pct"] for r in rows) / len(rows)
    hit = round(100 * len(wins) / len(rows))
    top = sorted(rows, key=lambda r: -(r["ret_pct"] or 0))[:5]
    bottom = sorted(rows, key=lambda r: (r["ret_pct"] or 0))[:5]

    title = f"Receipts: {hit}% hit rate on {len(rows)} graded calls"
    dek = (f"The last {days} days of board picks, graded at 20 sessions "
           f"— best and worst both shown.")
    L: list[str] = []
    L.append(f"{len(rows)} calls journaled over the last {days} days "
             f"are now graded at the 20-session mark. Average "
             f"direction-adjusted return **{avg:+.1f}%**, hit rate "
             f"**{hit}%**.\n")
    L.append("## What worked")
    for r in top:
        L.append(f"- **{r['symbol']}** {r['action'].lower()} "
                 f"({r['as_of']}) → **{r['ret_pct']:+.1f}%**")
    L.append("\n## What didn't")
    for r in bottom:
        L.append(f"- **{r['symbol']}** {r['action'].lower()} "
                 f"({r['as_of']}) → **{r['ret_pct']:+.1f}%**")
    L.append("\nThe misses stay on the page. A ledger you can edit "
             "isn't a ledger — the full record lives on "
             "[/receipts](/receipts).")

    slug = f"receipts-{date.today().isoformat()}"
    if _publish(slug, "receipts", title, dek, "\n".join(L),
                list({r["symbol"] for r in rows})[:12],
                {"n": len(rows), "hit": hit, "avg": round(avg, 2)}):
        return {"slug": slug, "title": title}
    return None


# --------------------------------------------------------------------- mover

def mover_post(sym: str, card: dict) -> Optional[dict]:
    """'Why <SYM> moved' — the health card rendered as an explainer.
    Called lazily from the posts endpoint when a mover request lands."""
    s = sym.upper()
    spot = card.get("spot")
    fv_up = card.get("fv_upside_pct")
    verdict = (card.get("verdict") or {})
    fund = card.get("fundamental") or {}
    tech = card.get("technical") or {}
    fv = card.get("fv") or {}
    capex = card.get("capex") or {}

    title = f"{s}: what the tape and the valuation are saying"
    dek = f"{card.get('name') or s} — regime context, fair value, and the readiness lanes."
    L: list[str] = []
    L.append(f"**{card.get('name') or s}** trades at "
             f"${float(spot):,.2f}." if spot else f"**{s}**")
    if fv_up is not None:
        L.append(f"Our expected fair value sits "
                 f"{'below' if fv_up < 0 else 'above'} spot — "
                 f"**{fv_up:+.1f}%**."
                 + (f" Expected ${float(fv['expected']):,.2f}."
                    if fv.get("expected") else ""))
    if verdict.get("verdict"):
        L.append(f"\n## The call\n{verdict['verdict']}")
        for w in (verdict.get("why") or [])[:5]:
            L.append(f"- {w}")
    L.append("\n## Evidence")
    L.append(f"- Momentum: `{tech.get('state') or '—'}` "
             f"(scored {str(tech.get('as_of'))[:10]})")
    L.append(f"- Fundamentals: `{fund.get('state') or '—'}`"
             + (f" — provider data {fund['data_as_of']}"
                if fund.get("data_as_of") else ""))
    if capex:
        L.append(f"- AI capex: {capex.get('exposure') or 'tracked'} — "
                 f"cycle {capex.get('band')} {capex.get('score')}/100")
    L.append("\n---\n*Full card: [/stock?sym=" + s + "]"
             f"(/stock?sym={s}). Advisory, deterministic.*")

    slug = f"mover-{s.lower()}-{date.today().isoformat()}"
    if _publish(slug, "mover", title, dek, "\n".join(L), [s],
                {"sym": s, "fv_up": fv_up}):
        return {"slug": slug, "title": title}
    return None


# ------------------------------------------------------------------ listings

def list_posts(kind: str | None = None, limit: int = 50) -> list[dict]:
    if kind:
        rows = _q(
            "SELECT slug, kind, title, dek, symbols, as_of, published_at"
            " FROM blog_posts WHERE kind=:k"
            " ORDER BY published_at DESC LIMIT :n",
            {"k": kind, "n": limit})
    else:
        rows = _q(
            "SELECT slug, kind, title, dek, symbols, as_of, published_at"
            " FROM blog_posts ORDER BY published_at DESC LIMIT :n",
            {"n": limit})
    for r in rows:
        r["as_of"] = str(r.get("as_of") or "")[:10]
        r["published_at"] = str(r.get("published_at") or "")[:19]
    return rows


def get_post(slug: str) -> Optional[dict]:
    rows = _q(
        "SELECT slug, kind, title, dek, body_md, symbols, tier, as_of,"
        " published_at FROM blog_posts WHERE slug=:s", {"s": slug})
    if not rows:
        return None
    r = rows[0]
    r["as_of"] = str(r.get("as_of") or "")[:10]
    r["published_at"] = str(r.get("published_at") or "")[:19]
    return r


def run() -> dict:
    """Generate today's posts — idempotent. Called lazily by /posts
    when today's brief is missing, and by the nightly job."""
    out = {}
    try:
        r = daily_brief()
        if r:
            out["daily_brief"] = r["slug"]
    except Exception as exc:
        logger.warning("daily brief failed: %s", exc)
    try:
        r = receipts_recap()
        if r:
            out["receipts"] = r["slug"]
    except Exception as exc:
        logger.warning("receipts recap failed: %s", exc)
    return out
