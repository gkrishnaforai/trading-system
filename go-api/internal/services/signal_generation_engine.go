package services

import (
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/models"
)

// SignalGenerationEngine generates AI-powered trading signals
type SignalGenerationEngine struct{}

func NewSignalGenerationEngine() *SignalGenerationEngine {
	return &SignalGenerationEngine{}
}

// GeneratePortfolioSignals creates signals for portfolio rebalancing
func (e *SignalGenerationEngine) GeneratePortfolioSignals(
	holdings []models.EnhancedHolding,
	analytics *models.PortfolioAnalytics,
) []models.AISignal {
	var signals []models.AISignal

	// Generate rebalancing signals if needed
	if analytics.ConcentrationRisk != nil && analytics.ConcentrationRisk.RiskLevel == "high" {
		signals = append(signals, models.AISignal{
			SignalID:    generateSignalID(),
			SignalType:  "rebalance",
			Confidence:  85.0,
			Reason:      "Portfolio concentration risk is high - consider diversification",
			Source:      "ai_model",
			TimeHorizon: "medium",
			CreatedAt:   time.Now(),
			ExpiresAt:   time.Now().Add(24 * time.Hour),
			Priority:    "medium",
		})
	}

	// Generate individual holding signals
	for _, holding := range holdings {
		holdingSignals := e.generateHoldingSignals(holding)
		signals = append(signals, holdingSignals...)
	}

	return signals
}

// GenerateWatchlistSignals creates signals for watchlist items
func (e *SignalGenerationEngine) GenerateWatchlistSignals(
	items []models.EnhancedWatchlistItem,
	analytics *models.WatchlistAnalytics,
) []models.AISignal {
	var signals []models.AISignal

	for _, item := range items {
		itemSignals := e.generateWatchlistSignals(item)
		signals = append(signals, itemSignals...)
	}

	return signals
}

// GenerateTechnicalSignals creates technical analysis signals
func (e *SignalGenerationEngine) GenerateTechnicalSignals(symbol string) []models.TechnicalSignal {
	// This would integrate with technical analysis service
	// For now, return mock signals
	signals := []models.TechnicalSignal{
		{
			Indicator:    "RSI",
			Signal:       "bullish",
			Strength:     75.0,
			Timestamp:    time.Now(),
			ChartPattern: "oversold",
		},
		{
			Indicator:    "MACD",
			Signal:       "bullish",
			Strength:     65.0,
			Timestamp:    time.Now(),
			ChartPattern: "bullish_crossover",
		},
		{
			Indicator:    "MovingAverage",
			Signal:       "bullish",
			Strength:     80.0,
			PriceLevel:   float64Ptr(150.0),
			Timestamp:    time.Now(),
			ChartPattern: "golden_cross",
		},
	}

	return signals
}

