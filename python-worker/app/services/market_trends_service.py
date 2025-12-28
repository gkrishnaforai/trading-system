"""
Market Trends Service
Calculates market trends for heat maps and trend analysis
Industry Standard: Market trend analysis and visualization
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


class MarketTrendsService(BaseService):
    """
    Service for calculating market trends
    
    SOLID: Single Responsibility - only handles market trends
    """
    
    def __init__(self):
        """Initialize market trends service"""
        super().__init__()
    
    def calculate_market_trends(self, snapshot_date: date = None) -> Dict[str, Any]:
        """
        Calculate market trends for sectors, industries, and market cap categories
        
        Args:
            snapshot_date: Date for snapshot (default: today)
        
        Returns:
            Dictionary with trend data
        """
        if snapshot_date is None:
            snapshot_date = date.today()
        
        try:
            # Calculate sector trends
            sector_trends = self._calculate_sector_trends(snapshot_date)
            
            # Calculate industry trends
            industry_trends = self._calculate_industry_trends(snapshot_date)
            
            # Calculate market cap trends
            market_cap_trends = self._calculate_market_cap_trends(snapshot_date)
            
            # Calculate overall market trend
            overall_trend = self._calculate_overall_trend(sector_trends)
            
            trends = {
                "date": snapshot_date.isoformat(),
                "sectors": sector_trends,
                "industries": industry_trends,
                "market_cap": market_cap_trends,
                "overall": overall_trend,
                "timestamp": datetime.now().isoformat()
            }
            
            # Save to database
            self._save_trends(trends, snapshot_date)
            
            return trends
            
        except Exception as e:
            logger.error(f"Error calculating market trends: {e}", exc_info=True)
            raise DatabaseError(f"Failed to calculate market trends: {str(e)}") from e
    
    def get_market_trends(self, trend_type: str = None, category: str = None) -> List[Dict[str, Any]]:
        """
        Get market trends from database
        
        Args:
            trend_type: Type of trend (sector, industry, market_cap, overall)
            category: Specific category (sector name, industry name, etc.)
        
        Returns:
            List of trend data
        """
        try:
            query = """
                SELECT date, trend_type, category, trend_score, price_change_avg,
                       volume_change_avg, momentum_score, strength
                FROM market_trends
                WHERE date = (SELECT MAX(date) FROM market_trends)
            """
            params = {}
            
            if trend_type:
                query += " AND trend_type = :trend_type"
                params["trend_type"] = trend_type
            
            if category:
                query += " AND category = :category"
                params["category"] = category
            
            query += " ORDER BY trend_score DESC"
            
            result = db.execute_query(query, params)
            
            return [
                {
                    "date": r['date'],
                    "trend_type": r['trend_type'],
                    "category": r['category'],
                    "trend_score": r['trend_score'],
                    "price_change_avg": r['price_change_avg'],
                    "volume_change_avg": r['volume_change_avg'],
                    "momentum_score": r['momentum_score'],
                    "strength": r['strength']
                }
                for r in result
            ]
            
        except Exception as e:
            logger.error(f"Error getting market trends: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get market trends: {str(e)}") from e
    
    def _calculate_sector_trends(self, snapshot_date: date) -> List[Dict[str, Any]]:
        """Calculate trends for each sector"""
        try:
            from app.services.sector_performance_service import SectorPerformanceService
            sector_service = SectorPerformanceService()
            sector_performance = sector_service.calculate_sector_performance(snapshot_date)
            
            trends = []
            for sector_data in sector_performance.get('sectors', []):
                avg_change = sector_data.get('avg_price_change_percent', 0)
                
                # Calculate trend score (-100 to 100)
                trend_score = min(max(avg_change * 10, -100), 100)  # Scale to -100/100
                
                # Determine strength
                if abs(trend_score) >= 80:
                    strength = "very_strong"
                elif abs(trend_score) >= 50:
                    strength = "strong"
                elif abs(trend_score) >= 20:
                    strength = "moderate"
                elif abs(trend_score) >= 10:
                    strength = "weak"
                else:
                    strength = "very_weak"
                
                trends.append({
                    "category": sector_data['sector'],
                    "trend_score": trend_score,
                    "price_change_avg": avg_change,
                    "momentum_score": abs(trend_score),
                    "strength": strength
                })
            
            return trends
            
        except Exception as e:
            logger.error(f"Error calculating sector trends: {e}", exc_info=True)
            return []
    
    def _calculate_industry_trends(self, snapshot_date: date) -> List[Dict[str, Any]]:
        """Calculate trends for each industry"""
        try:
            # Get industries from holdings and watchlists
            query = """
                SELECT DISTINCT industry, sector
                FROM holdings
                WHERE industry IS NOT NULL AND industry != ''
                UNION
                SELECT DISTINCT industry, sector
                FROM watchlist_items
                WHERE industry IS NOT NULL AND industry != ''
            """
            industries_result = db.execute_query(query)
            
            trends = []
            for industry_data in industries_result:
                industry = industry_data['industry']
                
                # Get average price change for this industry
                query = """
                    SELECT AVG(price_change_percent_since_added) as avg_change
                    FROM watchlist_items
                    WHERE industry = :industry
                """
                result = db.execute_query(query, {"industry": industry})
                
                if result and result[0].get('avg_change') is not None:
                    avg_change = result[0]['avg_change']
                    trend_score = min(max(avg_change * 10, -100), 100)
                    
                    # Determine strength
                    if abs(trend_score) >= 80:
                        strength = "very_strong"
                    elif abs(trend_score) >= 50:
                        strength = "strong"
                    elif abs(trend_score) >= 20:
                        strength = "moderate"
                    elif abs(trend_score) >= 10:
                        strength = "weak"
                    else:
                        strength = "very_weak"
                    
                    trends.append({
                        "category": industry,
                        "trend_score": trend_score,
                        "price_change_avg": avg_change,
                        "momentum_score": abs(trend_score),
                        "strength": strength
                    })
            
            return trends
            
        except Exception as e:
            logger.error(f"Error calculating industry trends: {e}", exc_info=True)
            return []
    
    def _calculate_market_cap_trends(self, snapshot_date: date) -> List[Dict[str, Any]]:
        """Calculate trends by market cap category"""
        try:
            market_cap_categories = ['mega', 'large', 'mid', 'small', 'micro']
            trends = []
            
            for category in market_cap_categories:
                # Get average price change for this market cap category
                query = """
                    SELECT AVG(price_change_percent_since_added) as avg_change
                    FROM watchlist_items
                    WHERE market_cap_category = :category
                """
                result = db.execute_query(query, {"category": category})
                
                if result and result[0].get('avg_change') is not None:
                    avg_change = result[0]['avg_change']
                    trend_score = min(max(avg_change * 10, -100), 100)
                    
                    # Determine strength
                    if abs(trend_score) >= 80:
                        strength = "very_strong"
                    elif abs(trend_score) >= 50:
                        strength = "strong"
                    elif abs(trend_score) >= 20:
                        strength = "moderate"
                    elif abs(trend_score) >= 10:
                        strength = "weak"
                    else:
                        strength = "very_weak"
                    
                    trends.append({
                        "category": category,
                        "trend_score": trend_score,
                        "price_change_avg": avg_change,
                        "momentum_score": abs(trend_score),
                        "strength": strength
                    })
            
            return trends
            
        except Exception as e:
            logger.error(f"Error calculating market cap trends: {e}", exc_info=True)
            return []
    
    def _calculate_overall_trend(self, sector_trends: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall market trend"""
        try:
            if not sector_trends:
                return {
                    "trend_score": 0,
                    "strength": "very_weak",
                    "direction": "neutral"
                }
            
            # Average all sector trend scores
            avg_trend_score = sum(t.get('trend_score', 0) for t in sector_trends) / len(sector_trends)
            
            # Determine strength
            if abs(avg_trend_score) >= 80:
                strength = "very_strong"
            elif abs(avg_trend_score) >= 50:
                strength = "strong"
            elif abs(avg_trend_score) >= 20:
                strength = "moderate"
            elif abs(avg_trend_score) >= 10:
                strength = "weak"
            else:
                strength = "very_weak"
            
            # Determine direction
            if avg_trend_score > 10:
                direction = "bullish"
            elif avg_trend_score < -10:
                direction = "bearish"
            else:
                direction = "neutral"
            
            return {
                "trend_score": avg_trend_score,
                "strength": strength,
                "direction": direction
            }
            
        except Exception as e:
            logger.error(f"Error calculating overall trend: {e}", exc_info=True)
            return {
                "trend_score": 0,
                "strength": "very_weak",
                "direction": "neutral"
            }
    
    def _save_trends(self, trends: Dict[str, Any], snapshot_date: date):
        """Save trends to database"""
        try:
            # Save sector trends
            for sector_trend in trends.get('sectors', []):
                query = """
                    INSERT OR REPLACE INTO market_trends
                    (date, trend_type, category, trend_score, price_change_avg,
                     momentum_score, strength)
                    VALUES (:date, 'sector', :category, :trend_score, :price_change_avg,
                            :momentum_score, :strength)
                """
                db.execute_update(query, {
                    "date": snapshot_date.isoformat(),
                    "category": sector_trend['category'],
                    "trend_score": sector_trend['trend_score'],
                    "price_change_avg": sector_trend['price_change_avg'],
                    "momentum_score": sector_trend['momentum_score'],
                    "strength": sector_trend['strength']
                })
            
            # Save industry trends
            for industry_trend in trends.get('industries', []):
                query = """
                    INSERT OR REPLACE INTO market_trends
                    (date, trend_type, category, trend_score, price_change_avg,
                     momentum_score, strength)
                    VALUES (:date, 'industry', :category, :trend_score, :price_change_avg,
                            :momentum_score, :strength)
                """
                db.execute_update(query, {
                    "date": snapshot_date.isoformat(),
                    "category": industry_trend['category'],
                    "trend_score": industry_trend['trend_score'],
                    "price_change_avg": industry_trend['price_change_avg'],
                    "momentum_score": industry_trend['momentum_score'],
                    "strength": industry_trend['strength']
                })
            
            # Save market cap trends
            for market_cap_trend in trends.get('market_cap', []):
                query = """
                    INSERT OR REPLACE INTO market_trends
                    (date, trend_type, category, trend_score, price_change_avg,
                     momentum_score, strength)
                    VALUES (:date, 'market_cap', :category, :trend_score, :price_change_avg,
                            :momentum_score, :strength)
                """
                db.execute_update(query, {
                    "date": snapshot_date.isoformat(),
                    "category": market_cap_trend['category'],
                    "trend_score": market_cap_trend['trend_score'],
                    "price_change_avg": market_cap_trend['price_change_avg'],
                    "momentum_score": market_cap_trend['momentum_score'],
                    "strength": market_cap_trend['strength']
                })
            
            # Save overall trend
            overall = trends.get('overall', {})
            query = """
                INSERT OR REPLACE INTO market_trends
                (date, trend_type, category, trend_score, momentum_score, strength)
                VALUES (:date, 'overall', 'market', :trend_score, :momentum_score, :strength)
            """
            db.execute_update(query, {
                "date": snapshot_date.isoformat(),
                "trend_score": overall.get('trend_score', 0),
                "momentum_score": abs(overall.get('trend_score', 0)),
                "strength": overall.get('strength', 'very_weak')
            })
            
        except Exception as e:
            logger.error(f"Error saving trends: {e}", exc_info=True)
            # Don't raise - this is non-critical

