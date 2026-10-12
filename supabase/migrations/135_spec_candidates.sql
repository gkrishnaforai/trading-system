-- spec_candidates — the incubator between the daily quality-mover
-- screen and engine membership. A name that keeps showing up on the
-- gainers list (institutional accumulation fingerprint) AND holds
-- the move AND stays structurally healthy graduates into
-- smallcap_members / rule_breaker_members at watch tier — the
-- engines own the thesis from there.

CREATE TABLE IF NOT EXISTS spec_candidates (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol         text NOT NULL,
    state          text NOT NULL DEFAULT 'incubating',
                   -- incubating | promoted | expired
    first_seen     date NOT NULL,
    last_seen      date NOT NULL,
    appearances    integer NOT NULL DEFAULT 0,
    best_chg_pct   double precision,
    admit_price    double precision,   -- close on the day admitted
    peak_price     double precision,   -- highest close since admission
    verdict        text,
    engine         text,               -- 5x-scout | rule-breakers
    mom_state      text,
    promoted_tier  text,
    expired_reason text,
    evidence       jsonb NOT NULL DEFAULT '{}',
    created_at     timestamptz DEFAULT now(),
    updated_at     timestamptz DEFAULT now(),
    UNIQUE (symbol, first_seen)        -- can re-enter after expiry
);

CREATE INDEX IF NOT EXISTS spec_candidates_state_idx
    ON spec_candidates (state, last_seen DESC);
