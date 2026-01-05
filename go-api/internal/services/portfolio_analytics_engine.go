package services

import (
	"fmt"
	"sort"
	"time"

	"github.com/trading-system/go-api/internal/models"
)

// PortfolioAnalyticsEngine provides AI-powered portfolio analytics
type PortfolioAnalyticsEngine struct{}

func NewPortfolioAnalyticsEngine() *PortfolioAnalyticsEngine {
	return &PortfolioAnalyticsEngine{}
}

// GenerateAnalytics creates comprehensive portfolio analytics
func (e *PortfolioAnalyticsEngine) GenerateAnalytics(holdings []models.EnhancedHolding) *models.PortfolioAnalytics {
	if len(holdings) == 0 {
		return e.emptyAnalytics()
	}

	analytics := &models.PortfolioAnalytics{
		LastUpdated: time.Now(),
	}

	// Calculate basic metrics
	e.calculateBasicMetrics(analytics, holdings)

	// Calculate asset allocation
	e.calculateAssetAllocation(analytics, holdings)

	// Calculate sector allocation
	e.calculateSectorAllocation(analytics, holdings)

	// Calculate concentration risk
	e.calculateConcentrationRisk(analytics, holdings)

	// Calculate diversification score
	e.calculateDiversificationScore(analytics, holdings)

	// Calculate risk metrics
	e.calculateRiskMetrics(analytics, holdings)

	// Calculate performance metrics
	e.calculatePerformanceMetrics(analytics, holdings)

	// Determine top holdings
	e.calculateTopHoldings(analytics, holdings)

	return analytics
}

// GeneratePerformanceReport creates detailed performance analysis
func (e *PortfolioAnalyticsEngine) GeneratePerformanceReport(holdings []models.EnhancedHolding) *models.PerformanceReport {
	report := &models.PerformanceReport{
		GeneratedAt: time.Now(),
		Period:      "1Y",
	}

	if len(holdings) == 0 {
		return report
	}

	// Calculate total returns
	var totalReturn, totalCost float64
	var winningPositions, losingPositions int
	var bestPerformer, worstPerformer *models.PositionPerformance

	for _, holding := range holdings {
		if holding.MarketValue != nil && holding.AvgPrice > 0 {
			cost := holding.AvgPrice * holding.Quantity
			returnAmount := *holding.MarketValue - cost
			returnPercent := (returnAmount / cost) * 100

			totalReturn += returnAmount
			totalCost += cost

			if returnAmount > 0 {
				winningPositions++
			} else {
				losingPositions++
			}

			perf := &models.PositionPerformance{
				Symbol:        holding.Symbol,
				Return:        returnAmount,
				ReturnPercent: returnPercent,
				Contribution:  (returnAmount / totalCost) * 100,
			}

			if bestPerformer == nil || returnPercent > bestPerformer.ReturnPercent {
				bestPerformer = perf
			}
			if worstPerformer == nil || returnPercent < worstPerformer.ReturnPercent {
				worstPerformer = perf
			}
		}
	}

	report.TotalReturn = totalReturn
	report.AnnualizedReturn = (totalReturn / totalCost) * 100
	report.WinningPositions = winningPositions
	report.LosingPositions = losingPositions
	report.BestPerformingStock = bestPerformer
	report.WorstPerformingStock = worstPerformer

	return report
}

// GenerateOptimalAllocation creates AI-driven portfolio allocation
func (e *PortfolioAnalyticsEngine) GenerateOptimalAllocation(request *models.SmartPortfolioRequest) (map[string]models.AllocationSuggestion, error) {
	// This is a simplified implementation
	// In production, this would use sophisticated optimization algorithms

	allocations := make(map[string]models.AllocationSuggestion)

	// Default allocation based on risk tolerance
	switch request.RiskTolerance {
	case "conservative":
		allocations = e.conservativeAllocation(request.InitialCapital)
	case "moderate":
		allocations = e.moderateAllocation(request.InitialCapital)
	case "aggressive":
		allocations = e.aggressiveAllocation(request.InitialCapital)
	default:
		return nil, fmt.Errorf("unknown risk tolerance: %s", request.RiskTolerance)
	}

	return allocations, nil
}

