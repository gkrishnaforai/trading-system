package models

import "time"

// AI Signal Types
type AISignal struct {
	SignalID    string    `json:"signal_id"`
	StockSymbol string    `json:"stock_symbol"`
	SignalType  string    `json:"signal_type"` // "buy", "sell", "hold", "rebalance", "alert"
	Confidence  float64   `json:"confidence"`  // 0-100
	Reason      string    `json:"reason"`
	Source      string    `json:"source"` // "technical", "fundamental", "sentiment", "ai_model"
	PriceTarget *float64  `json:"price_target,omitempty"`
	TimeHorizon string    `json:"time_horizon"` // "short", "medium", "long"
	CreatedAt   time.Time `json:"created_at"`
	ExpiresAt   time.Time `json:"expires_at"`
	Priority    string    `json:"priority"` // "low", "medium", "high", "critical"
}

// Technical Signal
type TechnicalSignal struct {
	Indicator    string    `json:"indicator"` // "RSI", "MACD", "MovingAverage", etc.
	Signal       string    `json:"signal"`    // "bullish", "bearish", "neutral"
	Strength     float64   `json:"strength"`  // 0-100
	PriceLevel   *float64  `json:"price_level,omitempty"`
	Timestamp    time.Time `json:"timestamp"`
	ChartPattern string    `json:"chart_pattern,omitempty"`
}

// Fundamental Score
type FundamentalScore struct {
	OverallScore         float64   `json:"overall_score"`          // 0-100
	GrowthScore          float64   `json:"growth_score"`           // 0-100
	ProfitabilityScore   float64   `json:"profitability_score"`    // 0-100
	FinancialHealthScore float64   `json:"financial_health_score"` // 0-100
	ValuationScore       float64   `json:"valuation_score"`        // 0-100
	PERatio              *float64  `json:"pe_ratio,omitempty"`
	PBRatio              *float64  `json:"pb_ratio,omitempty"`
	DERatio              *float64  `json:"de_ratio,omitempty"`
	ROE                  *float64  `json:"roe,omitempty"`
	RevenueGrowth        *float64  `json:"revenue_growth,omitempty"`
	EPSGrowth            *float64  `json:"eps_growth,omitempty"`
	LastUpdated          time.Time `json:"last_updated"`
}

// Security Information
type SecurityInfo struct {
	Symbol          string    `json:"symbol"`
	CompanyName     string    `json:"company_name"`
	Sector          string    `json:"sector"`
	Industry        string    `json:"industry"`
	MarketCap       *int64    `json:"market_cap,omitempty"`
	EnterpriseValue *int64    `json:"enterprise_value,omitempty"`
	Country         string    `json:"country"`
	Currency        string    `json:"currency"`
	Exchange        string    `json:"exchange"`
	Description     string    `json:"description"`
	Website         string    `json:"website"`
	Employees       *int      `json:"employees,omitempty"`
	FoundedYear     *int      `json:"founded_year,omitempty"`
	LastUpdated     time.Time `json:"last_updated"`
}

// Portfolio Analytics
type PortfolioAnalytics struct {
	TotalValue           float64             `json:"total_value"`
	TotalCost            float64             `json:"total_cost"`
	TotalReturn          float64             `json:"total_return"`
	TotalReturnPercent   float64             `json:"total_return_percent"`
	DailyChange          float64             `json:"daily_change"`
	DailyChangePercent   float64             `json:"daily_change_percent"`
	AssetAllocation      map[string]float64  `json:"asset_allocation"`      // sector/asset class allocation
	SectorAllocation     map[string]float64  `json:"sector_allocation"`     // sector breakdown
	GeographicAllocation map[string]float64  `json:"geographic_allocation"` // geographic breakdown
	ConcentrationRisk    *ConcentrationRisk  `json:"concentration_risk"`
	DiversificationScore float64             `json:"diversification_score"` // 0-100
	Volatility           float64             `json:"volatility"`            // portfolio volatility
	Beta                 *float64            `json:"beta,omitempty"`        // portfolio beta
	SharpeRatio          *float64            `json:"sharpe_ratio,omitempty"`
	MaxDrawdown          *float64            `json:"max_drawdown,omitempty"`
	WinRate              float64             `json:"win_rate"`     // percentage of profitable positions
	TopHoldings          []TopHolding        `json:"top_holdings"` // top 10 holdings
	PerformanceMetrics   *PerformanceMetrics `json:"performance_metrics"`
	LastUpdated          time.Time           `json:"last_updated"`
}

