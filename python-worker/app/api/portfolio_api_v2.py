"""
Portfolio Management API v2
Industry-standard portfolio management with proper stocks table integration
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
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
# WRONG: router = APIRouter(prefix="/api/v2/portfolio", tags=["portfolio-v2"])
# CORRECT: router = APIRouter(tags=["portfolio-v2"])
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

# Signup — the human-facing account creation path. Role is always
# 'basic' server-side: privilege is never taken from the request.
class SignupRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str


def _admin_override(user: dict) -> str:
    """MP_ADMIN_USERS (comma-sep usernames or emails) elevates the
    stored role — survives DB resets for operator accounts."""
    import os
    admins = {u.strip().lower() for u in
              os.getenv("MP_ADMIN_USERS", "").split(",") if u.strip()}
    if (user.get("username") or "").lower() in admins or \
       (user.get("email") or "").lower() in admins:
        return "admin"
    return user.get("role") or "basic"


def _session_token(user: dict) -> str:
    """UI session token — longer-lived than the 30min API default;
    the cookie on the frontend carries the same horizon."""
    import os
    days = float(os.getenv("MP_SESSION_DAYS", "7"))
    return create_access_token(
        data={"sub": str(user["id"]), "username": user["username"],
              "role": _admin_override(user), "email": user["email"]},
        expires_delta=timedelta(days=days))


# Login request model — `username` accepts an email too; humans log in
# with email, the device account still uses its username.
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


@router.post("/users/signup", response_model=LoginResponse)
async def signup_user(body: SignupRequest, db=Depends(get_db)):
    """Create an account from the signup form — email is the login
    identity and doubles as username; every signup lands 'basic'."""
    email = body.email.lower().strip()
    if len(body.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "password must be at least 8 characters")
    if db.execute_query_positional(
            "SELECT id FROM users WHERE email = $1", [email]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "an account with this email already exists")
    full = f"{body.first_name.strip()} {body.last_name.strip()}".strip()
    db.execute_update_positional(
        """INSERT INTO users (username, email, password_hash, full_name,
                              first_name, last_name, role)
           VALUES ($1, $2, $3, $4, $5, $6, 'basic')""",
        [email, email, hash_password(body.password), full,
         body.first_name.strip(), body.last_name.strip()])
    user = db.execute_query_positional(
        "SELECT id, username, email, full_name, role, is_active,"
        " created_at FROM users WHERE email = $1", [email])[0]
    return LoginResponse(
        access_token=_session_token(user), token_type="bearer",
        user=UserResponse(id=str(user["id"]), username=user["username"],
                          email=user["email"], full_name=user["full_name"],
                          role=user["role"], is_active=user["is_active"],
                          created_at=user["created_at"]))


@router.post("/users/login", response_model=LoginResponse)
async def login_user(login_data: LoginRequest, db=Depends(get_db)):
    """Authenticate user and return JWT token"""

    ident = login_data.username.strip()
    logger.info(f"Login attempt for: {ident}")

    user = db.execute_query_positional(
        """
        SELECT id, username, email, password_hash, full_name, role, is_active
        FROM users WHERE username = $1 OR email = $1
        """,
        [ident]
    )

    if not user:
        logger.warning(f"Login failed: '{ident}' not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    user_data = user[0]

    if not user_data['is_active']:
        logger.warning(f"Login failed: '{ident}' is inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive"
        )

    if not verify_password(login_data.password, user_data['password_hash']):
        logger.warning(f"Login failed: Invalid password for '{ident}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    logger.info(f"Login successful: {user_data['username']}")

    # Update last login
    db.execute_update(
        "UPDATE users SET last_login = :now WHERE id = :user_id",
        {"now": datetime.now(), "user_id": user_data['id']}
    )

    role = _admin_override(user_data)
    return LoginResponse(
        access_token=_session_token(user_data),
        token_type="bearer",
        user=UserResponse(
            id=str(user_data['id']),
            username=user_data['username'],
            email=user_data['email'],
            full_name=user_data['full_name'],
            role=role,
            is_active=user_data['is_active'],
            created_at=user_data['created_at'] if 'created_at' in user_data else datetime.now()
        )
    )

# ========================================
# Portfolio Management Endpoints
# ========================================

@router.get("/portfolios", response_model=List[PortfolioResponse])
async def get_user_portfolios(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get portfolios.

    Single-tenant cockpit: the pulse unions holdings across ALL books,
    so the picker must too — filtering by user_id hid books seeded
    under a different account row (the visible "missing portfolios"
    bug). Auth remains a device-local account; when real multi-user
    sign-in lands this regains `WHERE user_id = $1`."""

    portfolios = db.execute_query(
        """
        SELECT id, name, description, portfolio_type, initial_capital, currency,
               is_active, created_at, updated_at, holdings_count, total_invested
        FROM portfolio_summary
        ORDER BY created_at DESC
        """
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

@router.delete("/portfolios/{portfolio_id}")
async def delete_portfolio(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Delete a book and its holdings (FK cascade). Hard delete —
    the journal tables don't key off portfolios, so nothing else
    is orphaned."""
    portfolio = db.execute_query_positional(
        "SELECT id, name FROM portfolios WHERE id = $1",
        [portfolio_id]
    )
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    db.execute_update_positional(
        "DELETE FROM portfolios WHERE id = $1", [portfolio_id]
    )
    return {"message": f"Portfolio '{portfolio[0]['name']}' deleted"}

@router.get("/portfolios/{portfolio_id}/holdings", response_model=List[HoldingResponse])
async def get_portfolio_holdings(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get all holdings for a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute_query_positional(
        "SELECT id FROM portfolios WHERE id = $1",
        [portfolio_id]
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
        "SELECT id FROM portfolios WHERE id = $1",
        [portfolio_id]
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
    
    # Vivify the stocks row for any ticker — 'add any stock' shouldn't
    # 400 just because the universe hasn't ingested it yet. The FK +
    # enriched view pick it up once the pipelines see the symbol.
    db.execute_update_positional(
        """
        INSERT INTO stocks (symbol, is_active, created_at, updated_at)
        VALUES ($1, TRUE, NOW(), NOW())
        ON CONFLICT (symbol) DO UPDATE SET is_active = TRUE
        """,
        [holding_data.symbol.upper()]
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

    # Mirror into portfolio_positions — the signal layer (earnings
    # watch, tiers, thesis, book risk) reads positions, not holdings.
    # Without this, a UI add is invisible to every engine.
    stock_row = db.execute_query_positional(
        "SELECT id FROM stocks WHERE symbol = $1",
        [holding_data.symbol.upper()])
    if stock_row:
        db.execute_update_positional(
            """
            INSERT INTO portfolio_positions
                (portfolio_id, stock_id, quantity, avg_price, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (portfolio_id, stock_id)
            DO UPDATE SET quantity = EXCLUDED.quantity,
                avg_price = EXCLUDED.avg_price, updated_at = NOW()
            """,
            [portfolio_id, stock_row[0]['id'],
             float(holding_data.shares_held), float(holding_data.average_cost)])

    # Best-effort: prime bars/fundamentals/earnings + resolve FV in the
    # background so a fresh add isn't decision-blind until the next
    # scheduled sweep.
    try:
        from app.workers.job_producer import enqueue_fair_value_warmup
        enqueue_fair_value_warmup(holding_data.symbol.upper(),
                                  portfolio_id=portfolio_id)
    except Exception:
        pass

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

@router.put("/portfolios/{portfolio_id}/holdings/{symbol}", response_model=HoldingResponse)
async def update_holding(
    portfolio_id: str,
    symbol: str,
    holding_data: HoldingCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Update a holding in a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute_query_positional(
        "SELECT id FROM portfolios WHERE id = $1",
        [portfolio_id]
    )
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    # Check if holding exists
    existing = db.execute_query_positional(
        "SELECT id FROM portfolio_holdings WHERE portfolio_id = $1 AND symbol = $2",
        [portfolio_id, symbol.upper()]
    )
    
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holding for {symbol.upper()} not found in this portfolio"
        )
    
    # Update holding
    db.execute_update_positional(
        """
        UPDATE portfolio_holdings
        SET shares_held = $1, average_cost = $2, asset_type = $3,
            notes = $4, updated_at = CURRENT_TIMESTAMP
        WHERE portfolio_id = $5 AND symbol = $6
        """,
        [
            holding_data.shares_held,
            holding_data.average_cost,
            holding_data.asset_type,
            holding_data.notes or "",
            portfolio_id,
            symbol.upper()
        ]
    )

    # keep the signal-layer mirror in step
    db.execute_update_positional(
        """
        UPDATE portfolio_positions pp
        SET quantity = $1, avg_price = $2, updated_at = NOW()
        FROM stocks s
        WHERE pp.stock_id = s.id AND s.symbol = $3 AND pp.portfolio_id = $4
        """,
        [float(holding_data.shares_held), float(holding_data.average_cost),
         symbol.upper(), portfolio_id])
    
    # Get updated holding
    updated_holding = db.execute_query_positional(
        """
        SELECT ph.*, s.company_name, s.exchange, s.sector, s.industry, s.currency as stock_currency
        FROM portfolio_holdings ph
        LEFT JOIN stocks s ON ph.symbol = s.symbol
        WHERE ph.portfolio_id = $1 AND ph.symbol = $2
        """,
        [portfolio_id, symbol.upper()]
    )
    
    if updated_holding:
        holding = updated_holding[0]
        return HoldingResponse(
            id=str(holding['id']),
            portfolio_id=str(holding['portfolio_id']),
            symbol=holding['symbol'],
            asset_type=holding['asset_type'],
            shares_held=float(holding['shares_held']),
            average_cost=float(holding['average_cost']),
            total_cost=float(holding['shares_held'] * holding['average_cost']),
            current_price=None,
            market_value=None,
            unrealized_pnl=None,
            unrealized_pnl_pct=None,
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

@router.delete("/portfolios/{portfolio_id}/holdings/{symbol}")
async def delete_holding(
    portfolio_id: str,
    symbol: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Delete a holding from a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute_query_positional(
        "SELECT id FROM portfolios WHERE id = $1",
        [portfolio_id]
    )
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    # Check if holding exists
    existing = db.execute_query_positional(
        "SELECT id FROM portfolio_holdings WHERE portfolio_id = $1 AND symbol = $2",
        [portfolio_id, symbol.upper()]
    )
    
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holding for {symbol.upper()} not found in this portfolio"
        )
    
    # Delete holding
    db.execute_update_positional(
        "DELETE FROM portfolio_holdings WHERE portfolio_id = $1 AND symbol = $2",
        [portfolio_id, symbol.upper()]
    )

    # and the signal-layer mirror — a removed holding must stop being
    # 'in the book' for every engine.
    db.execute_update_positional(
        """
        DELETE FROM portfolio_positions pp
        USING stocks s
        WHERE pp.stock_id = s.id AND s.symbol = $1 AND pp.portfolio_id = $2
        """,
        [symbol.upper(), portfolio_id])
    
    return {"message": f"Holding for {symbol.upper()} deleted successfully"}

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
