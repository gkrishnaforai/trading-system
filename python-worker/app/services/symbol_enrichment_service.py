"""
Service for enriching missing symbols with comprehensive stock data.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from app.repositories.stocks_repository import StocksRepository, MissingSymbolsRepository
from app.repositories.earnings_calendar_repository import EarningsCalendarRepository
from app.database import db

logger = logging.getLogger(__name__)

class SymbolEnrichmentService:
    """Service for enriching missing symbols with stock data."""
    
    def __init__(self):
        # TODO: Initialize Alpha Vantage service when available
        # self.alpha_vantage = AlphaVantageService()
        pass
    
    def process_missing_symbols(self, batch_size: int = 10) -> Dict[str, int]:
        """Process pending missing symbols in batches."""
        results = {
            'processed': 0,
            'completed': 0,
            'failed': 0,
            'skipped': 0
        }
        
        # Get pending symbols
        pending_symbols = MissingSymbolsRepository.get_pending_symbols(batch_size)
        
        if not pending_symbols:
            logger.info("No pending symbols to process")
            return results
        
        logger.info(f"Processing {len(pending_symbols)} pending symbols")
        
        for symbol_record in pending_symbols:
            try:
                results['processed'] += 1
                
                # Check if symbol already exists in stocks table
                if StocksRepository.symbol_exists(symbol_record['symbol']):
                    MissingSymbolsRepository.mark_completed(symbol_record['id'])
                    results['completed'] += 1
                    continue
                
                # Enrich symbol with data
                stock_data = self._enrich_symbol(symbol_record['symbol'])
                
                if stock_data:
                    # Insert into stocks table
                    StocksRepository.upsert_stock(stock_data)
                    MissingSymbolsRepository.mark_completed(symbol_record['id'])
                    results['completed'] += 1
                    logger.info(f"Successfully enriched symbol: {symbol_record['symbol']}")
                else:
                    MissingSymbolsRepository.mark_failed(
                        symbol_record['id'], 
                        "Unable to fetch symbol data"
                    )
                    results['failed'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing symbol {symbol_record['symbol']}: {e}")
                MissingSymbolsRepository.mark_failed(
                    symbol_record['id'], 
                    str(e)
                )
                results['failed'] += 1
        
        return results
    
    def _enrich_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Enrich a single symbol with comprehensive data."""
        try:
            symbol = symbol.upper()
            
            # TODO: Implement Alpha Vantage integration
            # For now, return basic placeholder data
            logger.warning(f"Symbol enrichment not yet implemented for: {symbol}")
            return None
            
            # Original implementation (commented out until Alpha Vantage service exists):
            # overview = self.alpha_vantage.get_symbol_overview(symbol)
            # if not overview:
            #     logger.warning(f"No data found for symbol: {symbol}")
            #     return None
            # ... rest of the logic
            
        except Exception as e:
            logger.error(f"Error enriching symbol {symbol}: {e}")
            return None
    
    def _parse_numeric(self, value: str) -> Optional[int]:
        """Parse numeric values from Alpha Vantage response."""
        if not value or value == 'None':
            return None
        
        try:
            # Remove commas and convert to integer
            return int(float(str(value).replace(',', '')))
        except (ValueError, TypeError):
            return None
    
    def _get_existing_earnings_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get existing earnings data for a symbol."""
        try:
            query = """
            SELECT company_name, sector, industry, MAX(updated_at) as last_update
            FROM earnings_calendar 
            WHERE symbol = %s
            GROUP BY company_name, sector, industry
            """
            result = db.execute_query(query, (symbol,))
            return result[0] if result else None
        except Exception:
            return None
    
    def check_and_queue_missing_symbols(self, source_table: str) -> int:
        """Check a source table for missing symbols and queue them."""
        queued_count = 0
        
        if source_table == 'earnings_calendar':
            # Get symbols from earnings that are not in stocks table
            query = """
            SELECT DISTINCT ec.symbol, ec.id as source_record_id
            FROM earnings_calendar ec
            LEFT JOIN stocks s ON ec.symbol = s.symbol
            WHERE s.symbol IS NULL
            LIMIT 100
            """
            
            missing_symbols = db.execute_query(query)
            
            for symbol_record in missing_symbols:
                if MissingSymbolsRepository.add_missing_symbol(
                    symbol_record['symbol'], 
                    'earnings_calendar',
                    symbol_record['source_record_id']
                ):
                    queued_count += 1
        
        elif source_table == 'market_news':
            # Get symbols from market news that are not in stocks table
            query = """
            SELECT DISTINCT mn.related_symbols, mn.id as source_record_id
            FROM market_news mn
            LEFT JOIN stocks s ON mn.related_symbols ? s.symbol
            WHERE s.symbol IS NULL
            AND mn.related_symbols IS NOT NULL
            LIMIT 100
            """
            
            missing_symbols = db.execute_query(query)
            
            for record in missing_symbols:
                # Parse JSON array of symbols
                try:
                    import json
                    symbols = json.loads(record['related_symbols'])
                    for symbol in symbols:
                        if symbol and MissingSymbolsRepository.add_missing_symbol(
                            symbol, 
                            'market_news',
                            record['source_record_id']
                        ):
                            queued_count += 1
                except (json.JSONDecodeError, TypeError):
                    continue
        
        logger.info(f"Queued {queued_count} missing symbols from {source_table}")
        return queued_count