// Concentration Risk
type ConcentrationRisk struct {
	TopHoldingPercent   float64            `json:"top_holding_percent"`    // largest position % of portfolio
	Top3HoldingsPercent float64            `json:"top_3_holdings_percent"` // top 3 positions % of portfolio
	Top5HoldingsPercent float64            `json:"top_5_holdings_percent"` // top 5 positions % of portfolio
	SectorConcentration map[string]float64 `json:"sector_concentration"`   // sector concentration
	RiskLevel           string             `json:"risk_level"`             // "low", "medium", "high"
}

// Top Holding
type TopHolding struct {
	Symbol             string   `json:"symbol"`
	CompanyName        string   `json:"company_name"`
	Value              float64  `json:"value"`
	PercentOfPortfolio float64  `json:"percent_of_portfolio"`
	UnrealizedPnL      *float64 `json:"unrealized_pnl,omitempty"`
}

// Performance Metrics
type PerformanceMetrics struct {
	OneDay           *float64 `json:"one_day,omitempty"`
	OneWeek          *float64 `json:"one_week,omitempty"`
	OneMonth         *float64 `json:"one_month,omitempty"`
	ThreeMonths      *float64 `json:"three_months,omitempty"`
	SixMonths        *float64 `json:"six_months,omitempty"`
	OneYear          *float64 `json:"one_year,omitempty"`
	ThreeYears       *float64 `json:"three_years,omitempty"`
	FiveYears        *float64 `json:"five_years,omitempty"`
	SinceInception   *float64 `json:"since_inception,omitempty"`
	AnnualizedReturn *float64 `json:"annualized_return,omitempty"`
}

// Risk Metrics
type RiskMetrics struct {
	OverallRiskScore  float64            `json:"overall_risk_score"`      // 0-100
	Volatility        float64            `json:"volatility"`              // annualized volatility
	Beta              *float64           `json:"beta,omitempty"`          // portfolio beta
	ValueAtRisk       *float64           `json:"value_at_risk,omitempty"` // VaR 95%
	ExpectedShortfall *float64           `json:"expected_shortfall,omitempty"`
	MaxDrawdown       *float64           `json:"max_drawdown,omitempty"`
	SharpeRatio       *float64           `json:"sharpe_ratio,omitempty"`
	SortinoRatio      *float64           `json:"sortino_ratio,omitempty"`
	InformationRatio  *float64           `json:"information_ratio,omitempty"`
	RiskDecomposition map[string]float64 `json:"risk_decomposition"` // risk by sector/holding
	StressTestResults *StressTestResults `json:"stress_test_results,omitempty"`
	RiskLevel         string             `json:"risk_level"` // "low", "medium", "high"
	LastUpdated       time.Time          `json:"last_updated"`
}

// Stress Test Results
type StressTestResults struct {
	MarketCrashScenario float64 `json:"market_crash_scenario"` // % loss in -20% market scenario
	InterestRateShock   float64 `json:"interest_rate_shock"`   // % loss in +2% rates scenario
	RecessionScenario   float64 `json:"recession_scenario"`    // % loss in recession scenario
	InflationShock      float64 `json:"inflation_shock"`       // % loss in high inflation scenario
}

// Rebalancing Recommendation
type RebalancingRecommendation struct {
	Recommended        bool                `json:"recommended"`
	Reason             string              `json:"reason"`
	TargetAllocation   map[string]float64  `json:"target_allocation"`
	CurrentAllocation  map[string]float64  `json:"current_allocation"`
	RebalancingActions []RebalancingAction `json:"rebalancing_actions"`
	EstimatedCost      *float64            `json:"estimated_cost,omitempty"`
	TaxImplications    *TaxImplications    `json:"tax_implications,omitempty"`
	Priority           string              `json:"priority"` // "low", "medium", "high"
	GeneratedAt        time.Time           `json:"generated_at"`
}

