-- TSM reports in TWD — revenue_estimate ~1.33e12 overflows
-- numeric(20,8) (max ~1.2e12 integer digits). Widen to 24.
ALTER TABLE fundamental_estimate_snapshots
    ALTER COLUMN revenue_estimate TYPE numeric(24,8),
    ALTER COLUMN eps_estimate TYPE numeric(24,8);
