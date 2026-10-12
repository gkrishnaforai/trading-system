-- gm_qoq — sequential gross-margin delta (Q vs Q-1). gm_slope is the
-- YoY delta; the QoQ-vs-YoY divergence is the "temporary compression vs
-- structural breakdown" discriminator (CBRS: QoQ -590bps / YoY +940bps).
ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS gm_qoq double precision;