// Rebalancing Action
type RebalancingAction struct {
	Symbol        string   `json:"symbol"`
	Action        string   `json:"action"` // "buy", "sell"
	Quantity      float64  `json:"quantity"`
	CurrentWeight float64  `json:"current_weight"`
	TargetWeight  float64  `json:"target_weight"`
	EstimatedCost *float64 `json:"estimated_cost,omitempty"`
}

// Tax Implications
type TaxImplications struct {
	EstimatedShortTermGains *float64 `json:"estimated_short_term_gains,omitempty"`
	EstimatedLongTermGains  *float64 `json:"estimated_long_term_gains,omitempty"`
	EstimatedTaxLoss        *float64 `json:"estimated_tax_loss,omitempty"`
	TaxEfficiency           string   `json:"tax_efficiency"` // "high", "medium", "low"
}

// Performance Report
type PerformanceReport struct {
	Period               string               `json:"period"` // "1M", "3M", "6M", "1Y", etc.
	TotalReturn          float64              `json:"total_return"`
	AnnualizedReturn     float64              `json:"annualized_return"`
	Volatility           float64              `json:"volatility"`
	SharpeRatio          *float64             `json:"sharpe_ratio,omitempty"`
	BenchmarkReturn      *float64             `json:"benchmark_return,omitempty"`
	Alpha                *float64             `json:"alpha,omitempty"`
	Beta                 *float64             `json:"beta,omitempty"`
	MaxDrawdown          *float64             `json:"max_drawdown,omitempty"`
	WinningPositions     int                  `json:"winning_positions"`
	LosingPositions      int                  `json:"losing_positions"`
	BestPerformingStock  *PositionPerformance `json:"best_performing_stock,omitempty"`
	WorstPerformingStock *PositionPerformance `json:"worst_performing_stock,omitempty"`
	ContributionAnalysis map[string]float64   `json:"contribution_analysis"` // contribution by holding
	AttributionAnalysis  *AttributionAnalysis `json:"attribution_analysis,omitempty"`
	GeneratedAt          time.Time            `json:"generated_at"`
}

// Position Performance
type PositionPerformance struct {
	Symbol        string  `json:"symbol"`
	Return        float64 `json:"return"`
	ReturnPercent float64 `json:"return_percent"`
	Contribution  float64 `json:"contribution"` // contribution to portfolio return
}

// Attribution Analysis
type AttributionAnalysis struct {
	AssetAllocation   float64 `json:"asset_allocation"`   // contribution from asset allocation
	SectorSelection   float64 `json:"sector_selection"`   // contribution from sector selection
	SecuritySelection float64 `json:"security_selection"` // contribution from security selection
	CurrencyEffect    float64 `json:"currency_effect"`    // contribution from currency movements
	InteractionEffect float64 `json:"interaction_effect"` // interaction effects
	TotalActiveReturn float64 `json:"total_active_return"`
}

// Earnings Alert
type EarningsAlert struct {
	AlertID         string                   `json:"alert_id"`
	Symbol          string                   `json:"symbol"`
	CompanyName     string                   `json:"company_name"`
	EarningsDate    time.Time                `json:"earnings_date"`
	DaysUntil       int                      `json:"days_until"`
	ExpectedEPS     *float64                 `json:"expected_eps,omitempty"`
	PreviousEPS     *float64                 `json:"previous_eps,omitempty"`
	SurpriseHistory *EarningsSurpriseHistory `json:"surprise_history,omitempty"`
	AlertType       string                   `json:"alert_type"` // "upcoming", "premarket", "aftermarket"
	Priority        string                   `json:"priority"`   // "low", "medium", "high"
	WatchlistIDs    []string                 `json:"watchlist_ids"`
	PortfolioIDs    []string                 `json:"portfolio_ids"`
	CreatedAt       time.Time                `json:"created_at"`
}

// Earnings Surprise History
type EarningsSurpriseHistory struct {
	Last4QuartersSurpriseAvg float64 `json:"last_4_quarters_surprise_avg"`
	PositiveSurprises        int     `json:"positive_surprises"`
	NegativeSurprises        int     `json:"negative_surprises"`
	BeatRate                 float64 `json:"beat_rate"` // percentage of beats
}

