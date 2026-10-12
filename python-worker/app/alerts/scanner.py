"""Deterministic catalyst scanner: canonical deltas -> deduplicated alert items.

Three collectors over the universe (portfolio ∪ watchlist):
  1. analyst grade changes   (grade_change_events)
  2. EPS estimate revisions  (fundamental_estimate_snapshots diffs)
  3. catalyst snapshots      (catalyst_intelligence.assess_catalyst — news/earnings)

Dedup is by fingerprint so a scan window can be replayed safely.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.catalyst_intelligence.engine import assess_catalyst, classify_headline
from app.database import db
from app.market_data import MarketDataService

from .models import AlertItem

logger = logging.getLogger(__name__)

_MATERIALITY_SCORE = {"HIGH": 100.0, "MODERATE": 60.0, "LOW": 30.0}
EPS_REVISION_MIN_PCT = 5.0
EPS_REVISION_HIGH_PCT = 10.0


def universe() -> dict[str, dict]:
    """symbol -> {'in_portfolio': bool, 'in_watchlist': bool, 'position_qty': float}"""
    rows = db.execute_query(
        """
        SELECT s.symbol,
               bool_or(pp.quantity > 0) AS in_portfolio,
               COALESCE(sum(pp.quantity) FILTER (WHERE pp.quantity > 0), 0) AS qty
        FROM stocks s
        JOIN portfolio_positions pp ON pp.stock_id = s.id
        GROUP BY s.symbol
        UNION ALL
        SELECT s.symbol, false AS in_portfolio, 0 AS qty
        FROM stocks s
        JOIN watchlist_stocks ws ON ws.stock_id = s.id
        GROUP BY s.symbol
        """
    )
    result: dict[str, dict] = {}
    for row in rows:
        symbol = (row["symbol"] or "").strip()
        if not symbol or not any(c.isalpha() for c in symbol):
            continue
        entry = result.setdefault(symbol, {"in_portfolio": False, "in_watchlist": False, "position_qty": 0.0})
        if row["in_portfolio"]:
            entry["in_portfolio"] = True
            entry["position_qty"] = float(row["qty"] or 0)
        else:
            entry["in_watchlist"] = True
    return result


_DEMOTED_CACHE: dict[str, object] = {"at": None, "kinds": set()}
_DEMOTED_TTL_S = 6 * 3600


def _demoted_kinds() -> set[str]:
    """Headline kinds empirically bad at predicting moves — auto-demoted to
    the news bucket. Source: alert_kind_stats (forward returns after each
    alert). Bounded: needs n>=20 samples and <30% 5d hit rate; refreshed at
    most every 6h so a scan doesn't re-query per symbol."""
    import time
    now = time.time()
    if _DEMOTED_CACHE["at"] and now - _DEMOTED_CACHE["at"] < _DEMOTED_TTL_S:
        return _DEMOTED_CACHE["kinds"]  # type: ignore[return-value]
    kinds: set[str] = set()
    try:
        rows = db.execute_query(
            """SELECT kind, n, win_rate FROM alert_kind_stats
               WHERE horizon_days = 5 AND n >= 20 AND win_rate < 0.30""")
        kinds = {r["kind"] for r in rows}
    except Exception:
        kinds = set()
    _DEMOTED_CACHE.update(at=now, kinds=kinds)
    return kinds


def priority_score(item: AlertItem) -> float:
    score = _MATERIALITY_SCORE.get(item.materiality, 30.0)
    if item.in_portfolio:
        score += 30.0
        if item.direction == "NEGATIVE":
            score += 50.0  # trim-risk on a held position outranks everything
    elif item.in_watchlist:
        score += 15.0
    # Directional analyst actions (upgrade/downgrade/PT change) are the
    # highest-signal headline class — outrank same-tier generic catalysts
    if (item.event_type == "analyst_action"
            and item.direction in {"POSITIVE", "NEGATIVE"}):
        score += 25.0
    # Market-confirmed reaction outranks an unconfirmed headline match
    if (item.detail or {}).get("reaction_state") in {"POSITIVE_CONFIRMED", "NEGATIVE_CONFIRMED"}:
        score += 15.0
    return score


