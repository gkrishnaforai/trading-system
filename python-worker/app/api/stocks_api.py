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
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None

@router.get("/available")
async def get_available_stocks():
    """Get all available stocks from the stocks table"""
    try:
        query = """
            SELECT symbol, company_name, sector, industry, market_cap, 
                   country, currency, exchange, is_active
            FROM stocks 
            WHERE symbol IS NOT NULL AND is_active = true
            ORDER BY symbol
            LIMIT 10000
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
        
        return {
            "success": True,
            "data": stocks,
            "count": len(stocks)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/add")
async def add_stock(request: AddStockRequest):
    """Add a new stock symbol with auto-populated or manual company information"""
    try:
        symbol = request.symbol.upper().strip()
        
        # Check if symbol already exists
        check_query = "SELECT symbol FROM stocks WHERE symbol = :symbol"
        existing = db.execute_query(check_query, {"symbol": symbol})
        
        if existing:
            return {
                "success": False,
                "error": f"Symbol {symbol} already exists"
            }
        
        # If manual company information is provided, use it
        if request.company_name or request.sector or request.industry or request.country:
            # Use manual company information
            company_info = {
                'company_name': request.company_name or symbol,
                'sector': request.sector,
                'industry': request.industry,
                'market_cap': None,
                'country': request.country,
                'currency': 'USD',
                'exchange': None
            }
            print(f"Using manual company info: {company_info}")
        else:
            # Try to fetch from Yahoo Finance API
            company_info = await fetch_company_info(symbol)
            print(f"Using Yahoo Finance company info: {company_info}")
        
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
            stock_info = StockInfo(
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
            return {
                "success": True,
                "data": stock_info.dict()
            }
        else:
            return {
                "success": False,
                "error": "Failed to add stock"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

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
        
        return {
            "success": True,
            "data": stocks,
            "count": len(stocks)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.put("/update/{symbol}")
async def update_stock(symbol: str, request: AddStockRequest):
    """Update existing stock information"""
    try:
        symbol = symbol.upper().strip()
        
        # Check if symbol exists
        check_query = "SELECT symbol FROM stocks WHERE symbol = :symbol"
        existing = db.execute_query(check_query, {"symbol": symbol})
        
        if not existing:
            return {
                "success": False,
                "error": f"Symbol {symbol} not found"
            }
        
        # Update with provided information
        update_query = """
            UPDATE stocks 
            SET company_name = COALESCE(:company_name, company_name),
                sector = COALESCE(:sector, sector),
                industry = COALESCE(:industry, industry),
                country = COALESCE(:country, country),
                updated_at = NOW()
            WHERE symbol = :symbol
            RETURNING symbol, company_name, sector, industry, market_cap, country, currency, exchange, is_active
        """
        
        result = db.execute_query(update_query, {
            "symbol": symbol,
            "company_name": request.company_name,
            "sector": request.sector,
            "industry": request.industry,
            "country": request.country
        })
        
        if result:
            row = result[0]
            stock_info = StockInfo(
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
            return {
                "success": True,
                "data": stock_info.dict()
            }
        else:
            return {
                "success": False,
                "error": "Failed to update stock"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.delete("/delete/{symbol}")
async def delete_stock(symbol: str):
    """Soft delete (deactivate) a stock symbol"""
    try:
        symbol = symbol.upper().strip()
        
        # Check if symbol exists
        check_query = "SELECT symbol FROM stocks WHERE symbol = :symbol"
        existing = db.execute_query(check_query, {"symbol": symbol})
        
        if not existing:
            return {
                "success": False,
                "error": f"Symbol {symbol} not found"
            }
        
        # Soft delete by setting is_active = false
        delete_query = """
            UPDATE stocks 
            SET is_active = false, updated_at = NOW()
            WHERE symbol = :symbol
        """
        
        db.execute_query(delete_query, {"symbol": symbol})
        
        return {
            "success": True,
            "data": {"message": f"Symbol {symbol} deactivated successfully"}
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/{symbol}/coverage")
async def get_stock_coverage(symbol: str):
    """Get data coverage information for a specific stock"""
    try:
        symbol = symbol.upper().strip()
        
        # Check price data coverage
        price_query = "SELECT COUNT(*) as count FROM price_historical_daily WHERE symbol = :symbol"
        price_result = db.execute_query(price_query, {"symbol": symbol})
        has_price_data = price_result[0]['count'] > 0 if price_result else False
        
        # Check indicator data coverage
        indicator_query = "SELECT COUNT(*) as count FROM indicators_daily WHERE symbol = :symbol"
        indicator_result = db.execute_query(indicator_query, {"symbol": symbol})
        has_indicator_data = indicator_result[0]['count'] > 0 if indicator_result else False
        
        # Check fundamentals coverage
        fundamentals_query = "SELECT COUNT(*) as count FROM fundamentals_snapshots WHERE symbol = :symbol"
        fundamentals_result = db.execute_query(fundamentals_query, {"symbol": symbol})
        has_fundamentals_data = fundamentals_result[0]['count'] > 0 if fundamentals_result else False
        
        coverage_percentage = (
            100 if has_price_data and has_indicator_data and has_fundamentals_data
            else 66 if (has_price_data and has_indicator_data) or (has_price_data and has_fundamentals_data) or (has_indicator_data and has_fundamentals_data)
            else 33 if has_price_data or has_indicator_data or has_fundamentals_data
            else 0
        )
        
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "has_price_data": has_price_data,
                "has_indicator_data": has_indicator_data,
                "has_fundamentals_data": has_fundamentals_data,
                "coverage_percentage": coverage_percentage
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

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
            return {
                "success": False,
                "error": f"Symbol {symbol} not found"
            }
        
        row = result[0]
        stock_info = StockInfo(
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
        
        return {
            "success": True,
            "data": stock_info.dict()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
