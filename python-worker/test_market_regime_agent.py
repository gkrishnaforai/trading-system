"""
Market regime agent test — end-to-end through the LangGraph graph:

    fetch_market_state -> derive_facts -> analyze_regime -> MarketRegime

1. Replays evals/market_regime.jsonl (facts -> rules composition, no network)
2. Runs the live graph: ~130 symbols through the router, full 6-dimension
   snapshot, facts, then LLM classification (rules fallback if no LLM key).

Run:  ./venv/bin/python test_market_regime_agent.py
"""
import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.market_regime import (
    DimensionFacts, MarketRegime, MarketSnapshot, RegimeLabel,
    TrendState, analyze_regime, build_market_regime_graph, derive_facts,
    format_regime,
)


def test_rules_composition():
    """Evals: DimensionFacts -> composite regime via rules (no network)."""
    print("=== rules composition (evals/market_regime.jsonl) ===")
    with open("evals/market_regime.jsonl") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    for case in cases:
        facts = DimensionFacts(**case["facts"])
        # minimal snapshot — rules only read facts; snapshot is attached
        snap = MarketSnapshot(trend=TrendState(spy_price=760.0))
        regime = analyze_regime(snap, facts, use_llm=False)

        expected = RegimeLabel(case["expected"])
        exp2 = case.get("expected_secondary")
        ok = regime.regime == expected and (
            exp2 is None and regime.secondary_regime is None
            or regime.secondary_regime and regime.secondary_regime.value == exp2)
        print(f"  [{'PASS' if ok else 'FAIL'}] {case['name']:<22} -> "
              f"{regime.direction}/{regime.condition} "
              f"{regime.regime.value}"
              + (f" + {regime.secondary_regime.value}"
                 if regime.secondary_regime else "")
              + f" (expected {expected.value}"
              + (f"+{exp2}" if exp2 else "") + ")")
        assert ok, case["name"]
        assert regime.source == "rules"
        assert regime.dimensions.get("trend") == facts.trend
        # deterministic spine: probabilities + scores present on rules path
        assert regime.transition_probabilities
        assert abs(sum(regime.transition_probabilities.values()) - 1.0) < 0.05


async def test_live_graph():
    print("\n=== live graph (fetch -> facts -> analyze) ===")
    graph = build_market_regime_graph()
    final = await graph.ainvoke({})

    assert not final.get("error"), f"graph error: {final.get('error')}"
    snap = MarketSnapshot.model_validate(final["snapshot"])
    facts = DimensionFacts.model_validate(final["facts"])
    regime = MarketRegime.model_validate(final["regime"])

    # --- coverage sanity ---
    print(f"  coverage    : {snap.coverage}")
    assert snap.coverage.get("breadth", 0) >= 80, "breadth universe too thin"
    assert snap.trend.sma200 is not None

    # --- regime sanity ---
    assert regime.regime in RegimeLabel
    assert 0.0 <= regime.confidence <= 1.0
    assert regime.source in ("llm", "rules")
    assert regime.direction and regime.condition
    assert regime.trend_score is not None
    assert regime.deterioration_score is not None
    assert regime.transition_probabilities
    assert regime.confirmation_signals

    # --- the canonical report block ---
    print(format_regime(regime, snap, facts))

    if regime.regime_overridden:
        print(f"  override    : rules={regime.rules_regime.value} "
              f"-> llm={regime.regime.value}")
        print(f"  because     : {regime.override_justification}")

    # --- macro availability report ---
    missing = [n for n in ("us10y", "dxy", "wti", "gold", "btc")
               if n not in snap.macro.instruments]
    if missing:
        print(f"  note: macro instruments unavailable: {missing}")


async def main():
    test_rules_composition()
    await test_live_graph()
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
