-- Job registry — the AutoSys-style catalog. One row per job the
-- system knows: what it is, when it should run, what must succeed
-- first. The dispatcher (support/scheduler.py) reads this every
-- minute; enabled=false means manual-only (current behavior).
--
-- AutoSys concepts mapped:
--   cron           schedule expression (5-field, UTC)
--   depends_on     predecessors — must have a clean job_runs row
--                  within dep_max_age_h or the job waits
--   kind='box'     container job ('all' = REFRESH EVERYTHING)
--   cooldown_min   minimum spacing between scheduled fires
-- Runs live in job_runs (migration 080) — single source of truth for
-- 'last run' shared by the page, the custodian and the dispatcher.
CREATE TABLE IF NOT EXISTS job_definitions (
    name          text PRIMARY KEY,
    label         text,
    purpose       text,
    kind          text NOT NULL DEFAULT 'job',    -- job | box
    cron          text,                           -- '*/30 12-22 * * 1-5' UTC
    enabled       boolean NOT NULL DEFAULT false, -- scheduling OFF by default
    depends_on    text[],                         -- AutoSys-style predecessors
    dep_max_age_h int NOT NULL DEFAULT 24,
    cooldown_min  int NOT NULL DEFAULT 15,
    timeout_s     int,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

INSERT INTO job_definitions
 (name, label, purpose, kind, cron, depends_on) VALUES
 ('regime','Regime card','SPY/VIX/breadth posture — gates aggression','job','*/30 12-22 * * 1-5',NULL),
 ('momentum','Momentum flags','Canonical tape state + dip phase per symbol','job','30 13,21 * * 1-5',NULL),
 ('flywheel','Expectation gap','Fundamental scores feeding boards','job','0 14,22 * * 1-5',NULL),
 ('fund-flags','Fundamental flags','Distill flywheel → accelerating/slowing/…','job','30 14,22 * * 1-5','{flywheel}'),
 ('alerts','Catalyst scan','Alert collectors over portfolio∪watchlist','job','0 12-22 * * 1-5',NULL),
 ('focus-scan','Focus book scan','Contracts/roadmap/8-Ks on conviction names','job','15 12-22 * * 1-5',NULL),
 ('swing-scan','Swing screener','Setup engine — entry/stop/target','job','0 15 * * 1-5','{momentum}'),
 ('rule-breakers','RB eval','Gates/tier transitions + discovery','job','0 14 * * 1-5','{flywheel}'),
 ('smallcap','5x Scout eval','Small-cap gates + discovery','job','30 14 * * 1-5','{flywheel}'),
 ('outcomes','Outcome evals','Grade decisions/alerts/patterns at 5/10/20d','job','0 23 * * 1-5',NULL),
 ('leaps-mark','LEAPS mark','Reprice book + exit alerts','job','*/30 13-21 * * 1-5',NULL),
 ('priors','Pattern priors','Replay history → per-symbol hit-rates','job','0 0 * * 6',NULL),
 ('pilot','Swing pilot','Paper trades → learned weights','job','0 22 * * 1-5','{momentum,fund-flags}'),
 ('custodian','Support agent','Detect→diagnose→remediate→verify','job','*/10 * * * *',NULL),
 ('all','REFRESH EVERYTHING','Box job — all layers in dependency order','box','0 13 * * 1-5',NULL)
ON CONFLICT (name) DO NOTHING;
