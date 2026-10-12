"""
Yahoo Finance provider adapter — wraps YahooFinanceClient, normalizes to canonical models.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from app.observability.logging import get_logger
from app.providers.yahoo_finance.client import YahooFinanceClient

from ..base import MarketDataProvider, first, to_date, to_datetime, to_float
from ..errors import DataNotFound
from ..models import (
    CompanyProfile,
    EarningsEvent,
    FinancialStatements,
    FundamentalsSnapshot,
    NewsItem,
    OHLCVBar,
    Quote,
)

logger = get_logger("market_data_yahoo")


class YahooProvider(MarketDataProvider):
    name = "yahoo_finance"

    def __init__(self, client: Optional[YahooFinanceClient] = None):
        self._client = client or YahooFinanceClient.from_settings()

    async def get_ohlcv(
        self,
        symbol: str,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        period: Optional[str] = None,
        interval: str = "1d",
    ) -> List[OHLCVBar]:
        kwargs = {"interval": interval}
        if start is not None and end is not None:
            kwargs["start"] = start
            kwargs["end"] = end
        else:
            kwargs["period"] = period or "1y"

        df = self._require(
            await self._call(
                "ohlcv", self._client.fetch_price_data, symbol, **kwargs
            ),
            self.name,
            "ohlcv",
        )
        bars = []
        for row in df.to_dict(orient="records"):
            o, h, l, c = (to_float(row.get(k))
                          for k in ("open", "high", "low", "close"))
            if None in (o, h, l, c):
                # yfinance emits all-NaN rows for holidays/partial sessions
                continue
            bars.append(OHLCVBar(
                provider=self.name,
                symbol=symbol,
                timestamp=to_datetime(first(row, "ts", "date")),
                interval=str(first(row, "interval") or interval),
                open=o, high=h, low=l, close=c,
                adj_close=to_float(row.get("adj_close")),
                volume=to_float(row.get("volume")),
            ))
        return self._require(bars, self.name, "ohlcv")

    async def get_quote(self, symbol: str) -> Quote:
        data = self._require(
            await self._call("quote", self._client.fetch_current_price, symbol),
            self.name,
            "quote",
        )
        price = to_float(data.get("price"))
        if price is None:
            raise DataNotFound(self.name, "quote", "no price in quote payload")
        return Quote(
            provider=self.name,
            symbol=symbol,
            price=price,
            volume=to_float(data.get("volume")),
        )

    async def get_profile(self, symbol: str) -> CompanyProfile:
        data = self._require(
            await self._call("profile", self._client.fetch_symbol_details, symbol),
            self.name,
            "profile",
        )
        return CompanyProfile(
            provider=self.name,
            symbol=symbol,
            name=data.get("name"),
            exchange=data.get("exchange"),
            currency=data.get("currency"),
            sector=data.get("sector"),
            industry=data.get("industry"),
            country=data.get("country"),
            market_cap=to_float(data.get("market_cap")),
            beta=to_float(data.get("beta")),
            description=data.get("description"),
            website=data.get("website"),
        )

    async def get_fundamentals(self, symbol: str) -> FundamentalsSnapshot:
        data = self._require(
            await self._call(
                "fundamentals", self._client.fetch_fundamentals, symbol
            ),
            self.name,
            "fundamentals",
        )
        return FundamentalsSnapshot(
            provider=self.name,
            symbol=symbol,
            market_cap=to_float(data.get("market_cap")),
            pe_ratio=to_float(data.get("pe_ratio")),
            forward_pe=to_float(data.get("forward_pe")),
            pb_ratio=to_float(first(data, "pb_ratio", "price_to_book")),
            price_to_sales=to_float(data.get("price_to_sales")),
            peg_ratio=to_float(data.get("peg_ratio")),
            eps=to_float(first(data, "eps", "eps_trailing")),
            profit_margin=to_float(data.get("profit_margin")),
            gross_margin=to_float(data.get("gross_margin")),
            operating_margin=to_float(data.get("operating_margin")),
            roe=to_float(data.get("roe")),
            roa=to_float(data.get("roa")),
            revenue_growth=to_float(data.get("revenue_growth")),
            earnings_growth=to_float(data.get("earnings_growth")),
            current_ratio=to_float(data.get("current_ratio")),
            quick_ratio=to_float(data.get("quick_ratio")),
            debt_to_equity=to_float(data.get("debt_to_equity")),
            revenue=to_float(first(data, "revenue", "total_revenue")),
            gross_profit=to_float(first(data, "gross_profit", "gross_profits")),
            net_income=to_float(data.get("net_income")),
            ebitda=to_float(data.get("ebitda")),
            total_assets=to_float(data.get("total_assets")),
            total_liabilities=to_float(data.get("total_liabilities")),
            total_debt=to_float(first(data, "total_debt", "total_debt_yahoo")),
            total_equity=to_float(data.get("total_equity")),
            total_cash=to_float(data.get("total_cash")),
            operating_cash_flow=to_float(
                first(data, "operating_cash_flow", "operating_cash_flow_yahoo")
            ),
            free_cash_flow=to_float(
                first(data, "free_cash_flow", "free_cash_flow_yahoo")
            ),
            dividend_yield=to_float(data.get("dividend_yield")),
            raw=data,
        )

    async def get_financial_statements(
        self, symbol: str, period: Optional[str] = None
    ) -> FinancialStatements:
        # Yahoo client expects "quarterly" to select quarterly statements
        yahoo_period = "quarterly" if period in ("quarterly", "quarter") else None
        data = self._require(
            await self._call(
                "financial_statements",
                self._client.fetch_financial_statements,
                symbol,
                yahoo_period,
            ),
            self.name,
            "financial_statements",
        )
        income = data.get("income_statement") or []
        balance = data.get("balance_sheet") or []
        cash = data.get("cash_flow") or []
        if not income and not balance and not cash:
            raise DataNotFound(self.name, "financial_statements")

        as_of = None
        for rows in (income, balance, cash):
            if rows and isinstance(rows[0], dict):
                as_of = to_date(first(rows[0], "date", "asOfDate", "index"))
                if as_of:
                    break

        return FinancialStatements(
            provider=self.name,
            symbol=symbol,
            periodicity=data.get("periodicity") or period or "annual",
            income=income,
            balance_sheet=balance,
            cash_flow=cash,
            as_of=as_of,
        )

    async def get_news(self, symbol: str, limit: int = 10) -> List[NewsItem]:
        rows = self._require(
            await self._call("news", self._client.fetch_news, symbol, limit),
            self.name,
            "news",
        )
        items = [
            NewsItem(
                provider=self.name,
                symbol=symbol,
                title=r.get("title") or "",
                url=first(r, "link", "url"),
                publisher=r.get("publisher"),
                published_at=to_datetime(first(r, "published", "published_date")),
                summary=r.get("summary"),
                related_symbols=[symbol],
            )
            for r in rows
            if isinstance(r, dict)
        ]
        return self._require(items, self.name, "news")

    async def get_earnings(self, symbol: str) -> List[EarningsEvent]:
        rows = self._require(
            await self._call("earnings", self._client.fetch_earnings, symbol),
            self.name,
            "earnings",
        )
        events = [
            EarningsEvent(
                provider=self.name,
                symbol=symbol,
                date=to_date(first(r, "earnings_date", "date")),
                eps_estimate=to_float(r.get("eps_estimate")),
                revenue_estimate=to_float(r.get("revenue_estimate")),
                fiscal_period=(
                    f"Q{r['quarter']}" if r.get("quarter") is not None else None
                ),
                fiscal_year=(
                    int(r["year"])
                    if isinstance(r.get("year"), (int, float))
                    else None
                ),
            )
            for r in rows
            if isinstance(r, dict)
        ]
        return self._require(events, self.name, "earnings")
