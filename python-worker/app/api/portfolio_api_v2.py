"""
Portfolio Management API v2
Industry-standard portfolio management with proper stocks table integration
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
import json
from decimal import Decimal
import uuid

from app.database import get_db
from app.config import settings
from app.utils.auth import get_current_user, create_access_token, hash_password, verify_password
from app.observability.logging import get_logger

logger = get_logger("portfolio_api_v2")

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# ❌ WRONG: router = APIRouter(prefix="/api/v2/portfolio", tags=["portfolio-v2"])
# ✅ CORRECT: router = APIRouter(tags=["portfolio-v2"])
# ========================================
router = APIRouter(tags=["portfolio-v2"])

# ========================================
# Pydantic Models
# ========================================

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: str  # UUID
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime

class PortfolioCreate(BaseModel):
    name: str
    description: Optional[str] = None
    portfolio_type: str = "custom"
    initial_capital: Decimal = Decimal("10000.00")
    currency: str = "USD"

class PortfolioResponse(BaseModel):
    id: str  # UUID
    name: str
    description: Optional[str]
    portfolio_type: str
    initial_capital: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    holdings_count: int = 0
    total_invested: Decimal = Decimal("0")

class HoldingCreate(BaseModel):
    symbol: str  # Stock symbol from stocks table
    asset_type: str = "stock"
    shares_held: Decimal = Decimal("0")
    average_cost: Decimal = Decimal("0")
    notes: Optional[str] = None

class HoldingResponse(BaseModel):
    id: str  # UUID
    portfolio_id: str  # UUID
    symbol: str
    asset_type: str
    shares_held: Decimal
    average_cost: Decimal
    total_cost: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None
    # Enriched stock information
    company_name: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    stock_currency: Optional[str] = None

class SignalHistoryResponse(BaseModel):
    id: str  # UUID
    symbol: str
    signal_type: str
    confidence: Decimal
    price: Decimal
    signal_date: date
    actual_outcome: Optional[str]
    actual_return: Optional[Decimal]
    days_held: Optional[int]

class ScheduleCreate(BaseModel):
    schedule_type: str
    schedule_time: time
    schedule_day: Optional[int] = None

class ScheduleResponse(BaseModel):
    id: str  # UUID
    portfolio_id: str  # UUID
    schedule_type: str
    schedule_time: time
    schedule_day: Optional[int]
    is_active: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]

# ========================================
# Test Endpoint
# ========================================

@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify router is working"""
    return {"message": "Portfolio API v2 is working!"}

# ========================================
# User Management Endpoints
# ========================================

@router.post("/users/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, db=Depends(get_db)):
    """Register a new user"""
    
    # Check if user exists
    existing_user = db.execute_query_positional(
        "SELECT id FROM users WHERE username = $1 OR email = $2",
        [user_data.username, user_data.email]
    )
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )
    
    # Create user
    hashed_password = hash_password(user_data.password)
    
    db.execute_update_positional(
        """
        INSERT INTO users (username, email, password_hash, full_name)
        VALUES ($1, $2, $3, $4)
        """,
        [user_data.username, user_data.email, hashed_password, user_data.full_name]
    )
    
    # Get the created user
    user = db.execute_query_positional(
        "SELECT id, username, email, full_name, role, is_active, created_at FROM users WHERE username = $1",
        [user_data.username]
    )[0]
    
    return UserResponse(
        id=str(user['id']),
        username=user['username'],
        email=user['email'],
        full_name=user['full_name'],
        role=user['role'],
        is_active=user['is_active'],
        created_at=user['created_at'] if 'created_at' in user else datetime.now()
    )

# Login request model
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

