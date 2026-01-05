package repositories

import (
	"database/sql"
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
		WHERE stock_symbol = $1
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
	if err == sql.ErrNoRows {
		return nil, err
	}
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
		WHERE stock_symbol = $1
		  AND trade_date >= $2
		  AND trade_date <= $3
		ORDER BY trade_date ASC
	`

	rows, err := r.db.Query(query, symbol, startDate, endDate)
	if err != nil {
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
