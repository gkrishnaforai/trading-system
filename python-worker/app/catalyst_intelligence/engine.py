"""Deterministic catalyst intelligence from canonical news/earnings data."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from app.market_data.models import EarningsEvent, NewsItem

from .models import CatalystDirection, CatalystSeverity, CatalystSnapshot

_POSITIVE = ("beat", "raised", "upgrade", "contract", "partnership", "approval", "record", "growth", "bitcoin", "crypto", "tokenized", "exemption")
_NEGATIVE = ("miss", "cut", "downgrade", "lawsuit", "investigation", "recall", "warning", "layoff", "sells", "falls", "risk")

# Institutional-disclosure filler ("X Buys/Sells N Shares of Y", 13F filings,
# stake/position reports) — routine portfolio moves, not directional news.
_FILLER = re.compile(
    r"\b(buys|sells|acquires|trims|boosts|cuts|lowers|raises|lifts|"
    r"increases|decreases|discloses|sold|bought|purchased|acquired|"
    r"trimmed|boosted|lowered|lifted|increased|decreased|disclosed|"
    r"added|reduced|has|holds)\b[^.]{0,80}\bshares?\b"
    r"|\b13f\b"
    r"|\b(stake|position|holdings?)\s+(in|of)\b"
    r"|\bshares? of\b[^.]{0,60}\b(stake|position|filing)\b",
    re.IGNORECASE,
)


def is_filler_headline(title: str) -> bool:
    return bool(_FILLER.search(title or ""))


# ── Headline kind classifier ─────────────────────────────────────────────
# What actually moves a stock (research + desk consensus): earnings/guidance,
# analyst rating changes, M&A, regulatory decisions, material contracts,
# capital-return changes, dilution, C-suite exits, legal events, big layoffs.
# Everything else — opinion pieces, listicles, move recaps, awards, macro
# commentary, 13F stake noise — is context, not a catalyst: bucket "news".
_NOISE = re.compile(
    r"should (you|i|investors|we)\b|a (?:buy|sell|screaming buy)\b"
    r"|buy the dip|too late to|missed the (?:rally|boat)"
    r"|prediction:|forecast:|here'?s why|why .*stock"
    r"|\b\d+ (?:stocks|etfs|growth stocks|reasons|ways|things)\b"
    r"|stocks? to (?:buy|watch|own|sell|avoid)|top \d+|best .*stocks?"
    r"|named a leader|marketscape|recognized as|honored|award"
    r"|will be worth|could be worth|millionaire|regret|love this"
    # plaintiff-firm solicitations — "INVESTOR ALERT: lead the class
    # action" ads that follow every drop; not a real legal event.
    r"|investor alert|loss alert|investors? with (?:substantial )?losses"
    r"|opportunity to lead|lead plaintiff|reminds? investors"
    r"|urges? .*investors|notifies .*investors"
    r"|class action .*(?:deadline|reminder)|securities .*(?:deadline|reminder)"
    r"|deadline .*(?:lawsuit|class action)"
    r"|contact .*(?:law|llp|llc)\b|(?:llp|llc)\b.*(?:lawsuit|fraud)",
    re.IGNORECASE,
)
_KIND_RULES = [
    ("earnings",    r"\b(earnings|eps|ebitda|revenue|quarter(?:ly)? results|"
                    r"q[1-4]\b|guidance|outlook|raises? (?:full|fy|annual|"
                    r"guidance)|cuts? guidance|beats? estimates|"
                    r"misses? estimates|tops? estimates)\b"),
    ("analyst",     r"\b(upgrad|downgrad|price target|initiat\w* coverage|"
                    r"overweight|underweight|outperform|reiterat\w*|"
                    r"pt (?:raised|cut|hiked|lowered))\b"),
    ("ma",          r"\b(acquir\w+|merger|takeover|buyout|bids? for|"
                    r"go(?:es)? private|to acquire|merges)\b"),
    ("regulatory",  r"\b(fda|approval|approved|clearance|sec\b|cftc|doj|"
                    r"antitrust|probe|investigat\w+|ban(?:s|ned)?|penalt\w+|"
                    r"subpoena)\b"),
    ("contract",    r"\b(contract|partnership|deal worth|agreement|"
                    r"collaborat\w+|signs?\b|wins? .*deal)\b"),
    ("capital",     r"\b(buyback|repurchase|dividend|stock split|"
                    r"share split|spin.?off)\b"),
    ("dilution",    r"\b(offering|secondary|at.the.market|dilut\w+|"
                    r"share sale)\b"),
    ("management",  r"\b(ceo|cfo|chief|president|resign\w*|appoint\w*|"
                    r"steps? down|departs?|ousted)\b"),
    ("legal",       r"\b(lawsuit|sues|sued|settlement|class action|"
                    r"fraud|charged|indict\w*)\b"),
    ("layoffs",     r"\b(layoff\w*|job cuts|restructur\w*|workforce)\b"),
    ("price_action", r"\b(jumps|soars|surges|plunges|tumbles|crashes|"
                     r"rallies|slides|drops|falls|gains|spikes|"
                     r"52.week|all.time high|record high)\b"),
    ("macro",       r"\b(fed\b|fomc|rate (?:cut|hike|decision)|inflation|"
                    r"cpi|ppi|payroll|treasury|tariff)\b"),
]
_SIGNAL_KINDS = {"earnings", "analyst", "ma", "regulatory", "contract",
                 "capital", "dilution", "management", "legal", "layoffs"}
_KIND_RES = [(k, re.compile(p, re.IGNORECASE)) for k, p in _KIND_RULES]

# Rating-action detection — for the dedicated upgrades/downgrades lane.
# Case-insensitive patterns cover verbs; the firm-name "gets X boost"
# pattern is intentionally case-SENSITIVE so "gets a boost" (generic)
# doesn't match while "gets BofA boost" does.
_RATING_UP_RX = re.compile(
    r"\bupgrad\w*"
    r"|\b(?:price target|pt|target)\s+(?:raised|hiked|boosted|lifted|increased|upped)\b"
    r"|\b(?:raises?|hikes?|boosts?|lifts?|increases?|ups)\s+(?:its\s+|the\s+)?"
    r"(?:price target|pt|target)\b"
    r"|\bto\s+(?:outperform|overweight|buy|strong buy|conviction buy)\b"
    r"|\bscore[sd]?\s+upgrades?\b"
    r"|\binitiat\w*\s+(?:coverage\s+)?(?:at|with)\s+"
    r"(?:buy|outperform|overweight)\b",
    re.IGNORECASE)
_RATING_DN_RX = re.compile(
    r"\bdowngrad\w*"
    r"|\b(?:price target|pt|target)\s+(?:lowered|cut|slashed|trimmed|reduced)\b"
    r"|\b(?:lowers?|cuts?|slashes?|trims?|reduces?)\s+(?:its\s+|the\s+)?"
    r"(?:price target|pt|target)\b"
    r"|\bto\s+(?:underperform|underweight|sell|reduce)\b",
    re.IGNORECASE)
# Neutral rating moves — initiations/reiterations where direction isn't
# implied (a move TO neutral could be up or down).
_RATING_NEU_RX = re.compile(
    r"\binitiat\w*\s+coverage\b|\binitiates?\s+(?:at|with)\b"
    r"|\breiterat\w*|\bmaintain\w*\s+(?:rating|buy|neutral|hold)\b"
    r"|\bto\s+(?:neutral|hold|equal.?weight|market perform|sector perform|"
    r"in.?line|peer perform)\b"
    r"|\bnew price target\b|\bsets?\s+price target\b",
    re.IGNORECASE)
_FIRM_BOOST_RX = re.compile(r"\bgets?\s+(?:[A-Z][\w&.'-]+\s+){1,2}boost\b")

# FMP's action field misses some transitions ("initialise" on an
# Equal-Weight→Overweight move). Rank the grades to recover direction.
_GRADE_RANK = {
    "strong buy": 5, "conviction buy": 5, "positive": 5,
    "buy": 4, "outperform": 4, "overweight": 4,
    "market outperform": 4, "sector outperform": 4,
    "neutral": 3, "hold": 3, "equal-weight": 3, "equal weight": 3,
    "sector perform": 3, "market perform": 3, "in-line": 3,
    "peer perform": 3, "perform": 3, "sector weight": 3,
    "underperform": 2, "underweight": 2, "reduce": 2, "negative": 2,
    "sell": 1, "strong sell": 1,
}


def _grade_rank(g: Optional[str]) -> Optional[int]:
    return _GRADE_RANK.get((g or "").strip().lower()) or None


def grade_direction(prev_grade: Optional[str],
                    new_grade: Optional[str]) -> Optional[str]:
    """'upgrade' | 'downgrade' from a prev→new grade transition —
    the observed truth, used to correct FMP's occasionally-wrong
    `action` label (e.g. Underperform→Hold arriving as "downgrade")."""
    old, new = _grade_rank(prev_grade), _grade_rank(new_grade)
    if old is None or new is None or old == new:
        return None
    return "upgrade" if new > old else "downgrade"


def rating_action(title: str, event_type: str = "",
                  action: str = "", direction: str = "",
                  prev_grade: str = "", new_grade: str = "") -> Optional[str]:
    """'upgrade' | 'downgrade' | 'rating' for analyst-action events —
    None if this isn't a rating/PT event. The observed grade transition
    wins over FMP's `action` label when both grades rank; feed fields
    cover PT-only moves; headline regex is the fallback for news."""
    if event_type in ("analyst_action", "pt_repricing"):
        gd = grade_direction(prev_grade, new_grade)
        if gd:
            return gd
        if action in ("upgrade", "raise") or direction == "POSITIVE":
            return "upgrade"
        if action in ("downgrade", "lower") or direction == "NEGATIVE":
            return "downgrade"
        return "rating"
    t = title or ""
    if _RATING_UP_RX.search(t) or _FIRM_BOOST_RX.search(t):
        return "upgrade"
    if _RATING_DN_RX.search(t):
        return "downgrade"
    if _RATING_NEU_RX.search(t):
        return "rating"
    return None


def classify_headline(title: str) -> tuple[str, str]:
    """(kind, bucket) for a headline. bucket 'actionable' = event that
    moves the stock; 'news' = commentary/recap/filler — context only."""
    t = title or ""
    if is_filler_headline(t):
        return "filler", "news"
    if _NOISE.search(t):
        return "opinion", "news"
    for kind, rx in _KIND_RES:
        if rx.search(t):
            if kind in _SIGNAL_KINDS:
                return kind, "actionable"
            # price-action recaps aren't a catalyst but they do tell you the
            # stock is moving — own bucket, not the news pile.
            return kind, "tape" if kind == "price_action" else "news"
    return "other", "news"


def _headline_direction(title: str) -> str:
    if is_filler_headline(title):
        return "NEUTRAL"
    text = title.lower()
    positive = ("rallied", "buys", "upgrade", "raises", "growth", "adds", "support", "approval", "beat", "positive", "bitcoin", "crypto")
    negative = _NEGATIVE
    has_positive = any(word in text for word in positive)
    has_negative = any(word in text for word in negative)
    if has_positive and has_negative:
        return "MIXED"
    if has_positive:
        return "POSITIVE"
    if has_negative:
        return "NEGATIVE"
    return "NEUTRAL"


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _surprise(actual: Optional[float], estimate: Optional[float]) -> Optional[float]:
    if actual is None or estimate in (None, 0):
        return None
    return (actual - estimate) / abs(estimate)


def _direction(values: list[float], news_titles: list[str]) -> CatalystDirection:
    signal_titles = [t for t in news_titles if not is_filler_headline(t)]
    positive = sum(value > 0.02 for value in values) + sum(any(k in title for k in _POSITIVE) for title in signal_titles)
    negative = sum(value < -0.02 for value in values) + sum(any(k in title for k in _NEGATIVE) for title in signal_titles)
    if positive and negative:
        return CatalystDirection.MIXED
    if positive:
        return CatalystDirection.POSITIVE
    if negative:
        return CatalystDirection.NEGATIVE
    return CatalystDirection.NEUTRAL if values or news_titles else CatalystDirection.UNKNOWN


def assess_catalyst(
    symbol: str,
    earnings: Iterable[EarningsEvent],
    news: Iterable[NewsItem],
    *,
    now: Optional[datetime] = None,
    price_change_1d: Optional[float] = None,
    volume_ratio: Optional[float] = None,
) -> CatalystSnapshot:
    current = _as_utc(now or datetime.now(timezone.utc))
    assert current is not None
    today = current.date()
    earnings_list = list(earnings)
    news_list = list(news)
    upcoming = sorted((item for item in earnings_list if item.date and item.date >= today), key=lambda item: item.date)
    next_earnings = upcoming[0] if upcoming else None
    days = (next_earnings.date - today).days if next_earnings and next_earnings.date else None
    recent = [item for item in earnings_list if item.date and today - timedelta(days=30) <= item.date < today]
    values = [value for item in recent for value in (_surprise(item.eps_actual, item.eps_estimate), _surprise(item.revenue_actual, item.revenue_estimate)) if value is not None]
    recent_news = [
        item for item in news_list
        if _as_utc(item.published_at) is None
        or (current - _as_utc(item.published_at)).total_seconds() <= 7 * 86400
    ]
    titles = [item.title.lower() for item in recent_news]
    news_direction = _direction(values, titles)
    joined_titles = " ".join(titles)
    catalyst_type = (
        "REGULATORY" if any(word in joined_titles for word in ("sec", "cftc", "fdic", "regulatory", "approval"))
        else "CRYPTO_MARKET" if any(word in joined_titles for word in ("bitcoin", "crypto", "tokenized"))
        else "ANALYST_RATING" if any(word in joined_titles for word in ("upgrade", "downgrade", "price target"))
        else "EARNINGS" if recent or next_earnings else
        "CORPORATE" if recent_news else "NONE"
    )
    materiality = "LOW"
    if catalyst_type in {"REGULATORY", "EARNINGS"}:
        materiality = "HIGH"
    elif catalyst_type in {"CRYPTO_MARKET", "ANALYST_RATING"}:
        materiality = "MODERATE"
    reaction_state = "UNKNOWN"
    if price_change_1d is not None:
        if price_change_1d >= 0.03 and (volume_ratio is None or volume_ratio >= 1.2):
            reaction_state = "POSITIVE_CONFIRMED"
        elif price_change_1d <= -0.03 and (volume_ratio is None or volume_ratio >= 1.2):
            reaction_state = "NEGATIVE_CONFIRMED"
        else:
            reaction_state = "MIXED_OR_UNCONFIRMED"
    catalyst_direction = news_direction
    if reaction_state == "POSITIVE_CONFIRMED" and materiality in {"MODERATE", "HIGH"}:
        catalyst_direction = CatalystDirection.POSITIVE
    elif reaction_state == "NEGATIVE_CONFIRMED":
        catalyst_direction = CatalystDirection.NEGATIVE

    if days is not None and days <= 1:
        severity = CatalystSeverity.EXTREME
        policy, overnight = "RESTRICTED", "HIGH"
    elif days is not None and days <= 5:
        severity = CatalystSeverity.HIGH
        policy, overnight = "LIMITED", "ELEVATED"
    elif recent_news or recent:
        severity = CatalystSeverity.MODERATE
        policy, overnight = "NORMAL", "NORMAL"
    else:
        severity = CatalystSeverity.NONE
        policy, overnight = "NORMAL", "NORMAL"

    reasons = []
    if days is not None:
        reasons.append(f"earnings in {days} day(s)")
    if values:
        reasons.append("recent earnings surprise available")
    if recent_news:
        reasons.append(f"{len(recent_news)} recent news item(s)")
    if not earnings_list and not news_list:
        reasons.append("earnings/news data unavailable")

    providers = sorted({item.provider for item in earnings_list + news_list if item.provider})
    return CatalystSnapshot(
        symbol=symbol.upper(), as_of=current.isoformat(),
        next_earnings_date=next_earnings.date.isoformat() if next_earnings and next_earnings.date else None,
        days_to_earnings=days,
        earnings_session="UNKNOWN",
        eps_surprise_pct=next((v * 100 for v in values if v is not None), None),
        revenue_surprise_pct=None,
        recent_earnings_count=len(recent), news_count=len(recent_news),
        recent_news=[{
            "title": item.title,
            "publisher": item.publisher,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "headline_direction": _headline_direction(item.title),
        } for item in recent_news[:10]],
        direction=catalyst_direction, news_direction=news_direction,
        catalyst_direction=catalyst_direction, severity=severity,
        catalyst_type=catalyst_type, materiality=materiality,
        reaction_state=reaction_state, price_change_1d=price_change_1d,
        volume_ratio=volume_ratio, new_entry_policy=policy,
        overnight_risk=overnight, data_quality="GOOD" if earnings_list or news_list else "MISSING",
        providers=providers, reasons=reasons,
    )
