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
        if not self._is_available:
            logger.warning("⚠️  Database not available - returning fallback result")
            return self._get_fallback_result()
        
        try:
            with self.session_factory() as session:
                return query_func(session)
        except Exception as e:
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


# Service layer - follows Single Responsibility Principle
class DatabaseService:
    """High-level database service"""
    
    def __init__(self, session_factory=None):
        self.session_factory = session_factory
        self._stock_grades_repo = RepositoryFactory.create_stock_grades_repository(session_factory)
        self._market_news_repo = RepositoryFactory.create_market_news_repository(session_factory)
    
    @property
    def stock_grades(self) -> StockGradesRepository:
        """Get stock grades repository"""
        return self._stock_grades_repo
    
    @property
    def market_news(self) -> MarketNewsRepository:
        """Get market news repository"""
        return self._market_news_repo
    
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