@router.post("/users/login", response_model=LoginResponse)
async def login_user(login_data: LoginRequest, db=Depends(get_db)):
    """Authenticate user and return JWT token"""
    
    # Add logging
    logger.info(f"Login attempt for username: {login_data.username}")
    
    user = db.execute_query_positional(
        """
        SELECT id, username, email, password_hash, full_name, role, is_active
        FROM users WHERE username = $1
        """,
        [login_data.username]
    )
    
    if not user:
        logger.warning(f"Login failed: User '{login_data.username}' not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    user_data = user[0]
    
    if not user_data['is_active']:
        logger.warning(f"Login failed: User '{login_data.username}' is inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive"
        )
    
    if not verify_password(login_data.password, user_data['password_hash']):
        logger.warning(f"Login failed: Invalid password for user '{login_data.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    logger.info(f"Login successful for user: {login_data.username}")
    
    # Update last login
    db.execute_update(
        "UPDATE users SET last_login = :now WHERE id = :user_id",
        {"now": datetime.now(), "user_id": user_data['id']}
    )
    
    # Create JWT token
    access_token = create_access_token(
        data={"sub": str(user_data['id']), "username": user_data['username'], "role": user_data['role']}
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user_data['id']),
            username=user_data['username'],
            email=user_data['email'],
            full_name=user_data['full_name'],
            role=user_data['role'],
            is_active=user_data['is_active'],
            created_at=user_data['created_at'] if 'created_at' in user_data else datetime.now()
        )
    )

# ========================================
# Portfolio Management Endpoints
# ========================================