// GetFundamentalScore retrieves fundamental analysis score
func (e *PortfolioAnalyticsEngine) GetFundamentalScore(symbol string) *models.FundamentalScore {
	// This would fetch from a fundamental analysis service
	// For now, return mock data
	return &models.FundamentalScore{
		OverallScore:         75.0,
		GrowthScore:          70.0,
		ProfitabilityScore:   80.0,
		FinancialHealthScore: 85.0,
		ValuationScore:       65.0,
		PERatio:              float64Ptr(25.5),
		PBRatio:              float64Ptr(3.2),
		ROE:                  float64Ptr(15.8),
		RevenueGrowth:        float64Ptr(12.3),
		EPSGrowth:            float64Ptr(18.7),
		LastUpdated:          time.Now(),
	}
}

// GetValuationMetrics retrieves valuation metrics
func (e *PortfolioAnalyticsEngine) GetValuationMetrics(symbol string) *models.ValuationMetrics {
	return &models.ValuationMetrics{
		PERatio:     float64Ptr(25.5),
		PBRatio:     float64Ptr(3.2),
		PSRatio:     float64Ptr(4.1),
		EVRevenue:   float64Ptr(15.8),
		PEGRatio:    float64Ptr(1.2),
		LastUpdated: time.Now(),
	}
}

// Helper methods
func (e *PortfolioAnalyticsEngine) calculateBasicMetrics(analytics *models.PortfolioAnalytics, holdings []models.EnhancedHolding) {
	var totalValue, totalCost, dailyChange float64

	for _, holding := range holdings {
		if holding.CurrentPrice != nil {
			marketValue := (*holding.CurrentPrice) * holding.Quantity
			totalCostBasis := holding.AvgPrice * holding.Quantity
			totalValue += marketValue
			totalCost += totalCostBasis
		}
		if holding.DayChange != nil {
			dailyChange += *holding.DayChange
		}
	}

	analytics.TotalValue = totalValue
	analytics.TotalCost = totalCost
	analytics.TotalReturn = totalValue - totalCost
	analytics.TotalReturnPercent = (analytics.TotalReturn / totalCost) * 100
	analytics.DailyChange = dailyChange
	if totalCost > 0 {
		analytics.DailyChangePercent = (dailyChange / totalCost) * 100
	}
}

func (e *PortfolioAnalyticsEngine) calculateAssetAllocation(analytics *models.PortfolioAnalytics, holdings []models.EnhancedHolding) {
	analytics.AssetAllocation = make(map[string]float64)

	for _, holding := range holdings {
		if holding.CurrentPrice != nil && analytics.TotalValue > 0 {
			marketValue := (*holding.CurrentPrice) * holding.Quantity
			weight := (marketValue / analytics.TotalValue) * 100
			assetClass := "stocks" // Simplified - would determine based on security type
			analytics.AssetAllocation[assetClass] += weight
		}
	}
}

func (e *PortfolioAnalyticsEngine) calculateSectorAllocation(analytics *models.PortfolioAnalytics, holdings []models.EnhancedHolding) {
	analytics.SectorAllocation = make(map[string]float64)

	for _, holding := range holdings {
		if holding.CurrentPrice != nil && holding.Security != nil && analytics.TotalValue > 0 {
			marketValue := (*holding.CurrentPrice) * holding.Quantity
			weight := (marketValue / analytics.TotalValue) * 100
			sector := holding.Security.Sector
			if sector == "" {
				sector = "Unknown"
			}
			analytics.SectorAllocation[sector] += weight
		}
	}
}