// Smart Portfolio Request
type SmartPortfolioRequest struct {
	PortfolioName     string                 `json:"portfolio_name"`
	InitialCapital    float64                `json:"initial_capital"`
	RiskTolerance     string                 `json:"risk_tolerance"`     // "conservative", "moderate", "aggressive"
	InvestmentHorizon string                 `json:"investment_horizon"` // "short", "medium", "long"`
	InvestmentGoals   []string               `json:"investment_goals"`   // "growth", "income", "preservation"
	Sectors           []string               `json:"sectors"`            // preferred sectors
	ExcludeSectors    []string               `json:"exclude_sectors"`    // excluded sectors
	GeographicFocus   string                 `json:"geographic_focus"`   // "us", "global", "emerging"
	Strategy          string                 `json:"strategy"`           // "value", "growth", "balanced", "dividend"
	Notes             *string                `json:"notes,omitempty"`
	Preferences       map[string]interface{} `json:"preferences,omitempty"`
}

// Smart Watchlist Request
type SmartWatchlistRequest struct {
	WatchlistName     string                 `json:"watchlist_name"`
	Description       *string                `json:"description,omitempty"`
	Tags              *string                `json:"tags,omitempty"`
	SubscriptionLevel string                 `json:"subscription_level"`
	ScreeningCriteria *ScreeningCriteria     `json:"screening_criteria"`
	MaxSymbols        int                    `json:"max_symbols"`
	Sectors           []string               `json:"sectors,omitempty"`
	MarketCapRange    *MarketCapRange        `json:"market_cap_range,omitempty"`
	ExcludeSectors    []string               `json:"exclude_sectors,omitempty"`
	Preferences       map[string]interface{} `json:"preferences,omitempty"`
}

// Screening Criteria
type ScreeningCriteria struct {
	MarketCapMin        *int64                 `json:"market_cap_min,omitempty"`
	MarketCapMax        *int64                 `json:"market_cap_max,omitempty"`
	PEMin               *float64               `json:"pe_min,omitempty"`
	PEMax               *float64               `json:"pe_max,omitempty"`
	PBMin               *float64               `json:"pb_min,omitempty"`
	PBMax               *float64               `json:"pb_max,omitempty"`
	DividendYieldMin    *float64               `json:"dividend_yield_min,omitempty"`
	DividendYieldMax    *float64               `json:"dividend_yield_max,omitempty"`
	ROEMin              *float64               `json:"roe_min,omitempty"`
	DebtToEquityMax     *float64               `json:"debt_to_equity_max,omitempty"`
	RevenueGrowthMin    *float64               `json:"revenue_growth_min,omitempty"`
	EPSGrowthMin        *float64               `json:"eps_growth_min,omitempty"`
	BetaMin             *float64               `json:"beta_min,omitempty"`
	BetaMax             *float64               `json:"beta_max,omitempty"`
	VolumeMin           *int64                 `json:"volume_min,omitempty"`
	PriceMin            *float64               `json:"price_min,omitempty"`
	PriceMax            *float64               `json:"price_max,omitempty"`
	Sectors             []string               `json:"sectors,omitempty"`
	ExcludeSectors      []string               `json:"exclude_sectors,omitempty"`
	Countries           []string               `json:"countries,omitempty"`
	ExcludeCountries    []string               `json:"exclude_countries,omitempty"`
	TechnicalIndicators map[string]interface{} `json:"technical_indicators,omitempty"`
	FundamentalMetrics  map[string]interface{} `json:"fundamental_metrics,omitempty"`
}

// Market Cap Range
type MarketCapRange struct {
	Min int64 `json:"min"`
	Max int64 `json:"max"`
}

