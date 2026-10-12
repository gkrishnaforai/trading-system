"""Pattern learning loop: signal capture → outcome evaluation → calibration.

Deterministic throughout — no LLM. Records every detected setup as a signal,
evaluates forward outcomes from daily bars, aggregates empirical stats in
`pattern_stats`, and feeds a bounded score adjustment back into detect_setup.
"""
from .service import (
    evaluate_outcomes,
    pattern_stats,
    record_signal,
    score_adjustment,
)

__all__ = [
    "evaluate_outcomes",
    "pattern_stats",
    "record_signal",
    "score_adjustment",
]
