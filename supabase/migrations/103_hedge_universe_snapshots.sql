-- Hedge-universe daily journal — the four-bucket LEAP-put scan
-- (vulnerability / vol-discount / convexity / hedge-correlation) plus
-- the exact-contract ROI scenario, frozen nightly so candidates can
-- be graded: "when the target fell, did the named hedge pay?"
CREATE TABLE IF NOT EXISTS hedge_universe_snapshots (
    id             bigserial PRIMARY KEY,
    snap_date      date NOT NULL,
    symbol         text NOT NULL,
    hedge_target   text NOT NULL,
    engine_version text,               -- hedge_v1, v2...
    score          double precision,   -- final four-bucket score
    tier           text,               -- prime|watch|poor|no
    spot           double precision,
    beta_qqq       double precision,
    hv20           double precision,   -- realized vol, annualized
    atm_iv         double precision,   -- median near-ATM LEAP put IV
    iv_hv          double precision,   -- implied / realized
    convexity      double precision,   -- β×HV÷IV — downside move per
                                       -- unit of implied paid
    corr_target    double precision,   -- 60d corr vs the hedge target
    beta_to_target double precision,   -- regression β on target
    parts          jsonb,              -- the four bucket sub-scores
    put            jsonb,              -- the actual contract picked:
                                       -- strike/expiry/mid/iv/oi
    hedge_roi      jsonb,              -- BS-priced −30% scenario:
                                       -- premium/value_after/roi
    thin_chain     boolean,
    extension      double precision,   -- 0-15 the 'ATH + overbought'
                                       -- leg: dd52w/RSI/%B/vs_sma50
    setup          text,               -- put-window label: extension
                                       -- picks the candidate,
                                       -- rolling_over marks entry
    -- graded later: did it hedge?
    ret_20d        double precision,
    target_ret_20d double precision,   -- target's own move over 20d
    capture_20d    double precision,   -- sym move ÷ target move —
                                       -- high = it fell when target fell
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snap_date, symbol, hedge_target)
);
CREATE INDEX IF NOT EXISTS hedge_snap_date_idx
    ON hedge_universe_snapshots (snap_date DESC);
CREATE INDEX IF NOT EXISTS hedge_snap_sym_idx
    ON hedge_universe_snapshots (symbol, snap_date DESC);