def collect_analyst_events(scope: dict[str, dict], lookback_days: float = 0.5) -> list[AlertItem]:
    if not scope:
        return []
    cutoff = date.today() - timedelta(days=lookback_days)
    rows = db.execute_query(
        """
        SELECT gce.id, gce.symbol, gce.grading_company, gce.previous_grade,
               gce.new_grade, gce.grade_date, gce.event_type, gce.price_at_grade
        FROM grade_change_events gce
        WHERE gce.event_type IN ('upgrade', 'downgrade')
          AND gce.grade_date >= :cutoff
          AND gce.symbol = ANY(:symbols)
        ORDER BY gce.grade_date DESC
        """,
        {"cutoff": cutoff, "symbols": list(scope)},
    )
    items = []
    for row in rows:
        direction = "POSITIVE" if row["event_type"] == "upgrade" else "NEGATIVE"
        items.append(AlertItem(
            symbol=row["symbol"],
            event_type=f"analyst_{row['event_type']}",
            direction=direction,
            materiality="MODERATE",
            title=f"{row['event_type'].capitalize()}: {row['grading_company']} "
                  f"{row['previous_grade']} → {row['new_grade']}",
            detail={
                "grading_company": row["grading_company"],
                "previous_grade": row["previous_grade"],
                "new_grade": row["new_grade"],
                "grade_date": row["grade_date"].isoformat() if row["grade_date"] else None,
                "price_at_grade": float(row["price_at_grade"]) if row["price_at_grade"] is not None else None,
            },
            fingerprint=f"grade:{row['id']}",
            source="grade_change_events",
            source_timestamp=datetime.combine(row["grade_date"], datetime.min.time(), tzinfo=timezone.utc) if row["grade_date"] else None,
        ))
    return items


def collect_eps_revisions(scope: dict[str, dict]) -> list[AlertItem]:
    """Latest vs previous estimate snapshot per (symbol, fiscal year/period)."""
    if not scope:
        return []
    rows = db.execute_query(
        """
        WITH ranked AS (
            SELECT symbol, as_of_date, fiscal_period, fiscal_year,
                   eps_estimate, analysts_up, analysts_down, provider,
                   lag(eps_estimate) OVER (
                       PARTITION BY symbol, fiscal_period, fiscal_year
                       ORDER BY as_of_date
                   ) AS prev_eps_estimate
            FROM fundamental_estimate_snapshots
            WHERE symbol = ANY(:symbols) AND eps_estimate IS NOT NULL
        )
        SELECT * FROM ranked
        WHERE prev_eps_estimate IS NOT NULL
          AND prev_eps_estimate <> 0
          AND abs((eps_estimate - prev_eps_estimate) / abs(prev_eps_estimate)) * 100 >= :min_pct
        ORDER BY as_of_date DESC
        """,
        {"symbols": list(scope), "min_pct": EPS_REVISION_MIN_PCT},
    )
    items = []
    for row in rows:
        prev, cur = float(row["prev_eps_estimate"]), float(row["eps_estimate"])
        delta_pct = (cur - prev) / abs(prev) * 100
        items.append(AlertItem(
            symbol=row["symbol"],
            event_type="eps_revision",
            direction="POSITIVE" if delta_pct > 0 else "NEGATIVE",
            materiality="HIGH" if abs(delta_pct) >= EPS_REVISION_HIGH_PCT else "MODERATE",
            title=f"EPS estimate revised {delta_pct:+.1f}% "
                  f"({row['fiscal_period']} FY{row['fiscal_year']})",
            detail={
                "fiscal_period": row["fiscal_period"],
                "fiscal_year": row["fiscal_year"],
                "eps_estimate": cur,
                "prev_eps_estimate": prev,
                "delta_pct": round(delta_pct, 2),
                "analysts_up": row["analysts_up"],
                "analysts_down": row["analysts_down"],
                "provider": row["provider"],
            },
            fingerprint=f"eps:{row['symbol']}:{row['as_of_date']}:{row['fiscal_year']}:{row['fiscal_period']}",
            source="fundamental_estimate_snapshots",
            source_timestamp=datetime.combine(row["as_of_date"], datetime.min.time(), tzinfo=timezone.utc) if row["as_of_date"] else None,
        ))
    return items


