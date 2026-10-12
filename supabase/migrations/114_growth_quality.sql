-- 114: growth_quality journal + job
-- Composite score separating structural growers from cyclical peaks /
-- manufactured EPS. Append-only journal, same pattern as lt_power_runs.

create table if not exists growth_quality_runs (
    id            bigserial primary key,
    symbol        text not null,
    as_of         date not null,
    score         numeric(5,1),
    percentile    numeric(5,1),
    components    jsonb not null default '{}'::jsonb,
    detail        jsonb not null default '{}'::jsonb,
    flags         jsonb not null default '[]'::jsonb,
    inputs_hash   text,
    model_version text not null,
    created_at    timestamptz not null default now()
);
create index if not exists gq_runs_sym_asof on growth_quality_runs (symbol, as_of desc);
create index if not exists gq_runs_asof on growth_quality_runs (as_of desc);

-- nightly, after fund-snapshots has fresh rows to score
insert into job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority, dep_max_age_h)
values ('growth-quality', 'Growth-quality composite',
        'Slope+quality+revisions+structural composite over the tracked universe — ranks structural growers vs cyclical peaks',
        'job', '20 23 * * 1-5', true,
        array['flywheel'], 62, 48)
on conflict (name) do update set cron=excluded.cron, depends_on=excluded.depends_on,
       purpose=excluded.purpose, priority=excluded.priority, dep_max_age_h=excluded.dep_max_age_h;
