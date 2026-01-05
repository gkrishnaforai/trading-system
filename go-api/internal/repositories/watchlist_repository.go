package repositories

import (
	"database/sql"
	"fmt"
	"strings"

	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/models"
)

type WatchlistRepository struct {
	db *sql.DB
}

func NewWatchlistRepository() *WatchlistRepository {
	return &WatchlistRepository{
		db: database.DB,
	}
}

func (r *WatchlistRepository) ensureStockID(symbol string) (string, error) {
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

// GetByUserID gets all watchlists for a user
func (r *WatchlistRepository) GetByUserID(userID string) ([]models.Watchlist, error) {
	query := `
		SELECT id, user_id, name, description, is_default, is_archived, created_at, updated_at
		FROM watchlists
		WHERE user_id = $1
		ORDER BY is_default DESC, created_at DESC
	`

	rows, err := r.db.Query(query, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to query watchlists: %w", err)
	}
	defer rows.Close()

	var watchlists []models.Watchlist
	for rows.Next() {
		var w models.Watchlist
		if err := rows.Scan(
			&w.ID,
			&w.UserID,
			&w.Name,
			&w.Description,
			&w.IsDefault,
			&w.IsArchived,
			&w.CreatedAt,
			&w.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan watchlist: %w", err)
		}
		watchlists = append(watchlists, w)
	}

	return watchlists, nil
}

// GetByID gets a watchlist by ID
func (r *WatchlistRepository) GetByID(watchlistID string) (*models.Watchlist, error) {
	query := `
		SELECT id, user_id, name, description, is_default, is_archived, created_at, updated_at
		FROM watchlists
		WHERE id = $1
	`

	var w models.Watchlist
	err := r.db.QueryRow(query, watchlistID).Scan(
		&w.ID,
		&w.UserID,
		&w.Name,
		&w.Description,
		&w.IsDefault,
		&w.IsArchived,
		&w.CreatedAt,
		&w.UpdatedAt,
	)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("watchlist not found")
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get watchlist: %w", err)
	}

	return &w, nil
}

// Create creates a new watchlist
func (r *WatchlistRepository) Create(watchlist *models.Watchlist) error {
	query := `
		INSERT INTO watchlists (user_id, name, description, is_default)
		VALUES ($1, $2, $3, $4)
		RETURNING id, created_at, updated_at
	`

	err := r.db.QueryRow(query,
		watchlist.UserID,
		watchlist.Name,
		watchlist.Description,
		watchlist.IsDefault,
	).Scan(&watchlist.ID, &watchlist.CreatedAt, &watchlist.UpdatedAt)
	if err != nil {
		return fmt.Errorf("failed to create watchlist: %w", err)
	}
	return nil
}

// Update updates a watchlist
func (r *WatchlistRepository) Update(watchlistID string, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return nil
	}

	setParts := []string{}
	args := []interface{}{}

	allowedFields := map[string]bool{
		"name":        true,
		"description": true,
		"is_default":  true,
		"is_archived": true,
	}

	for field, value := range updates {
		if allowedFields[field] {
			setParts = append(setParts, fmt.Sprintf("%s = $%d", field, len(args)+1))
			args = append(args, value)
		}
	}

	if len(setParts) == 0 {
		return nil
	}

	setParts = append(setParts, "updated_at = CURRENT_TIMESTAMP")
	args = append(args, watchlistID)

	query := fmt.Sprintf(
		"UPDATE watchlists SET %s WHERE id = $%d",
		strings.Join(setParts, ", "),
		len(args),
	)

	_, err := r.db.Exec(query, args...)
	if err != nil {
		return fmt.Errorf("failed to update watchlist: %w", err)
	}

	// If is_default was set to true, unset other defaults
	return nil
}

// Delete deletes a watchlist
func (r *WatchlistRepository) Delete(watchlistID string) error {
	query := `DELETE FROM watchlists WHERE id = $1`
	_, err := r.db.Exec(query, watchlistID)
	if err != nil {
		return fmt.Errorf("failed to delete watchlist: %w", err)
	}
	return nil
}

