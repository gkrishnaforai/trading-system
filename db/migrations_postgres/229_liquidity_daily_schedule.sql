-- 229_liquidity_daily_schedule.sql — liquidity engine goes daily.
--
-- Was Sat-only ('0 14 * * 6'): a weekly snapshot misses fast
-- liquidity events (the July/November-style air pockets). The
-- market legs (flow matrix, breadth, IG/VIX) move every session;
-- the weekly FRED prints simply repeat between releases — obs_age
-- in the payload discloses that staleness honestly.
-- Post-close weekdays + Saturday keeps the weekly H.4.1 print.

SELECT pg_advisory_xact_lock(715229);

UPDATE job_definitions
   SET cron = '30 22 * * 1-6',
       purpose = 'Fed BS/TGA/RRP/reserves + HY/IG/VIX + ETF flow' ||
                 ' matrix + recovery sequence → 0-100 scores,' ||
                 ' journaled daily post-close',
       depends_on = '{momentum,live-bars}',
       dep_max_age_h = 96
 WHERE name = 'liquidity';
