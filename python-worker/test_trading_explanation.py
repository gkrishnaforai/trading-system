from app.trading_explanation import TradingExplanationService


def test_deterministic_fallback_preserves_action_and_risk():
    result = {
        "decision": {
            "action": "WAIT",
            "confidence": 0.75,
            "reasons": ["opportunity quality is low"],
            "vetoes": ["event policy blocks new entries"],
        },
        "opportunity": {
            "symbol": "RBRK",
            "fundamentals": {"data_quality": "partial"},
        },
    }
    explanation = TradingExplanationService(use_llm=False).explain("swing_review", result)
    assert explanation.action == "WAIT"
    assert explanation.source == "deterministic_fallback"
    assert "event policy blocks new entries" in explanation.risks
    assert explanation.data_gaps == ["fundamental coverage is incomplete"]


def test_llm_validation_removes_false_no_catalyst_gap():
    service = TradingExplanationService(use_llm=False)
    fallback = service.explain("swing_review", {
        "decision": {"action": "WAIT"},
        "opportunity": {"symbol": "HOOD"},
        "catalyst": {
            "news_count": 10,
            "catalyst_type": "REGULATORY",
            "materiality": "HIGH",
            "catalyst_direction": "POSITIVE",
            "reaction_state": "POSITIVE_CONFIRMED",
        },
    })
    result = service._validate({
        "headline": "HOOD review",
        "action_summary": "WAIT",
        "data_gaps": ["No recent significant market events or catalysts have been identified"],
    }, fallback, "WAIT", {
        "catalyst": {
            "news_count": 10,
            "catalyst_type": "REGULATORY",
            "materiality": "HIGH",
            "catalyst_direction": "POSITIVE",
            "reaction_state": "POSITIVE_CONFIRMED",
        }
    })
    assert result.data_gaps == []
    assert result.catalyst_direction == "POSITIVE"


def test_fallback_handles_market_result():
    explanation = TradingExplanationService(use_llm=False).explain(
        "market_regime",
        {"regime": {"direction": "neutral", "condition": "risk_off"}},
    )
    assert explanation.action == "MARKET_CONTEXT"
    assert explanation.agent == "market_regime"
