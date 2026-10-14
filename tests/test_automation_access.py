import asyncio
import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Response

import app.main as main
from app.services.cron_lock import CronAlreadyRunning


def configure(monkeypatch):
    monkeypatch.setattr(main, "settings", SimpleNamespace(
        is_vercel=True, enable_scheduler=True, auto_prediction=True,
        local_today=lambda: date(2026, 10, 14),
    ))


def request(method, path, **kwargs):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(run())


@pytest.mark.parametrize("path,creator", [
    ("/api/predictions/generate", "create_prediction"),
    ("/api/logistic-predictions/generate", "create_logistic_prediction"),
    ("/api/catboost-predictions/generate", "create_catboost_prediction"),
])
@pytest.mark.parametrize("legacy_env", [False, True])
def test_all_manual_models_work_without_keys(monkeypatch, path, creator, legacy_env):
    configure(monkeypatch)
    for name in ("ADMIN_API_KEY", "CRON_SECRET", "REQUIRE_ADMIN_AUTH"):
        if legacy_env:
            monkeypatch.setenv(name, "unused-legacy-key")
        else:
            monkeypatch.delenv(name, raising=False)
    database = SimpleNamespace(draw_results=SimpleNamespace(find_one=lambda query: None))
    calls = []
    monkeypatch.setattr(main, "_db", lambda request: database)

    def create(db, target, count):
        calls.append((target, count))
        return {"prediction_date": target.isoformat(), "selected_count": count}, True

    monkeypatch.setattr(main, creator, create)
    result = request("POST", path, json={"selected_count": 65})
    assert result.status_code == 200
    assert result.json()["created"] is True
    assert calls == [(date(2026, 10, 14), 65)]


@pytest.mark.parametrize("method,trigger", [("GET", "cron"), ("POST", "manual")])
@pytest.mark.parametrize("legacy_env", [False, True])
def test_cron_and_manual_recovery_run_without_secrets(monkeypatch, method, trigger, legacy_env):
    configure(monkeypatch)
    if legacy_env:
        monkeypatch.setenv("CRON_SECRET", "unused-legacy-key")
    else:
        monkeypatch.delenv("CRON_SECRET", raising=False)
    calls = []
    monkeypatch.setattr(main, "_execute_auto_daily", lambda req, res, **kw: calls.append(kw) or {"ok": True})
    assert request(method, "/api/auto-daily").status_code == 200
    assert calls == [{"trigger": trigger}]


class RunState:
    def __init__(self):
        self.latest = None
        self.transitions = []

    def find_one(self, query):
        return self.latest

    def update_one(self, query, update, **kwargs):
        self.latest = {**(self.latest or {}), **update["$set"]}
        self.transitions.append(dict(self.latest))


def execution(monkeypatch, *, locked=False):
    run_state = RunState()
    database = SimpleNamespace(automation_state=run_state)
    monkeypatch.setattr(main, "_db", lambda request: database)

    @contextmanager
    def lease(db, name, *, lease_seconds):
        config = json.loads((Path(__file__).parents[1] / "vercel.json").read_text())
        assert lease_seconds > config["functions"]["api/index.py"]["maxDuration"]
        assert name == "auto-daily"
        if locked:
            raise CronAlreadyRunning()
        yield

    monkeypatch.setattr(main, "mongo_cron_lease", lease)
    return database, run_state


@pytest.mark.parametrize("status,ok,sync_error,expected", [
    ("completed", True, None, 200), ("waiting_result", True, None, 200),
    ("partial_failure", False, None, 500), ("source_failed", False, "offline", 502),
])
def test_execution_records_result_and_reports_failures(monkeypatch, status, ok, sync_error, expected):
    _, run_state = execution(monkeypatch)
    result = {"ok": ok, "status": status, "sync_error": sync_error, "target_date": "2026-10-15"}
    monkeypatch.setattr(main, "_run_auto_daily", lambda db: result)
    response = Response()
    assert main._execute_auto_daily(None, response, trigger="cron") == result
    assert response.status_code == expected
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert [run["status"] for run in run_state.transitions] == ["running", status]
    assert run_state.latest["trigger"] == "cron"
    assert run_state.latest["finished_at"] >= run_state.latest["started_at"]


def test_unexpected_failure_is_recorded_without_error_details(monkeypatch):
    _, run_state = execution(monkeypatch)

    def fail(db):
        raise RuntimeError("private error details")

    monkeypatch.setattr(main, "_run_auto_daily", fail)
    with pytest.raises(RuntimeError):
        main._execute_auto_daily(None, Response(), trigger="manual")
    assert run_state.latest["status"] == "failed"
    assert "private error" not in str(run_state.latest)


def test_duplicate_execution_preserves_active_run(monkeypatch):
    _, run_state = execution(monkeypatch, locked=True)
    assert main._execute_auto_daily(None, Response(), trigger="cron")["status"] == "already_running"
    assert run_state.transitions == []


def test_automation_status_detects_interrupted_run_without_secret(monkeypatch):
    configure(monkeypatch)
    database, run_state = execution(monkeypatch)
    assert main._automation_status(database) == {
        "mode": "vercel_cron", "configured": True, "auto_prediction": True, "last_run": None,
    }
    monkeypatch.setenv("CRON_SECRET", "private-cron-key")
    run_state.latest = {"status": "running", "trigger": "cron", "secret": "hidden",
                        "started_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=6)}
    status = main._automation_status(database)
    assert status["configured"] is True
    assert status["last_run"]["status"] == "interrupted"
    assert status["last_run"]["started_at"].endswith("+00:00")
    assert "hidden" not in json.dumps(status)
    assert "private-cron-key" not in json.dumps(status)
