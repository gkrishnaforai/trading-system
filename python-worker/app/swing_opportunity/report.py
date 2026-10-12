"""Human-readable swing-opportunity report."""
from typing import Optional

from app.risk.models import RiskAssessment
from app.trade_decision.models import TradeDecision

from .models import SwingOpportunity


def format_opportunity(opportunity: SwingOpportunity,
                       risk: Optional[RiskAssessment] = None,
                       decision: Optional[TradeDecision] = None) -> str:
    stock = opportunity.stock
    t = stock.technicals
    rs = stock.relative_strength
    s = opportunity.setup
    fundamentals = opportunity.fundamentals
    return f"""SWING STOCK OPPORTUNITY

  symbol              : {opportunity.symbol}
  data_quality        : {stock.data_quality.sufficient and 'GOOD' or 'INSUFFICIENT'} ({stock.data_quality.bars}/{stock.data_quality.required_bars} bars)

MARKET CONTEXT
  regime              : {opportunity.market_regime.upper()}
  condition           : {opportunity.market_condition.upper()}
  swing_environment   : {opportunity.swing_environment.upper()}
  size_multiplier     : {opportunity.swing_size_multiplier:.2f}
  event_policy        : {opportunity.event_policy}
  new_entries_allowed : {str(opportunity.event_new_entries_allowed).lower()}

STOCK STATE
  price               : {t.price if t.price is not None else 'n/a'}
  EMA20 / SMA50       : {t.ema20 if t.ema20 is not None else 'n/a'} / {t.sma50 if t.sma50 is not None else 'n/a'}
  SMA200              : {t.sma200 if t.sma200 is not None else 'n/a'}
  RSI                 : {t.rsi if t.rsi is not None else 'n/a'}
  return 5d / 20d     : {t.ret5 if t.ret5 is not None else 'n/a'} / {t.ret20 if t.ret20 is not None else 'n/a'}
  volume ratio        : {t.volume_ratio if t.volume_ratio is not None else 'n/a'}
  relative strength   : {rs.tier} vs SPY20={rs.vs_spy20 if rs.vs_spy20 is not None else 'n/a'}
  sector alignment    : {stock.sector_alignment}

FUNDAMENTAL CONTEXT
  business type       : {fundamentals.get('business_type', 'unknown').upper()}
  quality score       : {(f"{fundamentals.get('quality_score'):.0f}/100" if fundamentals.get('quality_score') is not None else 'UNAVAILABLE')}
  valuation           : {fundamentals.get('valuation', {}).get('valuation_label', 'unavailable').upper()}
  data quality        : {fundamentals.get('data_quality', 'insufficient').upper()}

SETUP
  type                : {s.type.value.upper()}
  quality             : {s.quality.value.upper()}
  score               : {s.score:.0f}/100
  confirmation        : {s.confirmation}
  falling_knife       : {str(s.falling_knife).lower()}

OPPORTUNITY
  quality             : {opportunity.opportunity_quality.value.upper()}
  next_step           : {opportunity.next_step}

RISK ASSESSMENT
  status              : {risk.status.value.upper() if risk else 'NOT_RUN'}
  allowed             : {str(risk.allowed).lower() if risk else 'n/a'}
  entry / stop       : {(f'{risk.entry:.2f}' if risk and risk.entry is not None else 'n/a')} / {(f'{risk.stop:.2f}' if risk and risk.stop is not None else 'n/a')}
  target              : {(f'{risk.target:.2f}' if risk and risk.target is not None else 'n/a')}
  reward / risk       : {(f'{risk.reward_risk:.2f}' if risk and risk.reward_risk is not None else 'n/a')}
  shares              : {risk.shares if risk and risk.shares is not None else 'n/a'}
  position_pct        : {(f'{risk.position_size_pct:.2%}' if risk else 'n/a')}

RISK REASONS
""" + "\n".join(f"  - {reason}" for reason in (risk.blocking_reasons if risk else opportunity.reasons)) + f"""

FINAL DECISION
  action              : {decision.action.value if decision else 'NOT_RUN'}
  confidence          : {f'{decision.confidence:.0%}' if decision else 'n/a'}
  requires approval   : {str(decision.requires_approval).lower() if decision else 'n/a'}
  vetoes              : {', '.join(decision.vetoes) if decision and decision.vetoes else 'none'}
"""
