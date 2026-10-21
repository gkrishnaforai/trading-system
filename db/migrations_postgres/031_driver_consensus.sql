-- 031 — driver commitments vs street consensus.
-- A guide can be NEW (no prior commitment, no 'vs previously' in the
-- text) yet still below the street — NFLX's Q4 EPS guide ($0.67 vs
-- $0.73 est) repriced -6% and our delta logic can't see it because
-- delta-vs-prior reads 'new'. The market prices delta-vs-expectation;
-- store the comparison on the commitment itself.
ALTER TABLE driver_commitments
    ADD COLUMN IF NOT EXISTS consensus_value DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS consensus_pct   DOUBLE PRECISION;
