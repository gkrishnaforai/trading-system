package services

import (
	"context"
	"fmt"

	"github.com/trading-system/go-api/internal/models"
	"github.com/trading-system/go-api/internal/repositories"
)

type DataPreviewService struct {
	repo     *repositories.DataPreviewRepository
	registry map[string][]repositories.PreviewQuerySpec
	maxLimit int
	defLimit int
}

func NewDataPreviewService(repo *repositories.DataPreviewRepository) *DataPreviewService {
	s := &DataPreviewService{
		repo:     repo,
		registry: make(map[string][]repositories.PreviewQuerySpec),
		maxLimit: 500,
		defLimit: 50,
	}

	s.registry["fundamentals"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableFundamentalsSnapshots), Columns: []string{"stock_symbol", "as_of_date", "payload", "updated_at"}, SymbolCol: "stock_symbol", OrderBy: "as_of_date DESC"},
		{Table: string(models.TableFundamentalsSnapshots), Columns: []string{"symbol", "as_of_date", "payload", "updated_at"}, SymbolCol: "symbol", OrderBy: "as_of_date DESC"},
	}

	s.registry["price_historical"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableRawMarketDataDaily), Columns: []string{"stock_symbol", "trade_date", "open", "high", "low", "close", "adj_close", "volume", "source", "updated_at"}, SymbolCol: "stock_symbol", OrderBy: "trade_date DESC"},
		{Table: string(models.TableRawMarketDataDaily), Columns: []string{"symbol", "date", "open", "high", "low", "close", "adjusted_close", "volume", "data_source", "created_at"}, SymbolCol: "symbol", OrderBy: "date DESC"},
		{Table: string(models.TableRawMarketData), Columns: []string{"stock_symbol", "date", "open", "high", "low", "close", "volume", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "date DESC"},
	}

	s.registry["price_intraday_5m"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableRawMarketDataIntraday), Columns: []string{"stock_symbol", "ts", "interval", "open", "high", "low", "close", "volume", "source", "updated_at"}, SymbolCol: "stock_symbol", OrderBy: "ts DESC", WhereExpr: "interval = '5m'"},
		{Table: string(models.TableRawMarketDataIntraday), Columns: []string{"symbol", "ts", "interval", "open", "high", "low", "close", "volume", "data_source", "created_at"}, SymbolCol: "symbol", OrderBy: "ts DESC", WhereExpr: "interval = '5m'"},
	}

	s.registry["indicators"] = []repositories.PreviewQuerySpec{
		// Common schema (symbol/date) with narrow-row indicators (one row per indicator_name)
		// Prefer this first: some DBs have wide columns present but NULL, while narrow rows hold the real values.
		{Table: string(models.TableIndicatorsDaily), Columns: []string{"symbol", "date", "indicator_name", "indicator_value", "data_source", "updated_at"}, SymbolCol: "symbol", OrderBy: "date DESC"},

		// Legacy schema (stock_symbol/trade_date)
		{Table: string(models.TableIndicatorsDaily), Columns: []string{"stock_symbol", "trade_date", "sma_50", "sma_200", "ema_20", "rsi_14", "macd", "macd_signal", "macd_hist", "signal", "confidence_score", "updated_at"}, SymbolCol: "stock_symbol", OrderBy: "trade_date DESC"},

		// Common schema (symbol/date) with wide-row indicators
		{Table: string(models.TableIndicatorsDaily), Columns: []string{"symbol", "date", "sma_50", "sma_200", "ema_20", "rsi_14", "macd", "macd_signal", "macd_hist", "atr", "bb_width", "signal", "confidence_score", "updated_at"}, SymbolCol: "symbol", OrderBy: "date DESC"},

		// Transitional schema (symbol/trade_date)
		{Table: string(models.TableIndicatorsDaily), Columns: []string{"symbol", "trade_date", "sma_50", "sma_200", "ema_20", "rsi_14", "macd", "macd_signal", "macd_hist", "signal", "confidence_score", "updated_at"}, SymbolCol: "symbol", OrderBy: "trade_date DESC"},

		// Aggregated indicators table
		{Table: string(models.TableAggregatedIndicators), Columns: []string{"stock_symbol", "date", "sma50", "sma200", "ema20", "rsi", "macd", "macd_signal", "macd_histogram", "signal", "timestamp"}, SymbolCol: "stock_symbol", OrderBy: "date DESC"},
	}

	s.registry["news"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableStockNews), Columns: []string{"stock_symbol", "title", "publisher", "link", "published_at", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "published_at DESC NULLS LAST, created_at DESC"},
		{Table: string(models.TableStockNews), Columns: []string{"stock_symbol", "title", "publisher", "link", "published_date", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "published_date DESC NULLS LAST, created_at DESC"},
	}

	s.registry["earnings"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableEarningsData), Columns: []string{"stock_symbol", "earnings_date", "eps_estimate", "eps_actual", "revenue_estimate", "revenue_actual", "surprise_percentage", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "earnings_date DESC"},
	}

	s.registry["analyst_ratings"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableStockGrades), Columns: []string{}, SymbolCol: "symbol", OrderBy: "grade_date DESC"},
	}

	// "price_targets" is previewed from stock grade consensus in the current schema.
	s.registry["price_targets"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableStockGradeConsensus), Columns: []string{}, SymbolCol: "symbol", OrderBy: "last_updated DESC"},
	}

	s.registry["income_statements"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableIncomeStatements), Columns: []string{"stock_symbol", "period_end", "filing_date", "fiscal_year", "fiscal_quarter", "timeframe", "total_revenue", "gross_profit", "operating_income", "net_income", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "period_end DESC"},
	}

	s.registry["balance_sheets"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableBalanceSheets), Columns: []string{"stock_symbol", "period_end", "filing_date", "fiscal_year", "fiscal_quarter", "timeframe", "total_assets", "total_liabilities", "total_equity", "shares_outstanding", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "period_end DESC"},
	}

	s.registry["cash_flow_statements"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableCashFlowStatements), Columns: []string{"stock_symbol", "period_end", "filing_date", "fiscal_year", "fiscal_quarter", "timeframe", "net_cash_from_operating_activities", "net_cash_from_investing_activities", "net_cash_from_financing_activities", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "period_end DESC"},
	}

	s.registry["financial_ratios"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableFinancialRatios), Columns: []string{"stock_symbol", "period_end", "fiscal_year", "fiscal_quarter", "timeframe", "price_to_earnings", "price_to_book", "current_ratio", "debt_to_equity", "return_on_equity", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "period_end DESC"},
	}

	s.registry["short_interest"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableShortInterest), Columns: []string{"stock_symbol", "settlement_date", "short_interest", "average_volume", "days_to_cover", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "settlement_date DESC"},
	}

	s.registry["short_volume"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableShortVolume), Columns: []string{"stock_symbol", "date", "short_volume", "total_volume", "short_volume_ratio", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "date DESC"},
	}

	s.registry["share_float"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableShareFloat), Columns: []string{"stock_symbol", "date", "shares_outstanding", "float_shares", "restricted_shares", "insider_shares", "institutional_shares", "float_percentage", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "date DESC"},
	}

	s.registry["risk_factors"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableRiskFactors), Columns: []string{"stock_symbol", "filing_date", "period_end", "risk_category", "severity", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "filing_date DESC"},
	}

	s.registry["enhanced_fundamentals"] = []repositories.PreviewQuerySpec{
		{Table: string(models.TableEnhancedFundamentals), Columns: []string{"stock_symbol", "as_of_date", "market_cap", "pe_ratio", "price_to_book", "revenue", "net_income", "roe", "debt_to_equity", "current_ratio", "created_at"}, SymbolCol: "stock_symbol", OrderBy: "as_of_date DESC"},
	}

	return s
}

func (s *DataPreviewService) GetPreview(ctx context.Context, symbol string, dataType string, limit int, offset int, allColumns bool) (*models.DataPreviewResponse, error) {
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}
	if dataType == "" {
		return nil, fmt.Errorf("data_type is required")
	}
	if limit <= 0 {
		limit = s.defLimit
	}
	if limit > s.maxLimit {
		limit = s.maxLimit
	}
	if offset < 0 {
		offset = 0
	}

	candidates, ok := s.registry[dataType]
	if !ok {
		return nil, fmt.Errorf("unsupported data_type: %s", dataType)
	}

	spec, err := s.repo.ResolveSpec(ctx, candidates)
	if err != nil {
		return nil, fmt.Errorf("unsupported data_type in current schema: %s", dataType)
	}

	rows, err := s.repo.Fetch(ctx, spec, symbol, limit, offset, allColumns)
	if err != nil {
		return nil, err
	}

	resp := &models.DataPreviewResponse{
		Symbol:   symbol,
		DataType: dataType,
		Limit:    limit,
		Offset:   offset,
		Count:    len(rows),
		Rows:     rows,
	}
	return resp, nil
}
