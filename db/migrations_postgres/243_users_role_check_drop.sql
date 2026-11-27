-- 243_users_role_check_drop.sql — retire the stale role CHECK.
--
-- The deployed users table still carries users_role_check from an
-- older schema lineage: role IN ('admin','user','premium'). The 240
-- role catalog made 'basic' the default and FK'd role to roles — but
-- never dropped the old CHECK, so every 'basic'/'advanced'/
-- 'super-user' insert fails the constraint and signups 500.
-- The FK is the authority now; the CHECK is dropped.

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
