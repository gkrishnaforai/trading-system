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
import uuid

from app.database import get_db
from app.config import settings
from app.utils.auth import get_current_user, create_access_token, hash_password, verify_password
from app.observability.logging import get_logger
from app.services.portfolio_calculator import PortfolioCalculatorService

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


class FairValueSnapshot(BaseModel):
    run_id: Optional[str] = None
    as_of: Optional[datetime] = None
    current_price_at_valuation: Optional[Decimal] = None
    fair_value: Optional[Decimal] = None
    undervaluation_pct: Optional[Decimal] = None
    valuation_rating: Optional[str] = None
    method_weights: Optional[Dict[str, Any]] = None
    peg_selected_method: Optional[str] = None


class HoldingValuationResponse(BaseModel):
    holding: HoldingResponse
    fair_value: FairValueSnapshot
    action: str


class RebalanceSuggestion(BaseModel):
    symbol: str
    action: str
    reason: str
    current_allocation_pct: Optional[Decimal] = None
    suggested_allocation_pct: Optional[Decimal] = None


class PortfolioValuationResponse(BaseModel):
    portfolio_id: str
    as_of: datetime
    holdings: List[HoldingValuationResponse]
    suggestions: List[RebalanceSuggestion]

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
async def get_user_portfolios(user_id: Optional[str] = None, db=Depends(get_db)):
    """Get portfolios.

    NOTE: Authentication has been removed to allow the Streamlit admin dashboard
    to function without requiring a JWT token.
    """

    where_clause = ""
    params: Dict[str, Any] = {}
    if user_id:
        where_clause = "WHERE p.user_id = :user_id"
        params["user_id"] = user_id

    portfolios = db.execute_query(
        f"""
        SELECT
            p.id,
            p.user_id,
            p.name,
            p.created_at,
            p.updated_at,
            COUNT(pp.id) AS holdings_count
        FROM portfolios p
        LEFT JOIN portfolio_positions pp
          ON p.id = pp.portfolio_id
        {where_clause}
        GROUP BY p.id, p.user_id, p.name, p.created_at, p.updated_at
        ORDER BY p.created_at DESC
        """,
        params,
    )
    
    portfolio_responses = []
    for portfolio in portfolios:
        portfolio_responses.append(
            PortfolioResponse(
                id=str(portfolio["id"]),
                name=portfolio.get("name"),
                description=None,
                portfolio_type="mixed",
                initial_capital=Decimal("0"),
                current_value=Decimal("0"),
                currency="USD",
                is_active=True,
                created_at=portfolio.get("created_at") or datetime.now(),
                updated_at=portfolio.get("updated_at") or portfolio.get("created_at") or datetime.now(),
                holdings_count=int(portfolio.get("holdings_count") or 0),
            )
        )
    
    return portfolio_responses

