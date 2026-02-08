package repositories

import (
	"database/sql"
	"fmt"

	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/models"
)

type UserRepository struct {
	db *sql.DB
}

func NewUserRepository() *UserRepository {
	return &UserRepository{
		db: database.DB,
	}
}

func (r *UserRepository) ListUsers(limit int) ([]models.User, error) {
	query := `
		SELECT id AS user_id, username, email, 'basic' AS subscription_level, created_at, updated_at
		FROM users
		ORDER BY created_at DESC
		LIMIT $1
	`

	if limit <= 0 {
		limit = 100
	}

	rows, err := r.db.Query(query, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list users: %w", err)
	}
	defer rows.Close()

	users := []models.User{}
	for rows.Next() {
		u := models.User{}
		if err := rows.Scan(
			&u.UserID,
			&u.Username,
			&u.Email,
			&u.SubscriptionLevel,
			&u.CreatedAt,
			&u.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan user: %w", err)
		}
		users = append(users, u)
	}

	return users, nil
}

func (r *UserRepository) GetByID(userID string) (*models.User, error) {
	query := `
		SELECT id AS user_id, username, email, 'basic' AS subscription_level, created_at, updated_at
		FROM users
		WHERE id = $1
	`

	user := &models.User{}
	err := r.db.QueryRow(query, userID).Scan(
		&user.UserID,
		&user.Username,
		&user.Email,
		&user.SubscriptionLevel,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("user not found")
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get user: %w", err)
	}

	return user, nil
}

func (r *UserRepository) UpdateEmail(userID string, email string) (*models.User, error) {
	updateQuery := `
		UPDATE users
		SET email = $2,
			updated_at = NOW()
		WHERE id = $1
	`

	res, err := r.db.Exec(updateQuery, userID, email)
	if err != nil {
		return nil, fmt.Errorf("failed to update email: %w", err)
	}

	rowsAffected, err := res.RowsAffected()
	if err != nil {
		return nil, fmt.Errorf("failed to read rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return nil, fmt.Errorf("user not found")
	}

	updated, err := r.GetByID(userID)
	if err != nil {
		return nil, err
	}
	return updated, nil
}

func (r *UserRepository) GetByEmail(email string) (*models.User, error) {
	query := `
		SELECT id AS user_id, username, email, 'basic' AS subscription_level, created_at, updated_at
		FROM users
		WHERE email = $1
	`

	user := &models.User{}
	err := r.db.QueryRow(query, email).Scan(
		&user.UserID,
		&user.Username,
		&user.Email,
		&user.SubscriptionLevel,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("user not found")
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get user: %w", err)
	}

	return user, nil
}
