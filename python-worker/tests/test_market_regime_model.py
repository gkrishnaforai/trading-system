from app.market_regime.models import MarketRegime, RegimeLabel


def test_market_regime_schema_is_fully_resolved():
    regime = MarketRegime.model_validate(
        {"regime": RegimeLabel.BULL_LOW_VOL, "confidence": 0.5}
    )

    assert regime.regime == RegimeLabel.BULL_LOW_VOL
    assert regime.confirmation_families == {}
