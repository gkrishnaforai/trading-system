package services

import (
	"time"

	"github.com/trading-system/go-api/internal/models"
)

// RiskAssessmentEngine provides AI-powered risk analysis
type RiskAssessmentEngine struct{}

func NewRiskAssessmentEngine() *RiskAssessmentEngine {
	return &RiskAssessmentEngine{}
}

// AssessPortfolioRisk evaluates portfolio risk metrics
func (e *RiskAssessmentEngine) AssessPortfolioRisk(
	holdings []models.EnhancedHolding,
	analytics *models.PortfolioAnalytics,
) *models.RiskMetrics {
	riskMetrics := &models.RiskMetrics{
		LastUpdated: time.Now(),
	}

	// Calculate overall risk score
	e.calculateOverallRiskScore(riskMetrics, holdings, analytics)

	// Calculate volatility
	e.calculateVolatility(riskMetrics, holdings)

	// Calculate beta
	e.calculateBeta(riskMetrics, holdings)

	// Calculate Value at Risk
	e.calculateValueAtRisk(riskMetrics, holdings, analytics)

	// Calculate drawdown metrics
	e.calculateDrawdownMetrics(riskMetrics, analytics)

	// Calculate risk ratios
	e.calculateRiskRatios(riskMetrics, analytics)

	// Decompose risk by sector/holding
	e.calculateRiskDecomposition(riskMetrics, holdings, analytics)

	// Run stress tests
	e.runStressTests(riskMetrics, holdings, analytics)

	// Determine risk level
	e.determineRiskLevel(riskMetrics)

	return riskMetrics
}

// AssessHoldingRisk evaluates individual holding risk
func (e *RiskAssessmentEngine) AssessHoldingRisk(holding models.PortfolioPosition, security *models.SecurityInfo) string {
	// Simple risk assessment based on available data
	riskScore := 0

	// Factor in volatility (simplified)
	if security != nil {
		// Large cap stocks generally less risky
		if security.MarketCap != nil && *security.MarketCap > 100000000000 { // >$100B
			riskScore += 1
		} else if security.MarketCap != nil && *security.MarketCap > 10000000000 { // >$10B
			riskScore += 2
		} else {
			riskScore += 3
		}

		// Sector risk
		switch security.Sector {
		case "Utilities", "Consumer Staples":
			// Lower risk sectors
			riskScore += 1
		case "Technology", "Biotechnology":
			// Higher risk sectors
			riskScore += 3
		default:
			riskScore += 2
		}
	}

	// Position size risk
	if holding.Quantity*holding.AvgPrice > 50000 { // Large position
		riskScore += 2
	} else if holding.Quantity*holding.AvgPrice > 10000 { // Medium position
		riskScore += 1
	}

	// Convert score to risk level
	if riskScore <= 3 {
		return "low"
	} else if riskScore <= 6 {
		return "medium"
	}
	return "high"
}

// Helper methods
func (e *RiskAssessmentEngine) calculateOverallRiskScore(
	riskMetrics *models.RiskMetrics,
	holdings []models.EnhancedHolding,
	analytics *models.PortfolioAnalytics,
) {
	score := 50.0 // Base score

	// Adjust for concentration risk
	if analytics.ConcentrationRisk != nil {
		switch analytics.ConcentrationRisk.RiskLevel {
		case "high":
			score += 25
		case "medium":
			score += 15
		case "low":
			score += 5
		}
	}

	// Adjust for diversification
	diversificationPenalty := (100 - analytics.DiversificationScore) * 0.3
	score += diversificationPenalty

	// Adjust for volatility
	if analytics.Volatility > 25 {
		score += 20
	} else if analytics.Volatility > 15 {
		score += 10
	}

	// Ensure score is within bounds
	if score > 100 {
		score = 100
	}
	if score < 0 {
		score = 0
	}

	riskMetrics.OverallRiskScore = score
}

func (e *RiskAssessmentEngine) calculateVolatility(
	riskMetrics *models.RiskMetrics,
	holdings []models.EnhancedHolding,
) {
	// Simplified volatility calculation
	// In production, this would use historical price data
	riskMetrics.Volatility = 18.5 // Default - would calculate from historical returns
}

func (e *RiskAssessmentEngine) calculateBeta(
	riskMetrics *models.RiskMetrics,
	holdings []models.EnhancedHolding,
) {
	// Simplified beta calculation
	// In production, this would calculate weighted average beta
	beta := 1.0
	riskMetrics.Beta = &beta
}