// Enhanced Watchlist Item with AI-powered insights
type EnhancedWatchlistItem struct {
	WatchlistStock
	CurrentPrice     *float64            `json:"current_price,omitempty"`
	DailyChange      *float64            `json:"daily_change,omitempty"`
	DailyChangePct   *float64            `json:"daily_change_percent,omitempty"`
	Volume           *int64              `json:"volume,omitempty"`
	AvgVolume        *int64              `json:"avg_volume,omitempty"`
	Security         *SecurityInfo       `json:"security,omitempty"`
	TechnicalSignals []TechnicalSignal   `json:"technical_signals,omitempty"`
	FundamentalScore *FundamentalScore   `json:"fundamental_score,omitempty"`
	ValuationMetrics *ValuationMetrics   `json:"valuation_metrics,omitempty"`
	NewsSentiment    *SentimentScore     `json:"news_sentiment,omitempty"`
	AnalystRatings   *AnalystConsensus   `json:"analyst_ratings,omitempty"`
	EarningsData     *EarningsSummary    `json:"earnings_data,omitempty"`
	RiskScore        string              `json:"risk_score"`                  // "low", "medium", "high"
	OpportunityScore *float64            `json:"opportunity_score,omitempty"` // 0-100
	WatchReason      *string             `json:"watch_reason,omitempty"`
	AlertConfig      *AlertConfiguration `json:"alert_config,omitempty"`
	LastUpdated      time.Time           `json:"last_updated"`
}

// Screening Results
type ScreeningResults struct {
	TotalSymbols    int                     `json:"total_symbols"`
	MatchedSymbols  int                     `json:"matched_symbols"`
	MatchedItems    []EnhancedWatchlistItem `json:"matched_items"`
	Summary         ScreeningSummary        `json:"summary"`
	AppliedCriteria *ScreeningCriteria      `json:"applied_criteria"`
	GeneratedAt     time.Time               `json:"generated_at"`
}

// Screening Summary
type ScreeningSummary struct {
	AvgMarketCap     *float64       `json:"avg_market_cap,omitempty"`
	AvgPE            *float64       `json:"avg_pe,omitempty"`
	AvgPB            *float64       `json:"avg_pb,omitempty"`
	AvgDividendYield *float64       `json:"avg_dividend_yield,omitempty"`
	SectorBreakdown  map[string]int `json:"sector_breakdown"`
	TopMatches       []string       `json:"top_matches"`
}

// Market Movers Summary
type MarketMoversSummary struct {
	TopGainers []MarketMover `json:"top_gainers"`
	TopLosers  []MarketMover `json:"top_losers"`
	MostActive []MarketMover `json:"most_active"`
	Unusual    []MarketMover `json:"unusual_volume"`
	Updated    time.Time     `json:"updated"`
}

// Market Mover
type MarketMover struct {
	Symbol        string  `json:"symbol"`
	CompanyName   string  `json:"company_name"`
	Price         float64 `json:"price"`
	Change        float64 `json:"change"`
	ChangePercent float64 `json:"change_percent"`
	Volume        int64   `json:"volume"`
	VolumeRatio   float64 `json:"volume_ratio"` // volume / avg volume
	Sector        string  `json:"sector"`
}

// Sector Metrics
type SectorMetrics struct {
	Sector         string  `json:"sector"`
	Performance    float64 `json:"performance"` // sector performance %
	Volume         int64   `json:"volume"`
	MarketCap      int64   `json:"market_cap"`
	StockCount     int     `json:"stock_count"`
	AdvancingCount int     `json:"advancing_count"`
	DecliningCount int     `json:"declining_count"`
	UnchangedCount int     `json:"unchanged_count"`
	HeatmapColor   string  `json:"heatmap_color"` // for visualization
}

// Earnings Calendar Item
type EarningsCalendarItem struct {
	Symbol          string    `json:"symbol"`
	CompanyName     string    `json:"company_name"`
	EarningsDate    time.Time `json:"earnings_date"`
	Time            string    `json:"time"` // "premarket", "aftermarket", "during"
	ExpectedEPS     *float64  `json:"expected_eps,omitempty"`
	ExpectedRevenue *float64  `json:"expected_revenue,omitempty"`
	WatchlistIDs    []string  `json:"watchlist_ids"`
	PortfolioIDs    []string  `json:"portfolio_ids"`
}

