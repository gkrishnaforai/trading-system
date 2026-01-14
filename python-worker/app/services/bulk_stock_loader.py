"""
Bulk Stock Loading Script
Populate stocks table with comprehensive stock information from various sources
"""

import asyncio
import aiohttp
import time
from typing import List, Dict, Any
import logging
from sqlalchemy import create_engine, text
from app.config import settings

logger = logging.getLogger(__name__)

class BulkStockLoader:
    """Bulk stock loader with multiple data sources"""
    
    def __init__(self):
        self.engine = create_engine(settings.database_url)
        self.loaded_symbols = set()
        self.failed_symbols = []
        
    def get_existing_symbols(self) -> set:
        """Get symbols already in the database"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT symbol FROM stocks WHERE is_active = true"))
                return {row[0] for row in result.fetchall()}
        except Exception as e:
            logger.error(f"Error getting existing symbols: {e}")
            return set()
    
    def get_popular_stocks(self) -> List[str]:
        """Get list of popular stocks to load"""
        return [
            # Tech Giants
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "ADBE",
            
            # Major ETFs
            "SPY", "QQQ", "IWM", "VTI", "VOO", "GLD", "SLV", "TLT",
            
            # 3x Leveraged ETFs
            "TQQQ", "SOXL", "FNGU", "TECL", "WEBL", "YINN", "DPST", "LABU",
            
            # Financial Stocks
            "JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK",
            
            # Healthcare
            "JNJ", "PFE", "UNH", "ABBV", "TMO", "ABT", "MRK", "DHR",
            
            # Consumer
            "PG", "KO", "PEP", "WMT", "COST", "HD", "MCD", "NKE",
            
            # Energy
            "XOM", "CVX", "COP", "EOG", "SLB", "HAL", "BP", "SHEL",
            
            # Industrial
            "CAT", "GE", "HON", "MMM", "UPS", "RTX", "BA", "DE",
            
            # Emerging Tech
            "PLTR", "RIVN", "LCID", "SNAP", "ROKU", "ZM", "SQ", "DOCU",
            
            # Crypto Related
            "COIN", "MARA", "RIOT", "MSTR", "SQ", "PYPL",
            
            # Meme Stocks
            "GME", "AMC", "BB", "NOK", "BABA", "JD",
            
            # Biotech
            "MRNA", "BNTX", "PFE", "JNJ", "AZN", "GILD",
            
            # Semiconductor
            "AMD", "INTC", "QCOM", "TXN", "MU", "AMAT",
            
            # Retail
            "TGT", "LOW", "BBY", "TJX", "ROST", "KR",
            
            # Telecom
            "VZ", "T", "TMUS", "CMCSA", "CHTR",
            
            # Utilities
            "NEE", "DUK", "SO", "AEP", "XEL",
            
            # REITs
            "AMT", "PLD", "CCI", "EQIX", "PSA",
            
            # Materials
            "LIN", "APD", "SHW", "DD", "DOW",
            
            # International
            "ASML", "SAP", "TSM", "NESN", "NOVOB",
            
            # Indices
            "^VIX", "^VVIX", "^SPX", "^NDX", "^DJI",
            
            # Additional Popular Stocks
            "DIS", "NFLX", "UBER", "LYFT", "TWTR", "SNAP", "EA", "ATVI"
        ]
    
    async def fetch_yahoo_finance_info(self, session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
        """Fetch stock information from Yahoo Finance API with retry logic"""
        max_retries = 3
        base_delay = 2.0  # Start with 2 second delay
        
        for attempt in range(max_retries):
            try:
                url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
                params = {
                    "modules": "summaryDetail,assetProfile,defaultKeyStatistics,price"
                }
                
                # Add delay between requests to avoid rate limiting
                if attempt > 0:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    await asyncio.sleep(delay)
                
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        result = data.get('quoteSummary', {}).get('result', [])
                        if result:
                            quote_data = result[0]
                            
                            # Extract information from different modules
                            summary_detail = quote_data.get('summaryDetail', {})
                            asset_profile = quote_data.get('assetProfile', {})
                            key_stats = quote_data.get('defaultKeyStatistics', {})
                            price_info = quote_data.get('price', {})
                            
                            return {
                                'symbol': symbol,
                                'company_name': asset_profile.get('longName') or asset_profile.get('shortName') or symbol,
                                'sector': asset_profile.get('sector'),
                                'industry': asset_profile.get('industry'),
                                'market_cap': summary_detail.get('marketCap', {}).get('raw'),
                                'country': asset_profile.get('country'),
                                'currency': summary_detail.get('currency', 'USD'),
                                'exchange': price_info.get('exchangeName') or summary_detail.get('exchange'),
                                'current_price': price_info.get('regularMarketPrice', {}).get('raw'),
                                'success': True
                            }
                    
                    elif response.status == 429:
                        # Rate limited - wait and retry
                        if attempt < max_retries - 1:
                            wait_time = base_delay * (2 ** attempt)
                            logger.warning(f"Rate limited for {symbol}, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            return {'symbol': symbol, 'success': False, 'error': 'Rate limit exceeded after retries'}
                    
                    return {'symbol': symbol, 'success': False, 'error': f'HTTP {response.status}'}
                    
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
                    continue
                return {'symbol': symbol, 'success': False, 'error': 'Timeout after retries'}
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
                    continue
                return {'symbol': symbol, 'success': False, 'error': str(e)}
        
        return {'symbol': symbol, 'success': False, 'error': 'Max retries exceeded'}
    
    def insert_stock_data(self, stock_info: Dict[str, Any]) -> bool:
        """Insert stock data into database"""
        try:
            with self.engine.connect() as conn:
                insert_query = """
                    INSERT INTO stocks (
                        symbol, company_name, sector, industry, market_cap, 
                        country, currency, exchange, is_active, updated_at
                    )
                    VALUES (
                        :symbol, :company_name, :sector, :industry, :market_cap,
                        :country, :currency, :exchange, :is_active, NOW()
                    )
                    ON CONFLICT (symbol) DO UPDATE SET
                        company_name = EXCLUDED.company_name,
                        sector = EXCLUDED.sector,
                        industry = EXCLUDED.industry,
                        market_cap = EXCLUDED.market_cap,
                        country = EXCLUDED.country,
                        currency = EXCLUDED.currency,
                        exchange = EXCLUDED.exchange,
                        updated_at = NOW()
                """
                
                conn.execute(text(insert_query), {
                    'symbol': stock_info['symbol'],
                    'company_name': stock_info.get('company_name'),
                    'sector': stock_info.get('sector'),
                    'industry': stock_info.get('industry'),
                    'market_cap': stock_info.get('market_cap'),
                    'country': stock_info.get('country'),
                    'currency': stock_info.get('currency', 'USD'),
                    'exchange': stock_info.get('exchange'),
                    'is_active': True
                })
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error inserting {stock_info['symbol']}: {e}")
            return False
    
    async def load_stocks_batch(self, symbols: List[str], batch_size: int = 5) -> Dict[str, Any]:
        """Load stocks in batches to avoid rate limiting"""
        results = {
            'total': len(symbols),
            'loaded': 0,
            'failed': 0,
            'skipped': 0,
            'details': []
        }
        
        existing_symbols = self.get_existing_symbols()
        
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(symbols) + batch_size - 1)//batch_size}")
                
                # Fetch batch data sequentially to avoid rate limiting
                batch_results = []
                for symbol in batch:
                    result = await self.fetch_yahoo_finance_info(session, symbol)
                    batch_results.append(result)
                    # Add delay between individual requests
                    await asyncio.sleep(1.0)  # 1 second between requests
                
                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error(f"Exception in batch processing: {result}")
                        results['failed'] += 1
                        continue
                    
                    symbol = result['symbol']
                    
                    # Skip if already exists
                    if symbol in existing_symbols:
                        results['skipped'] += 1
                        results['details'].append({
                            'symbol': symbol,
                            'status': 'skipped',
                            'reason': 'Already exists'
                        })
                        continue
                    
                    # Process successful fetch
                    if result.get('success'):
                        if self.insert_stock_data(result):
                            results['loaded'] += 1
                            results['details'].append({
                                'symbol': symbol,
                                'status': 'loaded',
                                'company': result.get('company_name'),
                                'sector': result.get('sector')
                            })
                            logger.info(f"✅ Loaded: {symbol} - {result.get('company_name')}")
                        else:
                            results['failed'] += 1
                            results['details'].append({
                                'symbol': symbol,
                                'status': 'failed',
                                'reason': 'Database insert failed'
                            })
                    else:
                        results['failed'] += 1
                        self.failed_symbols.append(symbol)
                        results['details'].append({
                            'symbol': symbol,
                            'status': 'failed',
                            'reason': result.get('error', 'Unknown error')
                        })
                        logger.warning(f"❌ Failed: {symbol} - {result.get('error')}")
                
                # Rate limiting - longer delay between batches
                if i + batch_size < len(symbols):
                    await asyncio.sleep(3.0)  # 3 seconds between batches
        
        return results
    
    async def load_all_popular_stocks(self) -> Dict[str, Any]:
        """Load all popular stocks"""
        symbols = self.get_popular_stocks()
        logger.info(f"Starting bulk load of {len(symbols)} popular stocks")
        
        results = await self.load_stocks_batch(symbols, batch_size=5)
        
        logger.info(f"Bulk load completed:")
        logger.info(f"  Total: {results['total']}")
        logger.info(f"  Loaded: {results['loaded']}")
        logger.info(f"  Failed: {results['failed']}")
        logger.info(f"  Skipped: {results['skipped']}")
        
        return results
    
    def get_database_summary(self) -> Dict[str, Any]:
        """Get summary of stocks in database"""
        try:
            with self.engine.connect() as conn:
                # Total stocks
                total_result = conn.execute(text("SELECT COUNT(*) as total FROM stocks WHERE is_active = true"))
                total = total_result.fetchone()[0]
                
                # By sector
                sector_result = conn.execute(text("""
                    SELECT sector, COUNT(*) as count 
                    FROM stocks 
                    WHERE is_active = true AND sector IS NOT NULL 
                    GROUP BY sector 
                    ORDER BY count DESC
                """))
                sectors = {row[0]: row[1] for row in sector_result.fetchall()}
                
                # By exchange
                exchange_result = conn.execute(text("""
                    SELECT exchange, COUNT(*) as count 
                    FROM stocks 
                    WHERE is_active = true AND exchange IS NOT NULL 
                    GROUP BY exchange 
                    ORDER BY count DESC
                """))
                exchanges = {row[0]: row[1] for row in exchange_result.fetchall()}
                
                # Recent additions
                recent_result = conn.execute(text("""
                    SELECT symbol, company_name, updated_at 
                    FROM stocks 
                    WHERE is_active = true 
                    ORDER BY updated_at DESC 
                    LIMIT 10
                """))
                recent = [
                    {
                        'symbol': row[0],
                        'company': row[1],
                        'updated_at': row[2]
                    }
                    for row in recent_result.fetchall()
                ]
                
                return {
                    'total_stocks': total,
                    'by_sector': sectors,
                    'by_exchange': exchanges,
                    'recent_additions': recent
                }
                
        except Exception as e:
            logger.error(f"Error getting database summary: {e}")
            return {'error': str(e)}

async def main():
    """Main function to run bulk stock loading"""
    loader = BulkStockLoader()
    
    print("🚀 Starting Bulk Stock Loading...")
    print("=" * 50)
    
    # Show current database state
    print("📊 Current Database Summary:")
    summary = loader.get_database_summary()
    if 'error' not in summary:
        print(f"  Total stocks: {summary['total_stocks']}")
        print(f"  Sectors: {len(summary['by_sector'])}")
        print(f"  Exchanges: {len(summary['by_exchange'])}")
    print()
    
    # Load stocks
    results = await loader.load_all_popular_stocks()
    
    print("\n" + "=" * 50)
    print("📈 Loading Results:")
    print(f"  Total processed: {results['total']}")
    print(f"  ✅ Successfully loaded: {results['loaded']}")
    print(f"  ❌ Failed: {results['failed']}")
    print(f"  ⏭️ Skipped (already exist): {results['skipped']}")
    
    if loader.failed_symbols:
        print(f"\n❌ Failed symbols: {', '.join(loader.failed_symbols)}")
    
    # Show final database state
    print("\n📊 Final Database Summary:")
    final_summary = loader.get_database_summary()
    if 'error' not in final_summary:
        print(f"  Total stocks: {final_summary['total_stocks']}")
        
        if final_summary['by_sector']:
            print("\n🏢 Top Sectors:")
            for sector, count in list(final_summary['by_sector'].items())[:5]:
                print(f"    {sector}: {count}")
        
        if final_summary['by_exchange']:
            print("\n📈 Top Exchanges:")
            for exchange, count in list(final_summary['by_exchange'].items())[:5]:
                print(f"    {exchange}: {count}")
        
        print("\n🕐 Recent Additions:")
        for recent in final_summary['recent_additions'][:5]:
            print(f"    {recent['symbol']} - {recent['company']}")

if __name__ == "__main__":
    asyncio.run(main())
