-- Enable required PostgreSQL extensions
-- This should run first before other migrations

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable crypto extension for password hashing
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable pg_stat_statements for query statistics (optional)
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

