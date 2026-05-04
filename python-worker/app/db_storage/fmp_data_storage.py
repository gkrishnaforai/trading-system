"""
FMP Data Storage
Database models and storage logic for enhanced FMP data
"""
from sqlalchemy import BigInteger, Column, String, Integer, Float, DateTime, Text, Boolean, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Dict, Any, List, Optional
import json

# Import db directly to avoid circular imports
try:
    from app.database import db
except ImportError:
    # Fallback for testing without full database setup
    class MockDB:
        def __init__(self):
            self.session_factory = None
    db = MockDB()

from app.observability.logging import get_logger

logger = get_logger("fmp_data_storage")

Base = declarative_base()


class CompanyProfile(Base):
    """Company profile data"""
    __tablename__ = "fmp_company_profiles"
    
    symbol = Column(String(10), primary_key=True)
    company_name = Column(String(255), nullable=False)
    sector = Column(String(100))
    industry = Column(String(100))
    market_cap = Column(BigInteger)
    website = Column(String(255))
    description = Column(Text)
    country = Column(String(100))
    currency = Column(String(10))
    exchange = Column(String(50))
    ipo_date = Column(DateTime)
    logo_url = Column(String(255))
    phone = Column(String(50))
    address = Column(String(255))
    city = Column(String(100))
    state = Column(String(100))
    zip = Column(String(20))
    dcf_diff = Column(Float)
    dcf = Column(Float)
    image_url = Column(String(255))
    default_image = Column(Boolean, default=True)
    is_etf = Column(Boolean, default=False)
    is_actively_trading = Column(Boolean, default=True)
    is_adr = Column(Boolean, default=False)
    is_fund = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_company_profile_symbol', 'symbol'),
        Index('idx_company_profile_sector', 'sector'),
        Index('idx_company_profile_industry', 'industry'),
    )


class FinancialStatement(Base):
    """Financial statements (income, balance sheet, cash flow)"""
    __tablename__ = "fmp_financial_statements"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    statement_type = Column(String(50), nullable=False)  # income, balance, cash_flow
    period = Column(String(20), nullable=False)  # quarter, annual
    fiscal_date = Column(DateTime, nullable=False)
    calendar_date = Column(DateTime)
    
    # Financial data
    revenue = Column(Float)
    gross_profit = Column(Float)
    operating_income = Column(Float)
    net_income = Column(Float)
    eps = Column(Float)
    total_assets = Column(Float)
    total_liabilities = Column(Float)
    shareholders_equity = Column(Float)
    cash_from_operations = Column(Float)
    capital_expenditure = Column(Float)
    free_cash_flow = Column(Float)
    
    # Additional data as JSON
    raw_data = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_financial_statement_symbol', 'symbol'),
        Index('idx_financial_statement_type', 'statement_type'),
        Index('idx_financial_statement_period', 'period'),
        Index('idx_financial_statement_date', 'fiscal_date'),
    )


class KeyMetrics(Base):
    """Key financial metrics"""
    __tablename__ = "fmp_key_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    period = Column(String(20), nullable=False)  # quarter, annual, ttm
    fiscal_date = Column(DateTime, nullable=False)
    
    # Valuation metrics
    market_cap = Column(Float)
    enterprise_value = Column(Float)
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    ps_ratio = Column(Float)
    ev_to_sales = Column(Float)
    ev_to_ebitda = Column(Float)
    
    # Profitability metrics
    roe = Column(Float)
    roa = Column(Float)
    roic = Column(Float)
    gross_margin = Column(Float)
    operating_margin = Column(Float)
    net_margin = Column(Float)
    
    # Financial health metrics
    debt_to_equity = Column(Float)
    current_ratio = Column(Float)
    quick_ratio = Column(Float)
    interest_coverage = Column(Float)
    
    # Growth metrics
    revenue_growth = Column(Float)
    eps_growth = Column(Float)
    
    # Additional metrics as JSON
    raw_data = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_key_metrics_symbol', 'symbol'),
        Index('idx_key_metrics_period', 'period'),
        Index('idx_key_metrics_date', 'fiscal_date'),
    )


class StockGrades(Base):
    """Stock grades from analysts and financial institutions"""
    __tablename__ = "fmp_stock_grades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    grade_date = Column(DateTime, nullable=False)
    grading_company = Column(String(100), nullable=False)
    previous_grade = Column(String(20))
    new_grade = Column(String(20), nullable=False)
    action = Column(String(20), nullable=False)  # upgrade, downgrade, maintain
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_stock_grades_symbol', 'symbol'),
        Index('idx_stock_grades_date', 'grade_date'),
        Index('idx_stock_grades_company', 'grading_company'),
        Index('idx_stock_grades_action', 'action'),
    )