NEWS_FRESHNESS_HOURS = 12
EARNINGS_RECENT_DAYS = 2


def _published_within(published_at: Optional[str], hours: int) -> bool:
    if not published_at:
        return False
    try:
        ts = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts <= timedelta(hours=hours)
    except (ValueError, TypeError):
        return False


async def collect_catalysts(
    scope: dict[str, dict],
    service: Optional[MarketDataService] = None,
    llm: Optional[object] = None,
    news_freshness_hours: int = NEWS_FRESHNESS_HOURS,
    earnings_recent_days: int = EARNINGS_RECENT_DAYS,
) -> tuple[list[AlertItem], list[str]]:
    """Per-event catalyst alerts via assess_catalyst.

    Freshness rules (so scheduled rescans don't re-alert stale events):
      - news trigger: >=2 same-direction headlines published within `news_freshness_hours`
      - surprise trigger: earnings event dated within `earnings_recent_days`
      - imminent trigger: earnings <=2 days out (forward-looking, fine)
      - confirmed trigger: today's price/volume reaction
    Fingerprint is per-event (hash of triggers), not per-day — a genuinely new
    same-direction catalyst later today still produces a new alert.
    """
    svc = service or MarketDataService()
    items: list[AlertItem] = []
    errors: list[str] = []
    today = date.today()

    async def assess(symbol: str) -> Optional[AlertItem]:
        try:
            earnings, news = await asyncio.gather(
                svc.get_earnings(symbol), svc.get_news(symbol, limit=10)
            )
            earnings_list = list(earnings)
            snap = assess_catalyst(symbol, earnings_list, news)
            if snap.direction.value not in {"POSITIVE", "NEGATIVE"}:
                return None

            # Fresh headlines in the 12h window (not the engine's 7d context).
            # Keep (title, direction) pairs — actionable kinds can fire on a
            # single headline even when the headline's own direction is MIXED
            # or NEUTRAL ("PT hike" has no directional keyword but IS the event).
            fresh = [
                n for n in snap.recent_news
                if _published_within(n.get("published_at"), news_freshness_hours)
            ]
            fresh_pairs = [
                (n["title"], n.get("headline_direction")) for n in fresh]
            min_headlines = 2
            classification_source = "keyword"

            # Optional LLM pass: material same-direction verdicts on fresh titles.
            # Interpretation only — it cannot raise materiality above MODERATE.
            if fresh and llm is not None and llm.enabled:
                verdicts = llm.classify(symbol, [n["title"] for n in fresh])
                if verdicts:
                    classification_source = "llm"
                    fresh_pairs = [
                        (v.title, snap.direction.value) for v in verdicts
                        if v.direction == snap.direction.value
                        and v.material and v.event_kind != "filler"
                    ]
                    min_headlines = 1
            # Surprise must come from an earnings event within `earnings_recent_days`
            last_report = max(
                (e.date for e in earnings_list if e.date and e.date <= today), default=None
            )
            surprise_fresh = (
                snap.eps_surprise_pct is not None
                and last_report is not None
                and (today - last_report).days <= earnings_recent_days
            )
            earnings_imminent = (
                snap.days_to_earnings is not None and snap.days_to_earnings <= 2
            )
            confirmed = snap.reaction_state in {
                "POSITIVE_CONFIRMED", "NEGATIVE_CONFIRMED",
            }

            # Classify fresh headlines — which kind of event, and whether
            # it belongs to the actionable feed or the news bucket.
            # Kinds empirically poor at predicting moves get auto-demoted
            # to news by alert_kind_stats (bounded: needs n>=20 samples).
            demoted = _demoted_kinds()
            classified = [(t, d, *classify_headline(t))
                          for t, d in fresh_pairs]
            same_dir = [t for t, d, k, b in classified
                        if d == snap.direction.value]
            # Actionable kinds (PT hike, M&A, FDA...) fire on ONE headline —
            # the kind IS the signal; a direction keyword list can't capture
            # "price target hike". Only veto when the headline's own
            # direction contradicts the snap's (e.g. downgrade on a green day).
            _DOWN = ("downgrade", "cuts", "lowered", "sell rating",
                     "underperform", "underweight")
            _UP = ("upgrade", "raises", "hike", "initiat", "buy rating",
                   "outperform", "overweight")

            def _contradicts(t: str) -> bool:
                tl = t.lower()
                down = any(w in tl for w in _DOWN)
                up = any(w in tl for w in _UP)
                return ((snap.direction.value == "POSITIVE" and down and not up)
                        or (snap.direction.value == "NEGATIVE" and up and not down))

            sig_titles = [t for t, d, k, b in classified
                          if b == "actionable" and k not in demoted
                          and not _contradicts(t)]
            live_sig = sorted({k for t, d, k, b in classified
                               if b == "actionable" and k not in demoted
                               and not _contradicts(t)})

            triggers: list[str] = []
            if surprise_fresh:
                triggers.append(f"eps:{snap.eps_surprise_pct:.0f}:{last_report}")
            if earnings_imminent:
                triggers.append(f"due:{snap.next_earnings_date}")
            if confirmed:
                triggers.append(f"rxn:{snap.reaction_state}")
            if len(same_dir) >= min_headlines or sig_titles:
                trig_titles = sorted(set(same_dir) | set(sig_titles))
                triggers.append(
                    f"news:{hashlib.sha1('|'.join(trig_titles).encode()).hexdigest()[:12]}"
                )
            if not triggers:
                return None

            bucket = ("actionable"
                      if (surprise_fresh or earnings_imminent or confirmed
                          or live_sig)
                      else "tape" if any(b == "tape" for _, _, _, b in classified)
                      else "news")
            materiality = (
                "HIGH" if (surprise_fresh or earnings_imminent or confirmed)
                else "MODERATE" if live_sig
                else "LOW")
            # Title + kind come from the most material headline — the
            # actionable event if one exists, else the first same-direction
            # title. Never let a "Surges 6%" recap title an upgrade alert.
            kind = (live_sig[0] if live_sig
                    else classified[0][2] if classified
                    else snap.catalyst_type.lower())
            title_src = (sig_titles[0] if sig_titles
                         else same_dir[0] if same_dir else None)

            if surprise_fresh:
                title = f"EPS surprise {snap.eps_surprise_pct:+.1f}% (recent earnings)"
            elif earnings_imminent:
                title = f"earnings in {snap.days_to_earnings} day(s)"
            elif title_src:
                title = title_src
            else:
                title = snap.reasons[0] if snap.reasons else "catalyst detected"

            fp_hash = hashlib.sha1(
                f"{symbol}|{snap.direction.value}|{'|'.join(triggers)}".encode()
            ).hexdigest()[:16]
            return AlertItem(
                symbol=symbol,
                event_type="catalyst",
                direction=snap.direction.value,
                materiality=materiality,
                title=title[:200],
                detail={
                    "catalyst_type": snap.catalyst_type,
                    "severity": snap.severity.value,
                    "eps_surprise_pct": snap.eps_surprise_pct,
                    "last_report_date": last_report.isoformat() if last_report else None,
                    "days_to_earnings": snap.days_to_earnings,
                    "news_count": snap.news_count,
                    "fresh_headlines": len(fresh_pairs),
                    "reaction_state": snap.reaction_state,
                    "new_entry_policy": snap.new_entry_policy,
                    "triggers": triggers,
                    "classification_source": classification_source,
                    "bucket": bucket,
                    "kind": kind,
                    "headline_kinds": sorted({k for _, _, k, _ in classified}),
                    "demoted_kinds": sorted(demoted),
                    "reasons": snap.reasons,
                    "providers": snap.providers,
                },
                fingerprint=f"catalyst:{fp_hash}",
                source="catalyst_intelligence",
                source_timestamp=datetime.now(timezone.utc),
            )
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            return None

    results = await asyncio.gather(*(assess(sym) for sym in sorted(scope)))
    items.extend(r for r in results if r is not None)
    return items, errors


