"""Human-readable regime report — the canonical display block."""
from __future__ import annotations

from .models import DimensionFacts, MarketRegime, MarketSnapshot


def _hist(snap: MarketSnapshot, attr: str) -> str:
    """History as '20d -> 5d -> today' (skips the 1d column)."""
    pts = sorted(
        (h for h in snap.history if h.offset_days in (0, 5, 20)),
        key=lambda h: -h.offset_days)
    return " -> ".join(
        "n/a" if getattr(h, attr) is None else f"{getattr(h, attr):g}"
        for h in pts)


def _checklist(title: str, signals: dict) -> str:
    met = sum(1 for v in signals.values() if v)
    lines = [f"  {title} ({met}/{len(signals)} met)"]
    lines += [f"    [{'x' if v else ' '}] {k}" for k, v in signals.items()]
    return "\n".join(lines)


def format_regime(regime: MarketRegime,
                  snapshot: MarketSnapshot,
                  facts: DimensionFacts,
                  strategy_environments: dict | None = None,
                  event_aware_strategy_environments: dict | None = None,
                  market_event: dict | None = None,
                  event_reaction: dict | None = None) -> str:
    label = regime.regime.value.upper()
    if regime.secondary_regime:
        label += f" + {regime.secondary_regime.value.upper()}"
    override = ""
    if regime.regime_overridden and regime.rules_regime:
        override = (f"\n  note             : LLM overrode rules "
                    f"({regime.rules_regime.value.upper()} -> {label})")

    probs = "\n".join(
        f"  {k:<28}{v:.0%}" for k, v in
        sorted(regime.transition_probabilities.items(),
               key=lambda kv: -kv[1]))
    scores = "\n".join(
        f"  {k.capitalize():<16}{v:+.2f}"
        for k, v in regime.change_components.items())
    pref = "\n".join(f"  - {s}" for s in regime.strategies_preferred)
    avoid = "\n".join(f"  - {s}" for s in regime.strategies_avoid)
    trend_s = (f"{regime.trend_score:+.2f}"
               if regime.trend_score is not None else "n/a")
    det_s = (f"{regime.deterioration_score:+.2f}"
             if regime.deterioration_score is not None else "n/a")

    confirms = "\n\n".join(
        _checklist(name.replace("_", " ").upper(), signals)
        for name, signals in regime.confirmation_signals.items())

    perms = ""
    if regime.market_permissions:
        mp = regime.market_permissions
        perms = f"""
MARKET PERMISSIONS   (deterministic policy — how aggressive, not what)
  aggressive_long    : {str(mp.aggressive_long).lower()}
  normal_long        : {str(mp.normal_long).lower()}
  dip_buying         : {str(mp.dip_buying).lower()}
  breakout_buying    : {mp.breakout_buying}
  shorts_allowed     : {str(mp.shorts_allowed).lower()}
  leverage           : {str(mp.leverage).lower()}
  size_multiplier    : {mp.size_multiplier:.2f}
"""
        if mp.notes:
            perms += "\n".join(f"  note: {n}" for n in mp.notes) + "\n"

    event_lines = ""
    if market_event:
        event_lines += f"""
EVENT CONTEXT
  type               : {market_event.get('event_type', 'UNKNOWN')}
  name               : {market_event.get('event_name', 'UNKNOWN')}
  severity           : {market_event.get('severity', 'UNKNOWN')}
  status             : {market_event.get('status', 'UNKNOWN')}
  policy bias        : {market_event.get('policy_bias', 'UNKNOWN')}
  future policy     : {market_event.get('future_policy', {})}
"""
    else:
        event_lines += """
EVENT CONTEXT
  event              : NONE SUPPLIED
  policy             : NORMAL BASE POLICY
"""
    if event_reaction:
        event_lines += f"""  reaction           : {event_reaction.get('state', 'UNKNOWN')}
  confirmed          : {str(event_reaction.get('confirmation', False)).lower()}
"""

    environments = event_aware_strategy_environments or strategy_environments or {}
    environment_lines = "\n".join(
        f"  {horizon:<14}: quality={data.get('quality', 'n/a').upper()} "
        f"score={data.get('score', 'n/a')} "
        f"entries={data.get('new_entries_allowed', 'n/a')} "
        f"breakouts={data.get('breakout_permission', 'n/a')} "
        f"size={data.get('size_multiplier', 'n/a')} "
        f"event_policy={data.get('event_policy', 'NORMAL')}"
        for horizon, data in environments.items()
    ) or "  no strategy environments supplied"

    return f"""REGIME
  primary          : {regime.direction.upper()}
  condition        : {regime.condition.upper()}
  label            : {label}
  volatility       : {facts.volatility.upper()}
  risk             : {regime.risk_level.upper()}
  source           : {regime.source}{override}

SCORES   (deterministic — facts, not LLM)
  trend            : {trend_s}   (is the market still bullish?)
  deterioration    : {det_s}   (is the regime weakening?)
  bullish transition: {f"{regime.bullish_transition_score:.0f}/100" if regime.bullish_transition_score is not None else 'n/a'}
  transition stage : {regime.transition_stage}
  dip-buying env   : {regime.dip_buying_environment}
  transition delta : {regime.transition_delta_5d if regime.transition_delta_5d is not None else 'n/a'} (5d)
{scores}

CURRENT STATE CONFIDENCE : {regime.confidence:.0%}
  (confidence in the regime call — NOT a forecast probability)

FORWARD TRANSITION PROBABILITIES  (deterministic prior)
{probs}

CONFIRMATION SIGNALS
{confirms}
{perms}
{event_lines}
STRATEGY ENVIRONMENTS
{environment_lines}

FACTS

  trend            : {facts.trend}
  momentum         : {facts.momentum}
  breadth          : {facts.breadth}
  volatility       : {facts.volatility}
  participation    : {facts.participation}
  macro            : {facts.macro}
  structure        : {facts.structure}

HISTORY   (20d -> 5d -> today)

  SPY              : {_hist(snapshot, 'spy')}
  RSI              : {_hist(snapshot, 'rsi')}
  breadth          : {_hist(snapshot, 'breadth_pct50')}%
  VIX              : {_hist(snapshot, 'vix')}
  10Y              : {_hist(snapshot, 'us10y')}

INTERPRETATION

{regime.interpretation}

PREFERRED
{pref}

AVOID
{avoid}
"""
