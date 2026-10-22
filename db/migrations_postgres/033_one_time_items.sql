-- One-time charge annotation for earnings prints. A legal settlement
-- or severance charge can turn a headline beat into a reported miss
-- (META Q2-26: EPS $6.18 vs $7.22 est, but $3.58B of legal+severance
-- charges → adjusted ~$7.35, a beat). The raw actual stays untouched
-- (it IS what printed, and graders need it); the adjusted view rides
-- alongside so verdict logic can stop treating a one-time hit as
-- business deterioration.

ALTER TABLE earnings_data
    ADD COLUMN IF NOT EXISTS one_time_items jsonb,
    ADD COLUMN IF NOT EXISTS adjusted_eps_actual numeric;
