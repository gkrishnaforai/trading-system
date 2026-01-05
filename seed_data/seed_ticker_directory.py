#!/usr/bin/env python3
"""
Seed Ticker Directory (MVP: curated lists only)
Upserts curated symbols into the `stocks` table with Yahoo-enriched metadata.
Usage:
  python seed_data/seed_ticker_directory.py [--limit N] [--symbols AAPL,MSFT] [--no-enrich]
"""
import sys
import time
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Iterable, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'python-worker'))

from app.repositories.base_repository import BaseRepository
from app.providers.yahoo_finance.client import YahooFinanceClient
from app.database import init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import curated symbol lists from existing seed script
sys.path.insert(0, str(Path(__file__).parent.parent / 'db' / 'scripts'))
from seed_stock_symbols import SWING_TRADING_SYMBOLS, TRENDING_STOCKS

def _is_likely_personal_key(s: str) -> bool:
    personal_key_prefixes = {'sk-', 'pk_', 'sk_test_', 'sk_live_', 'acct_'}
    return any(s.startswith(p) for p in personal_key_prefixes)

def _sanitize_metadata(details: Dict[str, Any]) -> Dict[str, Any]:
    """Remove any personal keys from fetched metadata before upsert."""
    return {k: v for k, v in details.items() if not _is_likely_personal_key(str(k).full_name if hasattr(str(k), 'full_name') else str(k))}

def fetch_ticker_metadata(symbols: Iterable[str], enrich: bool = True) -> List[Dict[str, Any]]:
    client = YahooFinanceClient.from_settings()
    rows = []
    for symbol in symbols:
        try:
            logger.info(f"Fetching metadata for {symbol}...")
            details = client.fetch_symbol_details(symbol) if enrich else {"symbol": symbol}
            # Map to stocks table columns (only columns that exist in the schema)
            row = {
                "symbol": symbol,
                "company_name": details.get("name"),
                "exchange": details.get("exchange"),
                "sector": details.get("sector"),
                "industry": details.get("industry"),
                "country": details.get("country"),
                "currency": details.get("currency", "USD"),
                "market_cap": details.get("market_cap"),
                "is_active": True,
            }
            # Sanitize to remove any personal keys
            row = _sanitize_metadata(row)
            rows.append(row)
            # Rate-limit to avoid Yahoo throttling
            time.sleep(0.2)
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for {symbol}: {e}. Inserting minimal row.")
            rows.append({
                "symbol": symbol,
                "company_name": None,
                "exchange": None,
                "sector": None,
                "industry": None,
                "country": None,
                "currency": "USD",
                "market_cap": None,
                "is_active": True,
            })
    return rows

def main():
    parser = argparse.ArgumentParser(description="Seed ticker directory (MVP: curated lists only).")
    parser.add_argument("--limit", type=int, help="Limit number of symbols to process.")
    parser.add_argument("--symbols", help="Comma-separated list of symbols to process (overrides curated lists).")
    parser.add_argument("--no-enrich", action="store_true", help="Skip Yahoo enrichment (insert symbols only).")
    args = parser.parse_args()

    # Initialize DB
    init_database()

    # Determine symbol list
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        logger.info(f"Using provided symbol list: {symbols}")
    else:
        symbols = list(set(SWING_TRADING_SYMBOLS + TRENDING_STOCKS))
        logger.info(f"Using curated lists: {len(symbols)} symbols")

    if args.limit:
        symbols = symbols[:args.limit]
        logger.info(f"Limited to {len(symbols)} symbols")

    logger.info(f"Processing {len(symbols)} symbols...")

    # Fetch metadata
    rows = fetch_ticker_metadata(symbols, enrich=not args.no_enrich)

    # Upsert into stocks table
    try:
        inserted = BaseRepository.upsert_many(
            table="stocks",
            unique_columns=["symbol"],
            rows=rows,
            returning=None,
        )
        logger.info(f"✅ Upserted {inserted} rows into stocks table.")
    except Exception as e:
        logger.error(f"❌ Failed to upsert into stocks table: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
