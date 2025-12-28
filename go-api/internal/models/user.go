package models

import "time"

// User represents a user in the system
type User struct {
	UserID           string    `json:"user_id" db:"user_id"`
	Username         string    `json:"username" db:"username"`
	Email            string    `json:"email" db:"email"`
	PasswordHash     string    `json:"-" db:"password_hash"`
	SubscriptionLevel string   `json:"subscription_level" db:"subscription_level"`
	CreatedAt        time.Time `json:"created_at" db:"created_at"`
	UpdatedAt        time.Time `json:"updated_at" db:"updated_at"`
}

// SubscriptionLevel constants
const (
	SubscriptionBasic = "basic"
	SubscriptionPro   = "pro"
	SubscriptionElite = "elite"
)

// HasAccess checks if user has access to a feature level
func (u *User) HasAccess(requiredLevel string) bool {
	levels := map[string]int{
		SubscriptionBasic: 1,
		SubscriptionPro:    2,
		SubscriptionElite:  3,
	}
	return levels[u.SubscriptionLevel] >= levels[requiredLevel]
}

