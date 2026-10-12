-- Per-headline-kind outcome stats — the training signal for the alert
-- filter. Aggregates forward returns by catalyst headline kind so the
-- scanner can auto-demote kinds that don't precede moves (n>=20, win<30%).

CREATE OR REPLACE VIEW alert_kind_stats AS
SELECT a.detail->>'bucket'                       AS bucket,
       a.detail->>'kind'                         AS kind,
       a.direction,
       o.horizon_days,
       count(*)                                  AS n,
       round(avg(o.ret_pct), 2)                  AS avg_ret_pct,
       round(avg(o.mfe_pct), 2)                  AS avg_mfe_pct,
       round(avg(o.mae_pct), 2)                  AS avg_mae_pct,
       round(avg(CASE WHEN o.ret_pct > 0 THEN 1.0 ELSE 0.0 END), 3)
                                                 AS win_rate,
       max(a.created_at)::date                   AS last_alert_date
FROM alert_outcomes o
JOIN alert_items a ON a.id = o.alert_id
WHERE a.event_type = 'catalyst'
GROUP BY a.detail->>'bucket', a.detail->>'kind',
         a.direction, o.horizon_days;
