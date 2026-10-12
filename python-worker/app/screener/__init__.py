"""Swing setup screener — runs the real analyze_stock + detect_setup across
the universe and ranks candidates by backtest-informed criteria."""
from .service import run_screener_job, screener_status

__all__ = ["run_screener_job", "screener_status"]
