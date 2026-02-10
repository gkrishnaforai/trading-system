package database

import (
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Migration represents a database migration
type Migration struct {
	Version int
	File    string
	SQL     string
}

// RunMigrations runs all pending database migrations
func RunMigrations() error {
	log.Println("📝 Checking for pending migrations...")

	// Get migrations directory
	migrationsDir := os.Getenv("MIGRATIONS_DIR")
	if migrationsDir == "" {
		// Try common locations
		possibleDirs := []string{
			"./db/migrations",
			"/app/db/migrations",
			"../db/migrations",
		}
		for _, dir := range possibleDirs {
			if _, err := os.Stat(dir); err == nil {
				migrationsDir = dir
				break
			}
		}
		if migrationsDir == "" {
			return fmt.Errorf("migrations directory not found. Set MIGRATIONS_DIR environment variable")
		}
	}

	log.Printf("📁 Using migrations directory: %s", migrationsDir)

	// Read all migration files
	migrations, err := readMigrations(migrationsDir)
	if err != nil {
		return fmt.Errorf("failed to read migrations: %w", err)
	}

	if len(migrations) == 0 {
		log.Println("ℹ️  No migration files found")
		return nil
	}

	// Create migrations tracking table if it doesn't exist
	if err := createMigrationsTable(); err != nil {
		return fmt.Errorf("failed to create migrations table: %w", err)
	}

	// Get applied migrations
	applied, err := getAppliedMigrations()
	if err != nil {
		return fmt.Errorf("failed to get applied migrations: %w", err)
	}

	// Run pending migrations
	pendingCount := 0
	for _, migration := range migrations {
		if applied[migration.File] {
			log.Printf("⏭️  Migration %03d already applied: %s", migration.Version, migration.File)
			continue
		}

		log.Printf("🔄 Applying migration %03d: %s", migration.Version, migration.File)
		if err := applyMigration(migration); err != nil {
			return fmt.Errorf("failed to apply migration %03d (%s): %w", migration.Version, migration.File, err)
		}

		if err := recordMigration(migration.Version, migration.File); err != nil {
			return fmt.Errorf("failed to record migration %03d: %w", migration.Version, err)
		}

		log.Printf("✅ Applied migration %03d: %s", migration.Version, migration.File)
		pendingCount++
	}

	if pendingCount > 0 {
		log.Printf("✅ Applied %d migration(s)", pendingCount)
	} else {
		log.Println("✅ All migrations are up to date")
	}

	return nil
}

// readMigrations reads all migration files from the directory
func readMigrations(dir string) ([]Migration, error) {
	files, err := ioutil.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("failed to read migrations directory: %w", err)
	}

	var migrations []Migration
	for _, file := range files {
		if file.IsDir() {
			continue
		}

		// Migration files should be named like: 001_initial_schema.sql
		if !strings.HasSuffix(file.Name(), ".sql") {
			continue
		}

		// Extract version number from filename (first 3 digits)
		var version int
		if _, err := fmt.Sscanf(file.Name(), "%03d_", &version); err != nil {
			log.Printf("⚠️  Skipping migration file with invalid name format: %s", file.Name())
			continue
		}

		// Read migration SQL
		path := filepath.Join(dir, file.Name())
		sql, err := ioutil.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("failed to read migration file %s: %w", file.Name(), err)
		}

		migrations = append(migrations, Migration{
			Version: version,
			File:    file.Name(),
			SQL:     string(sql),
		})
	}

	// Sort by version
	sort.Slice(migrations, func(i, j int) bool {
		return migrations[i].Version < migrations[j].Version
	})

	return migrations, nil
}

// createMigrationsTable creates the migrations tracking table
func createMigrationsTable() error {
	log.Println("🔧 Creating migrations tracking table...")
	query := `
		CREATE TABLE IF NOT EXISTS public.schema_migrations (
			migration_name TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		);
	`
	_, err := DB.Exec(query)
	if err != nil {
		log.Printf("❌ Failed to create migrations table: %v", err)
		return err
	}
	log.Println("✅ Migrations table created/verified")
	return err
}

// getAppliedMigrations returns a map of applied migration filenames.
//
// Compatibility:
// - Postgres/Python worker uses schema_migrations(migration_name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)
// - Legacy Go migrations used schema_migrations(version INTEGER PRIMARY KEY, filename TEXT, applied_at TIMESTAMP)
func getAppliedMigrations() (map[string]bool, error) {
	log.Println("📋 Checking applied migrations...")

	// Preferred: migration_name-based tracking (used by python-worker)
	rows, err := DB.Query(`SELECT migration_name FROM schema_migrations`)
	if err == nil {
		defer rows.Close()
		applied := make(map[string]bool)
		count := 0
		for rows.Next() {
			var name string
			if err := rows.Scan(&name); err != nil {
				return nil, err
			}
			applied[name] = true
			count++
		}
		log.Printf("✅ Found %d applied migrations", count)
		return applied, nil
	}

	// Fallback: legacy version-based tracking
	rows, err = DB.Query(`SELECT filename FROM schema_migrations`)
	if err != nil {
		log.Printf("❌ Failed to query applied migrations: %v", err)
		return nil, err
	}
	defer rows.Close()

	applied := make(map[string]bool)
	count := 0
	for rows.Next() {
		var filename string
		if err := rows.Scan(&filename); err != nil {
			return nil, err
		}
		applied[filename] = true
		count++
	}

	log.Printf("✅ Found %d applied migrations", count)
	return applied, nil
}

