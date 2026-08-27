from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import app.main as app_main
from app.models import GenerateDigitPredictionRequest
from app.services.digit_prediction import rank_last_digits


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


def test_last_digit_ranking_returns_distribution_and_top_one() -> None:
    draws = synthetic_draws(400)
    start = date(2025, 6, 1)
    draws.extend(
        {
            "draw_date": (start + timedelta(days=index)).isoformat(),
            "last_two": "17" if index < 45 else f"{index % 10:02d}",
            "status": "observed",
        }
        for index in range(50)
    )

    result = rank_last_digits(draws, "2026-01-01")

    assert result["predicted_digit"] == "7"
    assert len(result["scores"]) == 10
    assert {item["digit"] for item in result["scores"]} == set("0123456789")
    assert sum(item["probability"] for item in result["scores"]) == pytest.approx(1.0)
    assert result["prediction_probability"] > result["random_baseline"]


def test_last_digit_ranking_ignores_current_and_future_draws() -> None:
    target = "2025-01-01"
    history = synthetic_draws(366)
    baseline = rank_last_digits(history, target)
    contaminated = history + [
        {"draw_date": target, "last_two": "99", "status": "observed"},
        {"draw_date": "2025-01-02", "last_two": "99", "status": "observed"},
    ]

    result = rank_last_digits(contaminated, target)

    assert result["dataset_hash"] == baseline["dataset_hash"]
    assert result["predicted_digit"] == baseline["predicted_digit"]
    assert result["scores"] == baseline["scores"]
    assert result["trained_through"] < target


def test_last_digit_ranking_requires_enough_history() -> None:
    with pytest.raises(ValueError, match="At least 30"):
        rank_last_digits(synthetic_draws(20), "2026-01-01")


@pytest.mark.parametrize(
    ("today_has_result", "expected_target"),
    [
        (False, date(2026, 8, 18)),
        (True, date(2026, 8, 19)),
    ],
)
def test_generate_digit_prediction_automatically_selects_today_or_tomorrow(
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

    def fake_create_digit_prediction(database, target):
        captured.update(database=database, target=target)
        return {
            "prediction_date": target.isoformat(),
            "predicted_digit": "8",
        }, True

    monkeypatch.setattr(
        app_main,
        "create_digit_prediction",
        fake_create_digit_prediction,
    )

    result = app_main.generate_digit_prediction(
        request,
        GenerateDigitPredictionRequest(),
    )

    assert captured == {"database": db, "target": expected_target}
    assert result["prediction"]["prediction_date"] == expected_target.isoformat()