// Watchlist Alert
type WatchlistAlert struct {
	AlertID      string     `json:"alert_id"`
	ItemID       string     `json:"item_id"`
	Symbol       string     `json:"symbol"`
	AlertType    string     `json:"alert_type"` // "price", "volume", "technical", "fundamental", "news"
	Condition    string     `json:"condition"`  // "above", "below", "crosses", "volume_spike"
	TriggerValue float64    `json:"trigger_value"`
	CurrentValue *float64   `json:"current_value,omitempty"`
	Message      string     `json:"message"`
	Priority     string     `json:"priority"` // "low", "medium", "high"
	Status       string     `json:"status"`   // "active", "triggered", "dismissed"
	CreatedAt    time.Time  `json:"created_at"`
	TriggeredAt  *time.Time `json:"triggered_at,omitempty"`
	ExpiresAt    *time.Time `json:"expires_at,omitempty"`
}

// Alert Configuration
type AlertConfiguration struct {
	PriceAlerts         []PriceAlert       `json:"price_alerts,omitempty"`
	VolumeAlerts        []VolumeAlert      `json:"volume_alerts,omitempty"`
	TechnicalAlerts     []TechnicalAlert   `json:"technical_alerts,omitempty"`
	FundamentalAlerts   []FundamentalAlert `json:"fundamental_alerts,omitempty"`
	NewsAlerts          []NewsAlert        `json:"news_alerts,omitempty"`
	EarningsAlerts      bool               `json:"earnings_alerts"`
	NotificationMethods []string           `json:"notification_methods"` // "email", "sms", "push", "webhook"
	IsEnabled           bool               `json:"is_enabled"`
}

// Price Alert
type PriceAlert struct {
	Condition string  `json:"condition"` // "above", "below", "crosses_above", "crosses_below"
	Value     float64 `json:"value"`
	IsEnabled bool    `json:"is_enabled"`
}

// Volume Alert
type VolumeAlert struct {
	Condition  string  `json:"condition"` // "above", "spike", "unusual"
	Value      int64   `json:"value"`
	Multiplier float64 `json:"multiplier,omitempty"` // for spike/unusual
	IsEnabled  bool    `json:"is_enabled"`
}

// Technical Alert
type TechnicalAlert struct {
	Indicator  string                 `json:"indicator"` // "RSI", "MACD", "MovingAverage"
	Condition  string                 `json:"condition"`
	Parameters map[string]interface{} `json:"parameters"`
	IsEnabled  bool                   `json:"is_enabled"`
}

// Fundamental Alert
type FundamentalAlert struct {
	Metric    string  `json:"metric"` // "pe_ratio", "dividend_yield", "earnings"
	Condition string  `json:"condition"`
	Value     float64 `json:"value"`
	IsEnabled bool    `json:"is_enabled"`
}

// News Alert
type NewsAlert struct {
	Keywords   []string `json:"keywords"`
	Sentiment  string   `json:"sentiment"`  // "positive", "negative", "any"`
	Importance string   `json:"importance"` // "high", "medium", "any"
	IsEnabled  bool     `json:"is_enabled"`
}

// Valuation Metrics
type ValuationMetrics struct {
	PERatio         *float64  `json:"pe_ratio,omitempty"`
	PBRatio         *float64  `json:"pb_ratio,omitempty"`
	PSRatio         *float64  `json:"ps_ratio,omitempty"`
	EVRevenue       *float64  `json:"ev_revenue,omitempty"`
	EVEBITDA        *float64  `json:"ev_ebitda,omitempty"`
	PriceToBook     *float64  `json:"price_to_book,omitempty"`
	PriceToSales    *float64  `json:"price_to_sales,omitempty"`
	PEGRatio        *float64  `json:"peg_ratio,omitempty"`
	EnterpriseValue *int64    `json:"enterprise_value,omitempty"`
	LastUpdated     time.Time `json:"last_updated"`
}

