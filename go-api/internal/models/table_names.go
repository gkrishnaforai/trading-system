package models

// TableName is a typed name for allowlisted database tables.
// This is intentionally a string type so it can be used directly in SQL builders.
//
// Keep this in sync with python-worker/app/data_management/table_mapping.py (Option A).
//
// NOTE: Do not add non-allowlisted tables here.
// NOTE: This is not an exhaustive list of all DB tables; only those used by preview/market-data endpoints.
//
//go:generate echo "(no codegen)"
type TableName string

const (
	TableFundamentalsSnapshots TableName = "fundamentals_snapshots"
	TableRawMarketDataDaily    TableName = "raw_market_data_daily"
	TableRawMarketDataIntraday TableName = "raw_market_data_intraday"
	TableIndicatorsDaily       TableName = "indicators_daily"
	TableAggregatedIndicators  TableName = "aggregated_indicators"
	TableRawMarketData         TableName = "raw_market_data"
	TableStockNews             TableName = "stock_news"
	TableEarningsData          TableName = "earnings_data"
	TableAnalystRatings        TableName = "analyst_ratings"
	TableAnalystConsensus      TableName = "analyst_consensus"
	TableIncomeStatements      TableName = "income_statements"
	TableBalanceSheets         TableName = "balance_sheets"
	TableCashFlowStatements    TableName = "cash_flow_statements"
	TableFinancialRatios       TableName = "financial_ratios"
	TableShortInterest         TableName = "short_interest"
	TableShortVolume           TableName = "short_volume"
	TableShareFloat            TableName = "share_float"
	TableRiskFactors           TableName = "risk_factors"
	TableEnhancedFundamentals  TableName = "enhanced_fundamentals"
	TableStockGrades           TableName = "stock_grades"
	TableRatingChangeLog       TableName = "rating_change_log"
	TableStockGradeConsensus   TableName = "stock_grade_consensus"
)
