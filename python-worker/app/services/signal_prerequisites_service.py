import os
from dataclasses import dataclass
from typing import Dict, List

from app.database import db
from app.repositories.fundamentals_repository import FundamentalsRepository
from app.services.indicator_service import IndicatorService


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

        if not self._has_price(sym, target_date):
            missing.append("price")

        indicators_present = self._indicators_present(sym, target_date, required_indicators)

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
        try:
            rows = db.execute_query(
                """
                SELECT indicator_name
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND date = CAST(:date AS date)
                  AND indicator_name = ANY(:names)
                GROUP BY indicator_name
                """,
                {"symbol": symbol, "date": target_date, "names": required},
            )
            for r in rows or []:
                name = str(r.get("indicator_name") or "").strip().lower()
                if name in present:
                    present[name] = True
            return present
        except Exception:
            return present
