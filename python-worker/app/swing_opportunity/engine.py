"""Deterministic stock feature and swing-setup calculations."""
from __future__ import annotations

from typing import Optional, Sequence

from app.market_data import indicators as ind
from app.market_data.models import OHLCVBar
from app.market_regime.models import MarketRegime
from app.strategy_environment.models import EnvironmentQuality, StrategyEnvironment, StrategyHorizon

from .models import (
    OpportunityQuality, RelativeStrength, SetupAssessment, SetupType,
    StockAnalysis, StockDataQuality, StockTechnicals,
)


def _quality(score: float) -> OpportunityQuality:
    if score >= 75:
        return OpportunityQuality.HIGH
    if score >= 55:
        return OpportunityQuality.MEDIUM
    return OpportunityQuality.LOW


def _tier(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value >= 0.10:
        return "strong_outperformer"
    if value >= 0.05:
        return "outperformer"
    if value > -0.05:
        return "neutral"
    return "underperformer"


def _stock_permission(t: StockTechnicals) -> str:
    """The stock's own regime proxy — same SMA50/200/ret20/dd20 rules as the
    index gate, applied to the symbol's technicals. Backtest evidence:
    stock-weak + index-weak is the kill zone; mean_reversion needs weakness."""
    if t.price is None or t.sma50 is None or t.sma200 is None:
        return "unknown"
    if t.price < t.sma200 or (t.price < t.sma50 and (t.ret20 or 0) < -0.03):
        return "disabled"
    if t.price < t.sma50 and (t.ret20 or 0) < 0:
        return "restricted"
    if t.price < t.sma50 or (t.ret20 or 0) < 0 or (t.drawdown20 or 0) < -0.05:
        return "limited"
    return "allowed"


def _trend_turn_bars(bars: Sequence[OHLCVBar], max_bars: int = 30) -> Optional[int]:
    """Bars since price last crossed above SMA50 — None if turn is stale or
    price is back below SMA50."""
    if len(bars) < 55:
        return None
    closes = ind.closes(list(bars))
    sma50 = ind.sma_series(list(bars), 50)
    n = len(closes)
    if closes.iloc[-1] <= sma50.iloc[-1]:
        return None
    for i in range(n - 1, 50, -1):
        if closes.iloc[i] > sma50.iloc[i] and closes.iloc[i - 1] <= sma50.iloc[i - 1]:
            bars_since = n - 1 - i
            return bars_since if bars_since <= max_bars else None
    return None


def _breakout_retest_level(bars: Sequence[OHLCVBar]) -> Optional[float]:
    """The second-chance entry: find the most recent breakout bar — a fresh
    20d high on >=1.3x prior-20d average volume — 3-15 bars back, and return
    its level only if price has come back to it (0-3% above), is holding
    above it, and pullback volume contracted vs the breakout bar. The level
    becomes resistance-turned-support; a close below it fails the setup."""
    bars = list(bars)
    n = len(bars)
    if n < 45:
        return None
    highs = [b.high for b in bars]
    vols = [b.volume or 0.0 for b in bars]
    price = ind.closes(bars).iloc[-1]
    ema20 = ind.ema(bars, 20)
    if ema20 is None or price <= ema20:
        return None
    # latest qualifying breakout bar first; if its level isn't being retested
    # held, no older level rescues the setup
    for i in range(n - 4, max(n - 16, 21), -1):
        prior_vol = vols[i - 20:i]
        avg_vol = sum(prior_vol) / len(prior_vol) if prior_vol else 0.0
        if not (avg_vol > 0 and highs[i] > max(highs[i - 20:i])
                and vols[i] >= 1.3 * avg_vol):
            continue
        level = highs[i]
        if not (level * 0.99 <= price <= level * 1.03):
            return None
        post = vols[i + 1:]
        if post and max(post) >= vols[i]:
            return None
        return level
    return None


def _bollinger(bars: list) -> tuple:
    """20/2 Bollinger bands → (sma20 midline, %b, bandwidth, squeeze).
    squeeze = bandwidth at its 126-day minimum (volatility compression
    that precedes expansion — a timing flag, not a direction signal)."""
    cl = ind.closes(bars)
    if len(cl) < 21:
        return None, None, None, None
    mid_s = cl.rolling(20).mean()
    sd = cl.rolling(20).std()
    mid, s = mid_s.iloc[-1], sd.iloc[-1]
    if not mid or not s or s != s:
        return float(mid) if mid else None, None, None, None
    upper, lower = mid + 2 * s, mid - 2 * s
    pctb = float((cl.iloc[-1] - lower) / (upper - lower)) if upper != lower else None
    bw_series = (4 * sd) / mid_s
    bw = float(bw_series.iloc[-1])
    tail = bw_series.tail(126).dropna()
    squeeze = bool(len(tail) >= 60 and bw <= float(tail.min()) * 1.001)
    return float(mid), pctb, bw, squeeze


def _feature_bars(bars: Sequence[OHLCVBar]) -> StockTechnicals:
    bars = list(bars)
    sma20, pctb, bb_bw, squeeze = _bollinger(bars)
    return StockTechnicals(
        price=ind.closes(bars).iloc[-1] if bars else None,
        ema20=ind.ema(bars, 20),
        sma50=ind.sma(bars, 50),
        sma200=ind.sma(bars, 200),
        rsi=ind.rsi(bars),
        rsi2=ind.rsi(bars, 2),
        trend_turn_bars=_trend_turn_bars(bars),
        macd_hist=ind.macd(bars)[2],
        ret1=ind.returns(bars, 1),
        ret5=ind.returns(bars, 5),
        ret20=ind.returns(bars, 20),
        atr_pct=ind.atr_pct(bars),
        volume_ratio=ind.volume_ratio(bars),
        drawdown20=ind.drawdown_from_high(bars, 20),
        breakout_level=_breakout_retest_level(bars),
        sma20=sma20, bb_pctb=pctb, bb_bandwidth=bb_bw, bb_squeeze=squeeze,
        higher_high=ind.swing_structure(bars)[0],
        higher_low=ind.swing_structure(bars)[1],
    )


def analyze_stock(
    symbol: str,
    bars: Sequence[OHLCVBar],
    spy_bars: Sequence[OHLCVBar],
    sector_bars: Optional[Sequence[OHLCVBar]] = None,
    *,
    sector: Optional[str] = None,
    sector_symbol: Optional[str] = None,
    required_bars: int = 200,
) -> StockAnalysis:
    technicals = _feature_bars(bars)
    reasons = []
    sufficient = len(bars) >= required_bars
    if not sufficient:
        reasons.append(f"insufficient daily history: {len(bars)}/{required_bars} bars")

    stock20, stock60 = ind.returns(list(bars), 20), ind.returns(list(bars), 60)
    spy20, spy60 = ind.returns(list(spy_bars), 20), ind.returns(list(spy_bars), 60)
    sector20 = ind.returns(list(sector_bars), 20) if sector_bars else None
    vs_spy20 = stock20 - spy20 if stock20 is not None and spy20 is not None else None
    vs_spy60 = stock60 - spy60 if stock60 is not None and spy60 is not None else None
    vs_sector20 = stock20 - sector20 if stock20 is not None and sector20 is not None else None
    rs = RelativeStrength(
        vs_spy20=vs_spy20, vs_spy60=vs_spy60, vs_sector20=vs_sector20,
        tier=_tier(vs_spy20), sector_symbol=sector_symbol,
    )

    volume_state = "unknown"
    if technicals.volume_ratio is not None:
        volume_state = "expanding" if technicals.volume_ratio >= 1.3 else "normal"
    sector_alignment = "unknown"
    if vs_sector20 is not None:
        sector_alignment = "aligned" if vs_sector20 >= -0.02 else "lagging"

    if not spy_bars:
        reasons.append("benchmark SPY data unavailable")
    if sector_symbol and not sector_bars:
        reasons.append("sector ETF data unavailable")
    return StockAnalysis(
        symbol=symbol,
        sector=sector,
        technicals=technicals,
        relative_strength=rs,
        sector_alignment=sector_alignment,
        data_quality=StockDataQuality(
            bars=len(bars), required_bars=required_bars, sufficient=sufficient,
            provider=bars[0].provider if bars else None, reasons=reasons,
        ),
        volume_state=volume_state,
    )


def detect_setup(
    stock: StockAnalysis,
    regime: MarketRegime,
    environment: StrategyEnvironment,
) -> SetupAssessment:
    t = stock.technicals
    if not stock.data_quality.sufficient or not environment.data_sufficient:
        return SetupAssessment(reasons=stock.data_quality.reasons + ["swing environment data is insufficient"])

    price, ema20, sma50, sma200 = t.price, t.ema20, t.sma50, t.sma200
    stock_perm = _stock_permission(t)
    falling_knife = bool(
        price is not None and sma50 is not None and sma200 is not None
        and price < sma50 and price < sma200
        and (t.ret20 or 0) < -0.08
        and (t.higher_low is not True)
    )
    if falling_knife:
        return SetupAssessment(
            type=SetupType.NO_SETUP, quality=OpportunityQuality.LOW, score=20,
            confirmation="failed", falling_knife=True, stock_permission=stock_perm,
            reasons=["price below SMA50 and SMA200", "material negative 20d return", "no higher-low confirmation"],
        )

    trend = bool(price is not None and sma50 is not None and price > sma50)
    above_200 = bool(price is not None and sma200 is not None and price > sma200)
    long_strength = (stock.relative_strength.vs_spy20 or -1) >= 0.02
    sector_ok = stock.sector_alignment in {"aligned", "unknown"}

    # Practice patterns (evidence-ranked):
    # first_pullback — first retest of the EMA20 zone after a fresh SMA50
    # trend turn (best documented swing edge: ~63% win, ~2.25 PF).
    # mean_reversion — Connors RSI(2) extreme within a long-term uptrend.
    near_ma = bool(
        ema20 is not None and price is not None and sma50 is not None
        and price <= ema20 * 1.04 and price >= sma50 * 0.98
    )
    orderly_pullback = bool(
        (t.ret5 or 0) < 0
        and (t.higher_low is True or (t.rsi is not None and t.rsi >= 40))
    )
    first_pullback = bool(
        trend and t.trend_turn_bars is not None and t.trend_turn_bars >= 3
        and near_ma and orderly_pullback
    )
    mean_reversion = bool(
        above_200 and t.rsi2 is not None and t.rsi2 < 10
        and (t.ret5 or 0) < 0
    )
    breakout = bool(
        trend and t.drawdown20 is not None and t.drawdown20 >= -0.02
        and t.volume_ratio is not None and t.volume_ratio >= 1.3
        and long_strength and environment.breakout_permission != "restricted"
    )
    # Episodic pivot (Kullamagi): a high-volume thrust day igniting off a
    # beaten-down base — fires before trend confirmation, in the gap between
    # the falling-knife veto clearing and price reclaiming SMA50. dd20 <= -4%
    # keeps it distinct from breakout (which requires price at the high).
    episodic_pivot = bool(
        t.ret1 is not None and t.ret1 >= 0.04
        and t.volume_ratio is not None and t.volume_ratio >= 1.2
        and t.drawdown20 is not None and t.drawdown20 <= -0.04
    )

    breakout_retest = bool(trend and t.breakout_level is not None)

    detected = []
    if first_pullback:
        detected.append("first_pullback")
    if mean_reversion:
        detected.append("rsi2_extreme")
    if breakout:
        detected.append("breakout")
    if breakout_retest:
        detected.append("breakout_retest")
    if episodic_pivot:
        detected.append("episodic_pivot")

    if breakout:
        setup_type = SetupType.BREAKOUT
        base = 60
        reasons = ["price is near the recent high", "volume is expanding", "relative strength confirms"]
    elif breakout_retest:
        setup_type = SetupType.BREAKOUT_RETEST
        base = 60
        reasons = [
            f"retesting the {t.breakout_level:,.2f} breakout level — former resistance acting as support",
            "pullback volume contracted vs the breakout bar — sellers are not pressing",
            "second-chance entry with the tightest stop in the system: just under the level",
        ]
    elif first_pullback:
        setup_type = SetupType.FIRST_PULLBACK
        base = 60
        reasons = [
            f"first pullback since SMA50 trend turn {t.trend_turn_bars} bars ago",
            "price is retesting the EMA20/SMA50 zone",
            "pullback has not broken structure",
        ]
    elif mean_reversion:
        setup_type = SetupType.MEAN_REVERSION
        base = 57
        reasons = [
            f"RSI(2) extreme at {t.rsi2:.0f} within long-term uptrend",
            "price above SMA200 — mean-reversion filter passes",
            "5-day pullback confirms washed-out condition",
        ]
    elif episodic_pivot:
        setup_type = SetupType.EPISODIC_PIVOT
        base = 52
        reasons = [
            f"episodic pivot: {t.ret1:+.1%} thrust on {t.volume_ratio:.1f}x volume",
            f"igniting {t.drawdown20:+.0%} below the 20d high — trend not yet confirmed",
            "counter-trend entry: requires fundamental backing; tight stop applies",
        ]
    elif trend and long_strength:
        setup_type = SetupType.TREND_CONTINUATION
        base = 50
        reasons = ["trend and relative strength are positive but setup is incomplete"]
    else:
        setup_type = SetupType.NO_SETUP
        base = 35
        reasons = ["no qualifying pullback or breakout pattern"]

    score = float(base)
    if long_strength:
        score += 12
    if sector_ok:
        score += 6
    if stock.volume_state == "expanding":
        score += 7
    if t.higher_low:
        score += 5
    if environment.long_permission == "restricted":
        score -= 15
        reasons.append("market environment restricts new swing longs")
    if regime.market_permissions and regime.market_permissions.size_multiplier < 0.5:
        score -= 5
        reasons.append("market size multiplier is reduced")

    # Stock's own regime — kill-zone veto / weak-stock penalty for trend
    # setups; mean_reversion is exempt (weakness is the setup by design).
    index_weak = environment.long_permission in {"limited", "restricted", "disabled"}
    stock_weak = stock_perm in {"limited", "restricted", "disabled"}
    if setup_type == SetupType.EPISODIC_PIVOT:
        # EP fires on weak stocks by design — skip the -8 stock-regime
        # penalty, but keep the kill-zone veto: igniting into a weak market
        # is still dangerous.
        if stock_weak and index_weak:
            score -= 20
            reasons.append(
                f"kill zone: stock regime {stock_perm} + market {environment.long_permission}")
    elif setup_type != SetupType.MEAN_REVERSION:
        if stock_weak and index_weak:
            score -= 20
            reasons.append(
                f"kill zone: stock regime {stock_perm} + market {environment.long_permission}")
        elif stock_perm in {"restricted", "disabled"}:
            score -= 8
            reasons.append(f"stock's own regime is {stock_perm} — trend setups penalized")
    try:
        from app.pattern_learning import score_adjustment
        adj, note = score_adjustment(setup_type.value)
        if adj:
            score += adj
            reasons.append(note)
    except Exception:
        pass
    quality = _quality(max(0, min(100, score)))
    confirmation = "confirmed" if quality == OpportunityQuality.HIGH else "partial"
    return SetupAssessment(
        type=setup_type, quality=quality, score=max(0, min(100, score)),
        confirmation=confirmation, falling_knife=False,
        stock_permission=stock_perm,
        detected_patterns=detected, reasons=reasons,
    )
