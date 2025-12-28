#!/bin/bash
# Convert SQLite migrations to PostgreSQL compatible

echo "🔄 Converting SQLite migrations to PostgreSQL..."

# Backup original migrations
mkdir -p ../migrations_sqlite_backup
cp *.sql ../migrations_sqlite_backup/ 2>/dev/null || true

# Convert AUTOINCREMENT to SERIAL/BIGSERIAL
for file in *.sql; do
    if [[ "$file" != *"postgres"* ]]; then
        echo "📝 Converting $file..."
        # Replace INTEGER PRIMARY KEY AUTOINCREMENT with BIGSERIAL PRIMARY KEY
        sed -i.bak 's/INTEGER PRIMARY KEY AUTOINCREMENT/BIGSERIAL PRIMARY KEY/g' "$file"
        # Replace id INTEGER PRIMARY KEY with id BIGSERIAL PRIMARY KEY (for cases where AUTOINCREMENT was implied)
        sed -i.bak 's/id INTEGER PRIMARY KEY,/id BIGSERIAL PRIMARY KEY,/g' "$file"
        echo "✅ Converted $file"
    fi
done

echo "🎯 Migration conversion complete!"
echo "📁 Original files backed up to ../migrations_sqlite_backup/"
echo "📁 .bak files created for each modified file"
