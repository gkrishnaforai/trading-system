"""Horizon capability routing."""
from .models import TradingHorizon, TradingIntent


def validate_horizon_support(intent: TradingIntent, *, daily_data_only: bool = True) -> list[str]:
    reasons: list[str] = []
    if daily_data_only and intent.horizon == TradingHorizon.DAY_TRADING:
        reasons.append("day trading requires intraday data; daily graph cannot authorize it")
    if intent.mode == "live":
        reasons.append("live execution requires explicit live-broker approval boundary")
    return reasons
