import pytest

from app.support import custodian


@pytest.mark.asyncio
async def test_running_job_does_not_consume_repair_attempt(monkeypatch):
    from app.database import db
    from app.api import board_api

    monkeypatch.setattr(db, "execute_update",
                        lambda *a, **k: None)
    monkeypatch.setitem(board_api._jobs, "momentum",
                        {"running": True})

    result, consume = await custodian._remediate(
        "job:momentum:error", "retry", 1)

    assert result == "momentum already running"
    assert consume is False


@pytest.mark.asyncio
async def test_unknown_job_consumes_repair_attempt(monkeypatch):
    from app.database import db

    monkeypatch.setattr(db, "execute_update",
                        lambda *a, **k: None)

    result, consume = await custodian._remediate(
        "job:not-a-job:error", "retry", 1)

    assert "unknown job" in result
    assert consume is True


@pytest.mark.asyncio
async def test_failed_job_is_restarted_and_consumes_attempt(monkeypatch):
    from app.database import db
    from app.api import board_api

    started = []
    async def fake_run(name):
        started.append(name)

    monkeypatch.setattr(db, "execute_update", lambda *a, **k: None)
    monkeypatch.setattr(board_api, "_run_job", fake_run)
    board_api._jobs.pop("momentum", None)

    result, consume = await custodian._remediate(
        "job:momentum:error", "retry", 1)
    await __import__("asyncio").sleep(0)

    assert result == "kicked momentum"
    assert consume is True
    assert started == ["momentum"]
