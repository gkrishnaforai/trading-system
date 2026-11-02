from datetime import date, timedelta

from app.signals.stock_health import _multiples, _pe_guidance


TODAY = date(2026, 4, 1)


def _earnings(eps, date_value="2026-02-01"):
    return [
        {"eps_actual": value, "earnings_date": date_value}
        for value in eps
    ]


def test_multiples_use_spot_and_reported_and_consensus_eps():
    result = _multiples(
        120,
        _earnings([2, 2, 2, 2]),
        {"fwd_eps_avg": 10, "updated_at": TODAY, "num_analysts": 8},
        today=TODAY,
    )

    assert result["pe_ttm"] == 15
    assert result["fwd_pe"] == 12
    assert result["guidance"]["growth_pct"] == 25
    assert result["guidance"]["label"] == "Attractive on growth screen"
    assert result["estimate_age_days"] == 0


def test_growth_adjusted_screen_scales_reasonable_multiple_with_growth():
    slow_growth = _pe_guidance(15, 10, 10.5, 0)
    faster_growth = _pe_guidance(40, 10, 13, 0)

    assert slow_growth["label"] == "Stretched / avoid"
    assert faster_growth["label"] == "Reasonable on growth screen"
    assert faster_growth["reasonable_pe_max"] == 45


def test_negative_or_non_growing_eps_fails_closed():
    loss_making = _pe_guidance(20, -1, 2, 0)
    declining = _pe_guidance(20, 10, 9, 0)
    unavailable = _pe_guidance(None, 10, None, 0)

    assert loss_making["label"] == "Profitability transition"
    assert declining["label"] == "Avoid on P/E basis"
    assert unavailable["label"] == "P/E not usable"
    assert unavailable["peg_like"] is None


def test_stale_or_undated_estimates_do_not_get_growth_guidance():
    stale = _pe_guidance(20, 10, 12, 46)
    unknown = _pe_guidance(20, 10, 12, None)

    assert stale["label"] == "Estimate is stale"
    assert unknown["label"] == "Estimate freshness unknown"


def test_missing_quarterly_eps_does_not_invent_trailing_pe():
    result = _multiples(
        100,
        _earnings([2, 2, 2]),
        {"fwd_eps_avg": 10, "updated_at": TODAY},
        today=TODAY,
    )

    assert result["eps_ttm"] is None
    assert result["pe_ttm"] is None
    assert result["guidance"]["label"] == "Trailing EPS unavailable"


def test_stale_estimate_snapshot_is_reported_in_card_multiples():
    result = _multiples(
        100,
        _earnings([2, 2, 2, 2]),
        {"fwd_eps_avg": 10, "updated_at": TODAY - timedelta(days=90)},
        today=TODAY,
    )

    assert result["fwd_pe"] == 10
    assert result["guidance"]["label"] == "Estimate is stale"


def test_stale_reported_eps_blocks_growth_guidance():
    result = _multiples(
        100,
        _earnings([2, 2, 2, 2], "2025-01-01"),
        {"fwd_eps_avg": 10, "updated_at": TODAY},
        today=TODAY,
    )

    assert result["pe_ttm"] == 12.5
    assert result["guidance"]["label"] == "Trailing EPS is stale"
