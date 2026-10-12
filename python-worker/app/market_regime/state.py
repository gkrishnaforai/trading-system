"""Build MarketState / MarketSnapshot from the routed market-data layer.

Quant layer entry point: provider-agnostic — works regardless of
which provider answered (FMP, Yahoo, Massive), because it consumes
canonical models only.

  build_market_state()    — light 8-field state (quick checks)
  build_market_snapshot() — full 6-dimension snapshot + history table
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from app.market_data import MarketDataService, indicators
from app.market_data.models import OHLCVBar

from .models import (
    BreadthState, MacroInstrument, MacroState, MarketSnapshot, MarketState,
    MomentumState, ParticipationState, SectorMove, SnapshotPoint,
    StructureState, TrendState, VolatilityState,
)
from .universe import (
    BREADTH_BASKET, INDEX_ETFS, MACRO_SYMBOLS, ROTATION_ETFS,
    SECTOR_ETFS, SPY, VIX, VIX3M, VXN,
)

logger = logging.getLogger(__name__)

HISTORY_OFFSETS = (0, 1, 5, 20)
MAX_CONCURRENT = 8          # keep Yahoo/FMP happy


# ======================= light state (unchanged API) =======================

async def build_market_state(
    service: MarketDataService,
    include_breadth: bool = True,
) -> MarketState:
    """Fetch SPY data through the router and derive the regime inputs."""
    md = await service.get_market_data(SPY, period="1y", min_bars=200)
    if not md or not md.bars:
        raise ValueError("No SPY bars returned by any provider")

    spy_price = md.bars[-1].close
    as_of = md.bars[-1].timestamp
    provider = getattr(md, "provider", None)

    quote = await service.get_quote(SPY)
    if quote and quote.price:
        spy_price = quote.price
        as_of = quote.as_of or as_of
        provider = getattr(quote, "provider", provider)

    vix = None
    vix_quote = await service.get_quote(VIX)
    if vix_quote and vix_quote.price:
        vix = vix_quote.price

    breadth = await breadth_above_sma50(service) if include_breadth else None

    return MarketState(
        spy_price=spy_price,
        ema20=indicators.ema(md.bars, 20),
        sma50=indicators.sma(md.bars, 50),
        sma200=indicators.sma(md.bars, 200),
        rsi=indicators.rsi(md.bars, 14),
        volume_ratio=indicators.volume_ratio(md.bars, 20),
        breadth_pct=breadth,
        vix=vix,
        as_of=as_of,
        provider=provider,
    )


async def breadth_above_sma50(
    service: MarketDataService,
    etfs: Optional[List[str]] = None,
) -> Optional[float]:
    """% of ETFs trading above their SMA50. Returns None if none fetched."""
    above = total = 0
    for symbol in etfs or SECTOR_ETFS:
        try:
            bars = await service.get_ohlcv(symbol, period="3mo", interval="1d")
            s50 = indicators.sma(bars, 50)
            if s50 is not None and bars:
                total += 1
                if bars[-1].close > s50:
                    above += 1
        except Exception as e:
            logger.warning("breadth: %s skipped (%s)", symbol, e)
    return round(above / total * 100, 1) if total else None


# ======================= full snapshot =======================

YAHOO_FIRST = ["yahoo_finance"]   # ETFs/macro/index symbols FMP doesn't serve


async def _fetch_bars(
    service: MarketDataService,
    symbols: List[str],
    period: str,
    sem: asyncio.Semaphore,
    prefer: Optional[List[str]] = None,
) -> Dict[str, List[OHLCVBar]]:
    """Bounded-concurrency fetch; failures are logged and skipped."""
    async def one(sym: str):
        async with sem:
            try:
                bars = await service.get_ohlcv(
                    sym, period=period, interval="1d", prefer=prefer)
                return sym, bars if bars else None
            except Exception as e:
                logger.debug("fetch %s failed: %s", sym, e)
                return sym, None

    results = await asyncio.gather(*(one(s) for s in symbols))
    return {s: b for s, b in results if b}


def _close_at(bars: List[OHLCVBar], offset: int) -> Optional[float]:
    i = len(bars) - 1 - offset
    return bars[i].close if 0 <= i < len(bars) else None


def _days_below(bars: List[OHLCVBar], ma_series) -> Optional[int]:
    """Consecutive trailing closes below the MA — persistence of the
    break matters more than the break itself (1 red day ≠ 3-day hold)."""
    s = ma_series.dropna()
    if s.empty or len(bars) < 2:
        return None
    n = 0
    for i in range(len(bars) - 1, -1, -1):
        ma = ma_series.get(bars[i].timestamp)
        if ma is None or ma != ma:
            break
        if bars[i].close < ma:
            n += 1
        else:
            break
    return n


def _close_location(bars: List[OHLCVBar], n: int = 1) -> Optional[float]:
    """(C-L)/(H-L): where in the day's range price closed. >0.6 on a
    red day = buyers absorbed the selling; <0.35 = closed near lows."""
    locs = []
    for b in bars[-max(1, n):]:
        rng = b.high - b.low
        if rng and rng > 0:
            locs.append((b.close - b.low) / rng)
    return round(sum(locs) / len(locs), 3) if locs else None


def _pct_above(
    universe: Dict[str, List[OHLCVBar]], window: int, offset: int = 0
) -> Optional[float]:
    """% of symbols with close > SMA(window) at `offset` bars back."""
    above = total = 0
    for bars in universe.values():
        s = indicators.sma_series(bars, window)
        i = len(bars) - 1 - offset
        if i < 0 or i >= len(s):
            continue
        ma = s.iloc[i]
        if ma is None or ma != ma:  # NaN check
            continue
        total += 1
        if bars[i].close > ma:
            above += 1
    return round(above / total * 100, 1) if total else None


def _breadth_state(
    universe: Dict[str, List[OHLCVBar]],
) -> BreadthState:
    advances = declines = new_highs = new_lows = 0
    up_vol = total_vol = 0.0

    for bars in universe.values():
        if len(bars) < 2:
            continue
        last, prev = bars[-1], bars[-2]
        chg = last.close - prev.close
        vol = last.volume or 0
        if chg > 0:
            advances += 1
            up_vol += vol
        elif chg < 0:
            declines += 1
        total_vol += vol
        # 52-week new high/low against all prior bars
        prior = bars[:-1]
        if prior:
            if last.close >= max(b.high for b in prior):
                new_highs += 1
            if last.close <= min(b.low for b in prior):
                new_lows += 1

    return BreadthState(
        universe_size=len(universe),
        pct_above_sma20=_pct_above(universe, 20),
        pct_above_sma50=_pct_above(universe, 50),
        pct_above_sma200=_pct_above(universe, 200),
        advances=advances,
        declines=declines,
        ad_ratio=round(advances / declines, 2) if declines else None,
        new_highs=new_highs,
        new_lows=new_lows,
        up_volume_ratio=round(up_vol / total_vol, 3) if total_vol else None,
        breadth_chg_1d=_breadth_chg(universe, 1),
        breadth_chg_5d=_breadth_chg(universe, 5),
        breadth_chg_20d=_breadth_chg(universe, 20),
    )


def _breadth_chg(universe, offset) -> Optional[float]:
    now = _pct_above(universe, 50, 0)
    then = _pct_above(universe, 50, offset)
    if now is None or then is None:
        return None
    return round(now - then, 1)


async def build_market_snapshot(
    service: MarketDataService,
    breadth_universe: Optional[List[str]] = None,
    include_breadth: bool = True,
    include_macro: bool = True,
) -> MarketSnapshot:
    """Fetch all groups in parallel and compute the 6-dimension state."""
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    coverage: Dict[str, int] = {}

    groups = {
        "index": _fetch_bars(service, [SPY, "QQQ"], "1y", sem),
        "rotation": _fetch_bars(
            service, [s for s in ROTATION_ETFS + INDEX_ETFS if s != SPY],
            "3mo", sem, prefer=YAHOO_FIRST),
        "sectors": _fetch_bars(service, SECTOR_ETFS, "6mo", sem,
                               prefer=YAHOO_FIRST),
        "vix": _fetch_bars(service, [VIX, VIX3M, VXN], "3mo", sem,
                           prefer=YAHOO_FIRST),
    }
    if include_breadth:
        groups["breadth"] = _fetch_bars(
            service, breadth_universe or BREADTH_BASKET, "1y", sem,
            prefer=YAHOO_FIRST)
    if include_macro:
        groups["macro"] = _fetch_bars(
            service, list(MACRO_SYMBOLS.values()), "3mo", sem,
            prefer=YAHOO_FIRST)

    results = dict(zip(groups, await asyncio.gather(*groups.values())))
    for k, v in results.items():
        coverage[k] = len(v)

    spy_bars = (results["index"] or {}).get(SPY)
    if not spy_bars:
        raise ValueError("No SPY bars returned by any provider")
    qqq_bars = (results["index"] or {}).get("QQQ")
    sectors = results.get("sectors") or {}
    breadth_univ = results.get("breadth") or {}
    vix_bars = (results.get("vix") or {}).get(VIX)
    vix3m_bars = (results.get("vix") or {}).get(VIX3M)
    vxn_bars = (results.get("vix") or {}).get(VXN)
    macro_bars = results.get("macro") or {}
    rotation = results.get("rotation") or {}

    close = spy_bars[-1].close

    # ---- trend ----
    sma20 = indicators.sma(spy_bars, 20)
    sma50 = indicators.sma(spy_bars, 50)
    sma200 = indicators.sma(spy_bars, 200)
    ema20 = indicators.ema(spy_bars, 20)
    trend = TrendState(
        spy_price=close,
        ema20=ema20, sma20=sma20, sma50=sma50, sma200=sma200,
        sma20_slope=indicators.sma_slope(spy_bars, 20),
        sma50_slope=indicators.sma_slope(spy_bars, 50),
        sma200_slope=indicators.sma_slope(spy_bars, 200),
        dist_ema20=close / ema20 - 1 if ema20 else None,
        dist_sma50=close / sma50 - 1 if sma50 else None,
        dist_sma200=close / sma200 - 1 if sma200 else None,
        above_sma20=close > sma20 if sma20 else None,
        above_sma50=close > sma50 if sma50 else None,
        above_sma200=close > sma200 if sma200 else None,
        days_below_ema20=_days_below(
            spy_bars, indicators.ema_series(spy_bars, 20)),
        days_below_sma50=_days_below(
            spy_bars, indicators.sma_series(spy_bars, 50)),
    )

    # ---- momentum ----
    macd_line, macd_sig, macd_hist = indicators.macd(spy_bars)
    rsi_now = indicators.rsi(spy_bars)
    rsi_5d = indicators.rsi(spy_bars, offset=5)
    momentum = MomentumState(
        rsi14=rsi_now,
        rsi_5d_ago=rsi_5d,
        rsi_5d_change=rsi_now - rsi_5d if rsi_now and rsi_5d else None,
        macd=macd_line, macd_signal=macd_sig, macd_hist=macd_hist,
        roc5=indicators.roc(spy_bars, 5),
        roc20=indicators.roc(spy_bars, 20),
        ret1=indicators.returns(spy_bars, 1),
        ret5=indicators.returns(spy_bars, 5),
        ret20=indicators.returns(spy_bars, 20),
        close_location=_close_location(spy_bars, 1),
        close_loc_3d=_close_location(spy_bars, 3),
    )

    # ---- breadth ----
    breadth = _breadth_state(breadth_univ) if breadth_univ else BreadthState()

    # ---- volatility ----
    vix = _close_at(vix_bars, 0) if vix_bars else None
    vix_1d = _close_at(vix_bars, 1) if vix_bars else None
    vix_5d = _close_at(vix_bars, 5) if vix_bars else None
    vix3m = _close_at(vix3m_bars, 0) if vix3m_bars else None
    vxn = _close_at(vxn_bars, 0) if vxn_bars else None
    vxn_5d = _close_at(vxn_bars, 5) if vxn_bars else None
    volatility = VolatilityState(
        vix=vix,
        vix_chg_1d=vix - vix_1d if vix and vix_1d else None,
        vix_chg_5d=vix - vix_5d if vix and vix_5d else None,
        vix_pctile_20d=indicators.percentile_rank(
            indicators.closes(vix_bars), 20) if vix_bars else None,
        vix3m=vix3m,
        vxn=vxn,
        vxn_chg_5d=vxn - vxn_5d if vxn and vxn_5d else None,
        vxn_pctile_20d=indicators.percentile_rank(
            indicators.closes(vxn_bars), 20) if vxn_bars else None,
        vxn_vix_ratio=vxn / vix if vxn and vix else None,
        vix_term_ratio=vix3m / vix if vix3m and vix else None,
        atr=indicators.atr(spy_bars),
        atr_pct=indicators.atr_pct(spy_bars),
        rvol5=indicators.realized_vol(spy_bars, 5),
        rvol20=indicators.realized_vol(spy_bars, 20),
    )

    # ---- participation ----
    spy_ret5 = momentum.ret5
    sector_moves: List[SectorMove] = []
    for sym, bars in sectors.items():
        r5 = indicators.returns(bars, 5)
        sector_moves.append(SectorMove(
            symbol=sym,
            ret5=r5,
            ret20=indicators.returns(bars, 20),
            vs_spy5=r5 - spy_ret5 if r5 is not None and spy_ret5 is not None else None,
            above_sma20=(bars[-1].close > indicators.sma(bars, 20))
                        if indicators.sma(bars, 20) else None,
            above_sma50=(bars[-1].close > indicators.sma(bars, 50))
                        if indicators.sma(bars, 50) else None,
        ))
    sector_moves.sort(key=lambda s: s.ret5 or -9)
    rel = {}
    for sym in ("QQQ", "SOXX", "IGV", "IWM"):
        bars = rotation.get(sym)
        if not bars:
            continue
        r5 = indicators.returns(bars, 5)
        if r5 is not None and spy_ret5 is not None:
            rel[sym] = round(r5 - spy_ret5, 4)
    n20 = [s.above_sma20 for s in sector_moves if s.above_sma20 is not None]
    n50 = [s.above_sma50 for s in sector_moves if s.above_sma50 is not None]
    participation = ParticipationState(
        sectors=sector_moves,
        pct_sectors_above_sma20=round(sum(n20) / len(n20) * 100, 1) if n20 else None,
        pct_sectors_above_sma50=round(sum(n50) / len(n50) * 100, 1) if n50 else None,
        rel_strength_5d=rel,
        leading=[s.symbol for s in sector_moves[-3:]],
        lagging=[s.symbol for s in sector_moves[:3]],
    )

    # ---- macro ----
    macro = MacroState(instruments={})
    for name, sym in MACRO_SYMBOLS.items():
        bars = macro_bars.get(sym)
        if not bars:
            continue
        c0, c5 = _close_at(bars, 0), _close_at(bars, 5)
        macro.instruments[name] = MacroInstrument(
            name=name,
            value=c0,
            chg1d=indicators.returns(bars, 1),
            chg5d=indicators.returns(bars, 5),
            chg20d=indicators.returns(bars, 20),
            delta5d=c0 - c5 if c0 is not None and c5 is not None else None,
        )

    # ---- structure ----
    spy_hh, spy_hl = indicators.swing_structure(spy_bars)
    qqq_hh = qqq_hl = qqq_above_50 = None
    if qqq_bars:
        qqq_hh, qqq_hl = indicators.swing_structure(qqq_bars)
        qqq_sma50 = indicators.sma(qqq_bars, 50)
        qqq_above_50 = (qqq_bars[-1].close > qqq_sma50
                        if qqq_sma50 is not None else None)
    soxx_bars = rotation.get("SOXX")
    soxx_ret5 = soxx_hl = None
    if soxx_bars:
        soxx_ret5 = indicators.returns(soxx_bars, 5)
        _, soxx_hl = indicators.swing_structure(soxx_bars)
    structure = StructureState(
        spy_higher_high=spy_hh,
        spy_higher_low=spy_hl,
        qqq_higher_high=qqq_hh,
        qqq_higher_low=qqq_hl,
        qqq_above_sma50=qqq_above_50,
        soxx_ret5=soxx_ret5,
        soxx_higher_low=soxx_hl,
        dist_from_20d_high=indicators.dist_from_extreme(spy_bars, 20, True),
        dist_from_20d_low=indicators.dist_from_extreme(spy_bars, 20, False),
        dist_from_52w_high=indicators.drawdown_from_high(spy_bars),
    )

    # ---- history table ----
    tnx = macro_bars.get(MACRO_SYMBOLS["us10y"])
    history = [
        SnapshotPoint(
            offset_days=o,
            spy=_close_at(spy_bars, o),
            rsi=indicators.rsi(spy_bars, offset=o),
            breadth_pct50=_pct_above(breadth_univ, 50, o) if breadth_univ else None,
            vix=_close_at(vix_bars, o) if vix_bars else None,
            us10y=_close_at(tnx, 0) if tnx and o == 0 else (
                _close_at(tnx, o) if tnx else None),
        )
        for o in HISTORY_OFFSETS
    ]

    return MarketSnapshot(
        as_of=spy_bars[-1].timestamp,
        provider=getattr(spy_bars[-1], "provider", None),
        trend=trend,
        momentum=momentum,
        breadth=breadth,
        volatility=volatility,
        participation=participation,
        macro=macro,
        structure=structure,
        history=history,
        coverage=coverage,
    )
