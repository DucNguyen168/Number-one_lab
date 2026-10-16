from datetime import date, datetime
from types import SimpleNamespace

import app.main as app_main


class _DrawResults:
    def __init__(self, has_today: bool) -> None:
        self.has_today = has_today

    def find_one(self, query, projection=None):
        return {"_id": "draw-1"} if self.has_today else None


def _configure_cycle(monkeypatch, *, has_today: bool, hour: int = 19):
    database = SimpleNamespace(draw_results=_DrawResults(has_today),
                               collector_runs=SimpleNamespace(find_one=lambda *a: None))
    settings = SimpleNamespace(
        local_today=lambda: date(2026, 9, 10),
        local_now=lambda: datetime(2026, 9, 10, hour, 10),
        result_sync_times=("18:35", "18:50", "19:10"),
        result_poll_start_time="18:30",
        auto_prediction=True,
        auto_prediction_count=65,
    )

    class Collector:
        def __init__(self, db, config) -> None:
            self.db = db

        def sync_year(self, year: int):
            return {"year": year, "status": "completed"}

        def sync_latest(self, target: date):
            return {"draw_date": target.isoformat(), "status": "completed"}

    monkeypatch.setattr(app_main, "settings", settings)
    monkeypatch.setattr(app_main, "KqxsCollector", Collector)
    monkeypatch.setattr(
        app_main,
        "evaluate_pending_predictions",
        lambda db: {"evaluated": 0},
    )
    monkeypatch.setattr(
        app_main,
        "evaluate_pending_digit_predictions",
        lambda db: {"evaluated": 0},
    )
    return database


def test_auto_daily_creates_tomorrows_predictions_after_result(monkeypatch) -> None:
    database = _configure_cycle(monkeypatch, has_today=True)
    created: list[tuple[str, date]] = []

    def create_two_digit(db, target: date, selected_count: int):
        created.append(("two", target))
        return {}, True

    def create_catboost(db, target: date, selected_count: int):
        created.append(("catboost", target))
        return {}, True

    monkeypatch.setattr(app_main, "create_prediction", create_two_digit)
    monkeypatch.setattr(app_main, "create_logistic_prediction", create_two_digit)
    monkeypatch.setattr(app_main, "create_catboost_prediction", create_catboost)

    result = app_main._run_auto_daily(database)

    assert result["ok"] is True
    assert result["target_date"] == "2026-09-11"
    assert created == [
        ("two", date(2026, 9, 11)),
        ("two", date(2026, 9, 11)),
        ("catboost", date(2026, 9, 11)),
    ]


def test_auto_daily_does_not_create_late_prediction_without_result(
    monkeypatch,
) -> None:
    database = _configure_cycle(monkeypatch, has_today=False)

    def must_not_run(*args, **kwargs):
        raise AssertionError("late prediction must not be created")

    monkeypatch.setattr(app_main, "create_prediction", must_not_run)
    monkeypatch.setattr(app_main, "create_logistic_prediction", must_not_run)
    monkeypatch.setattr(app_main, "create_catboost_prediction", must_not_run)

    result = app_main._run_auto_daily(database)

    assert result["ok"] is True
    assert result["target_date"] is None
    assert result["status"] == "waiting_result"
    assert "waiting for the next cron run" in result["prediction_error"]


def test_auto_daily_reports_disabled_without_training_or_failure(monkeypatch):
    database = _configure_cycle(monkeypatch, has_today=True)
    app_main.settings.auto_prediction = False

    def must_not_train(*args, **kwargs):
        raise AssertionError("disabled models must not run")

    for function in ("create_prediction", "create_logistic_prediction", "create_catboost_prediction"):
        monkeypatch.setattr(app_main, function, must_not_train)

    result = app_main._run_auto_daily(database)
    assert result["ok"] is True
    assert result["status"] == "disabled"


def test_evening_full_reconciliation_only_once(monkeypatch):
    database = _configure_cycle(monkeypatch, has_today=True)
    app_main.settings.auto_prediction = False
    database.collector_runs.find_one = lambda *a: {"_id": "completed-evening-sync"}
    result = app_main._run_auto_daily(database)
    assert result["sync"] == {"draw_date": "2026-09-10", "status": "completed"}
    database.collector_runs.find_one = lambda *a: None
    result = app_main._run_auto_daily(database)
    assert result["sync"] == {"year": 2026, "status": "completed"}


def test_before_draw_only_syncs_previous_day(monkeypatch):
    database = _configure_cycle(monkeypatch, has_today=False, hour=16)
    app_main.settings.auto_prediction = False
    result = app_main._run_auto_daily(database)
    assert result["sync"]["draw_date"] == "2026-09-09"
