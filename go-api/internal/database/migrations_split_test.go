package database

import (
	"strings"
	"testing"
)

// Regression: the comment branch used to eat the newline after "--",
// gluing the next line onto the comment; applyMigration then stripped
// the merged line and dropped the first line of the next statement
// (161_restore_dropped_live_tables incident).
func TestSplitSQLStatements_CommentThenStatement(t *testing.T) {
	sql := "-- blog_posts (from 001)\nCREATE TABLE IF NOT EXISTS blog_posts (\n  id UUID PRIMARY KEY\n);\n\nCREATE TABLE IF NOT EXISTS t2 (\n  a int\n);"
	stmts := splitSQLStatements(sql)
	if len(stmts) != 2 {
		t.Fatalf("want 2 statements, got %d: %v", len(stmts), stmts)
	}
	if !strings.Contains(stmts[0], "CREATE TABLE IF NOT EXISTS blog_posts") {
		t.Fatalf("statement 0 lost its CREATE line: %q", stmts[0])
	}
}

// Comments inside a column list must not eat the next column.
func TestSplitSQLStatements_InlineCommentInBody(t *testing.T) {
	sql := "CREATE TABLE t (\n  a int,  -- first col\n  b int\n);"
	stmts := splitSQLStatements(sql)
	if len(stmts) != 1 || !strings.Contains(stmts[0], "b int") {
		t.Fatalf("column after inline comment was lost: %v", stmts)
	}
}

// Block comments are opaque: quotes and semicolons inside /* ... */
// must not flip quote tracking or split statements.
func TestSplitSQLStatements_BlockCommentOpaque(t *testing.T) {
	sql := "/* it's; \"quoted\" */\nCREATE TABLE t (a int);\nCREATE TABLE u (b int);"
	stmts := splitSQLStatements(sql)
	if len(stmts) != 2 {
		t.Fatalf("want 2 statements, got %d: %v", len(stmts), stmts)
	}
}

// Existing protections keep working: apostrophes in line comments and
// semicolons inside string literals / dollar-quoted bodies.
func TestSplitSQLStatements_QuoteAndDollarSafety(t *testing.T) {
	sql := "-- it's a comment\nINSERT INTO t VALUES ('a;b');\n" +
		"CREATE FUNCTION f() RETURNS void AS $$ BEGIN RAISE NOTICE 'x;y'; END $$ LANGUAGE plpgsql;\n" +
		"SELECT 1;"
	stmts := splitSQLStatements(sql)
	if len(stmts) != 3 {
		t.Fatalf("want 3 statements, got %d: %v", len(stmts), stmts)
	}
}
