package repositories

import (
	"database/sql"
	"fmt"
	"strings"
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
		SELECT trade_date, sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, macd_hist, signal
		FROM indicators_daily
		WHERE symbol = $1
		ORDER BY trade_date DESC
		LIMIT 1
	`

	var tradeDate time.Time
	var sma50 sql.NullFloat64
	var sma200 sql.NullFloat64
	var ema20 sql.NullFloat64
	var rsi14 sql.NullFloat64
	var macd sql.NullFloat64
	var macdSignal sql.NullFloat64
	var macdHist sql.NullFloat64
	var signal sql.NullString

	err := r.db.QueryRow(query, symbol).Scan(
		&tradeDate,
		&sma50,
		&sma200,
		&ema20,
		&rsi14,
		&macd,
		&macdSignal,
		&macdHist,
		&signal,
	)
	if err != nil {
		// Fallback: indicators_daily stored as long/EAV schema (symbol,date,indicator_name,indicator_value,...)
		// Try to pivot the required fields.
		errStr := strings.ToLower(err.Error())
		if err == sql.ErrNoRows || strings.Contains(errStr, "column") || strings.Contains(errStr, "trade_date") {
			return r.getLatestFromEAV(symbol)
		}
		return nil, err
	}

	ind := &models.AggregatedIndicators{
		StockSymbol: symbol,
		Date:        tradeDate,
		Timestamp:   tradeDate,
	}
	if sma50.Valid {
		v := sma50.Float64
		ind.SMA50 = &v
	}
	if sma200.Valid {
		v := sma200.Float64
		ind.SMA200 = &v
	}
	if ema20.Valid {
		v := ema20.Float64
		ind.EMA20 = &v
	}
	if rsi14.Valid {
		v := rsi14.Float64
		ind.RSI = &v
	}
	if macd.Valid {
		v := macd.Float64
		ind.MACD = &v
	}
	if macdSignal.Valid {
		v := macdSignal.Float64
		ind.MACDSignal = &v
	}
	if macdHist.Valid {
		v := macdHist.Float64
		ind.MACDHistogram = &v
	}
	if signal.Valid {
		v := signal.String
		ind.Signal = &v
	}

	return ind, nil
}

func (r *IndicatorRepository) getLatestFromEAV(symbol string) (*models.AggregatedIndicators, error) {
	query := `
		SELECT
			d.date as trade_date,
			MAX(CASE WHEN d.indicator_name = 'sma_50' THEN d.indicator_value END) as sma_50,
			MAX(CASE WHEN d.indicator_name = 'sma_200' THEN d.indicator_value END) as sma_200,
			MAX(CASE WHEN d.indicator_name = 'ema_20' THEN d.indicator_value END) as ema_20,
			MAX(CASE WHEN d.indicator_name = 'rsi_14' THEN d.indicator_value END) as rsi_14,
			MAX(CASE WHEN d.indicator_name = 'macd' THEN d.indicator_value END) as macd,
			MAX(CASE WHEN d.indicator_name = 'macd_signal' THEN d.indicator_value END) as macd_signal,
			MAX(CASE WHEN d.indicator_name = 'macd_hist' THEN d.indicator_value END) as macd_hist,
			MAX(CASE WHEN d.indicator_name = 'signal' THEN NULLIF(d.indicator_value::text, '') END) as signal
		FROM indicators_daily d
		WHERE d.symbol = $1
		GROUP BY d.date
		ORDER BY d.date DESC
		LIMIT 1
	`

	var tradeDate time.Time
	var sma50 sql.NullFloat64
	var sma200 sql.NullFloat64
	var ema20 sql.NullFloat64
	var rsi14 sql.NullFloat64
	var macd sql.NullFloat64
	var macdSignal sql.NullFloat64
	var macdHist sql.NullFloat64
	var signal sql.NullString

	err := r.db.QueryRow(query, symbol).Scan(
		&tradeDate,
		&sma50,
		&sma200,
		&ema20,
		&rsi14,
		&macd,
		&macdSignal,
		&macdHist,
		&signal,
	)
	if err != nil {
		return nil, err
	}

	ind := &models.AggregatedIndicators{
		StockSymbol: symbol,
		Date:        tradeDate,
		Timestamp:   tradeDate,
	}
	if sma50.Valid {
		v := sma50.Float64
		ind.SMA50 = &v
	}
	if sma200.Valid {
		v := sma200.Float64
		ind.SMA200 = &v
		ind.SMA200 = &v
	}
	if ema20.Valid {
		v := ema20.Float64
		ind.EMA20 = &v
	}
	if rsi14.Valid {
		v := rsi14.Float64
		ind.RSI = &v
	}
	if macd.Valid {
		v := macd.Float64
		ind.MACD = &v
	}
	if macdSignal.Valid {
		v := macdSignal.Float64
		ind.MACDSignal = &v
	}
	if macdHist.Valid {
		v := macdHist.Float64
		ind.MACDHistogram = &v
	}
	if signal.Valid {
		v := signal.String
		ind.Signal = &v
	}

	return ind, nil
}

func (r *IndicatorRepository) GetByDateRange(symbol string, startDate, endDate time.Time) ([]models.AggregatedIndicators, error) {
	query := `
		SELECT trade_date, sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, macd_hist, signal
		FROM indicators_daily
		WHERE symbol = $1
		  AND trade_date >= $2
		  AND trade_date <= $3
		ORDER BY trade_date ASC
	`

	rows, err := r.db.Query(query, symbol, startDate, endDate)
	if err != nil {
		// Fallback: indicators_daily stored as long/EAV schema.
		errStr := strings.ToLower(err.Error())
		if strings.Contains(errStr, "column") || strings.Contains(errStr, "trade_date") {
			return r.getByDateRangeFromEAV(symbol, startDate, endDate)
		}
		return nil, err
	}
	defer rows.Close()

	out := make([]models.AggregatedIndicators, 0)
	for rows.Next() {
		var tradeDate time.Time
		var sma50 sql.NullFloat64
		var sma200 sql.NullFloat64
		var ema20 sql.NullFloat64
		var rsi14 sql.NullFloat64
		var macd sql.NullFloat64
		var macdSignal sql.NullFloat64
		var macdHist sql.NullFloat64
		var signal sql.NullString

		if err := rows.Scan(
			&tradeDate,
			&sma50,
			&sma200,
			&ema20,
			&rsi14,
			&macd,
			&macdSignal,
			&macdHist,
			&signal,
		); err != nil {
			return nil, err
		}

		ind := models.AggregatedIndicators{
			StockSymbol: symbol,
			Date:        tradeDate,
			Timestamp:   tradeDate,
		}
		if sma50.Valid {
			v := sma50.Float64
			ind.SMA50 = &v
		}
		if sma200.Valid {
			v := sma200.Float64
			ind.SMA200 = &v
		}
		if ema20.Valid {
			v := ema20.Float64
			ind.EMA20 = &v
		}
		if rsi14.Valid {
			v := rsi14.Float64
			ind.RSI = &v
		}
		if macd.Valid {
			v := macd.Float64
			ind.MACD = &v
		}
		if macdSignal.Valid {
			v := macdSignal.Float64
			ind.MACDSignal = &v
		}
		if macdHist.Valid {
			v := macdHist.Float64
			ind.MACDHistogram = &v
		}
		if signal.Valid {
			v := signal.String
			ind.Signal = &v
		}

		out = append(out, ind)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return out, nil
}

func (r *IndicatorRepository) getByDateRangeFromEAV(symbol string, startDate, endDate time.Time) ([]models.AggregatedIndicators, error) {
	query := `
		SELECT
			d.date as trade_date,
			MAX(CASE WHEN d.indicator_name = 'sma_50' THEN d.indicator_value END) as sma_50,
			MAX(CASE WHEN d.indicator_name = 'sma_200' THEN d.indicator_value END) as sma_200,
			MAX(CASE WHEN d.indicator_name = 'ema_20' THEN d.indicator_value END) as ema_20,
			MAX(CASE WHEN d.indicator_name = 'rsi_14' THEN d.indicator_value END) as rsi_14,
			MAX(CASE WHEN d.indicator_name = 'macd' THEN d.indicator_value END) as macd,
			MAX(CASE WHEN d.indicator_name = 'macd_signal' THEN d.indicator_value END) as macd_signal,
			MAX(CASE WHEN d.indicator_name = 'macd_hist' THEN d.indicator_value END) as macd_hist,
			MAX(CASE WHEN d.indicator_name = 'signal' THEN NULLIF(d.indicator_value::text, '') END) as signal
		FROM indicators_daily d
		WHERE d.symbol = $1
		  AND d.date >= $2
		  AND d.date <= $3
		GROUP BY d.date
		ORDER BY d.date ASC
	`

	rows, err := r.db.Query(query, symbol, startDate, endDate)
	if err != nil {
		return nil, fmt.Errorf("failed EAV indicators query: %w", err)
	}
	defer rows.Close()

	out := make([]models.AggregatedIndicators, 0)
	for rows.Next() {
		var tradeDate time.Time
		var sma50 sql.NullFloat64
		var sma200 sql.NullFloat64
		var ema20 sql.NullFloat64
		var rsi14 sql.NullFloat64
		var macd sql.NullFloat64
		var macdSignal sql.NullFloat64
		var macdHist sql.NullFloat64
		var signal sql.NullString

		if err := rows.Scan(
			&tradeDate,
			&sma50,
			&sma200,
			&ema20,
			&rsi14,
			&macd,
			&macdSignal,
			&macdHist,
			&signal,
		); err != nil {
			return nil, err
		}

		ind := models.AggregatedIndicators{
			StockSymbol: symbol,
			Date:        tradeDate,
			Timestamp:   tradeDate,
		}
		if sma50.Valid {
			v := sma50.Float64
			ind.SMA50 = &v
		}
		if sma200.Valid {
			v := sma200.Float64
			ind.SMA200 = &v
		}
		if ema20.Valid {
			v := ema20.Float64
			ind.EMA20 = &v
		}
		if rsi14.Valid {
			v := rsi14.Float64
			ind.RSI = &v
		}
		if macd.Valid {
			v := macd.Float64
			ind.MACD = &v
		}
		if macdSignal.Valid {
			v := macdSignal.Float64
			ind.MACDSignal = &v
		}
		if macdHist.Valid {
			v := macdHist.Float64
			ind.MACDHistogram = &v
		}
		if signal.Valid {
			v := signal.String
			ind.Signal = &v
		}

		out = append(out, ind)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return out, nil
}
