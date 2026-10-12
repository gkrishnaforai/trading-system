"""Terminal report for fundamental intelligence."""
from .models import FundamentalAssessment


def format_fundamentals(a: FundamentalAssessment) -> str:
    dimensions = [
        ("growth", a.growth),
        ("profitability", a.profitability),
        ("cash_flow_quality", a.cash_flow_quality),
        ("balance_sheet", a.balance_sheet),
        ("capital_efficiency", a.capital_efficiency),
        ("competitive_advantage", a.competitive_advantage),
        ("earnings_revision", a.earnings_revision),
        ("risk", a.risk),
    ]
    lines = "\n".join(
        f"  {name:<24}: {d.label.upper()}"
        + (f" ({d.score:.0f}/100, coverage={d.coverage:.0%})" if d.score is not None else "")
        for name, d in dimensions
    )
    flags = "\n".join(f"  - {flag}" for flag in a.risk_flags) or "  - none recorded"
    thesis = "\n".join(f"  - {item}" for item in a.thesis) or "  - none"
    v = a.valuation
    return f"""FUNDAMENTAL INTELLIGENCE

  symbol                  : {a.symbol}
  data_quality            : {a.data_quality.upper()}
  business_type           : {a.business_type.value.upper()}
  quality_score           : {f'{a.quality_score:.0f}/100' if a.quality_score is not None else 'UNAVAILABLE'}
  quality_coverage        : {a.quality_coverage:.0%}

DIMENSIONS
{lines}

VALUATION DIAGNOSTICS
  current price           : {v.current_price if v.current_price is not None else 'n/a'}
  trailing P/E            : {v.trailing_pe if v.trailing_pe is not None else 'n/a'}
  forward P/E             : {v.forward_pe if v.forward_pe is not None else 'n/a'}
  PEG                     : {v.peg if v.peg is not None else 'n/a'}
  valuation label         : {v.valuation_label.upper()}
  DCF available           : {str(v.dcf_available).lower()}

STYLE TAGS
  {', '.join(a.style_tags).upper() if a.style_tags else 'UNAVAILABLE'}

THESIS
{thesis}

RISK FLAGS
{flags}
"""
