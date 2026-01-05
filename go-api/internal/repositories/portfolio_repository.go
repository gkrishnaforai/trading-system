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

func (r *PortfolioRepository) ensureStockID(symbol string) (string, error) {
	query := `
		INSERT INTO stocks (symbol)
		VALUES ($1)
		ON CONFLICT (symbol) DO UPDATE SET symbol = EXCLUDED.symbol
		RETURNING id
	`

	var stockID string
	if err := r.db.QueryRow(query, symbol).Scan(&stockID); err != nil {
		return "", fmt.Errorf("failed to ensure stock id: %w", err)
	}
	return stockID, nil
}

func (r *PortfolioRepository) GetByID(portfolioID string) (*models.Portfolio, error) {
	query := `
		SELECT id, user_id, name, base_currency, is_default, is_archived, created_at, updated_at
		FROM portfolios
		WHERE id = $1
	`

	var p models.Portfolio
	err := r.db.QueryRow(query, portfolioID).Scan(
		&p.ID,
		&p.UserID,
		&p.Name,
		&p.BaseCurrency,
		&p.IsDefault,
		&p.IsArchived,
		&p.CreatedAt,
		&p.UpdatedAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("portfolio not found")
		}
		return nil, fmt.Errorf("failed to query portfolio: %w", err)
	}

	return &p, nil
}

