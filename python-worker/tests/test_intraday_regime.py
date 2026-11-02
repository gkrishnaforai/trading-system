from app.market_regime.intraday import _overlay


def test_risk_on_baseline_with_buyers_in_control_is_aligned():
    result = _overlay('risk_on', 'buyers_in_control')

    assert result['state'] == 'aligned'
    assert result['tone'] == 'good'
    assert 'staged adds' in result['action']


def test_risk_on_baseline_with_breaking_tape_pauses_adds():
    result = _overlay('strong_risk_on', 'sellers_regaining')

    assert result['state'] == 'tape_breaking'
    assert result['tone'] == 'bad'
    assert 'pause new adds' in result['action']


def test_defensive_baseline_is_not_overridden_by_green_tape():
    result = _overlay('risk_off', 'buyers_in_control')

    assert result['state'] == 'defensive'
    assert result['tone'] == 'bad'
    assert 'not an add signal' in result['action']


def test_no_tape_data_keeps_daily_baseline_without_upgrading():
    result = _overlay('neutral', 'no_data')

    assert result['state'] == 'baseline_only'
    assert result['tone'] == 'off'
