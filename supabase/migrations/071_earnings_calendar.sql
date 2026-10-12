-- Earnings calendar: extend the existing stocks.next_earnings_* property
-- block (date/session/source already exist via earnings_index_service)
-- with consensus estimates for the upcoming print. History lives in the
-- earnings_data event table; the alert scanner owns earnings alerts.

ALTER TABLE stocks
    ADD COLUMN IF NOT EXISTS next_earnings_eps_est DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS next_earnings_rev_est BIGINT;

ALTER TABLE stocks
    DROP COLUMN IF EXISTS earnings_session,
    DROP COLUMN IF EXISTS earnings_alerted_for,
    DROP COLUMN IF EXISTS earnings_cal_updated_at;

CREATE INDEX IF NOT EXISTS idx_stocks_next_earnings
    ON stocks(next_earnings_date)
    WHERE next_earnings_date IS NOT NULL;
