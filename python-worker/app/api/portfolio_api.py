"""
Portfolio Management API
Industry-standard portfolio management with user authentication, audit trails, and scheduling
"""

from fastapi import APIRouter, Depends, HTTPException, status, Form
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
import json
from decimal import Decimal

from app.database import get_db
from app.config import settings
from app.utils.auth import get_current_user, create_access_token, hash_password, verify_password
from app.observability.logging import get_logger

logger = get_logger("portfolio_api")

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])
# CORRECT: router = APIRouter(tags=["portfolio"])
# ========================================
router = APIRouter(tags=["portfolio"])

# Test endpoint
@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify router is working"""
    return {"message": "Portfolio API is working!"}

# ========================================
# Pydantic Models
# ========================================

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: str  # UUID string
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
    id: str  # UUID string
    name: str
    description: Optional[str]
    portfolio_type: str
    initial_capital: Decimal
    current_value: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    holdings_count: int = 0

class HoldingCreate(BaseModel):
    symbol: str
    asset_type: str
    shares_held: Decimal = Decimal("0")
    average_cost: Decimal = Decimal("0")
    notes: Optional[str] = None

class HoldingResponse(BaseModel):
    id: str  # UUID string
    symbol: str
    asset_type: str
    shares_held: Decimal
    average_cost: Decimal
    current_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    unrealized_pnl_pct: Optional[Decimal] = None
    status: str
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None

class SignalHistoryResponse(BaseModel):
    id: int
    symbol: str
    signal_type: str
    confidence: Decimal
    price: Decimal
    signal_date: date
    actual_outcome: Optional[str]
    actual_return: Optional[Decimal]
    days_held: Optional[int]

class ScheduledAnalysisCreate(BaseModel):
    portfolio_id: int
    schedule_type: str  # daily, weekly, monthly
    schedule_time: time
    schedule_day: Optional[int] = None
    notification_preferences: Dict[str, bool] = {"email": True, "push": False}

class ScheduledAnalysisResponse(BaseModel):
    id: int
    portfolio_id: int
    schedule_type: str
    schedule_time: time
    schedule_day: Optional[int]
    is_active: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]

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
        "SELECT id, username, email, full_name FROM users WHERE username = $1",
        [user_data.username]
    )[0]
    
    return UserResponse(
        id=str(user['id']),
        username=user['username'],
        email=user['email'],
        full_name=user['full_name'],
        role="user",
        is_active=True,
        created_at=datetime.now()
    )

# Login request model
class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/users/login")
async def login_user(login_data: LoginRequest, db=Depends(get_db)):
    """Login user and return access token"""
    
    # Add logging
    logger.info(f"Login attempt for username: {login_data.username}")
    
    user = db.execute_query_positional(
        """
        SELECT id, username, email, password_hash, full_name, role, is_active
        FROM users WHERE username = $1
        """,
        [login_data.username]
    )
    
    logger.info(f"User query result: {len(user)} records found")
    
    if not user:
        logger.warning(f"Login failed: User '{login_data.username}' not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    user_data = user[0]
    logger.info(f"User found: {user_data['username']}, checking password")
    
    if not verify_password(login_data.password, user_data['password_hash']):
        logger.warning(f"Login failed: Invalid password for user '{login_data.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    if not user_data['is_active']:
        logger.warning(f"Login failed: User '{login_data.username}' is inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive"
        )
    
    logger.info(f"Login successful for user: {login_data.username}")
    
    # Update last login
    db.execute_update(
        "UPDATE users SET last_login = :now WHERE id = :user_id",
        {"now": datetime.now(), "user_id": user_data['id']}
    )
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user_data['id'])})
    
    logger.info(f"Access token created for user: {login_data.username}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user_data['id']),
            "username": user_data['username'],
            "email": user_data['email'],
            "full_name": user_data['full_name'],
            "role": user_data['role']
        }
    }

# ========================================
# Portfolio Management Endpoints
# ========================================

@router.get("/portfolios", response_model=List[PortfolioResponse])
async def get_user_portfolios(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get all portfolios for current user"""
    
    portfolios = db.execute_query_positional(
        """
        SELECT p.id, p.name, p.description, p.portfolio_type, 
               p.initial_capital, p.currency, p.is_active, p.created_at,
               COUNT(ph.id) as holdings_count
        FROM portfolios p
        LEFT JOIN portfolio_holdings ph ON p.id = ph.portfolio_id AND ph.status = 'active'
        WHERE p.user_id = $1
        GROUP BY p.id, p.name, p.description, p.portfolio_type, 
                 p.initial_capital, p.currency, p.is_active, p.created_at
        ORDER BY p.created_at DESC
        """,
        [current_user["id"]]
    )
    
    portfolio_responses = []
    for portfolio in portfolios:
        # Calculate current value (simplified)
        current_value = float(portfolio['initial_capital'])
        
        portfolio_responses.append(PortfolioResponse(
            id=str(portfolio['id']),
            name=portfolio['name'],
            description=portfolio['description'],
            portfolio_type=portfolio['portfolio_type'],
            initial_capital=float(portfolio['initial_capital']),
            current_value=current_value,
            currency=portfolio['currency'],
            is_active=portfolio['is_active'],
            created_at=portfolio['created_at'],
            updated_at=portfolio['created_at'],  # TODO: Add updated_at to table
            holdings_count=portfolio['holdings_count']
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
        SELECT id, name, description, portfolio_type, initial_capital, currency, is_active, created_at 
        FROM portfolios 
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
        current_value=float(portfolio['initial_capital']),
        currency=portfolio['currency'],
        is_active=portfolio['is_active'],
        created_at=portfolio['created_at'],
        updated_at=portfolio['created_at'],
        holdings_count=0
    )

@router.get("/portfolios/{portfolio_id}/holdings", response_model=List[HoldingResponse])
async def get_portfolio_holdings(
    portfolio_id: int,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get all holdings for a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute(
        "SELECT id FROM portfolios WHERE id = %s AND user_id = %s",
        (portfolio_id, current_user["id"])
    ).fetchone()
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    holdings = db.execute(
        """
        SELECT ph.id, ph.symbol, ph.asset_type, ph.shares_held, ph.average_cost,
               ph.status, ph.created_at
        FROM portfolio_holdings ph
        WHERE ph.portfolio_id = %s AND ph.status = 'active'
        ORDER BY ph.created_at DESC
        """,
        (portfolio_id,)
    ).fetchall()
    
    # Get current prices for all symbols
    symbols = [holding[1] for holding in holdings]
    current_prices = {}
    
    if symbols:
        # Query current prices from market data
        price_query = """
        SELECT symbol, close as price
        FROM raw_market_data_daily 
        WHERE symbol = ANY(%s) 
        AND date = (
            SELECT MAX(date) FROM raw_market_data_daily 
            WHERE symbol = ANY(%s)
        )
        """
        price_results = db.execute(price_query, (symbols, symbols)).fetchall()
        current_prices = {result[0]: result[1] for result in price_results}
    
    holding_responses = []
    for holding in holdings:
        current_price = current_prices.get(holding[1])
        market_value = None
        unrealized_pnl = None
        unrealized_pnl_pct = None
        
        if current_price and holding[3] > 0:  # shares_held > 0
            market_value = current_price * holding[3]
            cost_basis = holding[4] * holding[3]  # average_cost * shares_held
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
        
        holding_responses.append(
            HoldingResponse(
                id=holding[0],
                symbol=holding[1],
                asset_type=holding[2],
                shares_held=holding[3],
                average_cost=holding[4],
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                status=holding[5],
                created_at=holding[6]
            )
        )
    
    return holding_responses

@router.post("/portfolios/{portfolio_id}/holdings", response_model=HoldingResponse)
async def add_holding(
    portfolio_id: int,
    holding_data: HoldingCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Add a holding to a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute(
        "SELECT id FROM portfolios WHERE id = %s AND user_id = %s",
        (portfolio_id, current_user["id"])
    ).fetchone()
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    # Check if holding already exists
    existing = db.execute(
        "SELECT id FROM portfolio_holdings WHERE portfolio_id = %s AND symbol = %s",
        (portfolio_id, holding_data.symbol.upper())
    ).fetchone()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Symbol already exists in portfolio"
        )
    
    # Add to symbol master table (audit trail)
    db.execute(
        """
        INSERT INTO symbol_master (symbol, asset_type, first_analyzed, last_analyzed)
        VALUES (%s, %s, CURRENT_DATE, CURRENT_DATE)
        ON CONFLICT (symbol) DO UPDATE SET
            asset_type = EXCLUDED.asset_type,
            last_analyzed = CURRENT_DATE
        """,
        (holding_data.symbol.upper(), holding_data.asset_type)
    )
    
    # Add holding
    holding_id = db.execute(
        """
        INSERT INTO portfolio_holdings 
        (portfolio_id, symbol, asset_type, shares_held, average_cost, notes, 
         first_purchase_date, last_purchase_date)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, CURRENT_DATE)
        RETURNING id, symbol, asset_type, shares_held, average_cost, status, created_at
        """,
        (portfolio_id, holding_data.symbol.upper(), holding_data.asset_type,
         holding_data.shares_held, holding_data.average_cost, holding_data.notes)
    ).fetchone()
    
    db.commit()
    
    return HoldingResponse(
        id=holding_id[0],
        symbol=holding_id[1],
        asset_type=holding_id[2],
        shares_held=holding_id[3],
        average_cost=holding_id[4],
        status=holding_id[5],
        created_at=holding_id[6]
    )

# ========================================
# Signal History & Analysis Endpoints
# ========================================

@router.get("/symbols/{symbol}/signals", response_model=List[SignalHistoryResponse])
async def get_symbol_signal_history(
    symbol: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get signal history for a specific symbol"""
    
    signals = db.execute(
        """
        SELECT id, symbol, signal_type, confidence, price, signal_date,
               actual_outcome, actual_return, days_held
        FROM signal_history
        WHERE symbol = %s
        ORDER BY signal_date DESC
        LIMIT %s
        """,
        (symbol.upper(), limit)
    ).fetchall()
    
    return [
        SignalHistoryResponse(
            id=signal[0],
            symbol=signal[1],
            signal_type=signal[2],
            confidence=signal[3],
            price=signal[4],
            signal_date=signal[5],
            actual_outcome=signal[6],
            actual_return=signal[7],
            days_held=signal[8]
        )
        for signal in signals
    ]

@router.post("/portfolios/{portfolio_id}/analyze")
async def analyze_portfolio(
    portfolio_id: int,
    target_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Run analysis on all symbols in a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute(
        "SELECT id, name FROM portfolios WHERE id = %s AND user_id = %s",
        (portfolio_id, current_user["id"])
    ).fetchone()
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    # Get portfolio holdings
    holdings = db.execute(
        """
        SELECT symbol, asset_type FROM portfolio_holdings
        WHERE portfolio_id = %s AND status = 'active'
        """,
        (portfolio_id,)
    ).fetchall()
    
    if not holdings:
        return {"success": False, "error": "No holdings found in portfolio"}
    
    # Create analysis log
    log_id = db.execute(
        """
        INSERT INTO analysis_logs (user_id, portfolio_id, analysis_type, symbols_analyzed, start_time, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (current_user["id"], portfolio_id, "portfolio", len(holdings), datetime.now(), "running")
    ).fetchone()[0]
    
    try:
        # Import signal generation logic
        from app.api.universal_backtest_api import generate_universal_signal
        
        signals_generated = 0
        successful_analyses = []
        
        for holding in holdings:
            symbol, asset_type = holding
            
            try:
                # Generate signal for this symbol
                signal_data = generate_universal_signal(
                    symbol=symbol,
                    target_date=target_date or datetime.now().date(),
                    asset_type=asset_type
                )
                
                if signal_data and "error" not in signal_data:
                    # Extract signal data
                    signal = signal_data.get("signal", {})
                    market_data = signal_data.get("market_data", {})
                    analysis = signal_data.get("analysis", {})
                    
                    # Store in signal history (audit trail)
                    db.execute(
                        """
                        INSERT INTO signal_history 
                        (symbol, portfolio_id, user_id, signal_type, confidence, price,
                         rsi, macd, macd_signal, sma_20, sma_50, ema_20, volume,
                         ema_slope, volatility, vix_level, recent_change,
                         fear_greed_state, fear_greed_bias, recovery_detected,
                         engine_type, asset_type, strategy, reasoning, signal_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (symbol, portfolio_id, current_user["id"],
                         signal.get("signal", "HOLD"), signal.get("confidence", 0),
                         market_data.get("price", 0), market_data.get("rsi", 0),
                         market_data.get("macd", 0), market_data.get("macd_signal", 0),
                         market_data.get("sma_20", 0), market_data.get("sma_50", 0),
                         market_data.get("ema_20", 0), market_data.get("volume", 0),
                         analysis.get("ema_slope", 0), analysis.get("real_volatility", 0),
                         analysis.get("vix_level", 0), analysis.get("recent_change", 0),
                         signal.get("metadata", {}).get("fear_greed_state"),
                         signal.get("metadata", {}).get("fear_greed_bias"),
                         signal.get("metadata", {}).get("recovery_detected", False),
                         signal_data.get("engine", {}).get("engine_type"),
                         asset_type, signal_data.get("engine", {}).get("engine_type"),
                         json.dumps(signal.get("reasoning", [])),
                         target_date or datetime.now().date())
                    )
                    
                    signals_generated += 1
                    successful_analyses.append({
                        "symbol": symbol,
                        "signal": signal.get("signal", "HOLD"),
                        "confidence": signal.get("confidence", 0),
                        "price": market_data.get("price", 0)
                    })
                
            except Exception as e:
                db.execute(
                    "UPDATE analysis_logs SET error_message = %s WHERE id = %s",
                    (f"Error analyzing {symbol}: {str(e)}", log_id)
                )
        
        # Update analysis log
        success_rate = (signals_generated / len(holdings) * 100) if holdings else 0
        db.execute(
            """
            UPDATE analysis_logs 
            SET signals_generated = %s, success_rate = %s, end_time = %s, 
                duration_ms = %s, status = %s
            WHERE id = %s
            """,
            (signals_generated, success_rate, datetime.now(),
             (datetime.now() - datetime.now()).microseconds // 1000, "completed", log_id)
        )
        
        db.commit()
        
        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio[1],
            "symbols_analyzed": len(holdings),
            "signals_generated": signals_generated,
            "success_rate": success_rate,
            "analysis_date": target_date or datetime.now().date(),
            "results": successful_analyses
        }
        
    except Exception as e:
        db.execute(
            "UPDATE analysis_logs SET status = %s, error_message = %s WHERE id = %s",
            ("failed", str(e), log_id)
        )
        db.commit()
        
        return {"success": False, "error": str(e)}

# ========================================
# Scheduled Analysis Endpoints
# ========================================

@router.get("/portfolios/{portfolio_id}/schedules", response_model=List[ScheduledAnalysisResponse])
async def get_portfolio_schedules(
    portfolio_id: int,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get scheduled analyses for a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute(
        "SELECT id FROM portfolios WHERE id = %s AND user_id = %s",
        (portfolio_id, current_user["id"])
    ).fetchone()
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    schedules = db.execute(
        """
        SELECT id, portfolio_id, schedule_type, schedule_time, schedule_day,
               is_active, last_run, next_run
        FROM scheduled_analyses
        WHERE portfolio_id = %s
        ORDER BY created_at DESC
        """,
        (portfolio_id,)
    ).fetchall()
    
    return [
        ScheduledAnalysisResponse(
            id=schedule[0],
            portfolio_id=schedule[1],
            schedule_type=schedule[2],
            schedule_time=schedule[3],
            schedule_day=schedule[4],
            is_active=schedule[5],
            last_run=schedule[6],
            next_run=schedule[7]
        )
        for schedule in schedules
    ]

@router.post("/portfolios/{portfolio_id}/schedules", response_model=ScheduledAnalysisResponse)
async def create_scheduled_analysis(
    portfolio_id: int,
    schedule_data: ScheduledAnalysisCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Create a scheduled analysis for a portfolio"""
    
    # Verify portfolio ownership
    portfolio = db.execute(
        "SELECT id FROM portfolios WHERE id = %s AND user_id = %s",
        (portfolio_id, current_user["id"])
    ).fetchone()
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    # Calculate next run time
    next_run = calculate_next_run_time(schedule_data.schedule_type, schedule_data.schedule_time, schedule_data.schedule_day)
    
    schedule_id = db.execute(
        """
        INSERT INTO scheduled_analyses 
        (user_id, portfolio_id, schedule_type, schedule_time, schedule_day, 
         notification_preferences, next_run)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, portfolio_id, schedule_type, schedule_time, schedule_day,
                  is_active, last_run, next_run
        """,
        (current_user["id"], portfolio_id, schedule_data.schedule_type,
         schedule_data.schedule_time, schedule_data.schedule_day,
         json.dumps(schedule_data.notification_preferences), next_run)
    ).fetchone()
    
    db.commit()
    
    return ScheduledAnalysisResponse(
        id=schedule_id[0],
        portfolio_id=schedule_id[1],
        schedule_type=schedule_id[2],
        schedule_time=schedule_id[3],
        schedule_day=schedule_id[4],
        is_active=schedule_id[5],
        last_run=schedule_id[6],
        next_run=schedule_id[7]
    )

def calculate_next_run_time(schedule_type: str, schedule_time: time, schedule_day: Optional[int]) -> datetime:
    """Calculate the next run time for a scheduled analysis"""
    from datetime import timedelta
    
    now = datetime.now()
    today = now.date()
    
    if schedule_type == "daily":
        next_run = datetime.combine(today, schedule_time)
        if next_run <= now:
            next_run += timedelta(days=1)
    
    elif schedule_type == "weekly":
        # schedule_day: 1=Monday, 7=Sunday
        if schedule_day:
            days_ahead = (schedule_day - 1 - today.weekday()) % 7
            if days_ahead == 0 and datetime.combine(today, schedule_time) <= now:
                days_ahead = 7
            next_run = datetime.combine(today + timedelta(days=days_ahead), schedule_time)
        else:
            next_run = datetime.combine(today + timedelta(days=7), schedule_time)
    
    elif schedule_type == "monthly":
        # schedule_day: day of month (1-31)
        if schedule_day:
            if today.day <= schedule_day:
                next_month = today.replace(day=schedule_day)
            else:
                # Move to next month
                if today.month == 12:
                    next_month = today.replace(year=today.year+1, month=1, day=schedule_day)
                else:
                    next_month = today.replace(month=today.month+1, day=schedule_day)
            
            # Handle invalid dates (e.g., February 31)
            try:
                next_run = datetime.combine(next_month, schedule_time)
            except ValueError:
                # Move to last valid day of month
                last_day = (next_month.replace(month=next_month.month+1, day=1) - timedelta(days=1)).day
                next_run = datetime.combine(next_month.replace(day=last_day), schedule_time)
        else:
            next_run = datetime.combine(today.replace(day=1), schedule_time)
            if next_run <= now:
                if today.month == 12:
                    next_run = datetime.combine(today.replace(year=today.year+1, month=1, day=1), schedule_time)
                else:
                    next_run = datetime.combine(today.replace(month=today.month+1, day=1), schedule_time)
    
    else:
        next_run = now + timedelta(days=1)  # Default to tomorrow
    
    return next_run
