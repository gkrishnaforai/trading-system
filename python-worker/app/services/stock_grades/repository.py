"""
Stock Grades Repository
Follows SOLID: Single Responsibility Principle
Handles all database operations for stock grades
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from app.database import get_db
from app.services.data_sources.base import StockGrade, ConsensusData

logger = logging.getLogger(__name__)


class StockGradesRepository:
    """Repository for stock grades database operations
    
    Single Responsibility: Only handles database operations
    Data Access Object Pattern - abstracts database access
    """
    
    def __init__(self):
        self.db = get_db()
    
    async def store_grades(self, symbol: str, grades: List[StockGrade]) -> bool:
        """Store stock grades in database
        
        Uses UPSERT logic to prevent duplicates based on unique constraint
        """
        try:
            stored_count = 0
            for grade in grades:
                success = await self._store_single_grade(grade)
                if success:
                    stored_count += 1
            
            logger.info(f"✅ Stored {stored_count}/{len(grades)} grades for {symbol}")
            return stored_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error storing grades for {symbol}: {e}")
            return False
    
    async def _store_single_grade(self, grade: StockGrade) -> bool:
        """Store a single stock grade"""
        try:
            query = """
                INSERT INTO stock_grades (
                    symbol, grade_date, grading_company, previous_grade, new_grade, action,
                    data_source, source_id, price_at_grade, volume_at_grade, market_cap_at_grade
                ) VALUES (
                    :symbol, :grade_date, :grading_company, :previous_grade, :new_grade, :action,
                    :data_source, :source_id, :price_at_grade, :volume_at_grade, :market_cap_at_grade
                )
                ON CONFLICT (symbol, grading_company, grade_date, data_source) 
                DO UPDATE SET
                    previous_grade = EXCLUDED.previous_grade,
                    new_grade = EXCLUDED.new_grade,
                    action = EXCLUDED.action,
                    price_at_grade = EXCLUDED.price_at_grade,
                    volume_at_grade = EXCLUDED.volume_at_grade,
                    market_cap_at_grade = EXCLUDED.market_cap_at_grade,
                    updated_at = NOW()
                RETURNING id
            """
            
            params = {
                'symbol': grade.symbol,
                'grade_date': grade.grade_date,
                'grading_company': grade.grading_company,
                'previous_grade': grade.previous_grade,
                'new_grade': grade.new_grade,
                'action': grade.action,
                'data_source': grade.data_source,
                'source_id': grade.source_id,
                'price_at_grade': grade.price_at_grade,
                'volume_at_grade': grade.volume_at_grade,
                'market_cap_at_grade': grade.market_cap_at_grade
            }
            
            result = self.db.execute_update(query, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"❌ Error storing grade {grade.symbol}: {e}")
            return False
    
    async def get_grades_by_symbol(self, symbol: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get grades for a specific symbol"""
        try:
            query = """
                SELECT id, symbol, grade_date, grading_company, previous_grade, new_grade, action,
                       data_source, source_id, price_at_grade, volume_at_grade, market_cap_at_grade,
                       created_at, updated_at
                FROM stock_grades
                WHERE symbol = :symbol
                ORDER BY grade_date DESC, created_at DESC
            """
            
            params = {'symbol': symbol}
            
            if limit:
                query += " LIMIT :limit"
                params['limit'] = limit
            
            results = self.db.execute_query(query, params)
            
            # Convert datetime objects to strings for JSON response
            formatted_results = []
            for result in results or []:
                formatted_result = result.copy()
                if 'id' in formatted_result and formatted_result['id']:
                    formatted_result['id'] = str(formatted_result['id'])
                if 'grade_date' in formatted_result and formatted_result['grade_date']:
                    formatted_result['grade_date'] = formatted_result['grade_date'].isoformat()
                if 'created_at' in formatted_result and formatted_result['created_at']:
                    formatted_result['created_at'] = formatted_result['created_at'].isoformat()
                if 'updated_at' in formatted_result and formatted_result['updated_at']:
                    formatted_result['updated_at'] = formatted_result['updated_at'].isoformat()
                formatted_results.append(formatted_result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"❌ Error getting grades for {symbol}: {e}")
            return []
    
    async def get_grades_by_year(self, symbol: str, year: int) -> List[Dict[str, Any]]:
        """Get grades for a specific symbol and year"""
        try:
            start_date = date(year, 1, 1)
            end_date = date(year + 1, 1, 1)
            
            query = """
                SELECT id, symbol, grade_date, grading_company, previous_grade, new_grade, action,
                       data_source, source_id, price_at_grade, volume_at_grade, market_cap_at_grade,
                       created_at, updated_at
                FROM stock_grades
                WHERE symbol = :symbol
                  AND grade_date >= :start_date
                  AND grade_date < :end_date
                ORDER BY grade_date DESC, created_at DESC
            """
            
            params = {
                'symbol': symbol,
                'start_date': start_date,
                'end_date': end_date
            }
            
            results = self.db.execute_query(query, params)
            return results or []
            
        except Exception as e:
            logger.error(f"❌ Error getting grades for {symbol} in {year}: {e}")
            return []
    
    async def get_recent_changes(self, symbol: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent grade changes for a symbol"""
        try:
            query = """
                SELECT id, symbol, grade_date, grading_company, previous_grade, new_grade, action,
                       data_source, source_id, price_at_grade, volume_at_grade, market_cap_at_grade,
                       created_at, updated_at
                FROM stock_grades
                WHERE symbol = :symbol
                  AND grade_date >= CURRENT_DATE - (:days || ' days')::interval
                  AND action IN ('upgrade', 'downgrade')
                ORDER BY grade_date DESC, created_at DESC
            """
            
            params = {'symbol': symbol, 'days': days}
            results = self.db.execute_query(query, params)
            return results or []
            
        except Exception as e:
            logger.error(f"❌ Error getting recent changes for {symbol}: {e}")
            return []

    async def get_recent_price_target_changes(self, symbol: str, days: int = 30) -> List[Dict[str, Any]]:
        try:
            query = """
                SELECT id, symbol,
                       old_price_target, new_price_target,
                       old_rating, new_rating,
                       rating_score, change_type,
                       data_source, created_at
                FROM rating_change_log
                WHERE symbol = :symbol
                  AND created_at >= NOW() - (:days || ' days')::interval
                  AND change_type IN ('price_target', 'both')
                  AND old_price_target IS NOT NULL
                  AND new_price_target IS NOT NULL
                  AND old_price_target <> new_price_target
                ORDER BY created_at DESC
            """

            params = {'symbol': symbol, 'days': days}
            results = self.db.execute_query(query, params) or []

            formatted = []
            for r in results:
                item = r.copy()
                if 'id' in item and item['id']:
                    item['id'] = str(item['id'])
                if 'created_at' in item and item['created_at']:
                    item['created_at'] = item['created_at'].isoformat()

                old_pt = item.get('old_price_target')
                new_pt = item.get('new_price_target')
                try:
                    if old_pt is not None and new_pt is not None:
                        delta = float(new_pt) - float(old_pt)
                        item['delta'] = delta
                        item['delta_percent'] = (delta / float(old_pt)) * 100 if float(old_pt) != 0 else None
                except Exception:
                    pass

                formatted.append(item)

            return formatted
        except Exception as e:
            logger.error(f"❌ Error getting recent price target changes for {symbol}: {e}")
            return []
    
    async def get_tier1_firm_grades(self, symbol: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get grades from Tier 1 firms only"""
        try:
            query = """
                SELECT g.id, g.symbol, g.grade_date, g.grading_company, g.previous_grade, g.new_grade, g.action,
                       g.data_source, g.source_id, g.price_at_grade, g.volume_at_grade, g.market_cap_at_grade,
                       g.created_at, g.updated_at
                FROM stock_grades g
                JOIN analyst_firm_rankings afr ON g.grading_company = afr.firm_name
                WHERE g.symbol = :symbol
                  AND afr.tier = 'Tier 1'
                  AND g.grade_date >= CURRENT_DATE - (:days || ' days')::interval
                ORDER BY g.grade_date DESC, g.created_at DESC
            """
            
            params = {'symbol': symbol, 'days': days}
            results = self.db.execute_query(query, params)
            return results or []
            
        except Exception as e:
            logger.error(f"❌ Error getting Tier 1 firm grades for {symbol}: {e}")
            return []
    
    async def store_consensus(self, consensus: ConsensusData) -> bool:
        """Store consensus data"""
        try:
            query = """
                INSERT INTO stock_grade_consensus (
                    symbol, strong_buy, buy, hold, sell, strong_sell, consensus_rating,
                    data_source, last_updated
                ) VALUES (
                    :symbol, :strong_buy, :buy, :hold, :sell, :strong_sell, :consensus_rating,
                    :data_source, NOW()
                )
                ON CONFLICT (symbol) 
                DO UPDATE SET
                    strong_buy = EXCLUDED.strong_buy,
                    buy = EXCLUDED.buy,
                    hold = EXCLUDED.hold,
                    sell = EXCLUDED.sell,
                    strong_sell = EXCLUDED.strong_sell,
                    consensus_rating = EXCLUDED.consensus_rating,
                    data_source = EXCLUDED.data_source,
                    last_updated = NOW()
                RETURNING symbol
            """
            
            params = {
                'symbol': consensus.symbol,
                'strong_buy': consensus.strong_buy,
                'buy': consensus.buy,
                'hold': consensus.hold,
                'sell': consensus.sell,
                'strong_sell': consensus.strong_sell,
                'consensus_rating': consensus.consensus_rating,
                'data_source': consensus.data_source
            }
            
            result = self.db.execute_update(query, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"❌ Error storing consensus for {consensus.symbol}: {e}")
            return False
    
    async def get_consensus(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get consensus data for a symbol"""
        try:
            query = """
                SELECT symbol, strong_buy, buy, hold, sell, strong_sell, consensus_rating,
                       total_analysts, consensus_score, data_source, last_updated, last_checked
                FROM stock_grade_consensus
                WHERE symbol = :symbol
            """
            
            params = {'symbol': symbol}
            result = self.db.execute_query(query, params)
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"❌ Error getting consensus for {symbol}: {e}")
            return None
    
    async def get_consensus_history(self, symbol: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get consensus history for a symbol"""
        try:
            query = """
                SELECT symbol, recorded_at, strong_buy, buy, hold, sell, strong_sell,
                       consensus_rating, consensus_score, total_analysts, confidence_score,
                       consensus_score_change, significance_level, market_impact, data_source, recorded_at
                FROM stock_consensus_history
                WHERE symbol = :symbol
                  AND recorded_at >= CURRENT_DATE - (:days || ' days')::interval
                ORDER BY recorded_at DESC
            """
            
            params = {'symbol': symbol, 'days': days}
            results = self.db.execute_query(query, params)
            return results or []
            
        except Exception as e:
            logger.error(f"❌ Error getting consensus history for {symbol}: {e}")
            return []
    
    async def get_symbols_with_recent_changes(self, days: int = 7) -> List[str]:
        """Get symbols with recent grade changes"""
        try:
            query = """
                SELECT DISTINCT symbol
                FROM stock_grades
                WHERE grade_date >= CURRENT_DATE - (:days || ' days')::interval
                  AND action IN ('upgrade', 'downgrade')
                ORDER BY symbol
            """
            
            params = {'days': days}
            results = self.db.execute_query(query, params)
            return [row['symbol'] for row in results] if results else []
            
        except Exception as e:
            logger.error(f"❌ Error getting symbols with recent changes: {e}")
            return []
    
    async def get_coverage_stats(self) -> Dict[str, Any]:
        """Get coverage statistics"""
        try:
            query = """
                SELECT 
                    COUNT(DISTINCT symbol) as total_symbols,
                    COUNT(DISTINCT grading_company) as total_firms,
                    COUNT(*) as total_ratings,
                    COUNT(CASE WHEN action = 'upgrade' THEN 1 END) as upgrades,
                    COUNT(CASE WHEN action = 'downgrade' THEN 1 END) as downgrades,
                    COUNT(CASE WHEN action = 'maintain' THEN 1 END) as maintains,
                    COUNT(CASE WHEN grade_date >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as last_7_days
                FROM stock_grades
            """
            
            result = self.db.execute_query(query)
            return result[0] if result else {}
            
        except Exception as e:
            logger.error(f"❌ Error getting coverage stats: {e}")
            return {}