def collect_movers(scope: dict[str, dict]) -> list[AlertItem]:
    """Universe symbols appearing on FMP's biggest movers / most-active lists.

    A portfolio or watchlist name moving on market-leading volume is the
    classic "something is happening" signal — feed for gap-and-go / RVOL
    day-trading screens and a risk flag for held positions.
    """
    if not scope:
        return []
    try:
        from app.providers.financial_modeling_prep.client import EnhancedFMPClient
        raw = EnhancedFMPClient.from_settings().get_market_movers()
    except Exception as exc:
        logger.warning("movers collection failed: %s", exc)
        return []
    items = []
    today = date.today()
    for kind in ("gainers", "losers", "most_active"):
        for r in raw.get(kind) or []:
            sym = str(r.get("symbol") or "").upper()
            if sym not in scope:
                continue
            chg = float(r.get("changesPercentage") or 0)
            direction = "NEGATIVE" if chg < 0 else "POSITIVE"
            items.append(AlertItem(
                symbol=sym,
                event_type="mover",
                direction=direction,
                materiality="HIGH" if abs(chg) >= 5 or kind == "most_active" else "MODERATE",
                title=f"{sym} on {kind.replace('_', ' ')} ({chg:+.1f}%)",
                detail={
                    "kind": kind, "change_pct": round(chg, 2),
                    "price": r.get("price"), "volume": r.get("volume"),
                },
                fingerprint=f"mover:{sym}:{today.isoformat()}:{kind}",
                source="fmp_market_movers",
            ))
    return items


