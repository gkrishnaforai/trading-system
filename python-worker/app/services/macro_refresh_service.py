"""Macro Refresh Service
Computes and persists market-wide macro snapshot used for market regime detection.

This service produces a single daily row in `macro_market_data`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from app.data_sources import get_data_source
from app.database import db
from app.observability.logging import get_logger
from app.repositories.macro_data_repository import MacroDataRepository


logger = get_logger(__name__)


@dataclass(frozen=True)
class MacroSnapshotConfig:
    nasdaq_proxy_symbol: str = "QQQ"  # practical proxy for NASDAQ trend
    vix_symbol: str = "^VIX"
    tnx_symbol: str = "^TNX"  # 10y
    irx_symbol: str = "^IRX"  # 13-week


class MacroRefreshService:
    def __init__(self, config: Optional[MacroSnapshotConfig] = None):
        self.config = config or MacroSnapshotConfig()
        self.data_source = get_data_source()

    def refresh_daily_macro_snapshot(self, *, snapshot_date: Optional[date] = None) -> Dict[str, Any]:
        """Compute and persist one macro snapshot row."""
        d = snapshot_date or date.today()

        nasdaq_close, nasdaq_sma50, nasdaq_sma200 = self._compute_trend_metrics(
            symbol=self.config.nasdaq_proxy_symbol,
            window_short=50,
            window_long=200,
        )

        vix_close, _, _ = self._compute_trend_metrics(
            symbol=self.config.vix_symbol,
            window_short=5,
            window_long=20,
        )

        tnx, _, _ = self._compute_trend_metrics(symbol=self.config.tnx_symbol, window_short=5, window_long=20)
        irx, _, _ = self._compute_trend_metrics(symbol=self.config.irx_symbol, window_short=5, window_long=20)

        yield_curve_spread = None
        if tnx is not None and irx is not None:
            try:
                yield_curve_spread = float(tnx) - float(irx)
            except Exception:
                yield_curve_spread = None

        sp500_above_50d_pct = self._compute_breadth_proxy()

        payload: Dict[str, Any] = {
            "data_date": d,
            "vix_close": vix_close,
            "nasdaq_symbol": self.config.nasdaq_proxy_symbol,
            "nasdaq_close": nasdaq_close,
            "nasdaq_sma50": nasdaq_sma50,
            "nasdaq_sma200": nasdaq_sma200,
            "tnx_yield": tnx,
            "irx_yield": irx,
            "yield_curve_spread": yield_curve_spread,
            "sp500_above_50d_pct": sp500_above_50d_pct,
            "source": getattr(self.data_source, "name", "unknown"),
        }

        rows = MacroDataRepository.save_macro_data(payload)
        logger.info(
            "✅ Macro snapshot saved",
            extra={
                "data_date": str(d),
                "rows": rows,
                "vix": vix_close,
                "nasdaq_close": nasdaq_close,
                "yield_curve_spread": yield_curve_spread,
                "breadth": sp500_above_50d_pct,
            },
        )

        return payload

    def _compute_trend_metrics(
        self,
        *,
        symbol: str,
        window_short: int,
        window_long: int,
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Fetch 1y daily data and compute latest close, SMA(short), SMA(long)."""
        try:
            df = self.data_source.fetch_price_data(symbol, period="1y")
        except Exception as e:
            logger.warning(f"Failed to fetch macro series {symbol}: {e}")
            return None, None, None

        if df is None or df.empty:
            return None, None, None

        # Normalize columns
        cols = {c.lower(): c for c in df.columns}
        close_col = cols.get("close")
        if not close_col:
            return None, None, None

        close = pd.to_numeric(df[close_col], errors="coerce")
        if close.isna().all():
            return None, None, None

        last_close = float(close.iloc[-1]) if close.iloc[-1] is not None and not np.isnan(close.iloc[-1]) else None
        sma_short = float(close.rolling(window_short).mean().iloc[-1]) if len(close) >= window_short else None
        sma_long = float(close.rolling(window_long).mean().iloc[-1]) if len(close) >= window_long else None
        return last_close, sma_short, sma_long

    def _compute_breadth_proxy(self) -> Optional[float]:
        """Breadth proxy: % of symbols with latest close > latest 50d SMA.

        Uses:
        - raw_market_data_daily.close
        - indicators_daily.sma_50
        """
        try:
            rows = db.execute_query(
                """
                WITH latest_ind AS (
                  SELECT DISTINCT ON (symbol)
                    symbol,
                    date,
                    sma_50
                  FROM indicators_daily
                  WHERE sma_50 IS NOT NULL
                  ORDER BY symbol, date DESC
                ),
                latest_px AS (
                  SELECT DISTINCT ON (symbol)
                    symbol,
                    date,
                    close
                  FROM raw_market_data_daily
                  WHERE close IS NOT NULL
                  ORDER BY symbol, date DESC
                )
                SELECT i.symbol,
                       p.close as close,
                       i.sma_50 as sma_50
                FROM latest_ind i
                JOIN latest_px p
                  ON p.symbol = i.symbol
                """
            )

            if not rows:
                return None

            total = 0
            above = 0
            for r in rows:
                c = r.get("close")
                s = r.get("sma_50")
                if c is None or s is None:
                    continue
                total += 1
                try:
                    if float(c) > float(s):
                        above += 1
                except Exception:
                    continue

            if total == 0:
                return None
            return above / total

        except Exception as e:
            logger.warning(f"Failed to compute breadth proxy: {e}")
            return None
