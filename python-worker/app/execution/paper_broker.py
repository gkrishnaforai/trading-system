"""In-memory paper broker with explicit order lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.orders.models import OrderPlan, OrderSide, OrderType


class PaperOrderStatus(str, Enum):
    NEW = "NEW"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PaperFill(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    timestamp: datetime


class PaperOrder(BaseModel):
    order_id: str
    plan_id: str
    symbol: str
    side: OrderSide
    quantity: int
    status: PaperOrderStatus
    submitted_at: datetime
    filled_at: Optional[datetime] = None
    fill: Optional[PaperFill] = None
    reason: Optional[str] = None


class PaperPosition(BaseModel):
    symbol: str
    quantity: int = 0
    average_price: float = 0.0
    stop_price: Optional[float] = None
    target_price: Optional[float] = None


class PaperAccount(BaseModel):
    cash: float = Field(ge=0)
    equity: float = Field(gt=0)
    positions: Dict[str, PaperPosition] = Field(default_factory=dict)
    orders: Dict[str, PaperOrder] = Field(default_factory=dict)
    fills: List[PaperFill] = Field(default_factory=list)


class PaperBroker:
    """Deterministic simulator; no network or live-broker calls."""

    def __init__(self, *, starting_cash: float, fee_bps: float = 1.0):
        if starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        self.account = PaperAccount(cash=starting_cash, equity=starting_cash)
        self.fee_bps = fee_bps

    def submit_order(
        self,
        plan: OrderPlan,
        *,
        market_price: float,
        approved: bool = False,
        timestamp: Optional[datetime] = None,
    ) -> PaperOrder:
        now = timestamp or datetime.now(timezone.utc)
        order_id = str(uuid4())
        if plan.approval_required and not approved:
            order = PaperOrder(
                order_id=order_id, plan_id=plan.plan_id, symbol=plan.symbol,
                side=plan.side, quantity=plan.quantity,
                status=PaperOrderStatus.REJECTED, submitted_at=now,
                reason="approval required",
            )
            self.account.orders[order_id] = order
            return order
        if market_price <= 0:
            return self._reject(order_id, plan, now, "market price must be positive")

        fill_price = market_price * (1 + plan.max_slippage_bps / 10000) if plan.side == OrderSide.BUY else market_price * (1 - plan.max_slippage_bps / 10000)
        if plan.order_type == OrderType.LIMIT and plan.limit_price is not None:
            executable = fill_price <= plan.limit_price if plan.side == OrderSide.BUY else fill_price >= plan.limit_price
            if not executable:
                return self._reject(order_id, plan, now, "limit price not marketable")
        gross = fill_price * plan.quantity
        fee = gross * self.fee_bps / 10000
        if plan.side == OrderSide.BUY and gross + fee > self.account.cash + 1e-9:
            return self._reject(order_id, plan, now, "insufficient paper cash")
        if plan.side == OrderSide.BUY:
            self.account.cash -= gross + fee
            self._add_position(plan, fill_price)
        else:
            self.account.cash += gross - fee
            self._reduce_position(plan, fill_price)

        fill = PaperFill(
            order_id=order_id, symbol=plan.symbol, side=plan.side,
            quantity=plan.quantity, price=fill_price, timestamp=now,
        )
        order = PaperOrder(
            order_id=order_id, plan_id=plan.plan_id, symbol=plan.symbol,
            side=plan.side, quantity=plan.quantity,
            status=PaperOrderStatus.FILLED, submitted_at=now,
            filled_at=now, fill=fill,
        )
        self.account.orders[order_id] = order
        self.account.fills.append(fill)
        self._refresh_equity({plan.symbol: market_price})
        return order

    def cancel_order(self, order_id: str) -> PaperOrder:
        order = self.account.orders[order_id]
        if order.status == PaperOrderStatus.NEW:
            order.status = PaperOrderStatus.CANCELLED
        return order

    def mark_to_market(self, prices: Dict[str, float]) -> PaperAccount:
        self._refresh_equity(prices)
        return self.account

    def check_exits(self, prices: Dict[str, float], *, timestamp: Optional[datetime] = None) -> List[PaperOrder]:
        exits: List[PaperOrder] = []
        for symbol, position in list(self.account.positions.items()):
            if position.quantity <= 0 or symbol not in prices:
                continue
            price = prices[symbol]
            exit_price = None
            reason = None
            if position.stop_price is not None and price <= position.stop_price:
                exit_price, reason = position.stop_price, "stop triggered"
            elif position.target_price is not None and price >= position.target_price:
                exit_price, reason = position.target_price, "target triggered"
            if exit_price is not None:
                plan = OrderPlan(
                    plan_id=str(uuid4()), symbol=symbol, side=OrderSide.SELL,
                    order_type=OrderType.MARKET, quantity=position.quantity,
                    approval_required=False, reasons=[reason],
                )
                exits.append(self.submit_order(plan, market_price=exit_price, approved=True, timestamp=timestamp))
        return exits

    def _add_position(self, plan: OrderPlan, fill_price: float) -> None:
        current = self.account.positions.get(plan.symbol, PaperPosition(symbol=plan.symbol))
        total = current.quantity + plan.quantity
        current.average_price = ((current.quantity * current.average_price) + (plan.quantity * fill_price)) / total
        current.quantity = total
        current.stop_price = plan.stop_price
        current.target_price = plan.target_price
        self.account.positions[plan.symbol] = current

    def _reduce_position(self, plan: OrderPlan, fill_price: float) -> None:
        current = self.account.positions.get(plan.symbol)
        if current is None or current.quantity < plan.quantity:
            raise ValueError("insufficient paper position")
        current.quantity -= plan.quantity
        if current.quantity == 0:
            del self.account.positions[plan.symbol]
        else:
            self.account.positions[plan.symbol] = current

    def _refresh_equity(self, prices: Dict[str, float]) -> None:
        value = self.account.cash
        for symbol, position in self.account.positions.items():
            value += position.quantity * prices.get(symbol, position.average_price)
        self.account.equity = value

    def _reject(self, order_id: str, plan: OrderPlan, now: datetime, reason: str) -> PaperOrder:
        order = PaperOrder(
            order_id=order_id, plan_id=plan.plan_id, symbol=plan.symbol,
            side=plan.side, quantity=plan.quantity,
            status=PaperOrderStatus.REJECTED, submitted_at=now, reason=reason,
        )
        self.account.orders[order_id] = order
        return order
