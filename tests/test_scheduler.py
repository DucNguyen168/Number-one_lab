import asyncio
from datetime import date
from types import SimpleNamespace

from app.services.scheduler import DailyScheduler


class _DrawResults:
    def __init__(self, result_exists: bool) -> None:
        self.result_exists = result_exists
        self.queries: list[tuple[dict[str, object], dict[str, object]]] = []

    def find_one(
        self,
        query: dict[str, object],
        projection: dict[str, object],
    ) -> dict[str, object] | None:
        self.queries.append((query, projection))
        return {"_id": "result-1"} if self.result_exists else None


def test_scheduler_retries_transient_failures(monkeypatch) -> None:
    scheduler = DailyScheduler(
        SimpleNamespace(),
        SimpleNamespace(
            scheduler_retry_attempts=3,
            scheduler_retry_delay_seconds=1,
        ),
    )
    attempts = 0
    delays: list[int] = []

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary source failure")

    async def no_wait(delay: int) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.services.scheduler.asyncio.sleep", no_wait)

    succeeded = asyncio.run(
        scheduler._run_with_retries("test sync", operation)
    )

    assert succeeded is True
    assert attempts == 3
    assert delays == [1, 2]


def test_sync_creates_next_day_model_snapshots_after_result(monkeypatch) -> None:
    draw_results = _DrawResults(result_exists=True)
    scheduler = DailyScheduler(
        SimpleNamespace(draw_results=draw_results),
        SimpleNamespace(auto_prediction=True, auto_prediction_count=65),
    )
    monkeypatch.setattr(
        scheduler.collector,
        "sync_year",
        lambda year: {"year": year, "status": "completed"},
    )
    monkeypatch.setattr(
        "app.services.scheduler.evaluate_pending_predictions",
        lambda db: {"evaluated": 1},
    )
    monkeypatch.setattr(
        "app.services.scheduler.evaluate_pending_digit_predictions",
        lambda db: {"evaluated": 1},
    )
    generated_for: list[date] = []

    async def generate(target: date) -> dict[str, object]:
        generated_for.append(target)
        return {
            "prediction_date": target.isoformat(),
            "two_digit_created": True,
            "catboost_two_digit_created": True,
        }

    monkeypatch.setattr(scheduler, "_generate_prediction", generate)

    outcome = asyncio.run(scheduler._sync_and_evaluate(date(2026, 9, 5)))

    assert generated_for == [date(2026, 9, 6)]
    assert outcome["next_prediction"] == {
        "prediction_date": "2026-09-06",
        "two_digit_created": True,
        "catboost_two_digit_created": True,
    }
    assert draw_results.queries == [
        (
            {
                "draw_date": "2026-09-05",
                "status": {"$ne": "conflict"},
            },
            {"_id": 1},
        )
    ]


def test_sync_waits_for_result_before_creating_next_day_prediction(
    monkeypatch,
) -> None:
    scheduler = DailyScheduler(
        SimpleNamespace(draw_results=_DrawResults(result_exists=False)),
        SimpleNamespace(auto_prediction=True, auto_prediction_count=65),
    )
    monkeypatch.setattr(
        scheduler.collector,
        "sync_year",
        lambda year: {"year": year, "status": "completed"},
    )
    monkeypatch.setattr(
        "app.services.scheduler.evaluate_pending_predictions",
        lambda db: {"evaluated": 0},
    )
    monkeypatch.setattr(
        "app.services.scheduler.evaluate_pending_digit_predictions",
        lambda db: {"evaluated": 0},
    )

    async def should_not_generate(target: date) -> dict[str, object]:
        raise AssertionError(f"unexpected prediction for {target}")

    monkeypatch.setattr(scheduler, "_generate_prediction", should_not_generate)

    outcome = asyncio.run(scheduler._sync_and_evaluate(date(2026, 9, 5)))

    assert outcome["next_prediction"] is None


def test_generate_prediction_creates_three_two_digit_model_snapshots(
    monkeypatch,
) -> None:
    database = SimpleNamespace()
    scheduler = DailyScheduler(
        database,
        SimpleNamespace(auto_prediction_count=65),
    )
    calls: list[tuple[str, date, int | None]] = []

    def create_two_digit(db, target: date, selected_count: int):
        calls.append(("two-digit", target, selected_count))
        return {"prediction_date": target.isoformat()}, True

    def create_catboost(db, target: date, selected_count: int):
        calls.append(("catboost-two-digit", target, selected_count))
        return {"prediction_date": target.isoformat()}, True

    def create_logistic(db, target: date, selected_count: int):
        calls.append(("logistic-two-digit", target, selected_count))
        return {"prediction_date": target.isoformat()}, True

    monkeypatch.setattr("app.services.scheduler.create_prediction", create_two_digit)
    monkeypatch.setattr(
        "app.services.scheduler.create_logistic_prediction",
        create_logistic,
    )
    monkeypatch.setattr(
        "app.services.scheduler.create_catboost_prediction",
        create_catboost,
    )

    outcome = asyncio.run(scheduler._generate_prediction(date(2026, 9, 6)))

    assert calls == [
        ("two-digit", date(2026, 9, 6), 65),
        ("logistic-two-digit", date(2026, 9, 6), 65),
        ("catboost-two-digit", date(2026, 9, 6), 65),
    ]
    assert outcome == {
        "prediction_date": "2026-09-06",
        "selected_count": 65,
        "two_digit_created": True,
        "logistic_two_digit_created": True,
        "logistic_two_digit_error": None,
        "catboost_two_digit_created": True,
        "catboost_two_digit_error": None,
    }
