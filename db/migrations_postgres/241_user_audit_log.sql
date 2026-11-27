-- 241_user_audit_log.sql — who did what, when.
--
-- One table covers both asks: sign-in history (login, login_failed,
-- signup, logout) and action history (portfolio/holding mutations).
-- user_id is nullable — a failed login for a nonexistent email still
-- gets journaled (it's the interesting half of the ledger); email is
-- denormalized on every row so the admin view reads cleanly even
-- when user_id is null or the account is later deleted.

CREATE TABLE IF NOT EXISTS user_audit_log (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  email       TEXT,
  event       TEXT NOT NULL,
  detail      JSONB NOT NULL DEFAULT '{}',
  ip          TEXT,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user ON user_audit_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event ON user_audit_log (event, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_time ON user_audit_log (created_at DESC);