class AnalystData(Base):
    """Analyst ratings and recommendations"""
    __tablename__ = "fmp_analyst_data"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    data_type = Column(String(50), nullable=False)  # ratings, price_targets, grades
    rating_date = Column(DateTime)
    
    # Ratings data
    strong_buy = Column(Integer)
    buy = Column(Integer)
    hold = Column(Integer)
    sell = Column(Integer)
    strong_sell = Column(Integer)
    
    # Price targets
    target_high = Column(Float)
    target_low = Column(Float)
    target_mean = Column(Float)
    target_median = Column(Float)
    current_price = Column(Float)
    
    # Grades
    grade = Column(String(10))
    grade_date = Column(DateTime)
    
    # Additional data as JSON
    raw_data = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_analyst_data_symbol', 'symbol'),
        Index('idx_analyst_data_type', 'data_type'),
        Index('idx_analyst_data_date', 'rating_date'),
    )


class MarketNews(Base):
    """Market news articles"""
    __tablename__ = "fmp_market_news"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(String(100), unique=True)
    title = Column(Text, nullable=False)
    text = Column(Text)
    url = Column(String(500))
    image_url = Column(String(500))
    source = Column(String(100))
    published_date = Column(DateTime)
    
    # Symbol associations
    symbols = Column(JSON)  # List of symbols mentioned
    
    # Sentiment analysis (if available)
    sentiment = Column(String(20))
    sentiment_score = Column(Float)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_market_news_published', 'published_date'),
        Index('idx_market_news_source', 'source'),
        Index('idx_market_news_symbols', 'symbols'),
    )


class RealTimePrice(Base):
    """Real-time price data"""
    __tablename__ = "fmp_real_time_prices"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    price = Column(Float, nullable=False)
    change = Column(Float)
    change_percent = Column(Float)
    volume = Column(Integer)
    
    # Additional price data
    day_high = Column(Float)
    day_low = Column(Float)
    year_high = Column(Float)
    year_low = Column(Float)
    market_cap = Column(Float)
    avg_volume = Column(Integer)
    
    # Timestamps
    price_timestamp = Column(DateTime)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_real_time_price_symbol', 'symbol'),
        Index('idx_real_time_price_timestamp', 'price_timestamp'),
    )