@router.post("/portfolios", response_model=PortfolioResponse)
async def create_portfolio(
    portfolio_data: PortfolioCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Create a new portfolio"""

    # The portfolios table uses a UUID PK column named `id` with default gen_random_uuid()
    portfolio_id = str(uuid.uuid4())
    db.execute_update(
        """
        INSERT INTO portfolios (id, user_id, name, description, portfolio_type, initial_capital, currency, is_active)
        VALUES (:id, :user_id, :name, :description, :portfolio_type, :initial_capital, :currency, true)
        """,
        {
            "id": portfolio_id,
            "user_id": current_user["id"],
            "name": portfolio_data.name,
            "description": portfolio_data.description,
            "portfolio_type": portfolio_data.portfolio_type,
            "initial_capital": float(portfolio_data.initial_capital),
            "currency": portfolio_data.currency,
        },
    )

    return PortfolioResponse(
        id=portfolio_id,
        name=portfolio_data.name,
        description=portfolio_data.description,
        portfolio_type=portfolio_data.portfolio_type,
        initial_capital=portfolio_data.initial_capital,
        current_value=Decimal("0"),
        currency=portfolio_data.currency,
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        holdings_count=0,
    )

@router.get("/portfolios/{portfolio_id}/holdings", response_model=List[HoldingResponse])
async def get_portfolio_holdings(
    portfolio_id: str,
    db=Depends(get_db)
):
    """Get all holdings for a portfolio.

    NOTE: Authentication/ownership checks have been removed to allow the Streamlit
    admin dashboard to function without requiring a JWT token.
    """

    portfolio_rows = db.execute_query(
        "SELECT id FROM portfolios WHERE id = :portfolio_id",
        {"portfolio_id": portfolio_id},
    )

    if not portfolio_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    holdings = db.execute_query(
        """
        SELECT
            pp.id AS holding_id,
            s.symbol,
            pp.quantity,
            pp.avg_price,
            pp.current_price,
            pp.current_value,
            pp.unrealized_gain_loss,
            pp.unrealized_gain_loss_percent,
            pp.created_at,
            pp.updated_at
        FROM portfolio_positions pp
        JOIN stocks s
          ON pp.stock_id = s.id
        WHERE pp.portfolio_id = :portfolio_id
        ORDER BY pp.created_at DESC
        """,
        {"portfolio_id": portfolio_id},
    )
    
    holding_responses: List[HoldingResponse] = []
    for holding in holdings:
        holding_responses.append(
            HoldingResponse(
                id=str(holding.get("holding_id") or ""),
                symbol=holding.get("symbol"),
                asset_type="stock",
                shares_held=Decimal(str(holding.get("quantity") or 0)),
                average_cost=Decimal(str(holding.get("avg_price") or 0)),
                current_price=(
                    Decimal(str(holding.get("current_price"))) if holding.get("current_price") is not None else None
                ),
                market_value=(
                    Decimal(str(holding.get("current_value"))) if holding.get("current_value") is not None else None
                ),
                unrealized_pnl=(
                    Decimal(str(holding.get("unrealized_gain_loss"))) if holding.get("unrealized_gain_loss") is not None else None
                ),
                unrealized_pnl_pct=(
                    Decimal(str(holding.get("unrealized_gain_loss_percent"))) if holding.get("unrealized_gain_loss_percent") is not None else None
                ),
                status="active",
                created_at=holding.get("created_at"),
                updated_at=holding.get("updated_at") or holding.get("created_at"),
                notes=None,
            )
        )

    return holding_responses


@router.post("/portfolios/{portfolio_id}/refresh-metrics")
async def refresh_portfolio_metrics(
    portfolio_id: str,
    db=Depends(get_db),
):
    """Refresh cached holding metrics (including current_price/current_value) for a portfolio."""

    portfolio_rows = db.execute_query(
        "SELECT id FROM portfolios WHERE id = :portfolio_id",
        {"portfolio_id": portfolio_id},
    )
    if not portfolio_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")

    calculator = PortfolioCalculatorService()
    updated_count = calculator.update_portfolio_holdings(portfolio_id)
    return {"success": True, "data": {"portfolio_id": portfolio_id, "holdings_updated": updated_count}}


def _action_from_undervaluation_pct(undervaluation_pct: Optional[float]) -> str:
    if undervaluation_pct is None:
        return "hold"
    if undervaluation_pct >= 20:
        return "buy"
    if undervaluation_pct <= -10:
        return "trim"
    return "hold"


@router.get("/portfolios/{portfolio_id}/valuation", response_model=PortfolioValuationResponse)
async def get_portfolio_valuation(
    portfolio_id: str,
    db=Depends(get_db),
):
    """Return portfolio holdings enriched with latest fair value runs and rebalance suggestions.

    Uses cached `portfolio_positions.current_price` and the latest `fair_value_runs` per symbol.
    """

    portfolio_rows = db.execute_query(
        "SELECT id FROM portfolios WHERE id = :portfolio_id",
        {"portfolio_id": portfolio_id},
    )
    if not portfolio_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")

    holdings_rows = db.execute_query(
        """
        SELECT
            pp.id AS holding_id,
            s.symbol AS stock_symbol,
            pp.quantity,
            pp.avg_price AS avg_entry_price,
            pp.created_at,
            pp.updated_at,
            pp.current_price,
            pp.current_value,
            pp.unrealized_gain_loss,
            pp.unrealized_gain_loss_percent
        FROM portfolio_positions pp
        JOIN stocks s
          ON pp.stock_id = s.id
        WHERE pp.portfolio_id = :portfolio_id
        ORDER BY COALESCE(pp.current_value, 0) DESC, pp.created_at DESC
        """,
        {"portfolio_id": portfolio_id},
    )

    symbols = [r["stock_symbol"] for r in holdings_rows if r.get("stock_symbol")]
    latest_runs_by_symbol: Dict[str, Dict[str, Any]] = {}
    if symbols:
        latest_runs = db.execute_query(
            """
            SELECT DISTINCT ON (symbol)
                run_id,
                symbol,
                as_of,
                current_price,
                fair_value,
                undervaluation_pct,
                valuation_rating,
                valuation_metrics
            FROM fair_value_runs
            WHERE symbol = ANY(:symbols)
            ORDER BY symbol, as_of DESC
            """,
            {"symbols": symbols},
        )
        latest_runs_by_symbol = {r["symbol"]: r for r in latest_runs}

    holdings: List[HoldingValuationResponse] = []
    suggestions: List[RebalanceSuggestion] = []

    # Build holding valuations
    for h in holdings_rows:
        symbol = h.get("stock_symbol")
        holding_resp = HoldingResponse(
            id=str(h.get("holding_id") or ""),
            symbol=symbol,
            asset_type="stock",
            shares_held=Decimal(str(h.get("quantity") or 0)),
            average_cost=Decimal(str(h.get("avg_entry_price") or 0)),
            current_price=(
                Decimal(str(h.get("current_price"))) if h.get("current_price") is not None else None
            ),
            market_value=(
                Decimal(str(h.get("current_value"))) if h.get("current_value") is not None else None
            ),
            unrealized_pnl=(
                Decimal(str(h.get("unrealized_gain_loss"))) if h.get("unrealized_gain_loss") is not None else None
            ),
            unrealized_pnl_pct=(
                Decimal(str(h.get("unrealized_gain_loss_percent"))) if h.get("unrealized_gain_loss_percent") is not None else None
            ),
            status="active",
            created_at=h.get("created_at"),
            updated_at=h.get("updated_at") or h.get("created_at"),
            notes=None,
        )

        run = latest_runs_by_symbol.get(symbol) if symbol else None
        method_weights = None
        peg_selected_method = None
        if run and run.get("valuation_metrics"):
            try:
                metrics = run["valuation_metrics"]
                if isinstance(metrics, str):
                    metrics = json.loads(metrics)
                method_weights = metrics.get("method_weights")
                peg_selected_method = metrics.get("peg_selected_method")
            except Exception:
                method_weights = None
                peg_selected_method = None

        undervaluation_pct = run.get("undervaluation_pct") if run else None
        action = _action_from_undervaluation_pct(undervaluation_pct)

        fv_snapshot = FairValueSnapshot(
            run_id=(run.get("run_id") if run else None),
            as_of=(run.get("as_of") if run else None),
            current_price_at_valuation=(
                Decimal(str(run.get("current_price"))) if run and run.get("current_price") is not None else None
            ),
            fair_value=(
                Decimal(str(run.get("fair_value"))) if run and run.get("fair_value") is not None else None
            ),
            undervaluation_pct=(
                Decimal(str(undervaluation_pct)) if undervaluation_pct is not None else None
            ),
            valuation_rating=(run.get("valuation_rating") if run else None),
            method_weights=method_weights,
            peg_selected_method=peg_selected_method,
        )

        holdings.append(HoldingValuationResponse(holding=holding_resp, fair_value=fv_snapshot, action=action))

        # Suggest trim/buy from valuation alone
        allocation_pct = None
        if action in {"buy", "trim"} and symbol:
            suggestions.append(
                RebalanceSuggestion(
                    symbol=symbol,
                    action=action,
                    reason=f"valuation_{action}",
                    current_allocation_pct=(
                        Decimal(str(allocation_pct)) if allocation_pct is not None else None
                    ),
                    suggested_allocation_pct=None,
                )
            )

    return PortfolioValuationResponse(
        portfolio_id=portfolio_id,
        as_of=datetime.now(),
        holdings=holdings,
        suggestions=suggestions,
    )

@router.post("/portfolios/{portfolio_id}/holdings", response_model=HoldingResponse)
async def add_holding(
    portfolio_id: str,
    holding_data: HoldingCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Add a holding to a portfolio"""

    portfolio_rows = db.execute_query(
        "SELECT id FROM portfolios WHERE id = :portfolio_id AND user_id = :user_id",
        {"portfolio_id": portfolio_id, "user_id": current_user["id"]},
    )
    if not portfolio_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")

    symbol = holding_data.symbol.upper()
    stock_rows = db.execute_query(
        "SELECT id FROM stocks WHERE symbol = :symbol LIMIT 1",
        {"symbol": symbol},
    )
    if stock_rows:
        stock_id = stock_rows[0].get("id")
    else:
        created_stock = db.execute_query(
            """
            INSERT INTO stocks (symbol, is_active, created_at, updated_at)
            VALUES (:symbol, true, NOW(), NOW())
            RETURNING id
            """,
            {"symbol": symbol},
        )
        stock_id = created_stock[0].get("id") if created_stock else None

    if not stock_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create/find stock")

    db.execute_update(
        """
        INSERT INTO portfolio_positions (portfolio_id, stock_id, quantity, avg_price, updated_at)
        VALUES (:portfolio_id, :stock_id, :quantity, :avg_price, NOW())
        ON CONFLICT (portfolio_id, stock_id)
        DO UPDATE SET
            quantity = EXCLUDED.quantity,
            avg_price = EXCLUDED.avg_price,
            updated_at = NOW()
        """,
        {
            "portfolio_id": portfolio_id,
            "stock_id": int(stock_id),
            "quantity": float(holding_data.shares_held),
            "avg_price": float(holding_data.average_cost),
        },
    )

    row = db.execute_query(
        """
        SELECT
            pp.id AS holding_id,
            s.symbol,
            pp.quantity,
            pp.avg_price,
            pp.current_price,
            pp.current_value,
            pp.unrealized_gain_loss,
            pp.unrealized_gain_loss_percent,
            pp.created_at,
            pp.updated_at
        FROM portfolio_positions pp
        JOIN stocks s
          ON pp.stock_id = s.id
        WHERE pp.portfolio_id = :portfolio_id
          AND pp.stock_id = :stock_id
        LIMIT 1
        """,
        {"portfolio_id": portfolio_id, "stock_id": int(stock_id)},
    )[0]

    return HoldingResponse(
        id=str(row.get("holding_id") or ""),
        symbol=row.get("symbol"),
        asset_type="stock",
        shares_held=Decimal(str(row.get("quantity") or 0)),
        average_cost=Decimal(str(row.get("avg_price") or 0)),
        current_price=Decimal(str(row.get("current_price"))) if row.get("current_price") is not None else None,
        market_value=Decimal(str(row.get("current_value"))) if row.get("current_value") is not None else None,
        unrealized_pnl=Decimal(str(row.get("unrealized_gain_loss"))) if row.get("unrealized_gain_loss") is not None else None,
        unrealized_pnl_pct=Decimal(str(row.get("unrealized_gain_loss_percent"))) if row.get("unrealized_gain_loss_percent") is not None else None,
        status="active",
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at") or row.get("created_at"),
        notes=holding_data.notes,
    )
@router.get("/symbols/{symbol}/signals", response_model=List[SignalHistoryResponse])
async def get_symbol_signal_history(
    symbol: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get signal history for a specific symbol"""

    try:
        signals = db.execute_query(
            """
            SELECT id, symbol, signal_type, confidence, price, signal_date,
                   actual_outcome, actual_return, days_held
            FROM signal_history
            WHERE symbol = :symbol
            ORDER BY signal_date DESC
            LIMIT :limit
            """,
            {"symbol": symbol.upper(), "limit": limit},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"signal_history table not available: {str(e)}",
        )

    return [
        SignalHistoryResponse(
            id=int(s.get("id")) if s.get("id") is not None else 0,
            symbol=s.get("symbol"),
            signal_type=s.get("signal_type"),
            confidence=Decimal(str(s.get("confidence") or 0)),
            price=Decimal(str(s.get("price") or 0)),
            signal_date=s.get("signal_date"),
            actual_outcome=s.get("actual_outcome"),
            actual_return=(
                Decimal(str(s.get("actual_return"))) if s.get("actual_return") is not None else None
            ),
            days_held=s.get("days_held"),
        )
        for s in signals
    ]

@router.post("/portfolios/{portfolio_id}/analyze")
async def analyze_portfolio(
    portfolio_id: str,
    target_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Run analysis on all symbols in a portfolio"""

    # This endpoint depends on analysis_logs + signal_history tables and a legacy portfolio_holdings
    # schema that isn't part of the Postgres migration set. Keep it from crashing the API.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Portfolio analysis endpoint is not implemented for the current Postgres schema. Use /refresh-metrics + /valuation.",
    )

# ========================================
# Scheduled Analysis Endpoints
# ========================================

@router.get("/portfolios/{portfolio_id}/schedules", response_model=List[ScheduledAnalysisResponse])
async def get_portfolio_schedules(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Get scheduled analyses for a portfolio"""

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Scheduled analyses are not implemented for the current Postgres schema.",
    )

@router.post("/portfolios/{portfolio_id}/schedules", response_model=ScheduledAnalysisResponse)
async def create_portfolio_schedule(
    portfolio_id: str,
    schedule_data: ScheduledAnalysisCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Create a scheduled analysis for a portfolio"""

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Scheduled analyses are not implemented for the current Postgres schema.",
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