// applyMigration applies a single migration
func applyMigration(migration Migration) error {
	// SQLite requires transactions for multi-statement migrations
	tx, err := DB.Begin()
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	// Execute migration SQL
	// Split by semicolon but be careful with semicolons inside strings
	statements := splitSQLStatements(migration.SQL)

	for _, stmt := range statements {
		stmt = strings.TrimSpace(stmt)
		if stmt == "" {
			continue
		}

		// Remove single-line comments
		lines := strings.Split(stmt, "\n")
		var cleanLines []string
		for _, line := range lines {
			trimmed := strings.TrimSpace(line)
			// Skip empty lines and comments
			if trimmed == "" || strings.HasPrefix(trimmed, "--") {
				continue
			}
			cleanLines = append(cleanLines, line)
		}
		cleanStmt := strings.Join(cleanLines, "\n")
		cleanStmt = strings.TrimSpace(cleanStmt)
		if cleanStmt == "" {
			continue
		}

		_, err := tx.Exec(cleanStmt)
		if err != nil {
			// Fail fast - no workarounds, no fallbacks
			// If migration fails, rollback and return error
			return fmt.Errorf("failed to execute migration statement: %w\nStatement: %s", err, cleanStmt)
		}
	}

	// Commit transaction
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit migration transaction: %w", err)
	}

	return nil
}

// splitSQLStatements splits SQL by semicolons.
//
// It must *not* split inside:
// - single-quoted strings: '...'
// - dollar-quoted blocks: $$ ... $$ or $tag$ ... $tag$ (used by PL/pgSQL)
func splitSQLStatements(sql string) []string {
	var statements []string
	var current strings.Builder

	inSingleQuote := false
	dollarTag := "" // e.g. "$$" or "$func$"; empty means not inside a dollar-quoted block

	bytes := []byte(sql)
	for i := 0; i < len(bytes); i++ {
		c := bytes[i]

		// Inside dollar-quoted block: only look for the closing tag.
		if dollarTag != "" {
			if i+len(dollarTag) <= len(bytes) && string(bytes[i:i+len(dollarTag)]) == dollarTag {
				current.WriteString(dollarTag)
				i += len(dollarTag) - 1
				dollarTag = ""
				continue
			}
			current.WriteByte(c)
			continue
		}

		// Inside single-quoted string: handle doubled quotes '' (SQL escaping).
		if inSingleQuote {
			if c == '\'' {
				// If next char is also a single quote, it's an escaped quote.
				if i+1 < len(bytes) && bytes[i+1] == '\'' {
					current.WriteByte(c)
					current.WriteByte(bytes[i+1])
					i++
					continue
				}
				inSingleQuote = false
				current.WriteByte(c)
				continue
			}
			current.WriteByte(c)
			continue
		}

		// Not inside any quoted context.
		if c == '\'' {
			inSingleQuote = true
			current.WriteByte(c)
			continue
		}

		// Start of a dollar-quoted tag: $$ or $tag$
		if c == '$' {
			// Find the next '$' to determine the tag.
			j := i + 1
			for j < len(bytes) {
				if bytes[j] == '$' {
					dollarTag = string(bytes[i : j+1])
					current.WriteString(dollarTag)
					i = j
					break
				}
				// Dollar tags cannot contain whitespace/newlines; bail early.
				if bytes[j] == '\n' || bytes[j] == '\r' || bytes[j] == '\t' || bytes[j] == ' ' {
					break
				}
				j++
			}
			if dollarTag != "" {
				continue
			}
			current.WriteByte(c)
			continue
		}

		if c == ';' {
			stmt := strings.TrimSpace(current.String())
			if stmt != "" {
				statements = append(statements, stmt)
			}
			current.Reset()
			continue
		}

		current.WriteByte(c)
	}

	stmt := strings.TrimSpace(current.String())
	if stmt != "" {
		statements = append(statements, stmt)
	}

	return statements
}

// recordMigration records that a migration has been applied
func recordMigration(version int, filename string) error {
	dbURL := os.Getenv("DATABASE_URL")
	if strings.HasPrefix(dbURL, "postgresql://") || strings.HasPrefix(dbURL, "postgres://") {
		// Preferred: migration_name schema (python-worker compatible)
		_, err := DB.Exec(
			`INSERT INTO schema_migrations (migration_name) VALUES ($1) ON CONFLICT (migration_name) DO NOTHING`,
			filename,
		)
		if err == nil {
			return nil
		}

		// Fallback: legacy schema
		query := `
			INSERT INTO schema_migrations (version, filename)
			VALUES ($1, $2)
			ON CONFLICT (version) DO NOTHING
		`
		_, err2 := DB.Exec(query, version, filename)
		return err2
	}

	// SQLite / non-postgres
	_, err := DB.Exec(
		`INSERT OR IGNORE INTO schema_migrations (migration_name) VALUES (?)`,
		filename,
	)
	if err == nil {
		return nil
	}

	// Fallback legacy SQLite schema
	query := `
		INSERT OR IGNORE INTO schema_migrations (version, filename)
		VALUES (?, ?)
	`
	_, err2 := DB.Exec(query, version, filename)
	return err2
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
