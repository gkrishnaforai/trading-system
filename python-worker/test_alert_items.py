"""Unit tests for the catalyst alert pipeline (scanner ranking, dedup, formatter, gating)."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.alerts import scanner, service
from app.alerts.models import AlertItem
from app.market_data.models import EarningsEvent, NewsItem


def _item(**kw) -> AlertItem:
    base = dict(
        symbol="NVDA", event_type="catalyst", direction="POSITIVE",
        materiality="MODERATE", title="t", fingerprint="fp", detail={},
    )
    base.update(kw)
    return AlertItem(**base)


# ---------- priority_score ----------

def test_priority_negative_held_outranks_everything():
    neg_held = _item(direction="NEGATIVE", in_portfolio=True, materiality="MODERATE")
    pos_held = _item(direction="POSITIVE", in_portfolio=True, materiality="HIGH")
    watch = _item(in_watchlist=True, materiality="HIGH")
    assert scanner.priority_score(neg_held) > scanner.priority_score(pos_held)
    assert scanner.priority_score(pos_held) > scanner.priority_score(watch)


def test_priority_materiality_ordering():
    h = scanner.priority_score(_item(materiality="HIGH"))
    m = scanner.priority_score(_item(materiality="MODERATE"))
    low = scanner.priority_score(_item(materiality="LOW"))
    assert h > m > low


# ---------- auto-review gating ----------

def test_auto_review_gate():
    assert service._should_auto_review(_item(materiality="HIGH"))
    assert service._should_auto_review(_item(materiality="MODERATE"))
    assert not service._should_auto_review(_item(materiality="LOW", direction="POSITIVE"))
    # negative on a held position bypasses materiality
    assert service._should_auto_review(
        _item(materiality="LOW", direction="NEGATIVE", in_portfolio=True))
    # negative on watchlist-only does not
    assert not service._should_auto_review(
        _item(materiality="LOW", direction="NEGATIVE", in_watchlist=True))


# ---------- format_summary ----------

def test_format_summary_full():
    item = _item(title="Upgrade: GS Neutral → Buy", direction="POSITIVE")
    result = {
        "decision": {
            "action": "BUY_SMALL", "reasons": ["strong setup", "regime ok"],
            "valuation_label": "fair", "position_size_pct": 0.10,
        },
        "fundamentals": {"valuation": {"price_vs_base_fv_pct": 2.7}},
        "event_aware_swing_environment": {"long_permission": "allowed", "size_multiplier": 0.5},
    }
    msg = service.format_summary(item, result)
    assert "NVDA" in msg and "BUY_SMALL" in msg and "strong setup" in msg
    assert "+2.7%" in msg and "allowed" in msg and "0.5" in msg


def test_format_summary_error():
    item = _item(direction="NEGATIVE", title="downgrade")
    msg = service.format_summary(item, {"error": "boom"})
    assert "failed" in msg and "boom" in msg


def test_format_summary_missing_decision():
    msg = service.format_summary(_item(), {})
    assert "N/A" in msg


# ---------- collect_eps_revisions ----------

def test_eps_revision_builds_signed_alert():
    row = {
        "symbol": "COIN", "as_of_date": date(2026, 9, 19),
        "fiscal_period": "FY", "fiscal_year": 2026,
        "eps_estimate": 8.0, "prev_eps_estimate": 10.0,
        "analysts_up": 2, "analysts_down": 9, "provider": "fmp",
    }
    with patch.object(scanner.db, "execute_query", return_value=[row]):
        items = scanner.collect_eps_revisions({"COIN": {}})
    assert len(items) == 1
    it = items[0]
    assert it.event_type == "eps_revision"
    assert it.direction == "NEGATIVE"
    assert it.materiality == "HIGH"        # -20% >= 10% threshold
    assert "-20.0%" in it.title
    assert it.fingerprint.startswith("eps:COIN:")


# ---------- collect_analyst_events ----------

def test_analyst_events_direction_and_fingerprint():
    rows = [{
        "id": "g1", "symbol": "HOOD", "grading_company": "Morgan Stanley",
        "previous_grade": "Equal Weight", "new_grade": "Buy",
        "grade_date": date(2026, 9, 18), "event_type": "upgrade",
        "price_at_grade": 100.0,
    }]
    with patch.object(scanner.db, "execute_query", return_value=rows):
        items = scanner.collect_analyst_events({"HOOD": {}})
    assert len(items) == 1
    it = items[0]
    assert it.direction == "POSITIVE" and it.event_type == "analyst_upgrade"
    assert it.fingerprint == "grade:g1"
    assert "Morgan Stanley" in it.title


# ---------- persist dedup ----------

def test_persist_dedup_by_fingerprint():
    item = _item(fingerprint="fp:1", priority_score=90.0)
    # first insert returns id, second (conflict) returns []
    calls = [[{"id": "a1"}], []]
    with patch.object(scanner.db, "execute_query", side_effect=lambda *a, **k: calls.pop(0)):
        ins, skip = scanner.persist([_item(fingerprint="fp:1", priority_score=90.0),
                                     _item(fingerprint="fp:1", priority_score=90.0)])
    assert ins == 1 and skip == 1


# ---------- fresh-review suppression ----------

def test_fresh_review_check():
    with patch.object(service.db, "execute_query", return_value=[{"?column?": 1}]):
        assert service._fresh_review_exists("NVDA")
    with patch.object(service.db, "execute_query", return_value=[]):
        assert not service._fresh_review_exists("NVDA")


# ---------- universe ----------

# ---------- catalyst freshness gate ----------

def _news(title: str, hours_ago: float) -> NewsItem:
    return NewsItem(
        symbol="NVDA", title=title, provider="test",
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


def _earnings_event(days_ago: int, surprise: float = 0.10) -> EarningsEvent:
    est = 1.0
    return EarningsEvent(
        symbol="NVDA", date=date.today() - timedelta(days=days_ago),
        eps_actual=est * (1 + surprise), eps_estimate=est, provider="test",
    )


def _svc(earnings, news):
    svc = MagicMock()
    async def _earn(symbol): return earnings
    async def _news_fn(symbol, limit=10): return news
    svc.get_earnings = _earn
    svc.get_news = _news_fn
    return svc


def _collect(svc, scope=None):
    return asyncio.run(
        scanner.collect_catalysts(scope or {"NVDA": {}}, service=svc))


def test_catalyst_stale_surprise_does_not_alert():
    """EPS surprise from 10 days ago must not re-alert."""
    svc = _svc([_earnings_event(days_ago=10)], [])
    items, errors = _collect(svc)
    assert items == []


def test_catalyst_fresh_surprise_alerts():
    svc = _svc([_earnings_event(days_ago=1)], [])
    items, _ = _collect(svc)
    assert len(items) == 1
    assert items[0].materiality == "HIGH"
    assert "EPS surprise" in items[0].title
    assert any(t.startswith("eps:") for t in items[0].detail["triggers"])


def test_catalyst_stale_headlines_do_not_alert():
    """Two same-direction headlines from 2 days ago — too old for the news trigger."""
    svc = _svc([], [
        _news("NVDA upgrade announced by analyst", hours_ago=50),
        _news("NVDA beats on growth outlook", hours_ago=60),
    ])
    items, _ = _collect(svc)
    assert items == []


def test_catalyst_fresh_headlines_alert_and_dedup_key():
    svc = _svc([], [
        _news("NVDA upgrade announced by analyst", hours_ago=2),
        _news("NVDA beats on growth outlook", hours_ago=3),
    ])
    items, _ = _collect(svc)
    assert len(items) == 1
    assert items[0].materiality == "MODERATE"
    assert items[0].fingerprint.startswith("catalyst:")
    # same event → same fingerprint → rescans dedup
    items2, _ = _collect(svc)
    assert items2[0].fingerprint == items[0].fingerprint


def test_catalyst_new_headline_gets_new_fingerprint():
    """A different headline later same day → different fingerprint → new alert."""
    svc1 = _svc([], [
        _news("NVDA upgrade announced by analyst", hours_ago=2),
        _news("NVDA beats on growth outlook", hours_ago=3),
    ])
    svc2 = _svc([], [
        _news("NVDA wins major contract approval", hours_ago=1),
        _news("NVDA beats on growth outlook", hours_ago=3),
    ])
    fp1 = _collect(svc1)[0][0].fingerprint
    fp2 = _collect(svc2)[0][0].fingerprint
    assert fp1 != fp2


# ---------- filler + keyword fixes ----------

def test_filler_headlines_are_neutral():
    from app.catalyst_intelligence.engine import is_filler_headline, _headline_direction
    assert is_filler_headline("Corient Private Wealth LP Sells 27,078 Shares of Vistra Corp. $VST")
    assert is_filler_headline("Nykredit A S Buys Shares of 119,162 Cloudflare, Inc. $NET")
    assert is_filler_headline("Isaiah Fields Sells 1,017 Shares of Axon Enterprise Stock")
    assert not is_filler_headline("Netflix Stock Gets Downgraded by Wells Fargo")
    # Filler never produces a direction
    assert _headline_direction("Vega Investment Solutions Sells 1,134 Shares of Meta $META") == "NEUTRAL"
    # Real signals still classify
    assert _headline_direction("NVDA upgrade announced") == "POSITIVE"
    assert _headline_direction("Netflix downgraded by Wells Fargo") == "NEGATIVE"


def test_sec_and_regulation_no_longer_positive():
    from app.catalyst_intelligence.engine import _headline_direction
    # "SEC investigation" must be NEGATIVE (was POSITIVE when "sec" was a positive keyword)
    assert _headline_direction("Company faces SEC investigation") == "NEGATIVE"
    assert _headline_direction("New regulation framework proposed") == "NEUTRAL"


def test_reaction_state_priority_bonus():
    plain = _item(detail={})
    confirmed = _item(detail={"reaction_state": "POSITIVE_CONFIRMED"})
    assert scanner.priority_score(confirmed) == scanner.priority_score(plain) + 15


# ---------- LLM classifier ----------

def test_llm_classifier_disabled_without_keys():
    from app.alerts.llm_classifier import HeadlineClassifier
    with patch("app.alerts.llm_classifier.settings") as s, \
         patch("app.alerts.llm_classifier._LITELLM", True):
        s.openai_api_key = None
        s.anthropic_api_key = None
        s.litellm_proxy_url = None
        clf = HeadlineClassifier()
        assert not clf.enabled
        assert clf.classify("NVDA", ["title"]) is None


def test_llm_classifier_parses_typed_verdicts():
    from app.alerts import llm_classifier as lc
    verdict_payload = json.dumps({"verdicts": [
        {"index": 1, "direction": "POSITIVE", "event_kind": "contract", "material": True},
        {"index": 2, "direction": "NEUTRAL", "event_kind": "filler", "material": False},
    ]})
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=verdict_payload))]
    with patch.object(lc, "_LITELLM", True), \
         patch.object(lc, "completion", return_value=fake_resp), \
         patch.object(lc.settings, "openai_api_key", "k", create=True):
        clf = lc.HeadlineClassifier()
        assert clf.enabled
        out = clf.classify("NVDA", ["NVDA wins contract", "X Buys Shares of NVDA"])
    assert len(out) == 2
    assert out[0].direction == "POSITIVE" and out[0].material and out[0].event_kind == "contract"
    assert out[1].event_kind == "filler" and not out[1].material


def test_llm_classifier_failure_returns_none():
    from app.alerts import llm_classifier as lc
    with patch.object(lc, "_LITELLM", True), \
         patch.object(lc, "completion", side_effect=RuntimeError("api down")), \
         patch.object(lc.settings, "openai_api_key", "k", create=True):
        clf = lc.HeadlineClassifier()
        assert clf.classify("NVDA", ["t"]) is None


def test_published_within():
    now_iso = datetime.now(timezone.utc).isoformat()
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
    assert scanner._published_within(now_iso, 12)
    assert not scanner._published_within(old_iso, 12)
    assert not scanner._published_within(None, 12)
    assert not scanner._published_within("garbage", 12)


def test_universe_filters_bad_symbols():
    rows = [
        {"symbol": "NVDA", "in_portfolio": True, "qty": 10},
        {"symbol": "0", "in_portfolio": False, "qty": 0},
        {"symbol": "  ", "in_portfolio": False, "qty": 0},
    ]
    with patch.object(scanner.db, "execute_query", return_value=rows):
        scope = scanner.universe()
    assert "NVDA" in scope and scope["NVDA"]["in_portfolio"]
    assert "0" not in scope and len(scope) == 1