// GetItems gets all items in a watchlist
func (r *WatchlistRepository) GetItems(watchlistID string) ([]models.WatchlistStock, error) {
	query := `
		SELECT ws.id, ws.watchlist_id, ws.stock_id, s.symbol, ws.added_at, ws.created_at, ws.updated_at
		FROM watchlist_stocks ws
		JOIN stocks s ON s.id = ws.stock_id
		WHERE ws.watchlist_id = $1
		ORDER BY ws.added_at DESC
	`

	rows, err := r.db.Query(query, watchlistID)
	if err != nil {
		return nil, fmt.Errorf("failed to query watchlist items: %w", err)
	}
	defer rows.Close()

	var items []models.WatchlistStock
	for rows.Next() {
		var item models.WatchlistStock
		if err := rows.Scan(
			&item.ID,
			&item.WatchlistID,
			&item.StockID,
			&item.Symbol,
			&item.AddedAt,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan watchlist item: %w", err)
		}
		items = append(items, item)
	}

	return items, nil
}

// AddStock adds a stock (by symbol) to a watchlist.
func (r *WatchlistRepository) AddStock(watchlistID string, symbol string) (*models.WatchlistStock, error) {
	stockID, err := r.ensureStockID(symbol)
	if err != nil {
		return nil, err
	}

	query := `
		INSERT INTO watchlist_stocks (watchlist_id, stock_id)
		VALUES ($1, $2)
		ON CONFLICT (watchlist_id, stock_id) DO UPDATE SET updated_at = NOW()
		RETURNING id, watchlist_id, stock_id, added_at, created_at, updated_at
	`

	var ws models.WatchlistStock
	ws.Symbol = symbol
	err = r.db.QueryRow(query, watchlistID, stockID).Scan(
		&ws.ID,
		&ws.WatchlistID,
		&ws.StockID,
		&ws.AddedAt,
		&ws.CreatedAt,
		&ws.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to add watchlist stock: %w", err)
	}
	return &ws, nil
}

// UpdateItem updates a watchlist stock record (metadata only).
func (r *WatchlistRepository) UpdateItem(itemID string, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return nil
	}

	setParts := []string{}
	args := []interface{}{}

	allowedFields := map[string]bool{
		"metadata": true,
	}

	for field, value := range updates {
		if allowedFields[field] {
			setParts = append(setParts, fmt.Sprintf("%s = $%d", field, len(args)+1))
			args = append(args, value)
		}
	}

	if len(setParts) == 0 {
		return nil
	}

	setParts = append(setParts, "updated_at = NOW()")
	args = append(args, itemID)

	query := fmt.Sprintf(
		"UPDATE watchlist_stocks SET %s WHERE id = $%d",
		strings.Join(setParts, ", "),
		len(args),
	)

	_, err := r.db.Exec(query, args...)
	if err != nil {
		return fmt.Errorf("failed to update watchlist stock: %w", err)
	}
	return nil
}

// RemoveItem removes a stock from a watchlist
func (r *WatchlistRepository) RemoveItem(itemID string) error {
	query := `DELETE FROM watchlist_stocks WHERE id = $1`
	_, err := r.db.Exec(query, itemID)
	if err != nil {
		return fmt.Errorf("failed to remove watchlist item: %w", err)
	}
	return nil
}

// RemoveItemBySymbol removes a stock from a watchlist by symbol.
func (r *WatchlistRepository) RemoveItemBySymbol(watchlistID string, stockSymbol string) error {
	stockID, err := r.ensureStockID(stockSymbol)
	if err != nil {
		return err
	}
	query := `DELETE FROM watchlist_stocks WHERE watchlist_id = $1 AND stock_id = $2`
	_, err = r.db.Exec(query, watchlistID, stockID)
	if err != nil {
		return fmt.Errorf("failed to remove watchlist stock: %w", err)
	}
	return nil
}

// GetItemByID gets a watchlist stock by its ID
func (r *WatchlistRepository) GetItemByID(itemID string) (*models.WatchlistStock, error) {
	query := `
		SELECT ws.id, ws.watchlist_id, ws.stock_id, s.symbol, ws.added_at, ws.created_at, ws.updated_at
		FROM watchlist_stocks ws
		JOIN stocks s ON s.id = ws.stock_id
		WHERE ws.id = $1
	`

	var item models.WatchlistStock
	err := r.db.QueryRow(query, itemID).Scan(
		&item.ID,
		&item.WatchlistID,
		&item.StockID,
		&item.Symbol,
		&item.AddedAt,
		&item.CreatedAt,
		&item.UpdatedAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("watchlist item not found")
		}
		return nil, fmt.Errorf("failed to get watchlist item: %w", err)
	}

	return &item, nil
}
