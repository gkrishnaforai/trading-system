import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from app.config import settings
from app.exceptions import DataSourceError
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

try:
    from massive import RESTClient

    MASSIVE_AVAILABLE = True
except ImportError as e:
    MASSIVE_AVAILABLE = False
    logger.warning(f"massive library not installed. Error: {e}. Install with: pip install -U massive")


@dataclass(frozen=True)
class MassiveClientConfig:
    api_key: str
    rate_limit_calls: int = 2
    rate_limit_window: int = 60


class MassiveClient:
    def __init__(self, config: MassiveClientConfig):
        if not MASSIVE_AVAILABLE:
            raise ImportError("Massive library not available")

        if not config.api_key:
            raise ValueError("Massive API key is required")

        self._config = config
        self._client = RESTClient(config.api_key)
        self._rate_limiter = RateLimiter(config.rate_limit_calls, config.rate_limit_window)

        logger.info(
            f"Initialized Massive.com client with conservative rate limit: "
            f"{config.rate_limit_calls} calls per {config.rate_limit_window}s"
        )

    @classmethod
    def from_settings(cls, api_key: Optional[str] = None) -> "MassiveClient":
        resolved_key = api_key or settings.massive_api_key
        config = MassiveClientConfig(
            api_key=resolved_key,
            rate_limit_calls=getattr(settings, "massive_rate_limit_calls", 2),
            rate_limit_window=getattr(settings, "massive_rate_limit_window", 60),
        )
        return cls(config)

    def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
        try:
            self._rate_limiter.acquire()

            multiplier = kwargs.get("multiplier", 1)
            timespan = kwargs.get("timespan", "day")
            from_date = kwargs.get("from_date", "2024-01-01")
            to_date = kwargs.get("to_date", datetime.now().strftime("%Y-%m-%d"))

            # massive SDK versions differ in parameter names for date bounds.
            # Try the modern signature first, then fall back to older aliases.
            try:
                aggs = self._client.list_aggs(
                    ticker=symbol,
                    multiplier=multiplier,
                    timespan=timespan,
                    from_date=from_date,
                    to_date=to_date,
                )
            except TypeError:
                try:
                    aggs = self._client.list_aggs(
                        ticker=symbol,
                        multiplier=multiplier,
                        timespan=timespan,
                        from_=from_date,
                        to=to_date,
                    )
                except TypeError:
                    aggs = self._client.list_aggs(
                        ticker=symbol,
                        multiplier=multiplier,
                        timespan=timespan,
                        start=from_date,
                        end=to_date,
                    )

            data_list: List[Dict[str, Any]] = []
            for agg in aggs:
                data_list.append(
                    {
                        "date": pd.to_datetime(agg.timestamp, unit="ms"),
                        "open": agg.open,
                        "high": agg.high,
                        "low": agg.low,
                        "close": agg.close,
                        "volume": agg.volume,
                        "symbol": symbol,
                    }
                )

            df = pd.DataFrame(data_list)
            if not df.empty:
                df = df.sort_values("date")
                df.reset_index(drop=True, inplace=True)

            logger.info(f"✅ Fetched {len(df)} rows of price data for {symbol} from Massive.com")
            return df

        except Exception as e:
            error_str = str(e).lower()
            if any(
                phrase in error_str
                for phrase in [
                    "not authorized",
                    "not entitled",
                    "upgrade your plan",
                    "pricing",
                ]
            ):
                logger.warning(f"Massive.com market data requires paid plan for {symbol}")
                return pd.DataFrame()

            logger.error(f"Error fetching price data for {symbol} from Massive.com: {e}")
            raise DataSourceError(f"Failed to fetch price data from Massive.com: {e}") from e

    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            trade = self._client.get_last_trade(ticker=symbol.upper())
            if trade:
                return {
                    "price": float(trade.price),
                    "volume": int(trade.size) if hasattr(trade, 'size') and trade.size else None,
                    "source": "massive"
                }
            return None
        except Exception as e:
            error_str = str(e).lower()
            if any(
                phrase in error_str
                for phrase in [
                    "not authorized",
                    "not entitled",
                    "upgrade your plan",
                    "pricing",
                ]
            ):
                logger.warning(f"Massive.com market data requires paid plan for {symbol}")
                return None

            logger.error(f"Error fetching current price for {symbol} from Massive.com: {e}")
            return None

    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        try:
            details = self._client.get_ticker_details(ticker=symbol.upper())

            if not details:
                return {}

            address = details.address or {}

            return {
                "symbol": details.ticker or symbol,
                "name": details.name,
                "description": details.description,
                "sector": getattr(details, "sector", None),
                "industry": getattr(details, "industry", None),
                "market_cap": details.market_cap,
                "currency": details.currency_name,
                "country": details.locale.upper() if details.locale else None,
                "exchange": details.primary_exchange,
                "market": details.market,
                "type": "Equity",
                "active": details.active,
                "employees": getattr(details, "total_employees", None),
                "phone": details.phone_number,
                "website": details.homepage_url,
                "address": (
                    f"{address.address1 or ''}, {address.city or ''}, "
                    f"{address.state or ''} {address.postal_code or ''}".strip(", ")
                    if address
                    else None
                ),
                "source": "massive",
            }

        except Exception as e:
            logger.error(f"Error fetching symbol details for {symbol} from Massive.com: {e}")
            return {}

    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            from massive.rest.models import TickerNews
            import time

            self._rate_limiter.acquire()
            time.sleep(1)

            news_items: List[Dict[str, Any]] = []
            for article in self._client.list_ticker_news(
                ticker=symbol,
                order="asc",
                limit=str(limit),
                sort="published_utc",
            ):
                if isinstance(article, TickerNews):
                    published_date = None
                    if hasattr(article, "published_utc"):
                        try:
                            published_date = pd.to_datetime(article.published_utc).to_pydatetime()
                        except Exception:
                            published_date = None

                    news_items.append(
                        {
                            "title": getattr(article, "title", ""),
                            "publisher": (
                                getattr(article, "publisher", {}).name
                                if hasattr(article, "publisher") and hasattr(article.publisher, "name")
                                else ""
                            ),
                            "link": getattr(article, "article_url", ""),
                            "published_date": published_date,
                            "published_utc": getattr(article, "published_utc", ""),
                            "related_symbols": getattr(article, "tickers", []),
                        }
                    )

            logger.info(f"✅ Fetched {len(news_items)} news articles for {symbol} from Massive.com")
            return news_items

        except Exception as e:
            logger.error(f"Error fetching news for {symbol} from Massive.com: {e}")
            return []

    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        try:
            if not self._config.api_key:
                return []

            earnings_data: List[Dict[str, Any]] = []
            for statement in self._client.list_financials_income_statements(
                tickers=symbol.upper(),
                limit=20,
                sort="period_end",
            ):
                earnings_data.append(
                    {
                        "period_end": getattr(statement, "period_end", None),
                        "fiscal_period": getattr(statement, "fiscal_period", None),
                        "fiscal_year": getattr(statement, "fiscal_year", None),
                        "net_income_per_share": getattr(statement, "net_income_per_share_basic", None),
                        "net_income": getattr(statement, "net_income", None),
                        "revenues": getattr(statement, "revenues", None),
                        "total_revenue": getattr(statement, "total_revenue", None),
                        "earnings_per_share": getattr(statement, "earnings_per_share_basic", None),
                        "source": "massive",
                    }
                )

            logger.info(
                f"✅ Fetched {len(earnings_data)} earnings records for {symbol} from Massive.com"
            )
            return earnings_data

        except Exception as e:
            logger.error(f"Error fetching earnings for {symbol} from Massive.com: {e}")
            return []

    def fetch_technical_indicators(self, symbol: str, days: int = 90) -> Dict[str, Any]:
        try:
            indicators: Dict[str, Any] = {}

            try:
                logger.info(f"📊 Fetching RSI for {symbol}...")
                if hasattr(self._client, "get_rsi"):
                    rsi_data = self._client.get_rsi(
                        ticker=symbol,
                        timespan="day",
                        adjusted="true",
                        window="14",
                        series_type="close",
                        order="desc",
                        limit=str(days),
                    )

                    rsi_values = []
                    if hasattr(rsi_data, "results") and hasattr(rsi_data.results, "values"):
                        rsi_values = rsi_data.results.values
                    elif hasattr(rsi_data, "values"):
                        rsi_values = rsi_data.values
                    elif hasattr(rsi_data, "__iter__") and not isinstance(rsi_data, str):
                        rsi_values = list(rsi_data)

                    indicators["RSI"] = []
                    for item in rsi_values:
                        try:
                            if hasattr(item, "timestamp") and hasattr(item, "value"):
                                indicators["RSI"].append(
                                    {
                                        "date": datetime.fromtimestamp(item.timestamp / 1000).date(),
                                        "value": float(item.value),
                                        "period": 14,
                                    }
                                )
                            elif isinstance(item, dict):
                                indicators["RSI"].append(
                                    {
                                        "date": datetime.fromtimestamp(item["timestamp"] / 1000).date(),
                                        "value": float(item.get("value", 0)),
                                        "period": 14,
                                    }
                                )
                        except Exception as e:
                            logger.error(f"Error processing RSI item {item}: {e}")

                    logger.info(f"✅ Fetched {len(indicators['RSI'])} RSI values for {symbol}")
                else:
                    logger.warning("RSI method not available in Massive client")
            except Exception as e:
                logger.error(f"Error fetching RSI: {type(e).__name__}: {str(e)}")

            import time

            logger.info("⏳ Waiting 2 seconds to avoid rate limiting...")
            time.sleep(2)

            try:
                logger.info(f"📊 Fetching MACD for {symbol}...")
                macd_data = self._client.get_macd(
                    ticker=symbol,
                    timespan="day",
                    adjusted="true",
                    short_window="12",
                    long_window="26",
                    signal_window="9",
                    series_type="close",
                    order="desc",
                    limit=str(days),
                )

                macd_values = []
                if hasattr(macd_data, "results") and hasattr(macd_data.results, "values"):
                    macd_values = macd_data.results.values
                elif hasattr(macd_data, "values"):
                    macd_values = macd_data.values
                elif hasattr(macd_data, "__iter__") and not isinstance(macd_data, str):
                    macd_values = list(macd_data)

                indicators["MACD"] = []
                for item in macd_values:
                    try:
                        if hasattr(item, "timestamp") and hasattr(item, "value"):
                            indicators["MACD"].append(
                                {
                                    "date": datetime.fromtimestamp(item.timestamp / 1000).date(),
                                    "value": float(item.value),
                                    "period": "12_26_9",
                                }
                            )
                        elif isinstance(item, dict):
                            indicators["MACD"].append(
                                {
                                    "date": datetime.fromtimestamp(item["timestamp"] / 1000).date(),
                                    "value": float(item.get("value", 0)),
                                    "period": "12_26_9",
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error processing MACD item {item}: {e}")

                logger.info(f"✅ Fetched {len(indicators['MACD'])} MACD values for {symbol}")
            except Exception as e:
                logger.error(f"Error fetching MACD: {type(e).__name__}: {str(e)}")

            logger.info("⏳ Waiting 2 seconds to avoid rate limiting...")
            time.sleep(2)

            try:
                logger.info(f"📊 Fetching SMA for {symbol}...")
                sma_data = self._client.get_sma(
                    ticker=symbol,
                    timespan="day",
                    adjusted="true",
                    window="50",
                    series_type="close",
                    order="desc",
                    limit=str(days),
                )

                sma_values = []
                if hasattr(sma_data, "results") and hasattr(sma_data.results, "values"):
                    sma_values = sma_data.results.values
                elif hasattr(sma_data, "values"):
                    sma_values = sma_data.values
                elif hasattr(sma_data, "__iter__") and not isinstance(sma_data, str):
                    sma_values = list(sma_data)

                sma_list = []
                for item in sma_values:
                    try:
                        if hasattr(item, "timestamp") and hasattr(item, "value"):
                            sma_list.append(
                                {
                                    "date": datetime.fromtimestamp(item.timestamp / 1000).date(),
                                    "value": float(item.value),
                                    "period": 50,
                                }
                            )
                        elif isinstance(item, dict):
                            sma_list.append(
                                {
                                    "date": datetime.fromtimestamp(item["timestamp"] / 1000).date(),
                                    "value": float(item["value"]),
                                    "period": 50,
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error processing SMA item {item}: {e}")

                indicators["SMA"] = {"SMA_50": sma_list}
                logger.info(f"✅ Fetched {len(indicators['SMA']['SMA_50'])} SMA values for {symbol}")
            except Exception as e:
                logger.error(f"Error fetching SMA: {type(e).__name__}: {str(e)}")

            logger.info("⏳ Waiting 2 seconds to avoid rate limiting...")
            time.sleep(2)

            try:
                logger.info(f"📊 Fetching EMA for {symbol}...")
                ema_data = self._client.get_ema(
                    ticker=symbol,
                    timespan="day",
                    adjusted="true",
                    window="20",
                    series_type="close",
                    order="desc",
                    limit=str(days),
                )

                ema_values = []
                if hasattr(ema_data, "results") and hasattr(ema_data.results, "values"):
                    ema_values = ema_data.results.values
                elif hasattr(ema_data, "values"):
                    ema_values = ema_data.values
                elif hasattr(ema_data, "__iter__") and not isinstance(ema_data, str):
                    ema_values = list(ema_data)

                ema_list = []
                for item in ema_values:
                    try:
                        if hasattr(item, "timestamp") and hasattr(item, "value"):
                            ema_list.append(
                                {
                                    "date": datetime.fromtimestamp(item.timestamp / 1000).date(),
                                    "value": float(item.value),
                                    "period": 20,
                                }
                            )
                        elif isinstance(item, dict):
                            ema_list.append(
                                {
                                    "date": datetime.fromtimestamp(item["timestamp"] / 1000).date(),
                                    "value": float(item["value"]),
                                    "period": 20,
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error processing EMA item {item}: {e}")

                indicators["EMA"] = {"EMA_20": ema_list}
                logger.info(f"✅ Fetched {len(indicators['EMA']['EMA_20'])} EMA values for {symbol}")
            except Exception as e:
                logger.error(f"Error fetching EMA: {type(e).__name__}: {str(e)}")

            return indicators

        except Exception as e:
            logger.error(
                f"Error fetching technical indicators from Massive: {type(e).__name__}: {str(e)}"
            )
            return {}

    def is_available(self) -> bool:
        try:
            details = self._client.get_ticker_details(ticker="AAPL")
            return details is not None and hasattr(details, "ticker")
        except Exception as e:
            error_str = str(e).lower()
            if any(
                phrase in error_str
                for phrase in [
                    "not authorized",
                    "not entitled",
                    "upgrade your plan",
                    "pricing",
                ]
            ):
                logger.error(f"Massive.com API plan limitation: {str(e)}")
                logger.error("Upgrade your plan at https://polygon.io/pricing")
                return False

            logger.debug(f"Massive.com availability check failed: {e}")
            return False
