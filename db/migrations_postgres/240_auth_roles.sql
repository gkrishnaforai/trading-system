-- 240_auth_roles.sql — roles catalog + name fields for real sign-up.
--
-- users.role was a free-text VARCHAR defaulting to 'user'. Now that
-- accounts are created by humans (not just the device account), the
-- role set becomes a catalog table so new tiers are data, not code:
--
--   basic        portfolio page only (the default every signup gets)
--   advanced     portfolio + the read surfaces (regime, board, ...)
--   super-user   advanced + heavier/compute surfaces later
--   admin        everything incl. ops (/admin, job controls)
--
-- rank orders the tiers — "at least advanced" = rank >= 20. New tiers
-- slot between ranks without touching the check.

CREATE TABLE IF NOT EXISTS roles (
  name        TEXT PRIMARY KEY,
  rank        INT  NOT NULL UNIQUE,
  description TEXT
);

INSERT INTO roles (name, rank, description) VALUES
  ('basic',      10, 'portfolio page only — default for every signup'),
  ('advanced',   20, 'portfolio + all read surfaces'),
  ('super-user', 30, 'advanced + heavy/compute surfaces'),
  ('admin',      40, 'full access incl. ops surfaces')
ON CONFLICT (name) DO NOTHING;

-- name fields for the signup form (full_name stays — display string)
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name  TEXT;

-- normalize: the old default 'user' meant "regular account" = basic,
-- and anything else outside the catalog would break the FK below
UPDATE users SET role = 'basic'
 WHERE role NOT IN (SELECT name FROM roles);
ALTER TABLE users ALTER COLUMN role SET DEFAULT 'basic';

-- role must be a catalog entry going forward
ALTER TABLE users
  ADD CONSTRAINT users_role_fkey
  FOREIGN KEY (role) REFERENCES roles(name);
