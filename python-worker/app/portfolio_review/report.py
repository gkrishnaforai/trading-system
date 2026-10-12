"""Terminal report for manual portfolio review."""
from .models import PortfolioReviewRun


def format_portfolio_review(run: PortfolioReviewRun) -> str:
    lines = [
        "PORTFOLIO REVIEW",
        "",
        f"  portfolio_id        : {run.portfolio_id}",
        f"  as_of               : {run.as_of}",
        f"  positions analyzed  : {run.position_count}",
        "  mode                : MANUAL REVIEW ONLY",
        "  orders created      : false",
        f"  shared market ctx   : {run.shared_market_context_reused}",
        f"  symbol concurrency  : {run.max_concurrency}",
        "",
        "POSITION ACTIONS",
    ]
    for item in run.actions:
        lines.extend([
            f"\n  {item.symbol}",
            f"    action            : {item.action.value}",
            f"    quantity          : {item.quantity:g}",
            f"    current price     : {item.current_price if item.current_price is not None else 'n/a'}",
            f"    setup             : {item.setup_type or 'n/a'}",
            f"    opportunity       : {item.opportunity_quality or 'n/a'}",
            f"    fundamentals     : {item.fundamental_quality or 'n/a'}",
            f"    event policy      : {item.event_policy or 'n/a'}",
            f"    risk status       : {item.risk_status or 'n/a'}",
            f"    confidence        : {item.confidence:.0%}",
            "    reasons:",
            *[f"      - {reason}" for reason in item.reasons],
        ])
    if run.reasons:
        lines.extend(["", "RUN NOTES", *[f"  - {reason}" for reason in run.reasons]])
    return "\n".join(lines)