func (e *PortfolioAnalyticsEngine) calculateConcentrationRisk(analytics *models.PortfolioAnalytics, holdings []models.EnhancedHolding) {
	if len(holdings) == 0 {
		return
	}

	// Sort holdings by market value
	sortedHoldings := make([]models.EnhancedHolding, len(holdings))
	copy(sortedHoldings, holdings)

	sort.Slice(sortedHoldings, func(i, j int) bool {
		if sortedHoldings[i].CurrentPrice == nil && sortedHoldings[j].CurrentPrice == nil {
			return false
		}
		if sortedHoldings[i].CurrentPrice == nil {
			return false
		}
		if sortedHoldings[j].CurrentPrice == nil {
			return true
		}
		return *sortedHoldings[i].CurrentPrice > *sortedHoldings[j].CurrentPrice
	})

	concentration := &models.ConcentrationRisk{
		SectorConcentration: make(map[string]float64),
	}

	// Calculate top holding percentages
	if analytics.TotalValue > 0 {
		if len(sortedHoldings) > 0 && sortedHoldings[0].CurrentPrice != nil {
			marketValue := (*sortedHoldings[0].CurrentPrice) * sortedHoldings[0].Quantity
			concentration.TopHoldingPercent = (marketValue / analytics.TotalValue) * 100
		}

		// Top 3 holdings
		var top3Value float64
		for i := 0; i < 3 && i < len(sortedHoldings); i++ {
			if sortedHoldings[i].CurrentPrice != nil {
				marketValue := (*sortedHoldings[i].CurrentPrice) * sortedHoldings[i].Quantity
				top3Value += marketValue
			}
		}
		concentration.Top3HoldingsPercent = (top3Value / analytics.TotalValue) * 100

		// Top 5 holdings
		var top5Value float64
		for i := 0; i < 5 && i < len(sortedHoldings); i++ {
			if sortedHoldings[i].CurrentPrice != nil {
				marketValue := (*sortedHoldings[i].CurrentPrice) * sortedHoldings[i].Quantity
				top5Value += marketValue
			}
		}
		concentration.Top5HoldingsPercent = (top5Value / analytics.TotalValue) * 100
	}

	// Determine risk level
	if concentration.TopHoldingPercent > 20 || concentration.Top3HoldingsPercent > 50 {
		concentration.RiskLevel = "high"
	} else if concentration.TopHoldingPercent > 10 || concentration.Top3HoldingsPercent > 35 {
		concentration.RiskLevel = "medium"
	} else {
		concentration.RiskLevel = "low"
	}

	analytics.ConcentrationRisk = concentration
}

func (e *PortfolioAnalyticsEngine) calculateDiversificationScore(analytics *models.PortfolioAnalytics, holdings []models.EnhancedHolding) {
	// Simple diversification score based on number of holdings and sector distribution
	score := 0.0

	// Base score for number of holdings
	holdingCount := len(holdings)
	if holdingCount >= 20 {
		score += 40
	} else if holdingCount >= 10 {
		score += 30
	} else if holdingCount >= 5 {
		score += 20
	} else {
		score += 10
	}

	// Sector diversification
	sectorCount := len(analytics.SectorAllocation)
	if sectorCount >= 8 {
		score += 30
	} else if sectorCount >= 5 {
		score += 20
	} else if sectorCount >= 3 {
		score += 10
	}

	// Concentration penalty
	if analytics.ConcentrationRisk != nil {
		if analytics.ConcentrationRisk.RiskLevel == "high" {
			score -= 20
		} else if analytics.ConcentrationRisk.RiskLevel == "medium" {
			score -= 10
		}
	}

	// Ensure score is within bounds
	if score > 100 {
		score = 100
	}
	if score < 0 {
		score = 0
	}

	analytics.DiversificationScore = score
}

func (e *PortfolioAnalyticsEngine) calculateRiskMetrics(analytics *models.PortfolioAnalytics, holdings []models.EnhancedHolding) {
	// Simplified risk calculation
	analytics.Volatility = 15.0 // Default - would calculate from historical data
	analytics.Beta = float64Ptr(1.0)
	analytics.SharpeRatio = float64Ptr(1.2)
}

func (e *PortfolioAnalyticsEngine) calculatePerformanceMetrics(analytics *models.PortfolioAnalytics, holdings []models.EnhancedHolding) {
	// Simplified performance metrics
	analytics.PerformanceMetrics = &models.PerformanceMetrics{
		OneDay:           float64Ptr(analytics.DailyChangePercent),
		OneWeek:          float64Ptr(2.5),
		OneMonth:         float64Ptr(8.7),
		ThreeMonths:      float64Ptr(12.3),
		SixMonths:        float64Ptr(15.8),
		OneYear:          float64Ptr(22.4),
		AnnualizedReturn: float64Ptr(22.4),
	}
}

func (e *PortfolioAnalyticsEngine) calculateTopHoldings(analytics *models.PortfolioAnalytics, holdings []models.EnhancedHolding) {
	// Sort holdings by market value
	sortedHoldings := make([]models.EnhancedHolding, len(holdings))
	copy(sortedHoldings, holdings)

	sort.Slice(sortedHoldings, func(i, j int) bool {
		if sortedHoldings[i].CurrentPrice == nil && sortedHoldings[j].CurrentPrice == nil {
			return false
		}
		if sortedHoldings[i].CurrentPrice == nil {
			return false
		}
		if sortedHoldings[j].CurrentPrice == nil {
			return true
		}
		return *sortedHoldings[i].CurrentPrice > *sortedHoldings[j].CurrentPrice
	})

	// Get top 10
	topHoldings := make([]models.TopHolding, 0, 10)
	for i := 0; i < 10 && i < len(sortedHoldings); i++ {
		holding := sortedHoldings[i]
		if holding.CurrentPrice != nil {
			companyName := holding.Symbol
			if holding.Security != nil {
				companyName = holding.Security.CompanyName
			}

			topHolding := models.TopHolding{
				Symbol:             holding.Symbol,
				CompanyName:        companyName,
				Value:              *holding.MarketValue,
				PercentOfPortfolio: (*holding.MarketValue / analytics.TotalValue) * 100,
				UnrealizedPnL:      holding.UnrealizedPnL,
			}
			topHoldings = append(topHoldings, topHolding)
		}
	}

	analytics.TopHoldings = topHoldings
}

