-- Setup signal + outcome tracking: the learning loop.
-- Every swing review that detects a setup records a signal, a daily evaluator
-- fills in forward outcomes, pattern_stats aggregates empirical win rates
-- which feed a bounded calibration back into detect_setup scoring.

CREATE TABLE IF NOT EXISTS setup_signals (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          text NOT NULL,
    signal_date     date NOT NULL,
    setup_type      text NOT NULL,
    detected_patterns text[] DEFAULT '{}',
    price           double precision,
    entry           double precision,
    stop            double precision,
    target          double precision,
    reward_risk     double precision,
    atr_pct         double precision,
    regime          text,
    long_permission text,
    size_multiplier double precision,
    decision_action text,
    risk_status     text,
    features        jsonb DEFAULT '{}',
    source          text NOT NULL DEFAULT 'alert_review',
    run_id          text,
    fingerprint     text NOT NULL UNIQUE,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_setup_signals_sym_date ON setup_signals (symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_setup_signals_type ON setup_signals (setup_type, signal_date DESC);

CREATE TABLE IF NOT EXISTS setup_outcomes (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id       uuid NOT NULL REFERENCES setup_signals(id) ON DELETE CASCADE,
    horizon_bars    int NOT NULL,
    exit_reason     text,            -- target | stop | horizon_close | incomplete
    exit_price      double precision,
    mfe_pct         double precision, -- max favorable excursion vs entry
    mae_pct         double precision, -- max adverse excursion vs entry
    r_multiple      double precision, -- realized R: (exit-entry)/(entry-stop)
    bars_held       int,
    evaluated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (signal_id, horizon_bars)
);

-- Empirical pattern performance — feeds score calibration and the UI.
CREATE OR REPLACE VIEW pattern_stats AS
SELECT s.setup_type,
       o.horizon_bars,
       count(*)                                              AS n,
       avg(CASE WHEN o.r_multiple > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
       avg(o.r_multiple)                                     AS avg_r,
       avg(o.mfe_pct)                                        AS avg_mfe_pct,
       avg(o.mae_pct)                                        AS avg_mae_pct,
       max(s.signal_date)                                    AS last_signal_date
FROM setup_signals s
JOIN setup_outcomes o ON o.signal_id = s.id
WHERE o.exit_reason IS NOT NULL AND o.exit_reason <> 'incomplete'
GROUP BY s.setup_type, o.horizon_bars;
