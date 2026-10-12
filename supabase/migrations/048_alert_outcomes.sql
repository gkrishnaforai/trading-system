-- Alert outcome evaluation — the honesty loop for the alert feed.
-- Mirrors setup_signals → setup_outcomes: for each persisted alert, record
-- forward returns at fixed horizons so we can measure which event types
-- actually precede moves vs post-move commentary.

CREATE TABLE IF NOT EXISTS alert_outcomes (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id      uuid NOT NULL REFERENCES alert_items(id) ON DELETE CASCADE,
    horizon_days  integer NOT NULL,
    entry_price   numeric,
    ret_pct       numeric,
    mfe_pct       numeric,
    mae_pct       numeric,
    evaluated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (alert_id, horizon_days)
);

CREATE INDEX IF NOT EXISTS idx_alert_outcomes_alert
    ON alert_outcomes (alert_id);

-- Per event_type × direction × horizon rollup — which alert kinds predict.
CREATE OR REPLACE VIEW alert_stats AS
SELECT a.event_type,
       a.direction,
       o.horizon_days,
       count(*) AS n,
       round(avg(o.ret_pct)::numeric, 2) AS avg_ret_pct,
       round(avg(o.mfe_pct)::numeric, 2) AS avg_mfe_pct,
       round(avg(o.mae_pct)::numeric, 2) AS avg_mae_pct,
       round(avg(CASE WHEN o.ret_pct > 0 THEN 1.0 ELSE 0.0 END)::numeric, 3) AS win_rate,
       max(a.created_at)::date AS last_alert_date
FROM alert_outcomes o
JOIN alert_items a ON a.id = o.alert_id
GROUP BY a.event_type, a.direction, o.horizon_days;
