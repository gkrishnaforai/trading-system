package database

import (
	"database/sql"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
	_ "github.com/mattn/go-sqlite3"
)

var DB *sql.DB

// InitDB initializes the database connection
func InitDB() error {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgresql://trading:trading-dev@localhost:5432/trading-system?sslmode=disable"
	}

	var err error
	var driver string

	// Detect driver from URL
	if strings.HasPrefix(dbURL, "postgresql://") || strings.HasPrefix(dbURL, "postgres://") {
		driver = "pgx"
	} else {
		driver = "sqlite3"
		// Handle SQLite file path
		if dbURL == "file:./db/trading.db" || dbURL == "" {
			// Ensure directory exists
			if err := os.MkdirAll("./db", 0755); err != nil {
				return fmt.Errorf("failed to create db directory: %w", err)
			}
			dbURL = "./db/trading.db"
		}
		// Remove file: prefix if present
		if len(dbURL) > 5 && dbURL[:5] == "file:" {
			dbURL = dbURL[5:]
		}
	}

	if driver == "pgx" {
		config, err := pgx.ParseConfig(dbURL)
		if err != nil {
			return fmt.Errorf("failed to parse database url: %w", err)
		}
		// Avoid prepared statement issues with PgBouncer/transaction pooling.
		config.DefaultQueryExecMode = pgx.QueryExecModeSimpleProtocol
		DB = stdlib.OpenDB(*config)
	} else {
		DB, err = sql.Open(driver, dbURL)
		if err != nil {
			return fmt.Errorf("failed to open database: %w", err)
		}
	}

	// Test connection
	if err := DB.Ping(); err != nil {
		return fmt.Errorf("failed to ping database: %w", err)
	}

	// Set connection pool settings
	maxOpen := 10
	if v := strings.TrimSpace(os.Getenv("DB_MAX_OPEN_CONNS")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			maxOpen = n
		}
	}
	maxIdle := 5
	if v := strings.TrimSpace(os.Getenv("DB_MAX_IDLE_CONNS")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			maxIdle = n
		}
	}
	DB.SetMaxOpenConns(maxOpen)
	DB.SetMaxIdleConns(maxIdle)

	log.Println("✅ Database connection established")

	// Run migrations
	if err := RunMigrations(); err != nil {
		return fmt.Errorf("failed to run migrations: %w", err)
	}

	return nil
}

// CloseDB closes the database connection
func CloseDB() error {
	if DB != nil {
		return DB.Close()
	}
	return nil
}
