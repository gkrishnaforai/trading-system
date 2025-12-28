#!/usr/bin/env python3
"""
Seed stock symbols and fetch initial data
Includes:
- 10 popular swing trading symbols (leveraged ETFs, popular swing stocks)
- 100 trending stocks (S&P 500, NASDAQ 100, popular tech stocks)
"""
import sys
import time
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Popular swing trading symbols (leveraged ETFs, high volatility)
SWING_TRADING_SYMBOLS = [
    'TQQQ',   # 3x NASDAQ-100
    'SQQQ',   # 3x Inverse NASDAQ-100
    'SPY',    # S&P 500 ETF
    'QQQ',    # NASDAQ-100 ETF
    'UVXY',   # VIX Short-Term Futures
    'SVIX',   # Short VIX Futures
    'SOXL',   # 3x Semiconductor
    'LABU',   # 3x Biotech
    'FAS',    # 3x Financial
    'TNA',    # 3x Small Cap
]

# 100 Trending Stocks (S&P 500 top stocks, NASDAQ 100, popular tech)
TRENDING_STOCKS = [
    # Tech Giants
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'NFLX',
    # Semiconductor
    'AMD', 'INTC', 'AVGO', 'MU', 'TXN', 'QCOM', 'AMAT', 'LRCX',
    # Cloud/SaaS
    'CRM', 'NOW', 'SNOW', 'DDOG', 'NET', 'ZS', 'CRWD', 'PANW',
    # AI/ML
    'PLTR', 'AI', 'C3AI', 'SOUN', 'PATH', 'UPST',
    # E-commerce/Retail
    'SHOP', 'ETSY', 'W', 'COIN', 'HOOD',
    # Financial
    'JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'PYPL', 'SQ',
    # Healthcare/Biotech
    'JNJ', 'PFE', 'UNH', 'ABBV', 'LLY', 'MRNA', 'BNTX',
    # Consumer
    'NKE', 'SBUX', 'MCD', 'DIS', 'CMCSA', 'T',
    # Energy
    'XOM', 'CVX', 'SLB', 'COP', 'EOG',
    # Industrial
    'BA', 'CAT', 'DE', 'GE', 'HON', 'RTX',
    # Communication
    'GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA',
    # Utilities
    'NEE', 'DUK', 'SO', 'AEP',
    # Real Estate
    'AMT', 'PLD', 'EQIX', 'PSA',
    # Materials
    'LIN', 'APD', 'ECL', 'SHW',
    # Consumer Staples
    'WMT', 'PG', 'KO', 'PEP', 'COST',
    # Other Popular
    'RIVN', 'LCID', 'F', 'GM', 'RBLX', 'UBER', 'LYFT', 'DASH',
    'ABNB', 'ZM', 'DOCN', 'GTLB', 'ESTC', 'MDB', 'OKTA',
    # ETFs
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO', 'VEA', 'VWO',
]

def fetch_symbol_data(symbol: str, refresh_manager):
    """
    Fetch and save data for a symbol

    Args:
        symbol: Stock symbol
        refresh_manager: Data refresh manager instance
    """
    try:
        logger.info(f"📥 Fetching data for {symbol}...")

        # Fetch historical data (1 year)
        result = refresh_manager.refresh_data(
            symbol=symbol.upper(),
            data_types=[
                'PRICE_HISTORICAL', 'FUNDAMENTALS',
                'EARNINGS', 'INDUSTRY_PEERS'
            ],
            mode='ON_DEMAND',
            force=True
        )

        if result.total_successful > 0:
            logger.info(
                f"✅ {symbol}: Fetched {result.total_successful} data types"
            )

            # Calculate indicators
            try:
                from app.services.indicator_service import IndicatorService
                indicator_service = IndicatorService()
                indicator_service.calculate_indicators(symbol.upper())
                logger.info(f"✅ {symbol}: Indicators calculated")
            except Exception as e:
                logger.warning(
                    f"⚠️ {symbol}: Failed to calculate indicators: {e}"
                )
        else:
            logger.warning(f"⚠️ {symbol}: No data fetched")

    except Exception as e:
        logger.error(
            f"❌ {symbol}: Error fetching data: {e}", exc_info=True
        )


def main():
    """Main seeding function"""
    logger.info("🌱 Starting stock symbol data seeding...")

    try:
        # Initialize database
        from app.database import init_database
        init_database()
        logger.info("✅ Database initialized")

        # Get data source and refresh manager
        from app.data_sources import get_data_source
        from app.data_management.refresh_manager import DataRefreshManager

        data_source = get_data_source()
        refresh_manager = DataRefreshManager(data_source=data_source)

        all_symbols = SWING_TRADING_SYMBOLS + TRENDING_STOCKS
        # Remove duplicates while preserving order
        seen = set()
        unique_symbols = []
        for sym in all_symbols:
            if sym not in seen:
                seen.add(sym)
                unique_symbols.append(sym)

        total_symbols = len(unique_symbols)
        logger.info(f"📊 Total unique symbols to seed: {total_symbols}")
        logger.info(
            f"   - Swing trading symbols: {len(SWING_TRADING_SYMBOLS)}"
        )
        logger.info(f"   - Trending stocks: {len(TRENDING_STOCKS)}")
        logger.info(f"   - Unique total: {total_symbols}")

        # Fetch data for each symbol
        successful = 0
        failed = 0

        for i, symbol in enumerate(unique_symbols, 1):
            logger.info(f"\n[{i}/{total_symbols}] Processing {symbol}...")
            try:
                fetch_symbol_data(symbol, refresh_manager)
                successful += 1
                # Small delay to avoid rate limiting
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"❌ Failed to process {symbol}: {e}")
                failed += 1
                continue

        logger.info("\n" + "=" * 60)
        logger.info("✅ Seeding complete!")
        logger.info(f"   - Successful: {successful}/{total_symbols}")
        logger.info(f"   - Failed: {failed}/{total_symbols}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Seeding failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
