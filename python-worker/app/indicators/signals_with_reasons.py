"""
Extended signal generation with explicit buy/sell/hold reasons
Aligned with: Buy in Fear, Sell in Greed
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def generate_signals_with_reasons(
    price: pd.Series,
    ema20: pd.Series,
    ema50: pd.Series,
    sma200: pd.Series,
    macd_line: pd.Series,
    macd_signal: pd.Series,
    macd_histogram: pd.Series,
    rsi: pd.Series,
    volume: pd.Series,
    volume_ma: pd.Series,
    long_term_trend: pd.Series,     # expected: bullish / bearish
    medium_term_trend: pd.Series,   # expected: bullish / bearish
) -> pd.DataFrame:
    """
    Generate BUY / SELL / HOLD signals with human-readable reasons.
    """

    index = price.index
    signals = pd.Series("hold", index=index, dtype="object")
    reasons = pd.Series("", index=index, dtype="object")

    # --- Safety check ---
    series_list = [
        ema20, ema50, sma200, macd_line, macd_signal,
        rsi, volume, volume_ma, long_term_trend, medium_term_trend
    ]
    if not all(len(s) == len(price) for s in series_list):
        logger.error("Indicator length mismatch")
        return pd.DataFrame({"signal": signals, "reason": reasons})

    # --- Crossovers (no lookahead) ---
    ema_cross_up = (ema20 > ema50) & (ema20.shift(1) <= ema50.shift(1))
    ema_cross_down = (ema20 < ema50) & (ema20.shift(1) >= ema50.shift(1))

    # --- Volume confirmation ---
    volume_confirmed = volume > (volume_ma * 1.2)

    for i in range(1, len(price)):

        # Skip incomplete rows
        if pd.isna(price.iloc[i]) or pd.isna(ema20.iloc[i]) or pd.isna(rsi.iloc[i]):
            continue

        # -----------------------
        # Trend State
        # -----------------------
        bullish_long = long_term_trend.iloc[i] == "bullish"
        bullish_medium = medium_term_trend.iloc[i] == "bullish"

        # -----------------------
        # Momentum State
        # -----------------------
        macd_bullish = macd_line.iloc[i] > macd_signal.iloc[i]
        macd_bearish = macd_line.iloc[i] < macd_signal.iloc[i]

        rsi_value = rsi.iloc[i]
        rsi_fear = rsi_value < 35
        rsi_neutral = 35 <= rsi_value <= 60
        rsi_greed = rsi_value > 70

        # =========================
        # SELL — SELL IN GREED
        # Highest priority
        # =========================
        sell_reasons = []

        if ema_cross_down.iloc[i]:
            sell_reasons.append("EMA20 crossed below EMA50")

        if macd_bearish:
            sell_reasons.append("MACD turned bearish")

        if rsi_greed:
            sell_reasons.append("RSI > 70 (greed zone)")

        if not bullish_long:
            sell_reasons.append("Price below SMA200 (long-term weakness)")

        if len(sell_reasons) >= 2:
            signals.iloc[i] = "sell"
            reasons.iloc[i] = "; ".join(sell_reasons)
            continue  # SELL overrides BUY

        # =========================
        # BUY — BUY IN FEAR
        # =========================
        buy_reasons = []

        if bullish_long:
            buy_reasons.append("Above SMA200 (long-term uptrend)")

        if bullish_medium:
            buy_reasons.append("EMA20 > EMA50 (medium-term uptrend)")

        if macd_bullish:
            buy_reasons.append("MACD bullish momentum")

        if rsi_fear:
            buy_reasons.append("RSI < 35 (fear / pullback)")

        if ema_cross_up.iloc[i]:
            buy_reasons.append("EMA20 crossed above EMA50")

        if volume_confirmed.iloc[i]:
            buy_reasons.append("Volume expansion confirms move")

        # Avoid late-stage chasing
        extended_run = ema20.iloc[i] > ema50.iloc[i] * 1.05
        if extended_run:
            buy_reasons.append("⚠ Extended move — caution")

        if len(buy_reasons) >= 4 and not extended_run:
            signals.iloc[i] = "buy"
            reasons.iloc[i] = "; ".join(buy_reasons)
            continue

        # =========================
        # HOLD
        # =========================
        hold_reasons = []

        if rsi_fear:
            hold_reasons.append("Oversold — wait for confirmation")
        elif rsi_greed:
            hold_reasons.append("Overbought — wait for pullback")
        elif bullish_long and bullish_medium:
            hold_reasons.append("Uptrend intact — no edge")
        else:
            hold_reasons.append("No clear setup")

        reasons.iloc[i] = "; ".join(hold_reasons)

    return pd.DataFrame(
        {
            "signal": signals,
            "reason": reasons
        }
    )
