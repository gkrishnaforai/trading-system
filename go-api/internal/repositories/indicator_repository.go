package repositories

import (
	"database/sql"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/models"
)

type IndicatorRepository struct {
	db *sql.DB
}

func NewIndicatorRepository() *IndicatorRepository {
	return &IndicatorRepository{
		db: database.DB,
	}
}

func (r *IndicatorRepository) GetLatest(symbol string) (*models.AggregatedIndicators, error) {
	query := `
		SELECT id, stock_symbol, date, ma7, ma21, sma50, ema20, ema50, sma200,
		       atr, macd, macd_signal, macd_histogram, rsi,
		       bb_upper, bb_middle, bb_lower,
		       long_term_trend, medium_term_trend, signal,
		       pullback_zone_lower, pullback_zone_upper, momentum_score,
		       volume, volume_ma, timestamp
		FROM aggregated_indicators
		WHERE stock_symbol = ?
		ORDER BY date DESC
		LIMIT 1
	`

	indicator := &models.AggregatedIndicators{}
	err := r.db.QueryRow(query, symbol).Scan(
		&indicator.ID,
		&indicator.StockSymbol,
		&indicator.Date,
		&indicator.MA7,
		&indicator.MA21,
		&indicator.SMA50,
		&indicator.EMA20,
		&indicator.EMA50,
		&indicator.SMA200,
		&indicator.ATR,
		&indicator.MACD,
		&indicator.MACDSignal,
		&indicator.MACDHistogram,
		&indicator.RSI,
		&indicator.BBUpper,
		&indicator.BBMiddle,
		&indicator.BBLower,
		&indicator.LongTermTrend,
		&indicator.MediumTermTrend,
		&indicator.Signal,
		&indicator.PullbackZoneLower,
		&indicator.PullbackZoneUpper,
		&indicator.MomentumScore,
		&indicator.Volume,
		&indicator.VolumeMA,
		&indicator.Timestamp,
	)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("indicators not found for symbol: %s", symbol)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get indicators: %w", err)
	}

	return indicator, nil
}

func (r *IndicatorRepository) GetByDateRange(symbol string, startDate, endDate time.Time) ([]models.AggregatedIndicators, error) {
	query := `
		SELECT id, stock_symbol, date, ma7, ma21, sma50, ema20, ema50, sma200,
		       atr, macd, macd_signal, macd_histogram, rsi,
		       bb_upper, bb_middle, bb_lower,
		       long_term_trend, medium_term_trend, signal,
		       pullback_zone_lower, pullback_zone_upper, momentum_score,
		       volume, volume_ma, timestamp
		FROM aggregated_indicators
		WHERE stock_symbol = ? AND date >= ? AND date <= ?
		ORDER BY date ASC
	`

	rows, err := r.db.Query(query, symbol, startDate, endDate)
	if err != nil {
		return nil, fmt.Errorf("failed to query indicators: %w", err)
	}
	defer rows.Close()

	var indicators []models.AggregatedIndicators
	for rows.Next() {
		var ind models.AggregatedIndicators
		if err := rows.Scan(
			&ind.ID,
			&ind.StockSymbol,
			&ind.Date,
			&ind.MA7,
			&ind.MA21,
			&ind.SMA50,
			&ind.EMA20,
			&ind.EMA50,
			&ind.SMA200,
			&ind.ATR,
			&ind.MACD,
			&ind.MACDSignal,
			&ind.MACDHistogram,
			&ind.RSI,
			&ind.BBUpper,
			&ind.BBMiddle,
			&ind.BBLower,
			&ind.LongTermTrend,
			&ind.MediumTermTrend,
			&ind.Signal,
			&ind.PullbackZoneLower,
			&ind.PullbackZoneUpper,
			&ind.MomentumScore,
			&ind.Volume,
			&ind.VolumeMA,
			&ind.Timestamp,
		); err != nil {
			return nil, fmt.Errorf("failed to scan indicator: %w", err)
		}
		indicators = append(indicators, ind)
	}

	return indicators, nil
}

