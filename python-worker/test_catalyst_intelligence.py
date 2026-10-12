from datetime import date, datetime, timedelta, timezone

from app.catalyst_intelligence import assess_catalyst
from app.market_data.models import EarningsEvent, NewsItem


def test_earnings_within_one_day_restricts_new_entries():
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    result = assess_catalyst(
        "CRDO",
        [EarningsEvent(provider="test", symbol="CRDO", date=date(2026, 9, 18), eps_estimate=1.0)],
        [], now=now,
    )
    assert result.days_to_earnings == 1
    assert result.severity.value == "EXTREME"
    assert result.new_entry_policy == "RESTRICTED"
    assert result.overnight_risk == "HIGH"


def test_recent_positive_earnings_and_news_are_classified():
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    result = assess_catalyst(
        "RBRK",
        [EarningsEvent(provider="test", symbol="RBRK", date=date(2026, 9, 10), eps_actual=1.1, eps_estimate=1.0)],
        [NewsItem(provider="test", symbol="RBRK", title="Analyst upgrade and raised guidance", published_at=now - timedelta(hours=2))],
        now=now,
    )
    assert result.direction.value == "POSITIVE"
    assert result.catalyst_type == "ANALYST_RATING"
    assert result.materiality == "MODERATE"
    assert result.recent_news[0]["headline_direction"] == "POSITIVE"
    assert result.news_count == 1
    assert result.data_quality == "GOOD"


def test_naive_news_timestamp_is_normalized():
    result = assess_catalyst(
        "RBRK", [],
        [NewsItem(provider="test", symbol="RBRK", title="Analyst upgrade and raised guidance", published_at=datetime(2026, 9, 17, 12, 0))],
        now=datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc),
    )
    assert result.news_count == 1
    assert result.direction.value == "POSITIVE"


def test_missing_catalyst_data_is_explicit():
    result = assess_catalyst("UNKNOWN", [], [], now=datetime(2026, 9, 17, tzinfo=timezone.utc))
    assert result.data_quality == "MISSING"
    assert result.severity.value == "NONE"
    assert result.direction.value == "UNKNOWN"
    assert result.new_entry_policy == "NORMAL"
