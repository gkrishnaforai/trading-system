package repositories

import (
	"database/sql"
	"fmt"
	"log"
	"strings"

	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/models"
)

type PortfolioRepository struct {
	db *sql.DB
}

func NewPortfolioRepository() *PortfolioRepository {
	return &PortfolioRepository{
		db: database.DB,
	}
}

func (r *PortfolioRepository) GetByUserID(userID string) ([]models.Portfolio, error) {
	query := `
		SELECT portfolio_id, user_id, portfolio_name, notes, created_at, updated_at
		FROM portfolios
		WHERE user_id = ?
		ORDER BY created_at DESC
	`

	rows, err := r.db.Query(query, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to query portfolios: %w", err)
	}
	defer rows.Close()

	var portfolios []models.Portfolio
	for rows.Next() {
		var p models.Portfolio
		if err := rows.Scan(
			&p.PortfolioID,
			&p.UserID,
			&p.PortfolioName,
			&p.Notes,
			&p.CreatedAt,
			&p.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan portfolio: %w", err)
		}
		portfolios = append(portfolios, p)
	}

	return portfolios, nil
}

func (r *PortfolioRepository) GetHoldings(portfolioID string) ([]models.Holding, error) {
	query := `
		SELECT holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price,
		       position_type, strategy_tag, notes, purchase_date, created_at, updated_at
		FROM holdings
		WHERE portfolio_id = ?
		ORDER BY purchase_date DESC
	`

	rows, err := r.db.Query(query, portfolioID)
	if err != nil {
		return nil, fmt.Errorf("failed to query holdings: %w", err)
	}
	defer rows.Close()

	var holdings []models.Holding
	for rows.Next() {
		var h models.Holding
		if err := rows.Scan(
			&h.HoldingID,
			&h.PortfolioID,
			&h.StockSymbol,
			&h.Quantity,
			&h.AvgEntryPrice,
			&h.PositionType,
			&h.StrategyTag,
			&h.Notes,
			&h.PurchaseDate,
			&h.CreatedAt,
			&h.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan holding: %w", err)
		}
		holdings = append(holdings, h)
	}

	return holdings, nil
}

func (r *PortfolioRepository) GetSignals(portfolioID string) ([]models.PortfolioSignal, error) {
	query := `
		SELECT signal_id, portfolio_id, stock_symbol, date, signal_type,
		       suggested_allocation, stop_loss, confidence_score, subscription_level_required, created_at
		FROM portfolio_signals
		WHERE portfolio_id = ?
		ORDER BY date DESC, created_at DESC
	`

	rows, err := r.db.Query(query, portfolioID)
	if err != nil {
		return nil, fmt.Errorf("failed to query signals: %w", err)
	}
	defer rows.Close()

	var signals []models.PortfolioSignal
	for rows.Next() {
		var s models.PortfolioSignal
		if err := rows.Scan(
			&s.SignalID,
			&s.PortfolioID,
			&s.StockSymbol,
			&s.Date,
			&s.SignalType,
			&s.SuggestedAllocation,
			&s.StopLoss,
			&s.ConfidenceScore,
			&s.SubscriptionLevelRequired,
			&s.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan signal: %w", err)
		}
		signals = append(signals, s)
	}

	return signals, nil
}

// CreatePortfolio creates a new portfolio
func (r *PortfolioRepository) CreatePortfolio(portfolio *models.Portfolio) error {
	log.Printf("INFO: Creating portfolio %s for user %s", portfolio.PortfolioID, portfolio.UserID)
	
	query := `
		INSERT INTO portfolios (portfolio_id, user_id, portfolio_name, notes)
		VALUES (?, ?, ?, ?)
	`
	
	_, err := r.db.Exec(query, portfolio.PortfolioID, portfolio.UserID, portfolio.PortfolioName, portfolio.Notes)
	if err != nil {
		log.Printf("ERROR: Failed to create portfolio: %v", err)
		return fmt.Errorf("failed to create portfolio: %w", err)
	}
	
	log.Printf("INFO: Successfully created portfolio %s", portfolio.PortfolioID)
	return nil
}

// UpdatePortfolio updates an existing portfolio
func (r *PortfolioRepository) UpdatePortfolio(portfolioID string, portfolioName *string, notes *string) error {
	updates := []string{}
	args := []interface{}{}
	
	if portfolioName != nil {
		updates = append(updates, "portfolio_name = ?")
		args = append(args, *portfolioName)
	}
	
	if notes != nil {
		updates = append(updates, "notes = ?")
		args = append(args, *notes)
	}
	
	if len(updates) == 0 {
		return nil // No updates
	}
	
	updates = append(updates, "updated_at = CURRENT_TIMESTAMP")
	args = append(args, portfolioID)
	
	query := fmt.Sprintf("UPDATE portfolios SET %s WHERE portfolio_id = ?", 
		strings.Join(updates, ", "))
	
	_, err := r.db.Exec(query, args...)
	if err != nil {
		return fmt.Errorf("failed to update portfolio: %w", err)
	}
	return nil
}

// DeletePortfolio deletes a portfolio
func (r *PortfolioRepository) DeletePortfolio(portfolioID string) error {
	query := `DELETE FROM portfolios WHERE portfolio_id = ?`
	
	_, err := r.db.Exec(query, portfolioID)
	if err != nil {
		return fmt.Errorf("failed to delete portfolio: %w", err)
	}
	return nil
}

// CreateHolding creates a new holding
func (r *PortfolioRepository) CreateHolding(holding *models.Holding) error {
	query := `
		INSERT INTO holdings (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price,
		                     position_type, strategy_tag, notes, purchase_date)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	`
	
	_, err := r.db.Exec(query, holding.HoldingID, holding.PortfolioID, holding.StockSymbol,
		holding.Quantity, holding.AvgEntryPrice, holding.PositionType, holding.StrategyTag,
		holding.Notes, holding.PurchaseDate)
	if err != nil {
		return fmt.Errorf("failed to create holding: %w", err)
	}
	return nil
}

// UpdateHolding updates an existing holding
func (r *PortfolioRepository) UpdateHolding(holdingID string, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return nil
	}
	
	setParts := []string{}
	args := []interface{}{}
	
	allowedFields := map[string]bool{
		"quantity": true, "avg_entry_price": true, "position_type": true,
		"strategy_tag": true, "notes": true, "purchase_date": true,
	}
	
	for field, value := range updates {
		if allowedFields[field] {
			setParts = append(setParts, fmt.Sprintf("%s = ?", field))
			args = append(args, value)
		}
	}
	
	if len(setParts) == 0 {
		return nil
	}
	
	setParts = append(setParts, "updated_at = CURRENT_TIMESTAMP")
	args = append(args, holdingID)
	
	query := fmt.Sprintf("UPDATE holdings SET %s WHERE holding_id = ?",
		strings.Join(setParts, ", "))
	
	_, err := r.db.Exec(query, args...)
	if err != nil {
		return fmt.Errorf("failed to update holding: %w", err)
	}
	return nil
}

// DeleteHolding deletes a holding
func (r *PortfolioRepository) DeleteHolding(holdingID string) error {
	query := `DELETE FROM holdings WHERE holding_id = ?`
	
	_, err := r.db.Exec(query, holdingID)
	if err != nil {
		return fmt.Errorf("failed to delete holding: %w", err)
	}
	return nil
}

