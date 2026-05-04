from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from app.data_management.refresh_strategy import DataType
from app.database import db


class TableName(str, Enum):
    FUNDAMENTALS_SNAPSHOTS = "fundamentals_snapshots"
    RAW_MARKET_DATA_DAILY = "raw_market_data_daily"
    RAW_MARKET_DATA_INTRADAY = "raw_market_data_intraday"
    INDICATORS_DAILY = "indicators_daily"
    STOCK_NEWS = "stock_news"
    EARNINGS_DATA = "earnings_data"
    INCOME_STATEMENTS = "income_statements"
    BALANCE_SHEETS = "balance_sheets"
    CASH_FLOW_STATEMENTS = "cash_flow_statements"
    FINANCIAL_RATIOS = "financial_ratios"
    SHORT_INTEREST = "short_interest"
    SHORT_VOLUME = "short_volume"
    SHARE_FLOAT = "share_float"
    RISK_FACTORS = "risk_factors"


@dataclass(frozen=True)
class DataTypeTableSpec:
    data_type: DataType
    table: TableName
    symbol_columns: Sequence[str]
    date_columns: Sequence[str]


DATA_TYPE_TABLE_MAP: dict[DataType, DataTypeTableSpec] = {
    DataType.FUNDAMENTALS: DataTypeTableSpec(
        data_type=DataType.FUNDAMENTALS,
        table=TableName.FUNDAMENTALS_SNAPSHOTS,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("as_of_date",),
    ),
    DataType.PRICE_HISTORICAL: DataTypeTableSpec(
        data_type=DataType.PRICE_HISTORICAL,
        table=TableName.RAW_MARKET_DATA_DAILY,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("trade_date", "date"),
    ),
    DataType.PRICE_INTRADAY_5M: DataTypeTableSpec(
        data_type=DataType.PRICE_INTRADAY_5M,
        table=TableName.RAW_MARKET_DATA_INTRADAY,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("ts",),
    ),
    DataType.INDICATORS: DataTypeTableSpec(
        data_type=DataType.INDICATORS,
        table=TableName.INDICATORS_DAILY,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("trade_date", "date"),
    ),
    DataType.NEWS: DataTypeTableSpec(
        data_type=DataType.NEWS,
        table=TableName.STOCK_NEWS,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("published_at", "published_date", "created_at"),
    ),
    DataType.EARNINGS: DataTypeTableSpec(
        data_type=DataType.EARNINGS,
        table=TableName.EARNINGS_DATA,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("earnings_date",),
    ),
    DataType.INCOME_STATEMENTS: DataTypeTableSpec(
        data_type=DataType.INCOME_STATEMENTS,
        table=TableName.INCOME_STATEMENTS,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("period_end",),
    ),
    DataType.BALANCE_SHEETS: DataTypeTableSpec(
        data_type=DataType.BALANCE_SHEETS,
        table=TableName.BALANCE_SHEETS,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("period_end",),
    ),
    DataType.CASH_FLOW_STATEMENTS: DataTypeTableSpec(
        data_type=DataType.CASH_FLOW_STATEMENTS,
        table=TableName.CASH_FLOW_STATEMENTS,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("period_end",),
    ),
    DataType.FINANCIAL_RATIOS: DataTypeTableSpec(
        data_type=DataType.FINANCIAL_RATIOS,
        table=TableName.FINANCIAL_RATIOS,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("period_end",),
    ),
    DataType.SHORT_INTEREST: DataTypeTableSpec(
        data_type=DataType.SHORT_INTEREST,
        table=TableName.SHORT_INTEREST,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("settlement_date",),
    ),
    DataType.SHORT_VOLUME: DataTypeTableSpec(
        data_type=DataType.SHORT_VOLUME,
        table=TableName.SHORT_VOLUME,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("date",),
    ),
    DataType.SHARE_FLOAT: DataTypeTableSpec(
        data_type=DataType.SHARE_FLOAT,
        table=TableName.SHARE_FLOAT,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("date",),
    ),
    DataType.RISK_FACTORS: DataTypeTableSpec(
        data_type=DataType.RISK_FACTORS,
        table=TableName.RISK_FACTORS,
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("filing_date", "period_end"),
    ),
    # Grading and analyst data types
    DataType.STOCK_GRADES: DataTypeTableSpec(
        data_type=DataType.STOCK_GRADES,
        table="stock_grades",
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("grade_date", "created_at", "published_at"),
    ),
    DataType.ANALYST_RATINGS: DataTypeTableSpec(
        data_type=DataType.ANALYST_RATINGS,
        table="analyst_ratings",
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("rating_date", "created_at", "published_at"),
    ),
    DataType.CONSENSUS_DATA: DataTypeTableSpec(
        data_type=DataType.CONSENSUS_DATA,
        table="consensus_data",
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("consensus_date", "created_at", "published_at"),
    ),
    DataType.PRICE_TARGETS: DataTypeTableSpec(
        data_type=DataType.PRICE_TARGETS,
        table="price_targets",
        symbol_columns=("stock_symbol", "symbol"),
        date_columns=("target_date", "created_at", "published_at"),
    ),
}


def resolve_column(table_name: str, candidates: Sequence[str]) -> str:
    if not candidates:
        raise ValueError("candidates must be non-empty")

    in_list = ",".join([f"'{c}'" for c in candidates])
    rows = db.execute_query(
        f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name = '{table_name}'
          AND column_name IN ({in_list})
        """
    )

    present = {r.get("column_name") for r in rows}
    for c in candidates:
        if c in present:
            return c

    return candidates[0]
