"""
Stocks Management API
Central stock symbols management with auto-population of company information
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import requests
from app.config import settings
from app.database import db

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/stocks", tags=["stocks"])
# CORRECT: router = APIRouter(tags=["stocks"])
# ========================================
router = APIRouter(tags=["stocks"])

class StockInfo(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[int] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None
    is_active: Optional[bool] = None

class AddStockRequest(BaseModel):
    symbol: str

@router.get("/available", response_model=List[StockInfo])
async def get_available_stocks():
    """Get all available stocks from the stocks table"""
    try:
        query = """
            SELECT symbol, company_name, sector, industry, market_cap, country, currency, exchange, is_active
            FROM stocks 
            WHERE symbol IS NOT NULL AND is_active = true
            ORDER BY symbol
        """
        
        result = db.execute_query(query)
        
        stocks = []
        for row in result:
            stocks.append(StockInfo(
                symbol=row['symbol'],
                company_name=row.get('company_name'),
                sector=row.get('sector'),
                industry=row.get('industry'),
                market_cap=row.get('market_cap'),
                country=row.get('country'),
                currency=row.get('currency'),
                exchange=row.get('exchange'),
                is_active=row.get('is_active')
            ))
        
        return stocks
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add", response_model=StockInfo)
async def add_stock(request: AddStockRequest):
    """Add a new stock symbol with auto-populated company information"""
    try:
        symbol = request.symbol.upper().strip()
        
        # Check if symbol already exists
        check_query = "SELECT symbol FROM stocks WHERE symbol = :symbol"
        existing = db.execute_query(check_query, {"symbol": symbol})
        
        if existing:
            raise HTTPException(status_code=400, detail=f"Symbol {symbol} already exists")
        
        # Fetch company information from Yahoo Finance API
        company_info = await fetch_company_info(symbol)
        
        # Insert into stocks table
        insert_query = """
            INSERT INTO stocks (symbol, company_name, sector, industry, market_cap, country, currency, exchange, is_active)
            VALUES (:symbol, :company_name, :sector, :industry, :market_cap, :country, :currency, :exchange, :is_active)
            ON CONFLICT (symbol) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                market_cap = EXCLUDED.market_cap,
                country = EXCLUDED.country,
                currency = EXCLUDED.currency,
                exchange = EXCLUDED.exchange,
                updated_at = NOW()
            RETURNING symbol, company_name, sector, industry, market_cap, country, currency, exchange, is_active
        """
        
        result = db.execute_query(insert_query, {
            "symbol": symbol,
            "company_name": company_info.get('company_name'),
            "sector": company_info.get('sector'),
            "industry": company_info.get('industry'),
            "market_cap": company_info.get('market_cap'),
            "country": company_info.get('country'),
            "currency": company_info.get('currency'),
            "exchange": company_info.get('exchange'),
            "is_active": True
        })
        
        if result:
            row = result[0]
            return StockInfo(
                symbol=row['symbol'],
                company_name=row.get('company_name'),
                sector=row.get('sector'),
                industry=row.get('industry'),
                market_cap=row.get('market_cap'),
                country=row.get('country'),
                currency=row.get('currency'),
                exchange=row.get('exchange'),
                is_active=row.get('is_active')
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to add stock")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def fetch_company_info(symbol: str) -> dict:
    """Fetch company information from Yahoo Finance API"""
    try:
        # Use Yahoo Finance API to get company info
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
        params = {
            "modules": "summaryDetail,assetProfile,defaultKeyStatistics"
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract company information
            result = data.get('quoteSummary', {}).get('result', [])
            if result:
                quote_data = result[0]
                
                # Summary detail
                summary_detail = quote_data.get('summaryDetail', {})
                asset_profile = quote_data.get('assetProfile', {})
                key_stats = quote_data.get('defaultKeyStatistics', {})
                
                return {
                    'company_name': asset_profile.get('companyName'),
                    'sector': asset_profile.get('sector'),
                    'industry': asset_profile.get('industry'),
                    'market_cap': summary_detail.get('marketCap'),
                    'country': asset_profile.get('country'),
                    'currency': summary_detail.get('currency'),
                    'exchange': asset_profile.get('exchange')
                }
        
        # Fallback to basic info
        return {
            'company_name': symbol,
            'sector': None,
            'industry': None,
            'market_cap': None,
            'country': None,
            'currency': 'USD',
            'exchange': None
        }
        
    except Exception as e:
        print(f"Error fetching company info for {symbol}: {e}")
        # Return basic info as fallback
        return {
            'company_name': symbol,
            'sector': None,
            'industry': None,
            'market_cap': None,
            'country': None,
            'currency': 'USD',
            'exchange': None
        }

@router.get("/search/{query}")
async def search_stocks(query: str):
    """Search stocks by symbol or company name"""
    try:
        search_query = """
            SELECT symbol, company_name, sector, industry, market_cap, country, currency, exchange, is_active
            FROM stocks 
            WHERE symbol ILIKE :query 
               OR company_name ILIKE :query
               AND is_active = true
            ORDER BY 
                CASE WHEN symbol ILIKE :query THEN 1 ELSE 2 END,
                symbol
            LIMIT 20
        """
        
        result = db.execute_query(search_query, {"query": f"%{query}%"})
        
        stocks = []
        for row in result:
            stocks.append(StockInfo(
                symbol=row['symbol'],
                company_name=row.get('company_name'),
                sector=row.get('sector'),
                industry=row.get('industry'),
                market_cap=row.get('market_cap'),
                country=row.get('country'),
                currency=row.get('currency'),
                exchange=row.get('exchange'),
                is_active=row.get('is_active')
            ))
        
        return stocks
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{symbol}")
async def get_stock_info(symbol: str):
    """Get detailed information for a specific stock"""
    try:
        query = """
            SELECT symbol, company_name, sector, industry, market_cap, country, currency, exchange, is_active
            FROM stocks 
            WHERE symbol = :symbol AND is_active = true
        """
        
        result = db.execute_query(query, {"symbol": symbol.upper()})
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        
        row = result[0]
        return StockInfo(
            symbol=row['symbol'],
            company_name=row.get('company_name'),
            sector=row.get('sector'),
            industry=row.get('industry'),
            market_cap=row.get('market_cap'),
            country=row.get('country'),
            currency=row.get('currency'),
            exchange=row.get('exchange'),
            is_active=row.get('is_active')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