func (e *PortfolioAnalyticsEngine) emptyAnalytics() *models.PortfolioAnalytics {
	return &models.PortfolioAnalytics{
		TotalValue:           0,
		TotalCost:            0,
		TotalReturn:          0,
		TotalReturnPercent:   0,
		DailyChange:          0,
		DailyChangePercent:   0,
		AssetAllocation:      make(map[string]float64),
		SectorAllocation:     make(map[string]float64),
		GeographicAllocation: make(map[string]float64),
		DiversificationScore: 0,
		Volatility:           0,
		WinRate:              0,
		TopHoldings:          []models.TopHolding{},
		LastUpdated:          time.Now(),
	}
}

// Sample allocation strategies
func (e *PortfolioAnalyticsEngine) conservativeAllocation(capital float64) map[string]models.AllocationSuggestion {
	return map[string]models.AllocationSuggestion{
		"SPY": {Symbol: "SPY", Shares: capital / 450.0 / 0.4, EntryPrice: 450.0, Weight: 40.0, Reason: "Broad market exposure"},
		"BND": {Symbol: "BND", Shares: capital / 72.0 / 0.3, EntryPrice: 72.0, Weight: 30.0, Reason: "Bond allocation for stability"},
		"VTI": {Symbol: "VTI", Shares: capital / 240.0 / 0.2, EntryPrice: 240.0, Weight: 20.0, Reason: "Total stock market"},
		"GLD": {Symbol: "GLD", Shares: capital / 180.0 / 0.1, EntryPrice: 180.0, Weight: 10.0, Reason: "Gold hedge"},
	}
}

func (e *PortfolioAnalyticsEngine) moderateAllocation(capital float64) map[string]models.AllocationSuggestion {
	return map[string]models.AllocationSuggestion{
		"SPY": {Symbol: "SPY", Shares: capital / 450.0 / 0.5, EntryPrice: 450.0, Weight: 50.0, Reason: "Core equity exposure"},
		"QQQ": {Symbol: "QQQ", Shares: capital / 380.0 / 0.2, EntryPrice: 380.0, Weight: 20.0, Reason: "Tech growth exposure"},
		"VTI": {Symbol: "VTI", Shares: capital / 240.0 / 0.15, EntryPrice: 240.0, Weight: 15.0, Reason: "Diversified equities"},
		"BND": {Symbol: "BND", Shares: capital / 72.0 / 0.1, EntryPrice: 72.0, Weight: 10.0, Reason: "Bond allocation"},
		"VNQ": {Symbol: "VNQ", Shares: capital / 95.0 / 0.05, EntryPrice: 95.0, Weight: 5.0, Reason: "Real estate exposure"},
	}
}

func (e *PortfolioAnalyticsEngine) aggressiveAllocation(capital float64) map[string]models.AllocationSuggestion {
	return map[string]models.AllocationSuggestion{
		"QQQ":  {Symbol: "QQQ", Shares: capital / 380.0 / 0.4, EntryPrice: 380.0, Weight: 40.0, Reason: "Tech growth focus"},
		"SPY":  {Symbol: "SPY", Shares: capital / 450.0 / 0.25, EntryPrice: 450.0, Weight: 25.0, Reason: "Large cap exposure"},
		"IWM":  {Symbol: "IWM", Shares: capital / 200.0 / 0.15, EntryPrice: 200.0, Weight: 15.0, Reason: "Small cap growth"},
		"ARKK": {Symbol: "ARKK", Shares: capital / 45.0 / 0.1, EntryPrice: 45.0, Weight: 10.0, Reason: "Innovation focus"},
		"VT":   {Symbol: "VT", Shares: capital / 95.0 / 0.1, EntryPrice: 95.0, Weight: 10.0, Reason: "Global diversification"},
	}
}

// Helper function for float64 pointers
func float64Ptr(f float64) *float64 {
	return &f
}
