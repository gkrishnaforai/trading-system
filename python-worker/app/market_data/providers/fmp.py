"""
FMP provider adapter — wraps EnhancedFMPClient, normalizes to canonical models.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.observability.logging import get_logger
from app.providers.financial_modeling_prep.client import EnhancedFMPClient

from ..base import MarketDataProvider, first, to_date, to_datetime, to_float, to_int
from ..errors import UnsupportedCapability
from ..fundamental_derivation import derive_statement_fields
from ..models import (
    AnalystGrade,
    CompanyProfile,
    EarningsEvent,
    FinancialEstimate,
    FinancialStatements,
    FundamentalsSnapshot,
    NewsItem,
    OHLCVBar,
    PriceTarget,
    Quote,
)

logger = get_logger("market_data_fmp")


def _period_to_start(period: Optional[str]) -> Optional[date]:
    """Convert '1y'/'6mo'/'30d' style periods into a start date."""
    if not period:
        return None
    p = period.strip().lower()
    days = {"1y": 365, "2y": 730, "5y": 1825, "6mo": 180, "3mo": 90, "1mo": 30}.get(p)
    if days is None:
        if p.endswith("d") and p[:-1].isdigit():
            days = int(p[:-1])
        else:
            return None
    return (datetime.now() - timedelta(days=days)).date()


class FMPProvider(MarketDataProvider):
    name = "fmp"

    def __init__(self, client: Optional[EnhancedFMPClient] = None):
        self._client = client or EnhancedFMPClient.from_settings()

    async def get_ohlcv(
        self,
        symbol: str,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        period: Optional[str] = None,
        interval: str = "1d",
    ) -> List[OHLCVBar]:
        if start is None and end is None:
            start = _period_to_start(period or "1y")

        start_s = start.isoformat() if isinstance(start, date) else start
        end_s = end.isoformat() if isinstance(end, date) else end

        if interval in ("1d", "1day", "day"):
            data = self._require(
                await self._call(
                    "ohlcv",
                    self._client.get_historical_prices_full,
                    symbol,
                    start_s,
                    end_s,
                ),
                self.name,
                "ohlcv",
            )
            rows = data.get("historical", []) if isinstance(data, dict) else data
        elif interval in ("5m", "5min"):
            rows = self._require(
                await self._call(
                    "ohlcv",
                    self._client.get_intraday_prices_5min,
                    symbol,
                    start_s,
                    end_s,
                ),
                self.name,
                "ohlcv",
            )
        else:
            raise UnsupportedCapability(self.name, "ohlcv")

        bars = [
            OHLCVBar(
                provider=self.name,
                symbol=symbol,
                timestamp=to_datetime(r.get("date") or r.get("datetime")),
                interval=interval,
                open=to_float(r.get("open")),
                high=to_float(r.get("high")),
                low=to_float(r.get("low")),
                close=to_float(r.get("close")),
                adj_close=to_float(first(r, "adjClose", "adj_close")),
                vwap=to_float(r.get("vwap")),
                volume=to_float(r.get("volume")),
            )
            for r in rows
            if isinstance(r, dict)
        ]
        return self._require(bars, self.name, "ohlcv")

    async def get_quote(self, symbol: str) -> Quote:
        data = self._require(
            await self._call("quote", self._client.get_real_time_quote, symbol),
            self.name,
            "quote",
        )
        price = to_float(data.get("price"))
        if price is None:
            from ..errors import DataNotFound

            raise DataNotFound(self.name, "quote", "no price in quote payload")
        return Quote(
            provider=self.name,
            symbol=symbol,
            price=price,
            change=to_float(data.get("change")),
            change_percent=to_float(
                first(data, "changesPercentage", "changePercentage")
            ),
            open=to_float(data.get("open")),
            day_low=to_float(data.get("dayLow")),
            day_high=to_float(data.get("dayHigh")),
            volume=to_float(data.get("volume")),
            market_cap=to_float(first(data, "marketCap", "mktCap")),
            as_of=to_datetime(data.get("timestamp")),
        )

    async def get_profile(self, symbol: str) -> CompanyProfile:
        data = self._require(
            await self._call("profile", self._client.get_company_profile, symbol),
            self.name,
            "profile",
        )
        return CompanyProfile(
            provider=self.name,
            symbol=symbol,
            name=first(data, "companyName", "name"),
            exchange=first(data, "exchange", "exchangeShortName"),
            currency=data.get("currency"),
            sector=data.get("sector"),
            industry=data.get("industry"),
            country=data.get("country"),
            market_cap=to_float(first(data, "mktCap", "marketCap")),
            beta=to_float(data.get("beta")),
            description=data.get("description"),
            website=data.get("website"),
        )

    async def get_fundamentals(self, symbol: str) -> FundamentalsSnapshot:
        profile = await self._call(
            "fundamentals", self._client.get_company_profile, symbol
        )
        metrics = (
            await self._call("fundamentals", self._client.get_key_metrics_ttm, symbol)
            or []
        )
        ratios = (
            await self._call(
                "fundamentals", self._client.get_financial_ratios_ttm, symbol
            )
            or []
        )

        if not profile and not metrics and not ratios:
            from ..errors import DataNotFound

            raise DataNotFound(self.name, "fundamentals")

        m: Dict[str, Any] = metrics[0] if metrics else {}
        r: Dict[str, Any] = ratios[0] if ratios else {}
        p: Dict[str, Any] = profile or {}
        statement_fields: Dict[str, Any] = {}
        statement_payload: Dict[str, Any] = {}
        try:
            income, balance, cash = await asyncio.gather(
                self._call("financial_statements", self._client.get_income_statement, symbol, "annual"),
                self._call("financial_statements", self._client.get_balance_sheet_statement, symbol, "annual"),
                self._call("financial_statements", self._client.get_cash_flow_statement, symbol, "annual"),
            )
            income = income or []
            balance = balance or []
            cash = cash or []
            statement_fields = derive_statement_fields(income, cash)
            statement_as_of = to_date(first(income[0], "date", "fiscalDateEnding", "fiscal_date_fiscal_year_end")) if income else None
            statement_payload = {"income": income, "balance_sheet": balance, "cash_flow": cash, "as_of": statement_as_of.isoformat() if statement_as_of else None}
        except Exception as exc:
            logger.info("FMP statement fallback unavailable for %s: %s", symbol, exc)

        return FundamentalsSnapshot(
            provider=self.name,
            symbol=symbol,
            market_cap=to_float(first(p, "mktCap", "marketCap") or first(m, "marketCapTTM")),
            pe_ratio=to_float(first(m, "peRatioTTM", "peRatio") or first(r, "priceEarningsRatioTTM")),
            forward_pe=to_float(first(m, "forwardPERatioTTM", "forwardPE")),
            pb_ratio=to_float(first(r, "priceToBookRatioTTM", "pbRatioTTM") or first(m, "pbRatioTTM")),
            price_to_sales=to_float(first(r, "priceToSalesRatioTTM") or first(m, "priceToSalesRatioTTM")),
            peg_ratio=to_float(first(r, "priceEarningsToGrowthRatioTTM", "pegRatioTTM")),
            eps=to_float(first(m, "netIncomePerShareTTM", "epsTTM") or first(r, "epsTTM") or statement_fields.get("eps")),
            profit_margin=to_float(first(r, "netProfitMarginTTM", "netIncomePerEBTTM")),
            gross_margin=to_float(first(r, "grossProfitMarginTTM")),
            operating_margin=to_float(first(r, "operatingProfitMarginTTM")),
            roe=to_float(first(r, "returnOnEquityTTM") or first(m, "roeTTM", "returnOnEquityTTM")),
            roa=to_float(first(r, "returnOnAssetsTTM")),
            revenue_growth=to_float(first(m, "revenueGrowthTTM") or statement_fields.get("revenue_growth")),
            earnings_growth=to_float(statement_fields.get("earnings_growth")),
            current_ratio=to_float(first(r, "currentRatioTTM") or first(m, "currentRatioTTM")),
            quick_ratio=to_float(first(r, "quickRatioTTM")),
            debt_to_equity=to_float(first(r, "debtEquityRatioTTM") or first(m, "debtToEquityTTM")),
            revenue=to_float(statement_fields.get("revenue")) or to_float(first(m, "revenuePerShareTTM")),
            net_income=to_float(statement_fields.get("net_income")),
            operating_cash_flow=to_float(statement_fields.get("operating_cash_flow")),
            free_cash_flow=to_float(statement_fields.get("free_cash_flow")) or to_float(first(m, "freeCashFlowPerShareTTM")),
            dividend_yield=to_float(first(r, "dividendYielTTM", "dividendYieldTTM") or first(m, "dividendYieldTTM")),
            as_of=to_date(statement_payload.get("as_of")) if statement_payload.get("as_of") else None,
            coverage={
                "growth": float(statement_fields.get("coverage", 0.0)),
                "statement_periods": float(statement_fields.get("statement_periods", 0)) / 2,
            },
            missing_fields=list(statement_fields.get("missing_fields", [])),
            raw={"profile": p, "key_metrics_ttm": m, "ratios_ttm": r, "statements": statement_payload, "derivation": statement_fields.get("derivation")},
        )

    async def get_financial_statements(
        self, symbol: str, period: Optional[str] = None
    ) -> FinancialStatements:
        income = await self._call(
            "financial_statements", self._client.get_income_statement, symbol, period
        )
        balance = await self._call(
            "financial_statements",
            self._client.get_balance_sheet_statement,
            symbol,
            period,
        )
        cash = await self._call(
            "financial_statements",
            self._client.get_cash_flow_statement,
            symbol,
            period,
        )

        income = income or []
        balance = balance or []
        cash = cash or []
        if not income and not balance and not cash:
            from ..errors import DataNotFound

            raise DataNotFound(self.name, "financial_statements")

        as_of = None
        for rows in (income, balance, cash):
            if rows and isinstance(rows[0], dict):
                as_of = to_date(
                    first(rows[0], "date", "fiscalDateEnding", "fiscal_date_ending")
                )
                if as_of:
                    break

        return FinancialStatements(
            provider=self.name,
            symbol=symbol,
            periodicity=period or "annual",
            income=income,
            balance_sheet=balance,
            cash_flow=cash,
            as_of=as_of,
        )

    async def get_financial_estimates(self, symbol: str, period: str = "annual", limit: int = 10) -> List[FinancialEstimate]:
        rows = await self._call("financial_estimates", self._client.get_financial_estimates, symbol, period, 0, limit) or []
        estimates = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            forecast_date = to_date(row.get("date"))
            estimates.append(FinancialEstimate(
                provider=self.name,
                symbol=symbol.upper(),
                forecast_date=forecast_date,
                fiscal_year=forecast_date.year if forecast_date else None,
                fiscal_period=period,
                eps_avg=to_float(row.get("epsAvg")),
                eps_low=to_float(row.get("epsLow")),
                eps_high=to_float(row.get("epsHigh")),
                revenue_avg=to_float(row.get("revenueAvg")),
                revenue_low=to_float(row.get("revenueLow")),
                revenue_high=to_float(row.get("revenueHigh")),
                analyst_count_eps=to_int(row.get("numAnalystsEps")),
                analyst_count_revenue=to_int(row.get("numAnalystsRevenue")),
            ))
        return self._require(estimates, self.name, "financial_estimates")

    async def get_news(self, symbol: str, limit: int = 10) -> List[NewsItem]:
        rows = self._require(
            await self._call("news", self._client.search_stock_news, symbol),
            self.name,
            "news",
        )
        items = [
            NewsItem(
                provider=self.name,
                symbol=symbol,
                title=r.get("title") or "",
                url=r.get("url"),
                publisher=r.get("site"),
                published_at=to_datetime(r.get("publishedDate")),
                summary=r.get("text"),
                related_symbols=[symbol],
            )
            for r in rows[:limit]
            if isinstance(r, dict)
        ]
        return self._require(items, self.name, "news")

    async def get_earnings(self, symbol: str) -> List[EarningsEvent]:
        rows = self._require(
            await self._call("earnings", self._client.get_earnings_report, symbol),
            self.name,
            "earnings",
        )
        events = [
            EarningsEvent(
                provider=self.name,
                symbol=symbol,
                date=to_date(first(r, "date", "fiscalDateEnding")),
                eps_actual=to_float(first(r, "epsActual", "eps")),
                eps_estimate=to_float(first(r, "epsEstimated", "epsEstimate")),
                revenue_actual=to_float(first(r, "revenueActual", "revenue")),
                revenue_estimate=to_float(
                    first(r, "revenueEstimated", "revenueEstimate")
                ),
                fiscal_period=r.get("period"),
                fiscal_year=to_int(r.get("fiscalYear") or r.get("year")),
            )
            for r in rows
            if isinstance(r, dict)
        ]
        return self._require(events, self.name, "earnings")

    async def get_analyst_grades(self, symbol: str) -> List[AnalystGrade]:
        rows = self._require(
            await self._call(
                "analyst_grades", self._client.get_stock_grades, symbol
            ),
            self.name,
            "analyst_grades",
        )
        grades = [
            AnalystGrade(
                provider=self.name,
                symbol=symbol,
                date=to_date(r.get("date")),
                grading_company=first(r, "gradingCompany", "grading_company"),
                previous_grade=first(r, "previousGrade", "previous_grade"),
                new_grade=first(r, "newGrade", "new_grade"),
                action=r.get("action"),
            )
            for r in rows
            if isinstance(r, dict)
        ]
        return self._require(grades, self.name, "analyst_grades")

    async def get_price_target(self, symbol: str) -> PriceTarget:
        data = self._require(
            await self._call(
                "price_target", self._client.get_price_target_consensus, symbol
            ),
            self.name,
            "price_target",
        )
        row = data[0] if isinstance(data, list) and data else data
        if not isinstance(row, dict):
            from ..errors import DataNotFound

            raise DataNotFound(self.name, "price_target")
        return PriceTarget(
            provider=self.name,
            symbol=symbol,
            target_mean=to_float(first(row, "targetMean", "targetConsensus")),
            target_high=to_float(row.get("targetHigh")),
            target_low=to_float(row.get("targetLow")),
            target_median=to_float(first(row, "targetMedian", "medianTarget")),
            analyst_count=to_int(first(row, "numberOfAnalysts", "analystCount")),
            last_updated=to_datetime(first(row, "lastUpdated", "updatedDate")),
        )
