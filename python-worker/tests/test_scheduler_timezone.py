from datetime import datetime, timezone

from app.support.scheduler import next_fire, _job_tz, cron_match


def test_new_york_cron_fires_at_8am_winter():
    now = datetime(2026, 11, 2, 12, 59, tzinfo=timezone.utc)

    assert next_fire("0 8 * * 1-5", now,
                     tz_name="America/New_York") == \
        datetime(2026, 11, 2, 13, 0, tzinfo=timezone.utc)


def test_new_york_cron_fires_at_8am_summer():
    now = datetime(2026, 7, 1, 11, 59, tzinfo=timezone.utc)

    assert next_fire("0 8 * * 1-5", now,
                     tz_name="America/New_York") == \
        datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def test_cron_match_uses_local_job_datetime():
    ny = _job_tz("America/New_York")
    utc_8am = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

    assert cron_match("0 8 * * 1-5", utc_8am.astimezone(ny))
    assert not cron_match("0 8 * * 1-5", utc_8am)
