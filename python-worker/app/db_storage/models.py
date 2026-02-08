"""
Database Models - Separate from business logic
Follows Single Responsibility Principle
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class CompanyProfile(Base):
    """Company profile data"""
    __tablename__ = "fmp_company_profiles"
    
    symbol = Column(String(10), primary_key=True)
    company_name = Column(String(255), nullable=False)
    sector = Column(String(100))
    industry = Column(String(100))
    market_cap = Column(Integer)
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
