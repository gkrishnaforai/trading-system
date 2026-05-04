"""
Stock Grades Repository
Handles storage and retrieval of stock grades/ratings data
"""
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.repositories.base_repository import BaseRepository


class StockGradesRepository(BaseRepository):
    """Repository for stock grades data"""
    
    def store_grades(self, symbol: str, grades: List[Dict[str, Any]]) -> bool:
        """Store stock grades in database"""
        try:
            rows = []
            for grade in grades:
                row = {
                    'stock_symbol': symbol,
                    'grade_date': self._parse_date(grade.get('gradeDate')),
                    'rating': grade.get('rating'),
                    'rating_scale': grade.get('ratingScale'),
                    'rating_symbol': grade.get('ratingSymbol'),
                    'grading_company': grade.get('gradingCompany'),
                    'grade_action': grade.get('gradeAction'),
                    'published_at': self._parse_date(grade.get('publishedAt')),
                    'created_at': datetime.utcnow(),
                    'payload': grade
                }
                rows.append(row)
            
            # Create table if not exists
            self._ensure_table()
            
            # Upsert grades
            BaseRepository.upsert_many(
                table='stock_grades',
                unique_columns=['stock_symbol', 'grade_date', 'grading_company'],
                rows=rows
            )
            
            return True
            
        except Exception as e:
            print(f"Error storing stock grades for {symbol}: {e}")
            return False
    
    def get_recent_grades(self, symbol: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent stock grades for a symbol"""
        try:
            query = """
            SELECT payload, grade_date, grading_company, rating
            FROM stock_grades
            WHERE stock_symbol = %s
              AND grade_date >= NOW() - INTERVAL '%s days'
            ORDER BY grade_date DESC
            """
            result = db.execute_query(query, (symbol, days))
            return [dict(row) for row in result]
        except Exception:
            return []
    
    def _ensure_table(self):
        """Ensure stock_grades table exists"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS stock_grades (
            stock_symbol VARCHAR(20) NOT NULL,
            grade_date DATE NOT NULL,
            grading_company VARCHAR(100),
            rating VARCHAR(20),
            rating_scale VARCHAR(50),
            rating_symbol VARCHAR(10),
            grade_action VARCHAR(50),
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payload JSONB,
            PRIMARY KEY (stock_symbol, grade_date, grading_company)
        );
        
        CREATE INDEX IF NOT EXISTS idx_stock_grades_symbol_date ON stock_grades(stock_symbol, grade_date DESC);
        """
        db.execute_query(create_table_sql)
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None
