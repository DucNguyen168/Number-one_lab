from datetime import date, datetime
from types import SimpleNamespace

import app.main as app_main


class _DrawResults:
    def __init__(self, has_today: bool) -> None:
        self.has_today = has_today

    def find_one(self, query, projection=None):
        return {"_id": "draw-1"} if self.has_today else None


def _configure_cycle(monkeypatch, *, has_today: bool, hour: int = 19):
    database = SimpleNamespace(draw_results=_DrawResults(has_today))
    settings = SimpleNamespace(
        local_today=lambda: date(2026, 9, 10),
        local_now=lambda: datetime(2026, 9, 10, hour, 10),
        result_sync_times=("18:35", "18:50", "19:10"),
        auto_prediction=True,
        auto_prediction_count=65,
    )

    class Collector:
        def __init__(self, db, config) -> None:
            self.db = db

        def sync_year(self, year: int):
            return {"year": year, "status": "completed"}

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
    assert "waiting for the next cron run" in result["prediction_error"]
