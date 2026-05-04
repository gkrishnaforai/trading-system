"""
Database Models - Separate from business logic
Follows Single Responsibility Principle
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Boolean, Index, Date, Numeric, UUID, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import JSONB, UUID as psqlUUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


class Stock(Base):
    """Stock information"""
    __tablename__ = "stocks"
    
    id = Column(psqlUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), nullable=False, unique=True)
    exchange = Column(String(10))
    company_name = Column(Text)
    sector = Column(String(50))
    industry = Column(String(100))
    country = Column(String(10))
    currency = Column(String(5))
    market_cap = Column(BigInteger)
    shares_outstanding = Column(BigInteger)
    float_shares = Column(BigInteger)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    next_earnings_date = Column(Date)
    next_earnings_time = Column(Text)
    next_earnings_session = Column(Text)
    next_earnings_source = Column(Text)
    next_earnings_earnings_id = Column(Text)
    next_earnings_updated_at = Column(DateTime)
    next_earnings_at = Column(DateTime)
    next_earnings_timezone = Column(Text)
    rating = Column(String(20))
    price_target = Column(Numeric(10, 2))
    rating_score = Column(Numeric(4, 2))
    rating_updated_at = Column(DateTime)
    rating_data_source = Column(String(50), default="fmp")
    alert_metadata = Column(JSONB, default='{}')
    last_alert_check = Column(DateTime)
    alert_subscription_count = Column(Integer, default=0)
    alert_events_count = Column(Integer, default=0)
    alert_preferences = Column(JSONB, default='{}')
    
    __table_args__ = (
        Index('idx_stocks_symbol', 'symbol'),
        Index('idx_stocks_active', 'is_active'),
    )


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


class MarketNews(Base):
    """Market news articles"""
    __tablename__ = "fmp_market_news"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    text = Column(Text)
    url = Column(String(500))
    image_url = Column(String(500))
    source = Column(String(100))
    published_date = Column(DateTime)
    symbols = Column(JSON)  # List of symbols mentioned
    sentiment = Column(String(20))
    sentiment_score = Column(Float)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_market_news_article_id', 'article_id'),
        Index('idx_market_news_published_date', 'published_date'),
        Index('idx_market_news_source', 'source'),
    )


class StockNews(Base):
    """Stock-specific news articles"""
    __tablename__ = "stock_news"
    
    id = Column(psqlUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stock_id = Column(psqlUUID(as_uuid=True), ForeignKey('stocks.id'), nullable=False)
    published_at = Column(DateTime)
    title = Column(Text, nullable=False)
    publisher = Column(Text)
    url = Column(Text)
    sentiment_score = Column(Numeric(8, 6))
    related_symbols = Column(JSONB)
    source = Column(String(50))
    raw_json = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_stock_news_stock_published', 'stock_id', 'published_at'),
    )


class RealTimePrice(Base):
    """Real-time price data"""
    __tablename__ = "fmp_real_time_prices"
    
    symbol = Column(String(10), primary_key=True)
    price = Column(Float, nullable=False)
    change = Column(Float)
    change_percent = Column(Float)
    volume = Column(Integer)
    day_low = Column(Float)
    day_high = Column(Float)
    year_high = Column(Float)
    year_low = Column(Float)
    market_cap = Column(Integer)
    price_avg_50 = Column(Float)
    price_avg_200 = Column(Float)
    exchange = Column(String(50))
    open_price = Column(Float)
    previous_close = Column(Float)
    price_timestamp = Column(DateTime, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data_source = Column(String(50), default="fmp")
    
    __table_args__ = (
        Index('idx_real_time_price_symbol', 'symbol'),
        Index('idx_real_time_price_timestamp', 'price_timestamp'),
    )


class AnalystRatings(Base):
    """Analyst ratings data"""
    __tablename__ = "analyst_ratings"
    
    symbol = Column(String(10), primary_key=True)
    rating_date = Column(Date, primary_key=True)
    analyst_name = Column(String(100), primary_key=True)
    analyst_firm = Column(String(100))
    rating = Column(String(20))
    rating_action = Column(String(50))
    price_target = Column(Numeric(10, 2))
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    payload = Column(JSON)
    
    __table_args__ = (
        Index('idx_analyst_ratings_symbol_date', 'symbol', 'rating_date'),
        Index('idx_analyst_ratings_firm', 'analyst_firm'),
    )


class PriceTargets(Base):
    """Price targets data"""
    __tablename__ = "price_targets"
    
    symbol = Column(String(10), primary_key=True)
    target_date = Column(Date, primary_key=True)
    analyst_name = Column(String(100), primary_key=True)
    analyst_firm = Column(String(100))
    price_target = Column(Numeric(10, 2))
    rating = Column(String(20))
    price_when_posted = Column(Numeric(10, 2))
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    payload = Column(JSON)
    
    __table_args__ = (
        Index('idx_price_targets_symbol_date', 'symbol', 'target_date'),
        Index('idx_price_targets_target', 'price_target'),
    )


class ConsensusData(Base):
    """Consensus analyst data"""
    __tablename__ = "consensus_data"
    
    symbol = Column(String(10), primary_key=True)
    consensus_date = Column(Date, nullable=False)
    analyst_count = Column(Integer)
    consensus_rating = Column(String(20))
    consensus_price_target = Column(Numeric(10, 2))
    price_target_high = Column(Numeric(10, 2))
    price_target_low = Column(Numeric(10, 2))
    buy_ratings = Column(Integer)
    hold_ratings = Column(Integer)
    sell_ratings = Column(Integer)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    payload = Column(JSON)
    
    __table_args__ = (
        Index('idx_consensus_data_date', 'consensus_date'),
    )
