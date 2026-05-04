"""
Repository Pattern - Follows SOLID Principles
Separates data access from business logic
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from app.observability.logging import get_logger

logger = get_logger("database_repository")


class DatabaseRepository(ABC):
    """Abstract base repository following Dependency Inversion Principle"""
    
    def __init__(self, session_factory=None):
        self.session_factory = session_factory
        self._is_available = session_factory is not None
        
        if not self._is_available:
            logger.warning("⚠️  Database not available - repository in fallback mode")
    
    @property
    def is_available(self) -> bool:
        """Check if database is available"""
        return self._is_available
    
    def _execute_query(self, query_func):
        """Execute a database query with proper error handling"""
        print(f"🔍 BASE REPO DEBUG: _is_available = {self._is_available}")
        if not self._is_available:
            logger.warning("⚠️  Database not available - returning fallback result")
            print(f"🔍 BASE REPO DEBUG: Returning fallback result: {self._get_fallback_result()}")
            return self._get_fallback_result()
        
        try:
            print(f"🔍 BASE REPO DEBUG: Executing query with session")
            with self.session_factory() as session:
                result = query_func(session)
                print(f"🔍 BASE REPO DEBUG: Query result: {result}")
                return result
        except Exception as e:
            print(f"🔍 BASE REPO DEBUG: Exception in query: {e}")
            logger.error(f"❌ Database query error: {e}")
            return self._get_fallback_result()
    
    @abstractmethod
    def _get_fallback_result(self):
        """Get fallback result when database is not available"""
        pass


class StockGradesRepository(DatabaseRepository):
    """Repository for stock grades data"""
    
    def store_grades(self, symbol: str, grades_data: List[Dict[str, Any]]) -> bool:
        """Store stock grades data"""
        def store_in_session(session):
            # Import models here to avoid circular imports
            from app.db_storage.models import StockGrades
            
            stored_count = 0
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
                    stored_count += 1
            
            session.commit()
            logger.info(f"✅ Stored {stored_count} stock grades for {symbol}")
            return True
        
        return self._execute_query(store_in_session)
    
    def get_latest_grades(self, symbol: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
        """Get latest stock grades"""
        def query_grades(session):
            # Import models here to avoid circular imports
            from app.db_storage.models import StockGrades
            
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
        
        return self._execute_query(query_grades)
    
    def get_grades_by_year(self, symbol: str, year: int) -> List[Dict[str, Any]]:
        """Get stock grades for a specific year"""
        def query_grades(session):
            # Import models here to avoid circular imports
            from app.db_storage.models import StockGrades
            
            # Filter by symbol and year
            start_date = datetime(year, 1, 1)
            end_date = datetime(year + 1, 1, 1)
            
            query = session.query(StockGrades).filter(
                StockGrades.symbol == symbol,
                StockGrades.grade_date >= start_date,
                StockGrades.grade_date < end_date
            )
            
            # Order by date descending (latest first)
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
                    "created_at": grade.created_at.isoformat() if grade.created_at else None,
                    "grade_date": grade.grade_date.isoformat() if grade.grade_date else None  # For UI compatibility
                })
            
            return results
        
        return self._execute_query(query_grades)
    
    def get_today_changes(self) -> List[Dict[str, Any]]:
        """Get stock grade changes for today"""
        def query_changes(session):
            # Import models here to avoid circular imports
            from app.db_storage.models import StockGrades
            
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
        
        return self._execute_query(query_changes)
    
    def _get_fallback_result(self):
        """Fallback result when database is not available"""
        return []


class StockNewsRepository(DatabaseRepository):
    """Repository for stock-specific news data"""
    
    def store_news(self, symbol: str, news_articles: List[Dict[str, Any]]) -> bool:
        """Store stock-specific news articles"""
        def store_in_session(session):
            # Import models here to avoid circular imports
            from app.db_storage.models import StockNews, Stock
            
            stored_count = 0
            
            # Get stock record
            stock = session.query(Stock).filter_by(symbol=symbol).first()
            if not stock:
                logger.warning(f"⚠️  Stock {symbol} not found - cannot store news")
                return 0
            
            for article in news_articles:
                # Check if article already exists (avoid duplicates)
                existing = session.query(StockNews).filter_by(
                    stock_id=stock.id,
                    title=article.get("title"),
                    published_at=article.get("publishedDate")
                ).first()
                
                if existing:
                    continue  # Skip existing articles
                
                record_data = {
                    "stock_id": stock.id,
                    "published_at": article.get("publishedDate"),
                    "title": article.get("title"),
                    "publisher": article.get("site"),
                    "url": article.get("url"),
                    "sentiment_score": article.get("sentiment"),
                    "related_symbols": article.get("tickers", []),
                    "source": "fmp",
                    "raw_json": article
                }
                
                news_record = StockNews(**record_data)
                session.add(news_record)
                stored_count += 1
            
            session.commit()
            logger.info(f"✅ Stored {stored_count} news articles for {symbol}")
            return stored_count
        
        return self._execute_query(store_in_session)
    
    def _get_fallback_result(self):
        """Fallback result when database is not available"""
        return False


class MarketNewsRepository(DatabaseRepository):
    """Repository for market news data"""
    
    def store_articles(self, articles: List[Dict[str, Any]]) -> bool:
        """Store market news articles"""
        def store_in_session(session):
            # Import models here to avoid circular imports
            from app.db_storage.models import MarketNews
            
            stored_count = 0
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
                stored_count += 1
            
            session.commit()
            logger.info(f"✅ Stored {stored_count} market news articles")
            return True
        
        return self._execute_query(store_in_session)
    
    def _get_fallback_result(self):
        """Fallback result when database is not available"""
        return True


class AnalystRatingsRepository(DatabaseRepository):
    """Repository for analyst ratings data"""
    
    def store_ratings(self, symbol: str, ratings_data: List[Dict[str, Any]]) -> bool:
        """Store analyst ratings data"""
        def store_in_session(session):
            print(f"🔍 REPO DEBUG: Starting store_ratings for {symbol} with {len(ratings_data)} ratings")
            # Import models here to avoid circular imports
            from app.db_storage.models import AnalystRatings
            
            stored_count = 0
            for i, rating in enumerate(ratings_data):
                print(f"🔍 REPO DEBUG: Processing rating {i+1}: {rating}")
                rating_date = rating.get("ratingDate") or rating.get("publishedAt") or rating.get("date")
                if not rating_date:
                    print(f"🔍 REPO DEBUG: Skipping rating {i+1} - no date")
                    continue
                
                # Parse rating date
                from datetime import datetime
                if isinstance(rating_date, str):
                    try:
                        rating_date = datetime.fromisoformat(rating_date.replace('Z', '+00:00')).date()
                    except:
                        rating_date = datetime.now().date()
                elif isinstance(rating_date, datetime):
                    rating_date = rating_date.date()
                
                print(f"🔍 REPO DEBUG: Parsed rating_date: {rating_date}")
                
                # Check if rating record exists
                try:
                    existing = session.query(AnalystRatings).filter_by(
                        symbol=symbol,
                        rating_date=rating_date,
                        analyst_name=rating.get("analystName", "")
                    ).first()
                    print(f"🔍 REPO DEBUG: Existing record found: {existing is not None}")
                except Exception as query_error:
                    print(f"🔍 REPO DEBUG: Query error: {query_error}")
                    continue
                
                if existing:
                    print(f"🔍 REPO DEBUG: Updating existing record")
                    # Update existing record
                    existing.rating = rating.get("rating")
                    existing.rating_action = rating.get("ratingAction")
                    existing.price_target = rating.get("priceTarget")
                    existing.analyst_firm = rating.get("analystFirm")
                    existing.updated_at = datetime.utcnow()
                else:
                    print(f"🔍 REPO DEBUG: Creating new record")
                    # Create new record
                    import json
                    
                    record_data = {
                        "symbol": symbol,
                        "rating_date": rating_date,
                        "analyst_name": rating.get("analystName", ""),
                        "analyst_firm": rating.get("analystFirm", ""),
                        "rating": rating.get("rating"),
                        "rating_action": rating.get("ratingAction"),
                        "price_target": rating.get("priceTarget"),
                        "published_at": rating.get("publishedAt"),
                        "payload": json.dumps(rating) if rating else "{}"
                    }
                    
                    print(f"🔍 REPO DEBUG: Record data: {record_data}")
                    
                    try:
                        analyst_rating = AnalystRatings(**record_data)
                        session.add(analyst_rating)
                        stored_count += 1
                        print(f"🔍 REPO DEBUG: Added new record, stored_count: {stored_count}")
                    except Exception as create_error:
                        print(f"🔍 REPO DEBUG: Create record error: {create_error}")
                        continue
            
            try:
                print(f"🔍 REPO DEBUG: Attempting to commit session with {stored_count} records")
                session.commit()
                print(f"🔍 REPO DEBUG: Session committed successfully")
                logger.info(f"✅ Stored {stored_count} analyst ratings for {symbol}")
                return True
            except Exception as commit_error:
                print(f"🔍 REPO DEBUG: Commit error: {commit_error}")
                session.rollback()
                print(f"🔍 REPO DEBUG: Session rolled back")
                return False
        
        return self._execute_query(store_in_session)
    
    def _get_fallback_result(self):
        return []


class PriceTargetsRepository(DatabaseRepository):
    """Repository for price targets data"""
    
    def store_price_targets(self, symbol: str, targets_data: List[Dict[str, Any]]) -> bool:
        """Store price targets data"""
        def store_in_session(session):
            # Import models here to avoid circular imports
            from app.db_storage.models import PriceTargets
            from datetime import datetime
            
            stored_count = 0
            for target in targets_data:
                print(f"🔍 REPO DEBUG: Processing price target: {target}")
                
                # Handle consensus data (no individual analyst info)
                if 'targetConsensus' in target or 'targetMedian' in target:
                    print(f"🔍 REPO DEBUG: Processing consensus data")
                    target_date = datetime.now().date()  # Use current date for consensus data
                    analyst_name = "Consensus"
                    analyst_firm = "Market Consensus"
                    price_target = target.get("targetConsensus") or target.get("targetMedian")
                    rating = None
                    price_when_posted = None
                    published_at = datetime.now().isoformat()
                else:
                    # Handle individual analyst data
                    print(f"🔍 REPO DEBUG: Processing individual analyst data")
                    target_date = target.get("targetDate") or target.get("publishedAt")
                    if not target_date:
                        print(f"🔍 REPO DEBUG: Skipping target - no date")
                        continue
                    
                    # Parse target date
                    if isinstance(target_date, str):
                        try:
                            target_date = datetime.fromisoformat(target_date.replace('Z', '+00:00')).date()
                        except:
                            target_date = datetime.now().date()
                    elif isinstance(target_date, datetime):
                        target_date = target_date.date()
                    
                    analyst_name = target.get("analystName", "")
                    analyst_firm = target.get("analystFirm", "")
                    price_target = target.get("priceTarget")
                    rating = target.get("rating")
                    price_when_posted = target.get("priceWhenPosted")
                    published_at = target.get("publishedAt")
                
                print(f"🔍 REPO DEBUG: Parsed target_date: {target_date}")
                
                # Check if target record exists
                try:
                    existing = session.query(PriceTargets).filter_by(
                        symbol=symbol,
                        target_date=target_date,
                        analyst_name=analyst_name
                    ).first()
                    print(f"🔍 REPO DEBUG: Existing record found: {existing is not None}")
                except Exception as query_error:
                    print(f"🔍 REPO DEBUG: Query error: {query_error}")
                    continue
                
                if existing:
                    print(f"🔍 REPO DEBUG: Updating existing record")
                    # Update existing record
                    existing.price_target = price_target
                    existing.rating = rating
                    existing.price_when_posted = price_when_posted
                    existing.analyst_firm = analyst_firm
                    existing.updated_at = datetime.utcnow()
                else:
                    print(f"🔍 REPO DEBUG: Creating new record")
                    # Create new record
                    import json
                    
                    record_data = {
                        "symbol": symbol,
                        "target_date": target_date,
                        "analyst_name": analyst_name,
                        "analyst_firm": analyst_firm,
                        "price_target": price_target,
                        "rating": rating,
                        "price_when_posted": price_when_posted,
                        "published_at": published_at,
                        "payload": json.dumps(target) if target else "{}"
                    }
                    
                    print(f"🔍 REPO DEBUG: Record data: {record_data}")
                    
                    try:
                        price_target_record = PriceTargets(**record_data)
                        session.add(price_target_record)
                        stored_count += 1
                        print(f"🔍 REPO DEBUG: Added new record, stored_count: {stored_count}")
                    except Exception as create_error:
                        print(f"🔍 REPO DEBUG: Create record error: {create_error}")
                        continue
            
            try:
                print(f"🔍 REPO DEBUG: Attempting to commit session with {stored_count} records")
                session.commit()
                print(f"🔍 REPO DEBUG: Session committed successfully")
                logger.info(f"✅ Stored {stored_count} price targets for {symbol}")
                return True
            except Exception as commit_error:
                print(f"🔍 REPO DEBUG: Commit error: {commit_error}")
                session.rollback()
                print(f"🔍 REPO DEBUG: Session rolled back")
                return False
        
        return self._execute_query(store_in_session)
    
    def _get_fallback_result(self):
        return []


class ConsensusDataRepository(DatabaseRepository):
    """Repository for consensus data"""
    
    def store_consensus(self, symbol: str, consensus_data_list: List[Dict[str, Any]]) -> bool:
        """Store consensus data"""
        def store_in_session(session):
            print(f"🔍 REPO DEBUG: Starting store_consensus for {symbol} with {len(consensus_data_list)} consensus records")
            # Import models here to avoid circular imports
            from app.db_storage.models import ConsensusData
            from datetime import datetime
            
            stored_count = 0
            for consensus_data in consensus_data_list:
                print(f"🔍 REPO DEBUG: Processing consensus data: {consensus_data}")
                
                # Parse consensus date - use current date if not provided
                consensus_date = datetime.now().date()
                published_at = datetime.now()
                
                print(f"🔍 REPO DEBUG: Parsed consensus_date: {consensus_date}")
                
                # Check if consensus record exists
                try:
                    existing = session.query(ConsensusData).filter_by(
                        symbol=symbol,
                        consensus_date=consensus_date
                    ).first()
                    print(f"🔍 REPO DEBUG: Existing record found: {existing is not None}")
                except Exception as query_error:
                    print(f"🔍 REPO DEBUG: Query error: {query_error}")
                    continue
                
                if existing:
                    print(f"🔍 REPO DEBUG: Updating existing record")
                    # Update existing record
                    existing.analyst_count = consensus_data.get("analystCount")
                    existing.consensus_rating = consensus_data.get("consensusRating")
                    existing.consensus_price_target = consensus_data.get("priceTarget")
                    existing.price_target_high = consensus_data.get("targetHigh")
                    existing.price_target_low = consensus_data.get("targetLow")
                    existing.buy_ratings = consensus_data.get("buy")
                    existing.hold_ratings = consensus_data.get("hold")
                    existing.sell_ratings = consensus_data.get("sell")
                    existing.published_at = published_at
                    existing.updated_at = datetime.utcnow()
                else:
                    print(f"🔍 REPO DEBUG: Creating new record")
                    # Create new record
                    import json
                    
                    record_data = {
                        "symbol": symbol,
                        "consensus_date": consensus_date,
                        "analyst_count": consensus_data.get("analystCount"),
                        "consensus_rating": consensus_data.get("consensusRating"),
                        "consensus_price_target": consensus_data.get("priceTarget"),
                        "price_target_high": consensus_data.get("targetHigh"),
                        "price_target_low": consensus_data.get("targetLow"),
                        "buy_ratings": consensus_data.get("buy"),
                        "hold_ratings": consensus_data.get("hold"),
                        "sell_ratings": consensus_data.get("sell"),
                        "published_at": published_at,
                        "payload": json.dumps(consensus_data) if consensus_data else "{}"
                    }
                    
                    print(f"🔍 REPO DEBUG: Record data: {record_data}")
                    
                    try:
                        consensus_record = ConsensusData(**record_data)
                        session.add(consensus_record)
                        stored_count += 1
                        print(f"🔍 REPO DEBUG: Added new record, stored_count: {stored_count}")
                    except Exception as create_error:
                        print(f"🔍 REPO DEBUG: Create record error: {create_error}")
                        continue
            
            try:
                print(f"🔍 REPO DEBUG: Attempting to commit session with {stored_count} records")
                session.commit()
                print(f"🔍 REPO DEBUG: Session committed successfully")
                logger.info(f"✅ Stored {stored_count} consensus data records for {symbol}")
                return True
            except Exception as commit_error:
                print(f"🔍 REPO DEBUG: Commit error: {commit_error}")
                session.rollback()
                print(f"🔍 REPO DEBUG: Session rolled back")
                return False
        
        return self._execute_query(store_in_session)
    
    def _get_fallback_result(self):
        return {}


# Factory for creating repositories - follows Factory Pattern
class RepositoryFactory:
    """Factory for creating repository instances"""
    
    @staticmethod
    def create_stock_grades_repository(session_factory=None) -> StockGradesRepository:
        """Create stock grades repository"""
        return StockGradesRepository(session_factory)
    
    @staticmethod
    def create_market_news_repository(session_factory=None) -> MarketNewsRepository:
        """Create market news repository"""
        return MarketNewsRepository(session_factory)
    
    @staticmethod
    def create_stock_news_repository(session_factory=None) -> StockNewsRepository:
        """Create stock news repository"""
        return StockNewsRepository(session_factory)
    
    @staticmethod
    def create_analyst_ratings_repository(session_factory=None) -> 'AnalystRatingsRepository':
        """Create analyst ratings repository"""
        return AnalystRatingsRepository(session_factory)
    
    @staticmethod
    def create_price_targets_repository(session_factory=None) -> 'PriceTargetsRepository':
        """Create price targets repository"""
        return PriceTargetsRepository(session_factory)
    
    @staticmethod
    def create_consensus_data_repository(session_factory=None) -> 'ConsensusDataRepository':
        """Create consensus data repository"""
        return ConsensusDataRepository(session_factory)


# Service layer - follows Single Responsibility Principle
class DatabaseService:
    """High-level database service"""
    
    def __init__(self, session_factory=None):
        self.session_factory = session_factory
        self._stock_grades_repo = RepositoryFactory.create_stock_grades_repository(session_factory)
        self._market_news_repo = RepositoryFactory.create_market_news_repository(session_factory)
        self._stock_news_repo = RepositoryFactory.create_stock_news_repository(session_factory)
        # Add missing analyst data repositories
        self._analyst_ratings_repo = RepositoryFactory.create_analyst_ratings_repository(session_factory)
        self._price_targets_repo = RepositoryFactory.create_price_targets_repository(session_factory)
        self._consensus_data_repo = RepositoryFactory.create_consensus_data_repository(session_factory)
    
    @property
    def stock_grades(self) -> StockGradesRepository:
        """Get stock grades repository"""
        return self._stock_grades_repo
    
    @property
    def market_news(self) -> MarketNewsRepository:
        """Get market news repository"""
        return self._market_news_repo
    
    @property
    def news(self) -> StockNewsRepository:
        """Get stock news repository"""
        return self._stock_news_repo
    
    @property
    def analyst_ratings(self) -> 'AnalystRatingsRepository':
        """Get analyst ratings repository"""
        return self._analyst_ratings_repo
    
    @property
    def price_targets(self) -> 'PriceTargetsRepository':
        """Get price targets repository"""
        return self._price_targets_repo
    
    @property
    def consensus_data(self) -> 'ConsensusDataRepository':
        """Get consensus data repository"""
        return self._consensus_data_repo
    
    def is_available(self) -> bool:
        """Check if database service is available"""
        return self._stock_grades_repo.is_available


# Global service instance - follows Dependency Injection pattern
def get_database_service(session_factory=None) -> DatabaseService:
    """Get database service instance
    
    Args:
        session_factory: Database session factory (optional)
                         If None, will try to get from app.database.db
    """
    if session_factory is None:
        try:
            # Try to get session factory from main database module
            # Use sys.modules to get the module directly, avoiding circular imports
            import sys
            database_module = sys.modules.get('app.database')
            if database_module and hasattr(database_module, 'db'):
                db = database_module.db
                
                # Auto-initialize if not already initialized
                if db.session_factory is None:
                    try:
                        db.initialize()
                        session_factory = db.session_factory
                        logger.info("✅ Database auto-initialized")
                    except Exception as e:
                        logger.warning(f"⚠️  Database initialization failed: {e}")
                        session_factory = None
                else:
                    session_factory = db.session_factory
            else:
                session_factory = None
        except (ImportError, AttributeError):
            # Database not available, use fallback mode
            session_factory = None
    
    return DatabaseService(session_factory)
