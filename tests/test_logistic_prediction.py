from datetime import date, timedelta

import pytest

from app.services.logistic_prediction import FEATURE_VERSION, MODEL_VERSION, rank_numbers


def patterned_draws(count: int = 850) -> list[dict[str, str]]:
    start = date(2023, 1, 1)
    values = [7, 42, 18]
    for index in range(3, count):
        values.append((values[index - 1] * 3 + values[index - 2] + index) % 100)
    return [
        {
            "draw_date": (start + timedelta(days=index)).isoformat(),
            "last_two": f"{values[index]:02d}",
            "status": "observed",
        }
        for index in range(count)
    ]


@pytest.mark.parametrize("selected_count", [60, 65, 70, 75, 80])
def test_logistic_ranking_returns_nested_unique_sets(selected_count: int) -> None:
    result = rank_numbers(
        patterned_draws(),
        "2026-01-01",
        selected_count,
        minimum_training_samples=100,
    )

    assert result["model_version"] == MODEL_VERSION
    assert result["feature_version"] == FEATURE_VERSION
    assert len(result["numbers"]) == selected_count
    assert len(set(result["numbers"])) == selected_count
    assert len(result["scores"]) == 100
    assert sum(item["probability"] for item in result["scores"]) == pytest.approx(1.0)


def test_logistic_prediction_ignores_target_and_future_results() -> None:
    target = "2025-04-01"
    history = patterned_draws(850)
    baseline = rank_numbers(history, target, 65, minimum_training_samples=100)
    contaminated = history + [
        {"draw_date": target, "last_two": "99", "status": "observed"},
        {"draw_date": "2025-04-02", "last_two": "99", "status": "observed"},
    ]

    result = rank_numbers(contaminated, target, 65, minimum_training_samples=100)

    assert result["dataset_hash"] == baseline["dataset_hash"]
    assert result["numbers"] == baseline["numbers"]
    assert result["trained_through"] < target


def test_logistic_prediction_requires_locked_minimum_history() -> None:
    with pytest.raises(ValueError, match="At least 733"):
        rank_numbers(patterned_draws(500), "2026-01-01", 65)