// Sentiment Score
type SentimentScore struct {
	OverallScore   float64   `json:"overall_score"` // -100 to 100
	NewsScore      float64   `json:"news_score"`    // -100 to 100
	SocialScore    float64   `json:"social_score"`  // -100 to 100
	AnalystScore   float64   `json:"analyst_score"` // -100 to 100
	Sentiment      string    `json:"sentiment"`     // "bullish", "bearish", "neutral"
	Confidence     float64   `json:"confidence"`    // 0-100
	ArticleCount   int       `json:"article_count"`
	SocialMentions int64     `json:"social_mentions"`
	LastUpdated    time.Time `json:"last_updated"`
}

// Analyst Consensus
type AnalystConsensus struct {
	StrongBuy         int       `json:"strong_buy"`
	Buy               int       `json:"buy"`
	Hold              int       `json:"hold"`
	Sell              int       `json:"sell"`
	StrongSell        int       `json:"strong_sell"`
	Consensus         string    `json:"consensus"` // "strong_buy", "buy", "hold", "sell", "strong_sell"`
	PriceTargetLow    *float64  `json:"price_target_low,omitempty"`
	PriceTargetHigh   *float64  `json:"price_target_high,omitempty"`
	PriceTargetMean   *float64  `json:"price_target_mean,omitempty"`
	PriceTargetMedian *float64  `json:"price_target_median,omitempty"`
	AnalystCount      int       `json:"analyst_count"`
	LastUpdated       time.Time `json:"last_updated"`
}

// Earnings Summary
type EarningsSummary struct {
	NextEarningsDate       *time.Time            `json:"next_earnings_date,omitempty"`
	PreviousEarningsDate   *time.Time            `json:"previous_earnings_date,omitempty"`
	ExpectedEPS            *float64              `json:"expected_eps,omitempty"`
	ActualEPS              *float64              `json:"actual_eps,omitempty"`
	EPSSurprise            *float64              `json:"eps_surprise,omitempty"`
	EPSSurprisePercent     *float64              `json:"eps_surprise_percent,omitempty"`
	ExpectedRevenue        *float64              `json:"expected_revenue,omitempty"`
	ActualRevenue          *float64              `json:"actual_revenue,omitempty"`
	RevenueSurprise        *float64              `json:"revenue_surprise,omitempty"`
	RevenueSurprisePercent *float64              `json:"revenue_surprise_percent,omitempty"`
	QuarterlyTrend         []EarningsQuarterData `json:"quarterly_trend"`
	LastUpdated            time.Time             `json:"last_updated"`
}

// Earnings Quarter Data
type EarningsQuarterData struct {
	Quarter         string   `json:"quarter"` // "Q1 2024", etc.
	EPS             *float64 `json:"eps,omitempty"`
	Revenue         *float64 `json:"revenue,omitempty"`
	Surprise        *float64 `json:"surprise,omitempty"`
	SurprisePercent *float64 `json:"surprise_percent,omitempty"`
}

// Enhanced Holding with AI-powered insights
type EnhancedHolding struct {
	PortfolioPosition
	CurrentPrice     *float64          `json:"current_price,omitempty"`
	MarketValue      *float64          `json:"market_value,omitempty"`
	UnrealizedPnL    *float64          `json:"unrealized_pnl,omitempty"`
	UnrealizedPnLPct *float64          `json:"unrealized_pnl_pct,omitempty"`
	DayChange        *float64          `json:"day_change,omitempty"`
	DayChangePct     *float64          `json:"day_change_pct,omitempty"`
	Security         *SecurityInfo     `json:"security,omitempty"`
	TechnicalSignals []TechnicalSignal `json:"technical_signals,omitempty"`
	FundamentalScore *FundamentalScore `json:"fundamental_score,omitempty"`
	RiskScore        string            `json:"risk_score"` // "low", "medium", "high"
	AllocationWeight *float64          `json:"allocation_weight,omitempty"`
	TargetWeight     *float64          `json:"target_weight,omitempty"`
	RebalanceSignal  string            `json:"rebalance_signal"` // "buy", "sell", "hold"
	LastUpdated      time.Time         `json:"last_updated"`
}

// Allocation suggestion for optimization
type AllocationSuggestion struct {
	Symbol     string  `json:"symbol"`
	Shares     float64 `json:"shares"`
	EntryPrice float64 `json:"entry_price"`
	Weight     float64 `json:"weight"`
	Reason     string  `json:"reason"`
}
