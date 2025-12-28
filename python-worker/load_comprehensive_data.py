#!/usr/bin/env python3
"""
Comprehensive Data Loading Script
Uses flexible data service to load from optimal sources:
- Historical data from Yahoo (deep coverage)
- Real-time/premium data from Massive
- Technical indicators from Massive
- Fundamentals from both sources
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd

from app.services.flexible_data_service import flexible_data_service, DataSource, DataStrategy
from app.data_sources.massive_fundamentals import MassiveFundamentalsLoader
from app.database import db
from sqlalchemy import text
from app.observability.logging import get_logger

logger = get_logger("comprehensive_data_loader")

class ComprehensiveDataLoader:
    """Load comprehensive market data using optimal sources"""
    
    def __init__(self):
        self.flexible_service = flexible_data_service
        self.massive_loader = MassiveFundamentalsLoader()
        
        # Popular symbols to load
        self.symbols = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM", 
            "JNJ", "V", "PG", "UNH", "HD", "MA", "BAC", "XOM", "PFE", "CSCO", "ADBE"
        ]
    
    def load_all_data(self, symbols: List[str] = None):
        """Load comprehensive data for all symbols"""
        if symbols is None:
            symbols = self.symbols
        
        logger.info(f"🚀 Starting comprehensive data load for {len(symbols)} symbols")
        
        # Initialize database
        if db.session_factory is None:
            db.initialize()
        
        # Create tables
        self._create_tables()
        
        results = {
            "price_data": {},
            "technical_indicators": {},
            "fundamentals": {},
            "market_sentiment": {}
        }
        
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"📊 Loading data for {symbol} ({i}/{len(symbols)})")
            
            try:
                # 1. Load Historical Price Data (from Yahoo)
                price_result = self._load_price_data(symbol)
                results["price_data"][symbol] = price_result
                
                # 2. Load Technical Indicators (from Massive)
                indicators_result = self._load_technical_indicators(symbol)
                results["technical_indicators"][symbol] = indicators_result
                
                # 3. Load Fundamentals (from Massive with Yahoo fallback)
                fundamentals_result = self._load_fundamentals(symbol)
                results["fundamentals"][symbol] = fundamentals_result
                
                # 4. Load Market Sentiment (from Massive)
                sentiment_result = self._load_market_sentiment(symbol)
                results["market_sentiment"][symbol] = sentiment_result
                
                logger.info(f"✅ Completed {symbol}: Price={price_result}, Indicators={indicators_result}, "
                          f"Fundamentals={fundamentals_result}, Sentiment={sentiment_result}")
                
            except Exception as e:
                logger.error(f"❌ Failed to load data for {symbol}: {e}")
                continue
        
        # Print summary
        self._print_summary(results)
        
        return results
    
    def _create_tables(self):
        """Create necessary database tables"""
        try:
            with db.get_session() as session:
                # Create price data table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS market_price_data (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        date DATE NOT NULL,
                        open_price DECIMAL(20,4),
                        high_price DECIMAL(20,4),
                        low_price DECIMAL(20,4),
                        close_price DECIMAL(20,4),
                        volume BIGINT,
                        adjusted_close DECIMAL(20,4),
                        data_source VARCHAR(20),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, date)
                    )
                """))
                
                # Create fundamentals summary table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS fundamentals_summary (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        data_type VARCHAR(50) NOT NULL,
                        period_end DATE,
                        market_cap DECIMAL(20,2),
                        revenue DECIMAL(20,2),
                        net_income DECIMAL(20,2),
                        pe_ratio DECIMAL(10,4),
                        pb_ratio DECIMAL(10,4),
                        debt_to_equity DECIMAL(10,4),
                        roe DECIMAL(10,4),
                        data_source VARCHAR(20),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, data_type, period_end)
                    )
                """))
                
                session.commit()
                logger.info("✅ Database tables created/verified")
                
        except Exception as e:
            logger.error(f"❌ Failed to create tables: {e}")
            raise
    
    def _load_price_data(self, symbol: str) -> int:
        """Load historical price data from Yahoo"""
        try:
            # Get 5 years of historical data from Yahoo
            end_date = datetime.now()
            start_date = end_date - timedelta(days=5*365)
            
            price_data = self.flexible_service.get_price_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                data_source=DataSource.YAHOO,
                strategy=DataStrategy.YAHOO_FIRST
            )
            
            if price_data is not None and not price_data.empty:
                # Save to database
                records = []
                for date, row in price_data.iterrows():
                    records.append({
                        'symbol': symbol,
                        'date': date.date(),
                        'open_price': row.get('Open'),
                        'high_price': row.get('High'),
                        'low_price': row.get('Low'),
                        'close_price': row.get('Close'),
                        'volume': row.get('Volume'),
                        'adjusted_close': row.get('Adj Close'),
                        'data_source': 'yahoo'
                    })
                
                self._save_price_data(records)
                logger.info(f"✅ Loaded {len(records)} price records for {symbol}")
                return len(records)
            else:
                logger.warning(f"⚠️ No price data available for {symbol}")
                return 0
                
        except Exception as e:
            logger.error(f"❌ Failed to load price data for {symbol}: {e}")
            return 0
    
    def _load_technical_indicators(self, symbol: str) -> int:
        """Load technical indicators from Massive"""
        try:
            # Create tables if needed
            self.massive_loader.create_fundamentals_tables()
            
            # Load all technical indicators
            indicators = ["RSI", "MACD", "EMA", "SMA"]
            total_records = 0
            
            for indicator in indicators:
                if indicator == "RSI":
                    data = self.massive_loader.load_rsi(symbol, limit="30")
                elif indicator == "MACD":
                    data = self.massive_loader.load_macd(symbol, limit="30")
                elif indicator == "EMA":
                    data = self.massive_loader.load_ema(symbol, limit="30")
                elif indicator == "SMA":
                    data = self.massive_loader.load_sma(symbol, limit="30")
                
                if data:
                    self.massive_loader.save_to_database("massive_technical_indicators", data)
                    total_records += len(data)
            
            logger.info(f"✅ Loaded {total_records} technical indicator records for {symbol}")
            return total_records
            
        except Exception as e:
            logger.error(f"❌ Failed to load technical indicators for {symbol}: {e}")
            return 0
    
    def _load_fundamentals(self, symbol: str) -> int:
        """Load fundamentals from Massive with Yahoo fallback"""
        try:
            # Create tables if needed
            self.massive_loader.create_fundamentals_tables()
            
            total_records = 0
            
            # Try Massive first
            try:
                balance_data = self.massive_loader.load_balance_sheets(symbol, limit=5)
                if balance_data:
                    self.massive_loader.save_to_database("massive_balance_sheets", balance_data)
                    total_records += len(balance_data)
                
                income_data = self.massive_loader.load_income_statements(symbol, limit=5)
                if income_data:
                    self.massive_loader.save_to_database("massive_income_statements", income_data)
                    total_records += len(income_data)
                
                cash_flow_data = self.massive_loader.load_cash_flow_statements(symbol, limit=5)
                if cash_flow_data:
                    self.massive_loader.save_to_database("massive_cash_flow_statements", cash_flow_data)
                    total_records += len(cash_flow_data)
                
                ratios_data = self.massive_loader.load_financial_ratios(symbol, limit=5)
                if ratios_data:
                    self.massive_loader.save_to_database("massive_financial_ratios", ratios_data)
                    total_records += len(ratios_data)
                
            except Exception as massive_error:
                logger.warning(f"⚠️ Massive fundamentals failed for {symbol}, trying Yahoo: {massive_error}")
                
                # Fallback to Yahoo
                yahoo_fundamentals = self.flexible_service.get_fundamentals(
                    symbol=symbol,
                    data_source=DataSource.YAHOO,
                    strategy=DataStrategy.YAHOO_FIRST
                )
                
                # Save Yahoo fundamentals to summary table
                self._save_fundamentals_summary(symbol, yahoo_fundamentals, "yahoo")
                total_records += sum(1 for v in yahoo_fundamentals.values() if v)
            
            logger.info(f"✅ Loaded {total_records} fundamental records for {symbol}")
            return total_records
            
        except Exception as e:
            logger.error(f"❌ Failed to load fundamentals for {symbol}: {e}")
            return 0
    
    def _load_market_sentiment(self, symbol: str) -> int:
        """Load market sentiment data from Massive"""
        try:
            # Create tables if needed
            self.massive_loader.create_fundamentals_tables()
            
            total_records = 0
            
            # Load short interest
            short_interest = self.massive_loader.load_short_interest(symbol, limit=10)
            if short_interest:
                self.massive_loader.save_to_database("massive_short_interest", short_interest)
                total_records += len(short_interest)
            
            # Load short volume
            short_volume = self.massive_loader.load_short_volume(symbol, limit=10)
            if short_volume:
                self.massive_loader.save_to_database("massive_short_volume", short_volume)
                total_records += len(short_volume)
            
            logger.info(f"✅ Loaded {total_records} sentiment records for {symbol}")
            return total_records
            
        except Exception as e:
            logger.error(f"❌ Failed to load market sentiment for {symbol}: {e}")
            return 0
    
    def _save_price_data(self, records: List[Dict[str, Any]]):
        """Save price data to database"""
        try:
            with db.get_session() as session:
                for record in records:
                    # Upsert price data
                    session.execute(text("""
                        INSERT INTO market_price_data 
                        (symbol, date, open_price, high_price, low_price, close_price, volume, adjusted_close, data_source)
                        VALUES (:symbol, :date, :open_price, :high_price, :low_price, :close_price, :volume, :adjusted_close, :data_source)
                        ON CONFLICT (symbol, date) 
                        DO UPDATE SET 
                            open_price = EXCLUDED.open_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            close_price = EXCLUDED.close_price,
                            volume = EXCLUDED.volume,
                            adjusted_close = EXCLUDED.adjusted_close,
                            data_source = EXCLUDED.data_source
                    """), record)
                
                session.commit()
                
        except Exception as e:
            logger.error(f"❌ Failed to save price data: {e}")
            raise
    
    def _save_fundamentals_summary(self, symbol: str, fundamentals: Dict[str, Any], source: str):
        """Save fundamentals summary to database"""
        try:
            with db.get_session() as session:
                # Extract key metrics from Yahoo fundamentals
                ratios = fundamentals.get("ratios", {})
                
                record = {
                    'symbol': symbol,
                    'data_type': 'summary',
                    'period_end': datetime.now().date(),
                    'market_cap': None,  # Would need to extract from ticker info
                    'revenue': None,     # Would need to extract from financials
                    'net_income': None,  # Would need to extract from financials
                    'pe_ratio': ratios.get('pe_ratio'),
                    'pb_ratio': ratios.get('pb_ratio'),
                    'debt_to_equity': ratios.get('debt_to_equity'),
                    'roe': ratios.get('roe'),
                    'data_source': source
                }
                
                session.execute(text("""
                    INSERT INTO fundamentals_summary 
                    (symbol, data_type, period_end, market_cap, revenue, net_income, pe_ratio, pb_ratio, debt_to_equity, roe, data_source)
                    VALUES (:symbol, :data_type, :period_end, :market_cap, :revenue, :net_income, :pe_ratio, :pb_ratio, :debt_to_equity, :roe, :data_source)
                    ON CONFLICT (symbol, data_type, period_end) 
                    DO UPDATE SET 
                        market_cap = EXCLUDED.market_cap,
                        revenue = EXCLUDED.revenue,
                        net_income = EXCLUDED.net_income,
                        pe_ratio = EXCLUDED.pe_ratio,
                        pb_ratio = EXCLUDED.pb_ratio,
                        debt_to_equity = EXCLUDED.debt_to_equity,
                        roe = EXCLUDED.roe,
                        data_source = EXCLUDED.data_source
                """), record)
                
                session.commit()
                
        except Exception as e:
            logger.error(f"❌ Failed to save fundamentals summary: {e}")
    
    def _print_summary(self, results: Dict[str, Any]):
        """Print loading summary"""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE DATA LOADING SUMMARY")
        print("="*80)
        
        # Calculate totals
        total_price = sum(results["price_data"].values())
        total_indicators = sum(results["technical_indicators"].values())
        total_fundamentals = sum(results["fundamentals"].values())
        total_sentiment = sum(results["market_sentiment"].values())
        
        print(f"\n📈 Price Data Records: {total_price:,}")
        print(f"📊 Technical Indicators: {total_indicators:,}")
        print(f"💰 Fundamentals Records: {total_fundamentals:,}")
        print(f"📉 Market Sentiment Records: {total_sentiment:,}")
        print(f"🎯 Total Records Loaded: {total_price + total_indicators + total_fundamentals + total_sentiment:,}")
        
        # Check data sources
        sources = flexible_data_service.get_available_sources()
        print(f"\n🔌 Data Sources Available:")
        print(f"   ✅ Yahoo Finance: {'Available' if sources['yahoo'] else 'Not Available'}")
        print(f"   ✅ Massive API: {'Available' if sources['massive'] else 'Not Available'}")
        
        # Readiness assessment
        print(f"\n🎯 STRATEGY READINESS:")
        if total_price > 0 and total_indicators > 0:
            print("   ✅ Technical Analysis Strategies: READY")
        else:
            print("   ❌ Technical Analysis Strategies: NEEDS DATA")
        
        if total_fundamentals > 0:
            print("   ✅ Fundamental Analysis Strategies: READY")
        else:
            print("   ❌ Fundamental Analysis Strategies: NEEDS DATA")
        
        if total_sentiment > 0:
            print("   ✅ Sentiment Analysis Strategies: READY")
        else:
            print("   ❌ Sentiment Analysis Strategies: NEEDS DATA")
        
        print("\n🚀 READY FOR STRATEGY DEVELOPMENT!")


def main():
    """Main loading function"""
    loader = ComprehensiveDataLoader()
    
    # Load data for all symbols
    results = loader.load_all_data()
    
    print("\n✅ Comprehensive data loading completed!")
    return results


if __name__ == "__main__":
    main()
