-- spec_pulse_evals: add the Spec Thesis Score + cut driver so the
-- journal tracks score momentum (sts drops → reviews) and splits
-- thesis-driven vs tape-driven cuts for outcome grading.

ALTER TABLE spec_pulse_evals
    ADD COLUMN IF NOT EXISTS sts numeric,
    ADD COLUMN IF NOT EXISTS driver text;
