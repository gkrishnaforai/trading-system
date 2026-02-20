"""
Industry Medians API Endpoints
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from app.services.industry_median_service import IndustryMedianService

router = APIRouter()

@router.get("/industry/{industry}/median-gross-margin")
async def get_industry_median_gross_margin(industry: str):
    """Get industry median gross margin"""
    median = IndustryMedianService.get_industry_median_gross_margin(industry)
    if median is None:
        raise HTTPException(status_code=404, detail=f"No data found for industry: {industry}")
    
    return {
        "industry": industry,
        "metric": "gross_margin",
        "median": median,
        "median_pct": median * 100  # Convert to percentage
    }

@router.get("/industry/{industry}/all-medians")
async def get_all_industry_medians(industry: str):
    """Get all industry median metrics"""
    medians = IndustryMedianService.get_all_industry_medians(industry)
    
    # Filter out None values and convert percentages
    result = {
        "industry": industry,
        "metrics": {}
    }
    
    for metric, value in medians.items():
        if value is not None:
            result["metrics"][metric] = {
                "value": value,
                "percentage": value * 100 if metric in ["gross_margin", "roic"] else value
            }
    
    if not result["metrics"]:
        raise HTTPException(status_code=404, detail=f"No data found for industry: {industry}")
    
    return result

@router.get("/symbol/{symbol}/industry-comparison")
async def get_symbol_industry_comparison(symbol: str):
    """Compare symbol's metrics against industry medians"""
    try:
        from sqlalchemy import text
        from app.database import db
        
        # Get symbol's industry and metrics
        with db.get_session() as session:
            query = """
            SELECT e.industry, f.gross_margin, f.roic, f.debt_to_equity, e.revenue_growth
            FROM enhanced_fundamentals e
            LEFT JOIN financial_ratios f ON e.stock_symbol = f.symbol
            WHERE e.stock_symbol = :symbol
            ORDER BY e.as_of_date DESC
            LIMIT 1
            """
            
            result = session.execute(text(query), {"symbol": symbol})
            row = result.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail=f"No data found for symbol: {symbol}")
            
            industry, gross_margin, roic, debt_to_equity, revenue_growth = row
            
            if not industry:
                raise HTTPException(status_code=404, detail=f"No industry data found for symbol: {symbol}")
        
        # Get industry medians
        medians = IndustryMedianService.get_all_industry_medians(industry)
        
        # Build comparison
        comparison = {
            "symbol": symbol,
            "industry": industry,
            "metrics": {}
        }
        
        # Compare each metric
        metrics = {
            "gross_margin": gross_margin,
            "roic": roic, 
            "debt_to_equity": debt_to_equity
        }
        
        for metric, value in metrics.items():
            if value is not None and medians.get(metric) is not None:
                median = medians[metric]
                comparison["metrics"][metric] = {
                    "symbol_value": value,
                    "industry_median": median,
                    "vs_median_pct": ((value - median) / median) * 100,
                    "outperforms": value > median if metric != "debt_to_equity" else value < median
                }
        
        # Add revenue growth (no industry comparison needed)
        if revenue_growth is not None:
            comparison["metrics"]["revenue_growth"] = {
                "symbol_value": revenue_growth,
                "target": 15.0,  # 15% target
                "meets_target": revenue_growth >= 15.0
            }
        
        return comparison
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