func (r *PortfolioRepository) GetByUserID(userID string) ([]models.Portfolio, error) {
	query := `
		SELECT id, user_id, name, base_currency, is_default, is_archived, created_at, updated_at
		FROM portfolios
		WHERE user_id = $1
		ORDER BY is_default DESC, created_at DESC
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
			&p.ID,
			&p.UserID,
			&p.Name,
			&p.BaseCurrency,
			&p.IsDefault,
			&p.IsArchived,
			&p.CreatedAt,
			&p.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan portfolio: %w", err)
		}
		portfolios = append(portfolios, p)
	}

	return portfolios, nil
}

func (r *PortfolioRepository) GetHoldings(portfolioID string) ([]models.PortfolioPosition, error) {
	query := `
		SELECT pp.id, pp.portfolio_id, pp.stock_id, s.symbol, pp.quantity, pp.avg_price,
		       pp.opened_at, pp.created_at, pp.updated_at
		FROM portfolio_positions pp
		JOIN stocks s ON s.id = pp.stock_id
		WHERE pp.portfolio_id = $1
		ORDER BY pp.created_at DESC
	`

	rows, err := r.db.Query(query, portfolioID)
	if err != nil {
		return nil, fmt.Errorf("failed to query holdings: %w", err)
	}
	defer rows.Close()

	var holdings []models.PortfolioPosition
	for rows.Next() {
		var h models.PortfolioPosition
		if err := rows.Scan(
			&h.ID,
			&h.PortfolioID,
			&h.StockID,
			&h.Symbol,
			&h.Quantity,
			&h.AvgPrice,
			&h.OpenedAt,
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
	_ = portfolioID
	return []models.PortfolioSignal{}, nil
}

// CreatePortfolio creates a new portfolio
func (r *PortfolioRepository) CreatePortfolio(portfolio *models.Portfolio) error {
	query := `
		INSERT INTO portfolios (user_id, name, base_currency, is_default, is_archived)
		VALUES ($1, $2, COALESCE($3, 'USD'), $4, $5)
		RETURNING id, created_at, updated_at
	`

	log.Printf("INFO: Creating portfolio for user %s", portfolio.UserID)
	err := r.db.QueryRow(query, portfolio.UserID, portfolio.Name, portfolio.BaseCurrency, portfolio.IsDefault, portfolio.IsArchived).
		Scan(&portfolio.ID, &portfolio.CreatedAt, &portfolio.UpdatedAt)
	if err != nil {
		log.Printf("ERROR: Failed to create portfolio: %v", err)
		return fmt.Errorf("failed to create portfolio: %w", err)
	}

	log.Printf("INFO: Successfully created portfolio %s", portfolio.ID)
	return nil
}

// UpdatePortfolio updates an existing portfolio
func (r *PortfolioRepository) UpdatePortfolio(portfolioID string, portfolioName *string, notes *string) error {
	updates := []string{}
	args := []interface{}{}

	if portfolioName != nil {
		updates = append(updates, fmt.Sprintf("name = $%d", len(args)+1))
		args = append(args, *portfolioName)
	}
	_ = notes

	if len(updates) == 0 {
		return nil
	}

	updates = append(updates, "updated_at = CURRENT_TIMESTAMP")
	args = append(args, portfolioID)
	query := fmt.Sprintf("UPDATE portfolios SET %s WHERE id = $%d", strings.Join(updates, ", "), len(args))

	_, err := r.db.Exec(query, args...)
	if err != nil {
		return fmt.Errorf("failed to update portfolio: %w", err)
	}
	return nil
}

// DeletePortfolio deletes a portfolio
func (r *PortfolioRepository) DeletePortfolio(portfolioID string) error {
	query := `DELETE FROM portfolios WHERE id = $1`

	_, err := r.db.Exec(query, portfolioID)
	if err != nil {
		return fmt.Errorf("failed to delete portfolio: %w", err)
	}
	return nil
}

// AddPositionBySymbol inserts/updates a portfolio position using a stock symbol.
func (r *PortfolioRepository) AddPositionBySymbol(portfolioID string, symbol string, quantity float64, avgPrice float64) (*models.PortfolioPosition, error) {
	stockID, err := r.ensureStockID(symbol)
	if err != nil {
		return nil, err
	}

	query := `
		INSERT INTO portfolio_positions (portfolio_id, stock_id, quantity, avg_price)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (portfolio_id, stock_id) DO UPDATE SET
			quantity = EXCLUDED.quantity,
			avg_price = EXCLUDED.avg_price,
			updated_at = NOW()
		RETURNING id, portfolio_id, stock_id, quantity, avg_price, opened_at, created_at, updated_at
	`

	var p models.PortfolioPosition
	p.Symbol = symbol
	err = r.db.QueryRow(query, portfolioID, stockID, quantity, avgPrice).Scan(
		&p.ID,
		&p.PortfolioID,
		&p.StockID,
		&p.Quantity,
		&p.AvgPrice,
		&p.OpenedAt,
		&p.CreatedAt,
		&p.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to upsert portfolio position: %w", err)
	}
	return &p, nil
}

// UpdateHolding updates an existing holding
func (r *PortfolioRepository) UpdateHolding(holdingID string, updates map[string]interface{}) error {
	_ = holdingID
	_ = updates
	return fmt.Errorf("UpdateHolding not implemented for normalized schema")
}

// DeleteHolding deletes a holding
func (r *PortfolioRepository) DeleteHolding(holdingID string) error {
	query := `DELETE FROM portfolio_positions WHERE id = $1`
	_, err := r.db.Exec(query, holdingID)
	if err != nil {
		return fmt.Errorf("failed to delete portfolio position: %w", err)
	}
	return nil
}

// GetHoldingByID gets a holding by its ID
func (r *PortfolioRepository) GetHoldingByID(holdingID string) (*models.PortfolioPosition, error) {
	query := `
		SELECT pp.id, pp.portfolio_id, pp.stock_id, s.symbol, pp.quantity, pp.avg_price,
		       pp.opened_at, pp.created_at, pp.updated_at
		FROM portfolio_positions pp
		JOIN stocks s ON s.id = pp.stock_id
		WHERE pp.id = $1
	`

	var holding models.PortfolioPosition
	err := r.db.QueryRow(query, holdingID).Scan(
		&holding.ID,
		&holding.PortfolioID,
		&holding.StockID,
		&holding.Symbol,
		&holding.Quantity,
		&holding.AvgPrice,
		&holding.OpenedAt,
		&holding.CreatedAt,
		&holding.UpdatedAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("holding not found")
		}
		return nil, fmt.Errorf("failed to get holding: %w", err)
	}

	return &holding, nil
}