def persist(items: list[AlertItem]) -> tuple[int, int]:
    """Insert new alerts; skip fingerprint duplicates. Returns (inserted, skipped)."""
    inserted = skipped = 0
    for item in items:
        row = db.execute_query(
            """
            INSERT INTO alert_items (
                symbol, event_type, direction, materiality, title, detail,
                fingerprint, source, source_timestamp,
                in_portfolio, in_watchlist, priority_score
            ) VALUES (
                :symbol, :event_type, :direction, :materiality, :title, CAST(:detail AS jsonb),
                :fingerprint, :source, :source_timestamp,
                :in_portfolio, :in_watchlist, :priority_score
            )
            ON CONFLICT (fingerprint) DO NOTHING
            RETURNING id
            """,
            {
                "symbol": item.symbol,
                "event_type": item.event_type,
                "direction": item.direction,
                "materiality": item.materiality,
                "title": item.title,
                "detail": json.dumps(item.detail),
                "fingerprint": item.fingerprint,
                "source": item.source,
                "source_timestamp": item.source_timestamp,
                "in_portfolio": item.in_portfolio,
                "in_watchlist": item.in_watchlist,
                "priority_score": item.priority_score,
            },
        )
        if row:
            item.id = row[0]["id"] if isinstance(row[0], dict) else str(row[0])
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


async def scan(
    service: Optional[MarketDataService] = None,
    lookback_days: float = 0.5,
    news_freshness_hours: int = NEWS_FRESHNESS_HOURS,
    portfolio_only: bool = False,
) -> tuple[list[AlertItem], int, list[str], int]:
    """Collect → annotate → score → persist. Returns (new_items, skipped, errors, scanned_count).

    portfolio_only narrows the universe to held names — the fast
    holdings-only pass."""
    scope = universe()
    if portfolio_only:
        scope = {s: f for s, f in scope.items() if f["in_portfolio"]}
    if not scope:
        return [], 0, [], 0

    from .llm_classifier import HeadlineClassifier
    analyst_items = collect_analyst_events(scope, lookback_days)
    eps_items = collect_eps_revisions(scope)
    catalyst_items, errors = await collect_catalysts(
        scope, service, llm=HeadlineClassifier(),
        news_freshness_hours=news_freshness_hours)
    mover_items = collect_movers(scope)

    all_items = analyst_items + eps_items + catalyst_items + mover_items
    for item in all_items:
        flags = scope.get(item.symbol, {})
        item.in_portfolio = flags.get("in_portfolio", False)
        item.in_watchlist = flags.get("in_watchlist", False)
        item.priority_score = priority_score(item)

    inserted, skipped = persist(all_items)
    new_items = [i for i in all_items if i.id]
    return new_items, skipped, errors, len(scope)