// Helper methods
func (e *SignalGenerationEngine) generateHoldingSignals(holding models.EnhancedHolding) []models.AISignal {
	var signals []models.AISignal

	// Generate signals based on unrealized P&L
	if holding.UnrealizedPnLPct != nil {
		pnl := *holding.UnrealizedPnLPct
		if pnl > 20 {
			signals = append(signals, models.AISignal{
				SignalID:    generateSignalID(),
				StockSymbol: holding.Symbol,
				SignalType:  "sell",
				Confidence:  70.0,
				Reason:      "Consider taking profits - position up significantly",
				Source:      "ai_model",
				PriceTarget: holding.CurrentPrice,
				TimeHorizon: "short",
				CreatedAt:   time.Now(),
				ExpiresAt:   time.Now().Add(4 * time.Hour),
				Priority:    "medium",
			})
		} else if pnl < -15 {
			signals = append(signals, models.AISignal{
				SignalID:    generateSignalID(),
				StockSymbol: holding.Symbol,
				SignalType:  "buy",
				Confidence:  75.0,
				Reason:      "Consider averaging down - position down significantly",
				Source:      "ai_model",
				PriceTarget: holding.CurrentPrice,
				TimeHorizon: "medium",
				CreatedAt:   time.Now(),
				ExpiresAt:   time.Now().Add(24 * time.Hour),
				Priority:    "medium",
			})
		}
	}

	// Generate signals based on technical indicators
	if len(holding.TechnicalSignals) > 0 {
		for _, techSignal := range holding.TechnicalSignals {
			if techSignal.Signal == "bullish" && techSignal.Strength > 70 {
				signals = append(signals, models.AISignal{
					SignalID:    generateSignalID(),
					StockSymbol: holding.Symbol,
					SignalType:  "buy",
					Confidence:  techSignal.Strength,
					Reason:      fmt.Sprintf("Strong bullish %s signal", techSignal.Indicator),
					Source:      "technical",
					PriceTarget: techSignal.PriceLevel,
					TimeHorizon: "short",
					CreatedAt:   time.Now(),
					ExpiresAt:   time.Now().Add(8 * time.Hour),
					Priority:    "low",
				})
			} else if techSignal.Signal == "bearish" && techSignal.Strength > 70 {
				signals = append(signals, models.AISignal{
					SignalID:    generateSignalID(),
					StockSymbol: holding.Symbol,
					SignalType:  "sell",
					Confidence:  techSignal.Strength,
					Reason:      fmt.Sprintf("Strong bearish %s signal", techSignal.Indicator),
					Source:      "technical",
					PriceTarget: techSignal.PriceLevel,
					TimeHorizon: "short",
					CreatedAt:   time.Now(),
					ExpiresAt:   time.Now().Add(8 * time.Hour),
					Priority:    "low",
				})
			}
		}
	}

	// Generate fundamental signals
	if holding.FundamentalScore != nil && holding.FundamentalScore.OverallScore > 80 {
		signals = append(signals, models.AISignal{
			SignalID:    generateSignalID(),
			StockSymbol: holding.Symbol,
			SignalType:  "buy",
			Confidence:  holding.FundamentalScore.OverallScore,
			Reason:      "Strong fundamental metrics",
			Source:      "fundamental",
			TimeHorizon: "long",
			CreatedAt:   time.Now(),
			ExpiresAt:   time.Now().Add(7 * 24 * time.Hour),
			Priority:    "low",
		})
	}

	return signals
}

func (e *SignalGenerationEngine) generateWatchlistSignals(item models.EnhancedWatchlistItem) []models.AISignal {
	var signals []models.AISignal

	// Generate buy signals for watchlist items with strong indicators
	if item.OpportunityScore != nil && *item.OpportunityScore > 75 {
		signals = append(signals, models.AISignal{
			SignalID:    generateSignalID(),
			StockSymbol: item.Symbol,
			SignalType:  "buy",
			Confidence:  *item.OpportunityScore,
			Reason:      "High opportunity score based on technical and fundamental analysis",
			Source:      "ai_model",
			PriceTarget: item.CurrentPrice,
			TimeHorizon: "medium",
			CreatedAt:   time.Now(),
			ExpiresAt:   time.Now().Add(24 * time.Hour),
			Priority:    "medium",
		})
	}

	// Generate signals based on technical analysis
	if len(item.TechnicalSignals) > 0 {
		for _, techSignal := range item.TechnicalSignals {
			if techSignal.Signal == "bullish" && techSignal.Strength > 80 {
				signals = append(signals, models.AISignal{
					SignalID:    generateSignalID(),
					StockSymbol: item.Symbol,
					SignalType:  "buy",
					Confidence:  techSignal.Strength,
					Reason:      fmt.Sprintf("Strong bullish %s signal - good entry point", techSignal.Indicator),
					Source:      "technical",
					PriceTarget: techSignal.PriceLevel,
					TimeHorizon: "short",
					CreatedAt:   time.Now(),
					ExpiresAt:   time.Now().Add(12 * time.Hour),
					Priority:    "high",
				})
			}
		}
	}

	// Generate earnings-related signals
	if item.EarningsData != nil && item.EarningsData.NextEarningsDate != nil {
		daysUntil := int(time.Until(*item.EarningsData.NextEarningsDate).Hours() / 24)
		if daysUntil <= 7 && daysUntil >= 0 {
			signals = append(signals, models.AISignal{
				SignalID:    generateSignalID(),
				StockSymbol: item.Symbol,
				SignalType:  "alert",
				Confidence:  90.0,
				Reason:      fmt.Sprintf("Earnings announcement in %d days", daysUntil),
				Source:      "fundamental",
				TimeHorizon: "short",
				CreatedAt:   time.Now(),
				ExpiresAt:   *item.EarningsData.NextEarningsDate,
				Priority:    "high",
			})
		}
	}

	return signals
}

func generateSignalID() string {
	return fmt.Sprintf("signal_%d", time.Now().UnixNano())
}
