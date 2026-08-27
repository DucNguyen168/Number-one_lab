from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import app.main as app_main
from app.models import GeneratePredictionRequest
from app.services.prediction import rank_numbers


def synthetic_draws(count: int = 500) -> list[dict[str, str]]:
    start = date(2024, 1, 1)
    return [
        {
            "draw_date": (start + timedelta(days=index)).isoformat(),
            "last_two": f"{index % 100:02d}",
            "status": "observed",
        }
        for index in range(count)
    ]


@pytest.mark.parametrize("selected_count", [60, 65, 70, 75, 80])
def test_ranking_returns_unique_locked_set(selected_count: int) -> None:
    result = rank_numbers(synthetic_draws(), "2026-01-01", selected_count)

    assert len(result["numbers"]) == selected_count
    assert len(set(result["numbers"])) == selected_count
    assert len(result["scores"]) == 100
    assert sum(item["probability"] for item in result["scores"]) == pytest.approx(1.0)
    assert 0 < result["coverage_probability"] < 1


def test_ranking_ignores_draws_on_or_after_target_date() -> None:
    target = "2025-01-01"
    history = synthetic_draws(366)
    baseline = rank_numbers(history, target, 65)
    contaminated = history + [
        {"draw_date": target, "last_two": "99", "status": "observed"},
        {"draw_date": "2025-01-02", "last_two": "99", "status": "observed"},
    ]

    result = rank_numbers(contaminated, target, 65)

    assert result["dataset_hash"] == baseline["dataset_hash"]
    assert result["numbers"] == baseline["numbers"]
    assert result["trained_through"] < target


def test_ranking_requires_enough_history() -> None:
    with pytest.raises(ValueError, match="At least 30"):
        rank_numbers(synthetic_draws(20), "2026-01-01", 65)


@pytest.mark.parametrize(
    ("today_has_result", "expected_target"),
    [
        (False, date(2026, 8, 18)),
        (True, date(2026, 8, 19)),
    ],
)
def test_generate_prediction_automatically_selects_today_or_tomorrow(
    monkeypatch, today_has_result: bool, expected_target: date
) -> None:
    class DrawResults:
        def find_one(self, query: dict[str, str]):
            assert query == {"draw_date": "2026-08-18"}
            return {"draw_date": "2026-08-18"} if today_has_result else None

    db = SimpleNamespace(draw_results=DrawResults())
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(mongo=SimpleNamespace(db=db)))
    )
    monkeypatch.setattr(
        app_main,
        "settings",
        SimpleNamespace(local_today=lambda: date(2026, 8, 18)),
    )

    captured: dict[str, object] = {}

    def fake_create_prediction(database, target, selected_count):
        captured.update(
            database=database,
            target=target,
            selected_count=selected_count,
        )
        return {
            "prediction_date": target.isoformat(),
            "selected_count": selected_count,
        }, True

    monkeypatch.setattr(app_main, "create_prediction", fake_create_prediction)

    result = app_main.generate_prediction(
        request,
        GeneratePredictionRequest(selected_count=65),
    )

    assert captured == {
        "database": db,
        "target": expected_target,
        "selected_count": 65,
    }
    assert result["prediction"]["prediction_date"] == expected_target.isoformat()
