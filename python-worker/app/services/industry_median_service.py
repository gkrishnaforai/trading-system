"""
Industry Median Service
Calculates industry median values for financial metrics
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy import text
from app.database import db

logger = logging.getLogger(__name__)

class IndustryMedianService:
    """Service for calculating industry median financial metrics"""
    
    @staticmethod
    def get_industry_median_gross_margin(industry: str) -> Optional[float]:
        """Calculate industry median gross margin"""
        try:
            with db.get_session() as session:
                query = """
                SELECT f.gross_margin 
                FROM financial_ratios f
                JOIN enhanced_fundamentals e ON f.symbol = e.stock_symbol
                WHERE e.industry = :industry 
                AND f.gross_margin IS NOT NULL 
                AND f.gross_margin > 0
                ORDER BY f.gross_margin
                """
                
                result = session.execute(text(query), {"industry": industry})
                margins = [row[0] for row in result.fetchall()]
                
                if not margins:
                    logger.warning(f"No gross margin data found for industry: {industry}")
                    return None
                
                # Calculate median
                n = len(margins)
                if n % 2 == 1:
                    median = margins[n // 2]
                else:
                    median = (margins[n // 2 - 1] + margins[n // 2]) / 2
                
                logger.info(f"Industry median gross margin for {industry}: {median:.4f}")
                return median
                
        except Exception as e:
            logger.error(f"Error calculating industry median gross margin for {industry}: {e}")
            return None
    
    @staticmethod
    def get_industry_median_roic(industry: str) -> Optional[float]:
        """Calculate industry median ROIC"""
        try:
            with db.get_session() as session:
                query = """
                SELECT f.roic 
                FROM financial_ratios f
                JOIN enhanced_fundamentals e ON f.symbol = e.stock_symbol
                WHERE e.industry = :industry 
                AND f.roic IS NOT NULL 
                AND f.roic > 0
                ORDER BY f.roic
                """
                
                cursor = conn.execute(query, {"industry": industry})
                roic_values = [row[0] for row in cursor.fetchall()]
                
                if not roic_values:
                    return None
                
                # Calculate median
                n = len(roic_values)
                if n % 2 == 1:
                    median = roic_values[n // 2]
                else:
                    median = (roic_values[n // 2 - 1] + roic_values[n // 2]) / 2
                
                return median
                
        except Exception as e:
            logger.error(f"Error calculating industry median ROIC for {industry}: {e}")
            return None
    
    @staticmethod
    def get_industry_median_debt_to_equity(industry: str) -> Optional[float]:
        """Calculate industry median debt-to-equity ratio"""
        try:
            with db.get_session() as session:
                query = """
                SELECT f.debt_to_equity 
                FROM financial_ratios f
                JOIN enhanced_fundamentals e ON f.symbol = e.stock_symbol
                WHERE e.industry = :industry 
                AND f.debt_to_equity IS NOT NULL 
                AND f.debt_to_equity >= 0
                ORDER BY f.debt_to_equity
                """
                
                cursor = conn.execute(query, {"industry": industry})
                debt_ratios = [row[0] for row in cursor.fetchall()]
                
                if not debt_ratios:
                    return None
                
                # Calculate median
                n = len(debt_ratios)
                if n % 2 == 1:
                    median = debt_ratios[n // 2]
                else:
                    median = (debt_ratios[n // 2 - 1] + debt_ratios[n // 2]) / 2
                
                return median
                
        except Exception as e:
            logger.error(f"Error calculating industry median debt-to-equity for {industry}: {e}")
            return None
    
    @staticmethod
    def get_all_industry_medians(industry: str) -> Dict[str, Optional[float]]:
        """Get all industry median metrics for comparison"""
        return {
            "gross_margin": IndustryMedianService.get_industry_median_gross_margin(industry),
            "roic": IndustryMedianService.get_industry_median_roic(industry),
            "debt_to_equity": IndustryMedianService.get_industry_median_debt_to_equity(industry)
        }
