-- fed_path engine journal — every daily rate-decision forecast,
-- versioned + gradable. Grading columns filled by meta_learn once
-- the FOMC outcome is known (Brier-style: was the top class right?
-- was expected_bps close to the realized move?).
CREATE TABLE IF NOT EXISTS fed_predictions (
    id               bigserial PRIMARY KEY,
    as_of            date NOT NULL UNIQUE,
    meeting_date     date,
    p_hike           int,
    p_hold           int,
    p_cut            int,
    expected_bps     double precision,
    lean_3_6m        text,
    expected_bps_3_6m double precision,
    confidence       text,
    payload          jsonb NOT NULL,
    rules_version    text,
    -- grading (filled after the meeting)
    actual_decision  text,               -- hike|hold|cut|emergency
    actual_bps       double precision,
    top_correct      boolean,
    graded_at        timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fed_pred_meeting_idx
    ON fed_predictions (meeting_date);

-- the job itself — before morning-regime so the card picks it up
INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES ('fed-path', 'Fed path — rate decision probabilities',
        'IRX/FRED → hike/hold/cut odds + 3-6m lean, journaled',
        '30 13 * * 1-5', true, '{momentum}', 24, 15, 70)
ON CONFLICT (name) DO NOTHING;