class FMPDataStorage:
    """Storage manager for FMP data"""
    
    def __init__(self):
        self.session_factory = None

        try:
            if hasattr(db, "session_factory") and db.session_factory is None:
                db.initialize()
            if hasattr(db, "session_factory") and db.session_factory is not None:
                self.session_factory = db.session_factory
                return
        except Exception as e:
            logger.warning(f"⚠️  Database not available - using fallback mode ({e})")
            self.session_factory = None
            return

        # Fallback for testing without database
        logger.warning("⚠️  Database not available - using fallback mode")
        
    def store_company_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Store company profile data"""
        if self.session_factory is None:
            logger.warning("⚠️  Database not available - skipping storage")
            return False
            
        try:
            with self.session_factory() as session:
                # Check if profile exists
                existing = session.query(CompanyProfile).filter_by(symbol=profile_data.get("symbol")).first()
                
                if existing:
                    # Update existing record
                    for key, value in profile_data.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new record
                    profile = CompanyProfile(**profile_data)
                    session.add(profile)
                
                session.commit()
                logger.info(f"✅ Stored company profile for {profile_data.get('symbol')}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing company profile: {e}")
            return False
    
    def store_financial_statement(self, symbol: str, statement_type: str, period: str, data: List[Dict[str, Any]]) -> bool:
        """Store financial statement data"""
        try:
            with self.session_factory() as session:
                for record in data:
                    fiscal_date = record.get("fiscalDate")
                    if not fiscal_date:
                        continue
                    
                    # Check if record exists
                    existing = session.query(FinancialStatement).filter_by(
                        symbol=symbol,
                        statement_type=statement_type,
                        period=period,
                        fiscal_date=fiscal_date
                    ).first()
                    
                    record_data = {
                        "symbol": symbol,
                        "statement_type": statement_type,
                        "period": period,
                        "fiscal_date": fiscal_date,
                        "calendar_date": record.get("calendarDate"),
                        "revenue": record.get("revenue"),
                        "gross_profit": record.get("grossProfit"),
                        "operating_income": record.get("operatingIncome"),
                        "net_income": record.get("netIncome"),
                        "eps": record.get("eps"),
                        "total_assets": record.get("totalAssets"),
                        "total_liabilities": record.get("totalLiabilities"),
                        "shareholders_equity": record.get("totalShareholderEquity"),
                        "cash_from_operations": record.get("cashFromOperations"),
                        "capital_expenditure": record.get("capitalExpenditure"),
                        "free_cash_flow": record.get("freeCashFlow"),
                        "raw_data": record
                    }
                    
                    if existing:
                        # Update existing record
                        for key, value in record_data.items():
                            if hasattr(existing, key):
                                setattr(existing, key, value)
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Create new record
                        statement = FinancialStatement(**record_data)
                        session.add(statement)
                
                session.commit()
                logger.info(f"✅ Stored {len(data)} {statement_type} records for {symbol}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing financial statement: {e}")
            return False
    
    def store_key_metrics(self, symbol: str, period: str, data: List[Dict[str, Any]]) -> bool:
        """Store key metrics data"""
        try:
            with self.session_factory() as session:
                for record in data:
                    fiscal_date = record.get("date")
                    if not fiscal_date:
                        continue
                    
                    # Check if record exists
                    existing = session.query(KeyMetrics).filter_by(
                        symbol=symbol,
                        period=period,
                        fiscal_date=fiscal_date
                    ).first()
                    
                    record_data = {
                        "symbol": symbol,
                        "period": period,
                        "fiscal_date": fiscal_date,
                        "market_cap": record.get("marketCap"),
                        "enterprise_value": record.get("enterpriseValue"),
                        "pe_ratio": record.get("peRatio"),
                        "pb_ratio": record.get("pbRatio"),
                        "ps_ratio": record.get("psRatio"),
                        "ev_to_sales": record.get("evToSales"),
                        "ev_to_ebitda": record.get("evToEbitda"),
                        "roe": record.get("roe"),
                        "roa": record.get("roa"),
                        "roic": record.get("roic"),
                        "gross_margin": record.get("grossMargin"),
                        "operating_margin": record.get("operatingMargin"),
                        "net_margin": record.get("netMargin"),
                        "debt_to_equity": record.get("debtToEquity"),
                        "current_ratio": record.get("currentRatio"),
                        "quick_ratio": record.get("quickRatio"),
                        "interest_coverage": record.get("interestCoverage"),
                        "revenue_growth": record.get("revenueGrowth"),
                        "eps_growth": record.get("epsGrowth"),
                        "raw_data": record
                    }
                    
                    if existing:
                        # Update existing record
                        for key, value in record_data.items():
                            if hasattr(existing, key):
                                setattr(existing, key, value)
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Create new record
                        metrics = KeyMetrics(**record_data)
                        session.add(metrics)
                
                session.commit()
                logger.info(f"✅ Stored {len(data)} key metrics records for {symbol}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing key metrics: {e}")
            return False
    
    def store_analyst_data(self, symbol: str, data_type: str, data: List[Dict[str, Any]]) -> bool:
        """Store analyst data"""
        try:
            with self.session_factory() as session:
                for record in data:
                    rating_date = record.get("ratingDate") or record.get("date")
                    
                    record_data = {
                        "symbol": symbol,
                        "data_type": data_type,
                        "rating_date": rating_date,
                        "strong_buy": record.get("strongBuy"),
                        "buy": record.get("buy"),
                        "hold": record.get("hold"),
                        "sell": record.get("sell"),
                        "strong_sell": record.get("strongSell"),
                        "target_high": record.get("targetHigh"),
                        "target_low": record.get("targetLow"),
                        "target_mean": record.get("targetMean"),
                        "target_median": record.get("targetMedian"),
                        "current_price": record.get("currentPrice"),
                        "grade": record.get("grade"),
                        "grade_date": record.get("gradeDate"),
                        "raw_data": record
                    }
                    
                    # Create new record (analyst data is time-series)
                    analyst = AnalystData(**record_data)
                    session.add(analyst)
                
                session.commit()
                logger.info(f"✅ Stored {len(data)} {data_type} records for {symbol}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing analyst data: {e}")
            return False
    
    def store_stock_grades(self, symbol: str, grades_data: List[Dict[str, Any]]) -> bool:
        """Store stock grades data"""
        if self.session_factory is None:
            logger.warning("⚠️  Database not available - skipping stock grades storage")
            return False
            
        try:
            with self.session_factory() as session:
                for grade in grades_data:
                    grade_date = grade.get("date")
                    if not grade_date:
                        continue
                    
                    # Check if grade record exists
                    existing = session.query(StockGrades).filter_by(
                        symbol=symbol,
                        grade_date=grade_date,
                        grading_company=grade.get("gradingCompany")
                    ).first()
                    
                    if existing:
                        # Update existing record
                        existing.previous_grade = grade.get("previousGrade")
                        existing.new_grade = grade.get("newGrade")
                        existing.action = grade.get("action")
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Create new record
                        record_data = {
                            "symbol": symbol,
                            "grade_date": grade_date,
                            "grading_company": grade.get("gradingCompany"),
                            "previous_grade": grade.get("previousGrade"),
                            "new_grade": grade.get("newGrade"),
                            "action": grade.get("action")
                        }
                        
                        stock_grade = StockGrades(**record_data)
                        session.add(stock_grade)
                
                session.commit()
                logger.info(f"✅ Stored {len(grades_data)} stock grades for {symbol}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing stock grades: {e}")
            return False
    
    def get_latest_stock_grades(self, symbol: str = None, days: int = 7) -> List[Dict[str, Any]]:
        """Get latest stock grades"""
        if self.session_factory is None:
            logger.warning("⚠️  Database not available - returning empty list")
            return []
            
        try:
            with self.session_factory() as session:
                from datetime import timedelta
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                query = session.query(StockGrades).filter(
                    StockGrades.grade_date >= cutoff_date
                )
                
                if symbol:
                    query = query.filter(StockGrades.symbol == symbol)
                
                # Order by date descending
                grades = query.order_by(StockGrades.grade_date.desc()).all()
                
                results = []
                for grade in grades:
                    results.append({
                        "symbol": grade.symbol,
                        "date": grade.grade_date.isoformat() if grade.grade_date else None,
                        "grading_company": grade.grading_company,
                        "previous_grade": grade.previous_grade,
                        "new_grade": grade.new_grade,
                        "action": grade.action,
                        "created_at": grade.created_at.isoformat() if grade.created_at else None
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"❌ Error fetching latest stock grades: {e}")
            return []
    
    def get_grade_changes_today(self) -> List[Dict[str, Any]]:
        """Get stock grade changes for today"""
        if self.session_factory is None:
            logger.warning("⚠️  Database not available - returning empty list")
            return []
            
        try:
            with self.session_factory() as session:
                today = datetime.utcnow().date()
                
                grades = session.query(StockGrades).filter(
                    StockGrades.grade_date >= today
                ).order_by(StockGrades.grade_date.desc()).all()
                
                results = []
                for grade in grades:
                    # Only include upgrades/downgrades, not maintains
                    if grade.action in ["upgrade", "downgrade"]:
                        results.append({
                            "symbol": grade.symbol,
                            "date": grade.grade_date.isoformat() if grade.grade_date else None,
                            "grading_company": grade.grading_company,
                            "previous_grade": grade.previous_grade,
                            "new_grade": grade.new_grade,
                            "action": grade.action,
                            "created_at": grade.created_at.isoformat() if grade.created_at else None
                        })
                
                return results
                
        except Exception as e:
            logger.error(f"❌ Error fetching today's grade changes: {e}")
            return []
    
    def store_market_news(self, articles: List[Dict[str, Any]]) -> bool:
        """Store market news articles"""
        try:
            with self.session_factory() as session:
                for article in articles:
                    article_id = article.get("id") or f"{article.get('publishedDate')}_{article.get('title')[:50]}"
                    
                    # Check if article exists
                    existing = session.query(MarketNews).filter_by(article_id=article_id).first()
                    
                    if existing:
                        continue  # Skip existing articles
                    
                    record_data = {
                        "article_id": article_id,
                        "title": article.get("title"),
                        "text": article.get("text"),
                        "url": article.get("url"),
                        "image_url": article.get("image"),
                        "source": article.get("source"),
                        "published_date": article.get("publishedDate"),
                        "symbols": article.get("symbols", []),
                        "sentiment": article.get("sentiment"),
                        "sentiment_score": article.get("sentimentScore")
                    }
                    
                    # Create new record
                    news = MarketNews(**record_data)
                    session.add(news)
                
                session.commit()
                logger.info(f"✅ Stored {len(articles)} market news articles")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing market news: {e}")
            return False
    
    def store_real_time_price(self, price_data: Dict[str, Any]) -> bool:
        """Store real-time price data"""
        try:
            with self.session_factory() as session:
                record_data = {
                    "symbol": price_data.get("symbol"),
                    "price": price_data.get("price"),
                    "change": price_data.get("change"),
                    "change_percent": price_data.get("changesPercent"),
                    "volume": price_data.get("volume"),
                    "day_high": price_data.get("dayHigh"),
                    "day_low": price_data.get("dayLow"),
                    "year_high": price_data.get("yearHigh"),
                    "year_low": price_data.get("yearLow"),
                    "market_cap": price_data.get("marketCap"),
                    "avg_volume": price_data.get("avgVolume"),
                    "price_timestamp": price_data.get("timestamp")
                }
                
                # Create new record (real-time data is time-series)
                price = RealTimePrice(**record_data)
                session.add(price)
                
                session.commit()
                logger.info(f"✅ Stored real-time price for {price_data.get('symbol')}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing real-time price: {e}")
            return False
    
    def get_company_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get company profile from database"""
        try:
            with self.session_factory() as session:
                profile = session.query(CompanyProfile).filter_by(symbol=symbol).first()
                
                if profile:
                    return {
                        "symbol": profile.symbol,
                        "company_name": profile.company_name,
                        "sector": profile.sector,
                        "industry": profile.industry,
                        "market_cap": profile.market_cap,
                        "website": profile.website,
                        "description": profile.description,
                        "country": profile.country,
                        "currency": profile.currency,
                        "exchange": profile.exchange,
                        "created_at": profile.created_at.isoformat(),
                        "updated_at": profile.updated_at.isoformat()
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting company profile: {e}")
            return None
    
    def get_latest_financial_statements(self, symbol: str, statement_type: str, period: str = "quarter") -> List[Dict[str, Any]]:
        """Get latest financial statements"""
        try:
            with self.session_factory() as session:
                statements = session.query(FinancialStatement).filter_by(
                    symbol=symbol,
                    statement_type=statement_type,
                    period=period
                ).order_by(FinancialStatement.fiscal_date.desc()).limit(4).all()
                
                return [stmt.raw_data for stmt in statements if stmt.raw_data]
                
        except Exception as e:
            logger.error(f"❌ Error getting financial statements: {e}")
            return []
    
    def get_latest_key_metrics(self, symbol: str, period: str = "quarter") -> List[Dict[str, Any]]:
        """Get latest key metrics"""
        try:
            with self.session_factory() as session:
                metrics = session.query(KeyMetrics).filter_by(
                    symbol=symbol,
                    period=period
                ).order_by(KeyMetrics.fiscal_date.desc()).limit(4).all()
                
                return [metric.raw_data for metric in metrics if metric.raw_data]
                
        except Exception as e:
            logger.error(f"❌ Error getting key metrics: {e}")
            return []
    
    def get_latest_analyst_data(self, symbol: str) -> Dict[str, Any]:
        """Get latest analyst data"""
        try:
            with self.session_factory() as session:
                result = {}
                
                # Get ratings
                ratings = session.query(AnalystData).filter_by(
                    symbol=symbol,
                    data_type="ratings"
                ).order_by(AnalystData.rating_date.desc()).first()
                
                if ratings:
                    result["ratings"] = ratings.raw_data
                
                # Get price targets
                targets = session.query(AnalystData).filter_by(
                    symbol=symbol,
                    data_type="price_targets"
                ).order_by(AnalystData.rating_date.desc()).first()
                
                if targets:
                    result["price_targets"] = targets.raw_data
                
                # Get grades
                grades = session.query(AnalystData).filter_by(
                    symbol=symbol,
                    data_type="grades"
                ).order_by(AnalystData.rating_date.desc()).first()
                
                if grades:
                    result["grades"] = grades.raw_data
                
                return result
                
        except Exception as e:
            logger.error(f"❌ Error getting analyst data: {e}")
            return {}
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to manage database size"""
        try:
            with self.session_factory() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
                
                # Clean up old real-time prices
                deleted_prices = session.query(RealTimePrice).filter(
                    RealTimePrice.created_at < cutoff_date
                ).delete()
                
                # Clean up old market news
                deleted_news = session.query(MarketNews).filter(
                    MarketNews.published_date < cutoff_date
                ).delete()
                
                session.commit()
                logger.info(f"✅ Cleaned up {deleted_prices} old prices and {deleted_news} old news articles")
                
        except Exception as e:
            logger.error(f"❌ Error cleaning up old data: {e}")


# Global storage instance
fmp_storage = FMPDataStorage()
