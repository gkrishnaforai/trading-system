create table if not exists growth_compare_daily (
  as_of date not null,
  payload jsonb not null,
  created_at timestamptz default now(),
  primary key (as_of)
);
