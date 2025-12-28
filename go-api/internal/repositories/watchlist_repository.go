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

// GetByUserID gets all watchlists for a user
func (r *WatchlistRepository) GetByUserID(userID string) ([]models.Watchlist, error) {
	query := `
		SELECT watchlist_id, user_id, watchlist_name, description, tags, 
		       is_default, subscription_level_required, created_at, updated_at
		FROM watchlists
		WHERE user_id = ?
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
			&w.WatchlistID,
			&w.UserID,
			&w.WatchlistName,
			&w.Description,
			&w.Tags,
			&w.IsDefault,
			&w.SubscriptionLevelRequired,
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
		SELECT watchlist_id, user_id, watchlist_name, description, tags,
		       is_default, subscription_level_required, created_at, updated_at
		FROM watchlists
		WHERE watchlist_id = ?
	`

	var w models.Watchlist
	err := r.db.QueryRow(query, watchlistID).Scan(
		&w.WatchlistID,
		&w.UserID,
		&w.WatchlistName,
		&w.Description,
		&w.Tags,
		&w.IsDefault,
		&w.SubscriptionLevelRequired,
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
		INSERT INTO watchlists 
		(watchlist_id, user_id, watchlist_name, description, tags, is_default, subscription_level_required)
		VALUES (?, ?, ?, ?, ?, ?, ?)
	`

	_, err := r.db.Exec(query,
		watchlist.WatchlistID,
		watchlist.UserID,
		watchlist.WatchlistName,
		watchlist.Description,
		watchlist.Tags,
		watchlist.IsDefault,
		watchlist.SubscriptionLevelRequired,
	)
	if err != nil {
		return fmt.Errorf("failed to create watchlist: %w", err)
	}

	// If this is set as default, unset other defaults for this user
	if watchlist.IsDefault {
		return r.setAsDefault(watchlist.WatchlistID, watchlist.UserID)
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
		"watchlist_name": true,
		"description":    true,
		"tags":           true,
		"is_default":     true,
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
	args = append(args, watchlistID)

	query := fmt.Sprintf("UPDATE watchlists SET %s WHERE watchlist_id = ?",
		strings.Join(setParts, ", "))

	_, err := r.db.Exec(query, args...)
	if err != nil {
		return fmt.Errorf("failed to update watchlist: %w", err)
	}

	// If is_default was set to true, unset other defaults
	if isDefault, ok := updates["is_default"].(bool); ok && isDefault {
		watchlist, err := r.GetByID(watchlistID)
		if err == nil {
			return r.setAsDefault(watchlistID, watchlist.UserID)
		}
	}

	return nil
}

// setAsDefault sets a watchlist as default and unsets others
func (r *WatchlistRepository) setAsDefault(watchlistID string, userID string) error {
	// Unset all defaults for this user
	_, err := r.db.Exec(
		"UPDATE watchlists SET is_default = 0 WHERE user_id = ? AND watchlist_id != ?",
		userID, watchlistID,
	)
	return err
}

// Delete deletes a watchlist
func (r *WatchlistRepository) Delete(watchlistID string) error {
	query := `DELETE FROM watchlists WHERE watchlist_id = ?`
	_, err := r.db.Exec(query, watchlistID)
	if err != nil {
		return fmt.Errorf("failed to delete watchlist: %w", err)
	}
	return nil
}

// GetItems gets all items in a watchlist
func (r *WatchlistRepository) GetItems(watchlistID string) ([]models.WatchlistItem, error) {
	query := `
		SELECT item_id, watchlist_id, stock_symbol, added_at, notes, priority, tags, alert_config
		FROM watchlist_items
		WHERE watchlist_id = ?
		ORDER BY priority DESC, added_at DESC
	`

	rows, err := r.db.Query(query, watchlistID)
	if err != nil {
		return nil, fmt.Errorf("failed to query watchlist items: %w", err)
	}
	defer rows.Close()

	var items []models.WatchlistItem
	for rows.Next() {
		var item models.WatchlistItem
		if err := rows.Scan(
			&item.ItemID,
			&item.WatchlistID,
			&item.StockSymbol,
			&item.AddedAt,
			&item.Notes,
			&item.Priority,
			&item.Tags,
			&item.AlertConfig,
		); err != nil {
			return nil, fmt.Errorf("failed to scan watchlist item: %w", err)
		}
		items = append(items, item)
	}

	return items, nil
}

// AddItem adds a stock to a watchlist
func (r *WatchlistRepository) AddItem(item *models.WatchlistItem) error {
	query := `
		INSERT OR REPLACE INTO watchlist_items 
		(item_id, watchlist_id, stock_symbol, notes, priority, tags, alert_config)
		VALUES (?, ?, ?, ?, ?, ?, ?)
	`

	_, err := r.db.Exec(query,
		item.ItemID,
		item.WatchlistID,
		item.StockSymbol,
		item.Notes,
		item.Priority,
		item.Tags,
		item.AlertConfig,
	)
	if err != nil {
		return fmt.Errorf("failed to add watchlist item: %w", err)
	}
	return nil
}

// UpdateItem updates a watchlist item
func (r *WatchlistRepository) UpdateItem(itemID string, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return nil
	}

	setParts := []string{}
	args := []interface{}{}

	allowedFields := map[string]bool{
		"notes":       true,
		"priority":    true,
		"tags":        true,
		"alert_config": true,
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

	args = append(args, itemID)

	query := fmt.Sprintf("UPDATE watchlist_items SET %s WHERE item_id = ?",
		strings.Join(setParts, ", "))

	_, err := r.db.Exec(query, args...)
	if err != nil {
		return fmt.Errorf("failed to update watchlist item: %w", err)
	}
	return nil
}

// RemoveItem removes a stock from a watchlist
func (r *WatchlistRepository) RemoveItem(itemID string) error {
	query := `DELETE FROM watchlist_items WHERE item_id = ?`
	_, err := r.db.Exec(query, itemID)
	if err != nil {
		return fmt.Errorf("failed to remove watchlist item: %w", err)
	}
	return nil
}

// RemoveItemBySymbol removes a stock from a watchlist by symbol
func (r *WatchlistRepository) RemoveItemBySymbol(watchlistID string, stockSymbol string) error {
	query := `DELETE FROM watchlist_items WHERE watchlist_id = ? AND stock_symbol = ?`
	_, err := r.db.Exec(query, watchlistID, stockSymbol)
	if err != nil {
		return fmt.Errorf("failed to remove watchlist item: %w", err)
	}
	return nil
}

