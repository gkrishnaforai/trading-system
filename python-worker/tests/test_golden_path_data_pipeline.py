"""Golden-path regression test for data pipeline.

This is intended to be the primary integration test you run after any change to:
- data sources / provider clients
- refresh manager
- indicator/signal generation
- screeners

It acts as an executable contract for what the Go API can rely on:
- base daily bars exist in Postgres
- latest indicators + signal exist in Postgres
- screener can query across the derived tables without schema errors

Notes:
- Uses real data sources (no mocks). Skips if required provider config is missing.
- Uses Postgres migrations in db/migrations_postgres via init_database().
"""

import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.database import init_database, db
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import DataType, RefreshMode
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.services.stock_screener_service import StockScreenerService
from app.utils.database_helper import DatabaseQueryHelper


class TestGoldenPathDataPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

        cls.refresh_manager = DataRefreshManager()
        cls.indicator_service = IndicatorService()
        cls.strategy_service = StrategyService()
        cls.screener_service = StockScreenerService()

        # Keep this small so it is fast and stable.
        cls.symbols = ["AAPL", "MSFT"]

        # Skip if no provider is usable.
        # - Massive requires MASSIVE_ENABLED=true and API key.
        # - Otherwise the system should fall back to Yahoo/fallback.
        if settings.primary_data_provider == "massive" or settings.default_data_provider == "massive":
            if not settings.massive_enabled or not settings.massive_api_key:
                raise unittest.SkipTest("Massive configured but not enabled or API key missing")

    def _assert_min_rows(self, table: str, symbol: str, min_rows: int):
        rows = db.execute_query(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE stock_symbol = :symbol",
            {"symbol": symbol},
        )
        cnt = rows[0]["cnt"] if rows else 0
        self.assertGreaterEqual(cnt, min_rows, f"{symbol}: expected >= {min_rows} rows in {table}, got {cnt}")
        return cnt

    def test_golden_path_refresh_indicators_signal_screener(self):
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                # 1) Refresh base datasets.
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL, DataType.FUNDAMENTALS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
                )

                price_res = result.results.get(DataType.PRICE_HISTORICAL.value)
                self.assertIsNotNone(price_res, f"{symbol}: missing price_historical result")
                self.assertEqual(price_res.status.value, "success", f"{symbol}: price refresh failed: {price_res.error}")

                # 2) Validate base data exists (Go API contract: it can read it from Postgres).
                bars = self._assert_min_rows("raw_market_data_daily", symbol, min_rows=200)

                # 3) Indicators should have been auto-calculated by refresh_manager.
                latest = db.execute_query(
                    """
                    SELECT *
                    FROM indicators_daily
                    WHERE stock_symbol = :symbol
                    ORDER BY trade_date DESC
                    LIMIT 1
                    """,
                    {"symbol": symbol},
                )
                self.assertTrue(latest, f"{symbol}: expected latest indicators row")

                # Sanity check required fields.
                row = latest[0]
                self.assertIn("signal", row)
                self.assertIn(row["signal"], ["buy", "sell", "hold", None])

                # 4) Execute strategy explicitly using latest indicators (guard against API changes).
                # Build minimal indicator dict from DBHelper + recent market data.
                indicators_row = DatabaseQueryHelper.get_latest_indicators(symbol)
                self.assertIsNotNone(indicators_row, f"{symbol}: no indicators available via helper")

                # Fetch market data via DB helper for strategy validation.
                market_data = DatabaseQueryHelper.get_historical_data(symbol)
                self.assertGreaterEqual(len(market_data), 200, f"{symbol}: expected >= 200 historical bars")

                # Prepare minimal Series-based structure (StrategyService expects series-like inputs).
                import pandas as pd

                md_df = pd.DataFrame(market_data)
                md_df["date"] = pd.to_datetime(md_df["date"])
                md_df.set_index("date", inplace=True)

                indicators = {
                    "price": md_df["close"],
                    "close": md_df["close"],
                    "sma50": pd.Series([indicators_row.get("sma_50")]),
                    "sma200": pd.Series([indicators_row.get("sma_200")]),
                    "ema20": pd.Series([indicators_row.get("ema_20")]),
                    "rsi": pd.Series([indicators_row.get("rsi_14")]),
                    "macd": pd.Series([indicators_row.get("macd")]),
                    "macd_signal": pd.Series([indicators_row.get("macd_signal")]),
                }

                strategy_result = self.strategy_service.execute_strategy(
                    strategy_name="technical",
                    indicators=indicators,
                    market_data=md_df,
                    context={"symbol": symbol},
                )
                self.assertIsNotNone(strategy_result)
                self.assertIn(strategy_result.signal, ["buy", "sell", "hold"])

                # 5) Screener should run without schema errors and return structured output.
                screener_result = self.screener_service.screen_stocks(max_rsi=70.0, limit=50)
                self.assertIsInstance(screener_result, dict)
                self.assertIn("stocks", screener_result)
                self.assertIn("count", screener_result)
                self.assertGreaterEqual(screener_result["count"], 0)

                # If our symbol is present, it should have expected keys.
                for stock in screener_result["stocks"]:
                    if stock.get("symbol") == symbol:
                        self.assertIn("current_price", stock)
                        self.assertIn("rsi", stock)

                # Extra: ensure we have a refresh state row.
                state_rows = db.execute_query(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM data_ingestion_state
                    WHERE stock_symbol = :symbol
                    """,
                    {"symbol": symbol},
                )
                self.assertGreaterEqual(state_rows[0]["cnt"], 1, f"{symbol}: expected ingestion state row")

                # Quick printed context if running with -s.
                print(f"{symbol}: bars={bars}, strategy_signal={strategy_result.signal}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
