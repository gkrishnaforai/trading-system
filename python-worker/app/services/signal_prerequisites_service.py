import os
from dataclasses import dataclass
from typing import Dict, List

from app.database import db
from app.repositories.fundamentals_repository import FundamentalsRepository
from app.services.indicator_service import IndicatorService
from app.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SignalPrereqResult:
    ok: bool
    missing: List[str]
    backfilled: List[str]
    indicators_present: Dict[str, bool]
    fundamentals_present: bool


class SignalPrerequisitesService:
    def ensure_ready(
        self,
        symbol: str,
        target_date: str,
        required_indicators: List[str] = None,
        require_fundamentals: bool = None,
    ) -> SignalPrereqResult:
        sym = symbol.strip().upper()

        if required_indicators is None:
            required_indicators = ["rsi_14", "sma_50", "ema_20", "macd", "macd_signal"]
        missing: List[str] = []
        backfilled: List[str] = []

        env_require_fundamentals = (os.getenv("SIGNAL_REQUIRE_FUNDAMENTALS") or "true").strip().lower() == "true"
        if require_fundamentals is None:
            require_fundamentals = env_require_fundamentals
        else:
            # Env var can still force fundamentals requirement system-wide.
            require_fundamentals = bool(require_fundamentals) or env_require_fundamentals
        auto_backfill_indicators = (os.getenv("SIGNAL_AUTO_BACKFILL_INDICATORS") or "true").strip().lower() == "true"
        
        logger.info(f"🔍 DEBUG: ensure_ready called for {sym} on {target_date}")
        logger.info(f"🔍 DEBUG: auto_backfill_indicators = {auto_backfill_indicators}")
        logger.info(f"🔍 DEBUG: required_indicators = {required_indicators}")

        if not self._has_price(sym, target_date):
            missing.append("price")

        logger.info(f"🔍 DEBUG: About to call _indicators_present")
        indicators_present = self._indicators_present(sym, target_date, required_indicators)
        logger.info(f"🔍 DEBUG: _indicators_present returned: {indicators_present}")

        if auto_backfill_indicators and "price" not in missing:
            if any(not v for v in indicators_present.values()):
                ok = False
                try:
                    ok = bool(IndicatorService().calculate_indicators_with_fmp(sym))
                except Exception:
                    ok = False
                if ok:
                    backfilled.append("indicators")
                    indicators_present = self._indicators_present(sym, target_date, required_indicators)

        missing.extend([k for k, v in indicators_present.items() if not v])

        fundamentals_present = bool(FundamentalsRepository().fetch_by_symbol(sym))
        if require_fundamentals and not fundamentals_present:
            missing.append("fundamentals")

        return SignalPrereqResult(
            ok=len(missing) == 0,
            missing=sorted(set(missing)),
            backfilled=backfilled,
            indicators_present=indicators_present,
            fundamentals_present=fundamentals_present,
        )

    def _has_price(self, symbol: str, target_date: str) -> bool:
        try:
            rows = db.execute_query(
                """
                SELECT 1
                FROM raw_market_data_daily
                WHERE symbol = :symbol AND date = CAST(:date AS date)
                LIMIT 1
                """,
                {"symbol": symbol, "date": target_date},
            )
            return bool(rows)
        except Exception:
            return False

    def _indicators_present(self, symbol: str, target_date: str, required: List[str]) -> Dict[str, bool]:
        present = {k: False for k in required}
        logger.info(f"🔍 DEBUG: Checking indicators for {symbol} on {target_date}, required: {required}")
        try:
            # First check narrow format (fmp_api data source)
            rows = db.execute_query(
                """
                SELECT indicator_name
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND date = CAST(:date AS date)
                  AND interval = '1d'
                  AND indicator_name = ANY(:names)
                """,
                {"symbol": symbol, "date": target_date, "names": required},
            )
            logger.info(f"🔍 DEBUG: Narrow format query returned {len(rows or [])} rows")
            for r in rows or []:
                name = str(r.get("indicator_name") or "").strip().lower()
                if name in present:
                    present[name] = True
                    logger.info(f"🔍 DEBUG: Found {name} in narrow format")
            
            # Then check wide format (calculated data source) for MACD indicators
            wide_format_indicators = ['macd', 'macd_signal', 'rsi_14', 'sma_50', 'ema_20']
            wide_required = [k for k in required if k in wide_format_indicators]
            logger.info(f"🔍 DEBUG: Wide format indicators to check: {wide_required}")
            if wide_required:
                wide_rows = db.execute_query(
                    """
                    SELECT macd, macd_signal, rsi_14, sma_50, ema_20
                    FROM indicators_daily
                    WHERE symbol = :symbol
                      AND date = CAST(:date AS date)
                      AND interval = '1d'
                      AND data_source = 'calculated'
                    """,
                    {"symbol": symbol, "date": target_date},
                )
                logger.info(f"🔍 DEBUG: Wide format query returned {len(wide_rows or [])} rows")
                if wide_rows:
                    row = wide_rows[0]
                    logger.info(f"🔍 DEBUG: Wide format row: macd={row.get('macd')}, macd_signal={row.get('macd_signal')}, rsi_14={row.get('rsi_14')}")
                    if 'macd' in wide_required and row.get('macd') is not None:
                        present['macd'] = True
                        logger.info(f"🔍 DEBUG: Found macd in wide format")
                    if 'macd_signal' in wide_required and row.get('macd_signal') is not None:
                        present['macd_signal'] = True
                        logger.info(f"🔍 DEBUG: Found macd_signal in wide format")
                    if 'rsi_14' in wide_required and row.get('rsi_14') is not None:
                        present['rsi_14'] = True
                        logger.info(f"🔍 DEBUG: Found rsi_14 in wide format")
                    if 'sma_50' in wide_required and row.get('sma_50') is not None:
                        present['sma_50'] = True
                        logger.info(f"🔍 DEBUG: Found sma_50 in wide format")
                    if 'ema_20' in wide_required and row.get('ema_20') is not None:
                        present['ema_20'] = True
                        logger.info(f"🔍 DEBUG: Found ema_20 in wide format")
            
            logger.info(f"🔍 DEBUG: Final indicators present: {present}")
            return present
        except Exception as e:
            logger.info(f"🔍 DEBUG: Exception in _indicators_present: {e}")
            return present