func (e *RiskAssessmentEngine) calculateValueAtRisk(
	riskMetrics *models.RiskMetrics,
	holdings []models.EnhancedHolding,
	analytics *models.PortfolioAnalytics,
) {
	if analytics.TotalValue > 0 {
		// Simplified VaR calculation (95% confidence, 1 day)
		// VaR = Portfolio Value * Volatility * 1.65 * sqrt(1/252)
		dailyVolatility := riskMetrics.Volatility / 100.0 / sqrt(252)
		var95 := analytics.TotalValue * dailyVolatility * 1.65
		riskMetrics.ValueAtRisk = &var95

		// Expected Shortfall (CVaR) - simplified
		expectedShortfall := var95 * 1.2
		riskMetrics.ExpectedShortfall = &expectedShortfall
	}
}

func (e *RiskAssessmentEngine) calculateDrawdownMetrics(
	riskMetrics *models.RiskMetrics,
	analytics *models.PortfolioAnalytics,
) {
	// Simplified drawdown calculation
	// In production, this would use historical portfolio values
	maxDrawdown := -12.5 // Example max drawdown
	riskMetrics.MaxDrawdown = &maxDrawdown
}

func (e *RiskAssessmentEngine) calculateRiskRatios(
	riskMetrics *models.RiskMetrics,
	analytics *models.PortfolioAnalytics,
) {
	if riskMetrics.Volatility > 0 {
		// Simplified Sharpe ratio (assuming risk-free rate of 2%)
		annualReturn := analytics.TotalReturnPercent / 100.0
		riskFreeRate := 0.02
		sharpeRatio := (annualReturn - riskFreeRate) / (riskMetrics.Volatility / 100.0)
		riskMetrics.SharpeRatio = &sharpeRatio

		// Simplified Sortino ratio (assuming downside deviation is 80% of volatility)
		downsideDeviation := riskMetrics.Volatility * 0.8 / 100.0
		if downsideDeviation > 0 {
			sortinoRatio := (annualReturn - riskFreeRate) / downsideDeviation
			riskMetrics.SortinoRatio = &sortinoRatio
		}
	}
}

func (e *RiskAssessmentEngine) calculateRiskDecomposition(
	riskMetrics *models.RiskMetrics,
	holdings []models.EnhancedHolding,
	analytics *models.PortfolioAnalytics,
) {
	riskMetrics.RiskDecomposition = make(map[string]float64)

	if analytics.TotalValue == 0 {
		return
	}

	// Calculate risk contribution by sector
	sectorWeights := make(map[string]float64)
	for _, holding := range holdings {
		if holding.MarketValue != nil && holding.Security != nil {
			weight := (*holding.MarketValue / analytics.TotalValue) * 100
			sector := holding.Security.Sector
			if sector == "" {
				sector = "Unknown"
			}
			sectorWeights[sector] += weight
		}
	}

	// Risk contribution is proportional to weight (simplified)
	for sector, weight := range sectorWeights {
		riskMetrics.RiskDecomposition[sector] = weight
	}
}

func (e *RiskAssessmentEngine) runStressTests(
	riskMetrics *models.RiskMetrics,
	holdings []models.EnhancedHolding,
	analytics *models.PortfolioAnalytics,
) {
	if analytics.TotalValue == 0 {
		return
	}

	// Simplified stress test scenarios
	stressResults := &models.StressTestResults{
		MarketCrashScenario: -20.0, // 20% loss in major market crash
		InterestRateShock:   -8.0,  // 8% loss in rising rate environment
		RecessionScenario:   -15.0, // 15% loss in recession
		InflationShock:      -12.0, // 12% loss in high inflation
	}

	riskMetrics.StressTestResults = stressResults
}

func (e *RiskAssessmentEngine) determineRiskLevel(riskMetrics *models.RiskMetrics) {
	score := riskMetrics.OverallRiskScore

	if score >= 75 {
		riskMetrics.RiskLevel = "high"
	} else if score >= 40 {
		riskMetrics.RiskLevel = "medium"
	} else {
		riskMetrics.RiskLevel = "low"
	}
}

func sqrt(x float64) float64 {
	// Simple square root implementation
	// In production, use math.Sqrt
	if x == 0 {
		return 0
	}

	// Newton's method
	guess := x / 2
	for i := 0; i < 10; i++ {
		guess = (guess + x/guess) / 2
	}
	return guess
}
