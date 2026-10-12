-- Custodian — the support/self-healing agent layer.
-- Supervisor (custodian.py) → sensor/diagnoser/remediator workers.
-- Risk-tiered: T1/T2 auto-remediate bounded actions, T3 escalates to
-- the human on the board. Every action audited, every fix re-verified.
CREATE TABLE IF NOT EXISTS custodian_incidents (
    signature    text PRIMARY KEY,        -- 'job:momentum:error', 'stale:momentum'…
    source       text NOT NULL,           -- which sensor saw it
    severity     text NOT NULL,           -- low|medium|high
    status       text NOT NULL DEFAULT 'open',  -- open|mitigated|resolved|escalated
    detail       jsonb,
    diagnosis    text,
    remediation  text,
    attempts     int NOT NULL DEFAULT 0,
    occurrences  int NOT NULL DEFAULT 1,
    first_seen   timestamptz NOT NULL DEFAULT now(),
    last_seen    timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz
);
CREATE INDEX IF NOT EXISTS custodian_incidents_status_idx
    ON custodian_incidents (status) WHERE status != 'resolved';

CREATE TABLE IF NOT EXISTS custodian_actions (
    id         serial PRIMARY KEY,
    signature  text NOT NULL,
    action     text NOT NULL,             -- 'retry:momentum', 'kick:fund-flags'…
    tier       int NOT NULL,              -- 1 retry / 2 dependency / 3 escalate
    params     jsonb,
    result     text,
    created_at timestamptz NOT NULL DEFAULT now()
);
