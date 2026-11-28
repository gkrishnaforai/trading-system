-- 244_email_verified.sql — email ownership proof on the account.
--
-- Signup proves only that someone typed an address; verification
-- proves they can read mail sent to it. A verified flag rides the
-- session JWT so the UI can nag/lock without extra round-trips.
-- Existing operator accounts are grandfathered verified — they were
-- created outside the signup flow.

ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;

-- operator/seeded accounts predate the flow — mark them verified
UPDATE users SET email_verified = true, email_verified_at = NOW()
 WHERE email_verified_at IS NULL;
