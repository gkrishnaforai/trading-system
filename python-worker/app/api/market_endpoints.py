"""
Market Movers API Endpoints
Industry-standard market movers and sector analysis
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import requests
import pandas as pd
from datetime import datetime, date
import logging

from app.observability.logging import get_logger

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/api/v1/market", tags=["market"])
# CORRECT: router = APIRouter(tags=["market"])
# ========================================
router = APIRouter(tags=["market"])
logger = get_logger(__name__)

class MarketMover(BaseModel):
    symbol: str
    company: str
    price: float
    change: float
    change_percent: float
    volume: str
    market_cap: str

class MarketMoversResponse(BaseModel):
    gainers: List[MarketMover]
    losers: List[MarketMover]
    market_status: str
    last_updated: str

class SectorPerformance(BaseModel):
    sector: str
    change: float
    status: str

class MarketOverview(BaseModel):
    sp500: Dict[str, float]
    nasdaq: Dict[str, float]
    dow: Dict[str, float]
    vix: Dict[str, float]

@router.get("/movers", response_model=MarketMoversResponse)
async def get_market_movers():
    """
    Get today's top market movers and losers
    
    Returns:
        MarketMoversResponse with gainers, losers, and market status
    """
    try:
        logger.info("📈 Fetching market movers data")
        
        # In a real implementation, this would fetch from a market data provider
        # For now, we'll return sample data
        gainers = [
            MarketMover(
                symbol="NVDA",
                company="NVIDIA Corporation",
                price=485.09,
                change=25.67,
                change_percent=5.58,
                volume="45.2M",
                market_cap="1.2T"
            ),
            MarketMover(
                symbol="TSLA",
                company="Tesla, Inc.",
                price=242.84,
                change=12.31,
                change_percent=5.34,
                volume="112.3M",
                market_cap="770B"
            ),
            MarketMover(
                symbol="AMD",
                company="Advanced Micro Devices",
                price=125.43,
                change=5.89,
                change_percent=4.93,
                volume="67.8M",
                market_cap="203B"
            ),
            MarketMover(
                symbol="META",
                company="Meta Platforms",
                price=325.67,
                change=14.22,
                change_percent=4.56,
                volume="23.4M",
                market_cap="834B"
            ),
            MarketMover(
                symbol="GOOGL",
                company="Alphabet Inc.",
                price=139.82,
                change=5.43,
                change_percent=4.04,
                volume="28.9M",
                market_cap="1.8T"
            )
        ]
        
        losers = [
            MarketMover(
                symbol="BA",
                company="Boeing Company",
                price=198.45,
                change=-8.92,
                change_percent=-4.30,
                volume="8.7M",
                market_cap="119B"
            ),
            MarketMover(
                symbol="DIS",
                company="Walt Disney Company",
                price=89.23,
                change=-3.78,
                change_percent=-4.06,
                volume="15.2M",
                market_cap="161B"
            ),
            MarketMover(
                symbol="NFLX",
                company="Netflix Inc.",
                price=445.67,
                change=-16.89,
                change_percent=-3.65,
                volume="12.1M",
                market_cap="198B"
            ),
            MarketMover(
                symbol="INTC",
                company="Intel Corporation",
                price=42.18,
                change=-1.47,
                change_percent=-3.36,
                volume="35.6M",
                market_cap="176B"
            ),
            MarketMover(
                symbol="CSCO",
                company="Cisco Systems",
                price=48.92,
                change=-1.58,
                change_percent=-3.13,
                volume="18.9M",
                market_cap="202B"
            )
        ]
        
        response = MarketMoversResponse(
            gainers=gainers,
            losers=losers,
            market_status="Open",
            last_updated=datetime.now().isoformat()
        )
        
        logger.info(f"✅ Market movers data retrieved: {len(gainers)} gainers, {len(losers)} losers")
        return response
        
    except Exception as e:
        logger.error(f"❌ Error fetching market movers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch market movers: {str(e)}")

@router.get("/overview", response_model=MarketOverview)
async def get_market_overview():
    """
    Get market overview with major indices
    
    Returns:
        MarketOverview with major indices data
    """
    try:
        logger.info("📊 Fetching market overview")
        
        # Sample market data
        overview = MarketOverview(
            sp500={"value": 4532.16, "change": 54.39, "change_percent": 1.2},
            nasdaq={"value": 14125.48, "change": 291.23, "change_percent": 2.1},
            dow={"value": 35678.23, "change": 284.22, "change_percent": 0.8},
            vix={"value": 15.42, "change": -0.5, "change_percent": -3.1}
        )
        
        logger.info("✅ Market overview retrieved")
        return overview
        
    except Exception as e:
        logger.error(f"❌ Error fetching market overview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch market overview: {str(e)}")

@router.get("/sectors", response_model=List[SectorPerformance])
async def get_sector_performance():
    """
    Get sector performance data
    
    Returns:
        List of sector performance data
    """
    try:
        logger.info("🏭 Fetching sector performance")
        
        sectors = [
            SectorPerformance(sector="Technology", change=2.1, status="positive"),
            SectorPerformance(sector="Healthcare", change=-0.3, status="negative"),
            SectorPerformance(sector="Financials", change=1.4, status="positive"),
            SectorPerformance(sector="Energy", change=-1.8, status="negative"),
            SectorPerformance(sector="Consumer Discretionary", change=0.8, status="positive"),
            SectorPerformance(sector="Industrials", change=-0.5, status="negative"),
            SectorPerformance(sector="Materials", change=1.2, status="positive"),
            SectorPerformance(sector="Utilities", change=-0.2, status="negative"),
            SectorPerformance(sector="Real Estate", change=0.3, status="positive"),
            SectorPerformance(sector="Communication", change=1.8, status="positive")
        ]
        
        logger.info(f"✅ Sector performance retrieved: {len(sectors)} sectors")
        return sectors
        
    except Exception as e:
        logger.error(f"❌ Error fetching sector performance: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch sector performance: {str(e)}")

@router.get("/stock/{symbol}/info")
async def get_stock_info(symbol: str):
    """
    Get basic stock information
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Basic stock information
    """
    try:
        logger.info(f"📈 Fetching stock info for {symbol}")
        
        # In a real implementation, this would fetch from a market data provider
        # For now, return sample data
        stock_info = {
            "symbol": symbol.upper(),
            "price": 150.25,
            "change": 2.45,
            "change_percent": 1.66,
            "volume": "10.5M",
            "market_cap": "2.5T",
            "company_name": f"{symbol.upper()} Corporation",
            "sector": "Technology",
            "industry": "Software"
        }
        
        logger.info(f"✅ Stock info retrieved for {symbol}")
        return stock_info
        
    except Exception as e:
        logger.error(f"❌ Error fetching stock info for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch stock info: {str(e)}")

@router.post("/stock/{symbol}/add-to-portfolio")
async def add_stock_to_portfolio(symbol: str, portfolio_id: int, shares: float = 0):
    """
    Add stock to portfolio (simplified endpoint)
    
    Args:
        symbol: Stock symbol
        portfolio_id: Portfolio ID
        shares: Number of shares (optional)
        
    Returns:
        Success/failure message
    """
    try:
        logger.info(f"➕ Adding {symbol} to portfolio {portfolio_id}")
        
        # This would integrate with the existing portfolio API
        # For now, return success
        result = {
            "success": True,
            "message": f"Successfully added {symbol} to portfolio",
            "symbol": symbol.upper(),
            "portfolio_id": portfolio_id
        }
        
        logger.info(f"✅ Added {symbol} to portfolio {portfolio_id}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error adding {symbol} to portfolio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add stock to portfolio: {str(e)}")
