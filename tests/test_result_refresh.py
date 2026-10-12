from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import Response

import app.main as app_main
from app.services.collector import CollectorSourcesUnavailable
from app.services.cron_lock import CronAlreadyRunning


def configure_refresh(monkeypatch, *, hour=18, minute=30):
    calls = []
    state = {"recent": None, "latest": None, "failure": False, "locked": False}
    now = datetime(2026, 10, 12, hour, minute, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    db = SimpleNamespace(
        draw_results=SimpleNamespace(find_one=lambda **kwargs: state["latest"]),
        collector_runs=SimpleNamespace(find_one=lambda *args: state["recent"]),
    )
    monkeypatch.setattr(app_main, "_db", lambda request: db)
    monkeypatch.setattr(app_main, "settings", SimpleNamespace(
        local_now=lambda: now, result_poll_start_time="18:30",
        result_poll_interval_seconds=10,
    ))

    @contextmanager
    def lease(database, name, *, lease_seconds=240):
        assert name == "auto-daily"
        assert lease_seconds == 75
        if state["locked"]:
            raise CronAlreadyRunning()
        yield

    class Collector:
        def __init__(self, *args):
            pass

        def sync_latest(self, target):
            calls.append(target.isoformat())
            state["recent"] = {"_id": "attempt"}
            if state["failure"]:
                raise CollectorSourcesUnavailable("offline")
            state["latest"] = {"draw_date": target.isoformat(), "special_prize": "00123"}
            return {"status": "completed"}

    monkeypatch.setattr(app_main, "mongo_cron_lease", lease)
    monkeypatch.setattr(app_main, "KqxsCollector", Collector)
    monkeypatch.setattr(app_main, "evaluate_pending_predictions", lambda db: calls.append("evaluate"))
    monkeypatch.setattr(app_main, "evaluate_pending_digit_predictions", lambda db: None)
    return state, calls


def test_refresh_does_not_fetch_before_1830(monkeypatch):
    _, calls = configure_refresh(monkeypatch, hour=18, minute=29)
    assert app_main.refresh_latest_result(None, Response())["status"] == "outside_window"
    assert calls == []


def test_refresh_throttles_visitors_together_and_disables_cache(monkeypatch):
    _, calls = configure_refresh(monkeypatch)
    response = Response()
    result = app_main.refresh_latest_result(None, response)
    assert result["result"]["special_prize"] == "00123"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert app_main.refresh_latest_result(None, Response())["status"] == "throttled"
    assert calls == ["2026-10-12", "evaluate"]


def test_refresh_respects_running_cron(monkeypatch):
    state, calls = configure_refresh(monkeypatch)
    state["locked"] = True
    assert app_main.refresh_latest_result(None, Response())["status"] == "already_running"
    assert calls == []


def test_refresh_throttles_failed_attempt_then_retries(monkeypatch):
    state, calls = configure_refresh(monkeypatch)
    state["failure"] = True
    response = Response()
    assert app_main.refresh_latest_result(None, response)["status"] == "source_failed"
    assert response.status_code == 502
    assert app_main.refresh_latest_result(None, Response())["status"] == "throttled"
    state.update(recent=None, failure=False)
    assert app_main.refresh_latest_result(None, Response())["status"] == "completed"
    assert calls == ["2026-10-12", "2026-10-12", "evaluate"]


def test_latest_result_never_uses_http_cache(monkeypatch):
    configure_refresh(monkeypatch)
    response = Response()
    app_main.latest_result(None, response)
    assert response.headers["cache-control"] == "no-store, max-age=0"