@router.get("/portfolios", response_model=List[PortfolioResponse])
async def get_user_portfolios(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get all portfolios for current user"""
    
    portfolios = db.execute_query_positional(
        """
        SELECT id, name, description, portfolio_type, initial_capital, currency, 
               is_active, created_at, updated_at, holdings_count, total_invested
        FROM portfolio_summary
        WHERE user_id = $1
        ORDER BY created_at DESC
        """,
        [current_user["id"]]
    )
    
    portfolio_responses = []
    for portfolio in portfolios:
        portfolio_responses.append(PortfolioResponse(
            id=str(portfolio['id']),
            name=portfolio['name'],
            description=portfolio['description'],
            portfolio_type=portfolio['portfolio_type'],
            initial_capital=float(portfolio['initial_capital']),
            currency=portfolio['currency'],
            is_active=portfolio['is_active'],
            created_at=portfolio['created_at'],
            updated_at=portfolio['updated_at'],
            holdings_count=portfolio['holdings_count'],
            total_invested=float(portfolio['total_invested'])
        ))
    
    return portfolio_responses

@router.post("/portfolios", response_model=PortfolioResponse)
async def create_portfolio(
    portfolio_data: PortfolioCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Create a new portfolio"""
    
    # Insert portfolio
    db.execute_update_positional(
        """
        INSERT INTO portfolios (user_id, name, description, portfolio_type, initial_capital, currency)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        [current_user["id"], portfolio_data.name, portfolio_data.description, 
         portfolio_data.portfolio_type, portfolio_data.initial_capital, portfolio_data.currency]
    )
    
    # Get the created portfolio (most recent one for this user)
    portfolio = db.execute_query_positional(
        """
        SELECT id, name, description, portfolio_type, initial_capital, currency, 
               is_active, created_at, updated_at, holdings_count, total_invested
        FROM portfolio_summary 
        WHERE user_id = $1 
        ORDER BY created_at DESC 
        LIMIT 1
        """,
        [current_user["id"]]
    )[0]
    
    return PortfolioResponse(
        id=str(portfolio['id']),
        name=portfolio['name'],
        description=portfolio['description'],
        portfolio_type=portfolio['portfolio_type'],
        initial_capital=float(portfolio['initial_capital']),
        currency=portfolio['currency'],
        is_active=portfolio['is_active'],
        created_at=portfolio['created_at'],
        updated_at=portfolio['updated_at'],
        holdings_count=portfolio['holdings_count'],
        total_invested=float(portfolio['total_invested'])
    )

@router.get("/portfolios/{portfolio_id}/holdings", response_model=List[HoldingResponse])
async def get_portfolio_holdings(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get all holdings for a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute_query_positional(
        "SELECT id FROM portfolios WHERE id = $1 AND user_id = $2",
        [portfolio_id, current_user["id"]]
    )
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    # Get enriched holdings
    holdings = db.execute_query_positional(
        """
        SELECT id, portfolio_id, symbol, asset_type, shares_held, average_cost,
               status, created_at, updated_at, notes, company_name, exchange,
               sector, industry, stock_currency, total_cost
        FROM portfolio_holdings_enriched
        WHERE portfolio_id = $1 AND status = 'active'
        ORDER BY created_at DESC
        """,
        [portfolio_id]
    )
    
    holding_responses = []
    for holding in holdings:
        holding_responses.append(HoldingResponse(
            id=str(holding['id']),
            portfolio_id=str(holding['portfolio_id']),
            symbol=holding['symbol'],
            asset_type=holding['asset_type'],
            shares_held=float(holding['shares_held']),
            average_cost=float(holding['average_cost']),
            total_cost=float(holding['total_cost']),
            status=holding['status'],
            created_at=holding['created_at'],
            updated_at=holding['updated_at'],
            notes=holding['notes'],
            company_name=holding['company_name'],
            exchange=holding['exchange'],
            sector=holding['sector'],
            industry=holding['industry'],
            stock_currency=holding['stock_currency']
        ))
    
    return holding_responses

@router.post("/portfolios/{portfolio_id}/holdings", response_model=HoldingResponse)
async def add_holding(
    portfolio_id: str,
    holding_data: HoldingCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Add a holding to a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute_query_positional(
        "SELECT id FROM portfolios WHERE id = $1 AND user_id = $2",
        [portfolio_id, current_user["id"]]
    )
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    # Check if holding already exists
    existing = db.execute_query_positional(
        "SELECT id FROM portfolio_holdings WHERE portfolio_id = $1 AND symbol = $2",
        [portfolio_id, holding_data.symbol.upper()]
    )
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Holding for {holding_data.symbol.upper()} already exists in this portfolio"
        )
    
    # Verify stock exists in stocks table (trigger will also validate)
    stock = db.execute_query_positional(
        "SELECT symbol, company_name FROM stocks WHERE symbol = $1 AND is_active = TRUE",
        [holding_data.symbol.upper()]
    )
    
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stock {holding_data.symbol.upper()} not found or not active"
        )
    
    # Add holding
    db.execute_update_positional(
        """
        INSERT INTO portfolio_holdings 
        (portfolio_id, symbol, asset_type, shares_held, average_cost, notes)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        [portfolio_id, holding_data.symbol.upper(), holding_data.asset_type,
         holding_data.shares_held, holding_data.average_cost, holding_data.notes]
    )
    
    # Get the created holding
    holding = db.execute_query_positional(
        """
        SELECT id, portfolio_id, symbol, asset_type, shares_held, average_cost,
               status, created_at, updated_at, notes, company_name, exchange,
               sector, industry, stock_currency, total_cost
        FROM portfolio_holdings_enriched
        WHERE portfolio_id = $1 AND symbol = $2
        """,
        [portfolio_id, holding_data.symbol.upper()]
    )[0]
    
    return HoldingResponse(
        id=str(holding['id']),
        portfolio_id=str(holding['portfolio_id']),
        symbol=holding['symbol'],
        asset_type=holding['asset_type'],
        shares_held=float(holding['shares_held']),
        average_cost=float(holding['average_cost']),
        total_cost=float(holding['total_cost']),
        status=holding['status'],
        created_at=holding['created_at'],
        updated_at=holding['updated_at'],
        notes=holding['notes'],
        company_name=holding['company_name'],
        exchange=holding['exchange'],
        sector=holding['sector'],
        industry=holding['industry'],
        stock_currency=holding['stock_currency']
    )

@router.get("/stocks/search", response_model=List[Dict[str, Any]])
async def search_stocks(
    query: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Search for stocks in the master stocks table"""
    
    stocks = db.execute_query_positional(
        """
        SELECT symbol, company_name, exchange, sector, industry, market_cap
        FROM stocks
        WHERE is_active = TRUE
        AND (symbol ILIKE $1 OR company_name ILIKE $1)
        ORDER BY 
            CASE WHEN symbol ILIKE $1 THEN 1 ELSE 2 END,
            market_cap DESC
        LIMIT 20
        """,
        [f"%{query}%"]
    )
    
    return stocks

@router.get("/stocks/{symbol}", response_model=Dict[str, Any])
async def get_stock_info(
    symbol: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get detailed information about a stock"""
    
    stock = db.execute_query_positional(
        """
        SELECT symbol, company_name, exchange, sector, industry, market_cap,
               country, currency, is_active, has_fundamentals, has_earnings,
               has_market_data, has_indicators, last_fundamentals_update,
               last_earnings_update, last_market_data_update, last_indicators_update
        FROM stocks
        WHERE symbol = $1
        """,
        [symbol.upper()]
    )
    
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock {symbol.upper()} not found"
        )
    
    return stock[0]
