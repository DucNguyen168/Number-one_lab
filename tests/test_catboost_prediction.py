from datetime import date, timedelta

import pytest

import app.services.catboost_prediction as catboost_prediction


def patterned_draws(count: int | None = None) -> list[dict[str, str]]:
    count = count or catboost_prediction.LAG_COUNT + 120
    start = date(2023, 1, 1)
    values = [7, 42, 18]
    for index in range(3, count):
        values.append((values[index - 1] * 7 + values[index - 3] + index) % 100)
    return [
        {
            "draw_date": (start + timedelta(days=index)).isoformat(),
            "last_two": f"{values[index]:02d}",
            "status": "observed",
        }
        for index in range(count)
    ]


class _FakeCatBoost:
    classes_ = list(range(100))

    def predict_proba(self, features):
        weights = [101 - number for number in range(100)]
        total = sum(weights)
        return [[weight / total for weight in weights]]


@pytest.fixture(autouse=True)
def fake_classifier(monkeypatch):
    monkeypatch.setattr(
        catboost_prediction,
        "_fit_classifier",
        lambda features, labels: _FakeCatBoost(),
    )


@pytest.mark.parametrize("selected_count", [60, 65, 70, 75, 80])
def test_catboost_ranking_returns_complete_unique_distribution(selected_count: int) -> None:
    history = patterned_draws()
    target = (
        date.fromisoformat(history[-1]["draw_date"]) + timedelta(days=1)
    ).isoformat()
    result = catboost_prediction.rank_numbers(
        history,
        target,
        selected_count,
        minimum_training_samples=100,
    )

    assert result["model_version"] == catboost_prediction.MODEL_VERSION
    assert result["feature_version"] == catboost_prediction.FEATURE_VERSION
    assert result["model_config"]["has_time"] is True
    assert result["model_config"]["lag_count"] == 2_000
    assert result["model_config"]["raw_lag_count"] == 14
    assert result["model_config"]["feature_count"] == 287
    assert result["feature_lookback_draw_count"] == 2_000
    assert len(result["numbers"]) == selected_count
    assert len(set(result["numbers"])) == selected_count
    assert len(result["scores"]) == 100
    assert sum(item["probability"] for item in result["scores"]) == pytest.approx(1.0)


def test_catboost_ignores_target_and_future_results() -> None:
    history = patterned_draws()
    target_date = date.fromisoformat(history[-1]["draw_date"]) + timedelta(days=1)
    target = target_date.isoformat()
    baseline = catboost_prediction.rank_numbers(
        history, target, 65, minimum_training_samples=100
    )
    contaminated = history + [
        {"draw_date": target, "last_two": "99", "status": "observed"},
        {
            "draw_date": (target_date + timedelta(days=1)).isoformat(),
            "last_two": "00",
            "status": "observed",
        },
    ]

    result = catboost_prediction.rank_numbers(
        contaminated, target, 65, minimum_training_samples=100
    )

    assert result["dataset_hash"] == baseline["dataset_hash"]
    assert result["numbers"] == baseline["numbers"]
    assert result["trained_through"] < target


def test_catboost_requires_locked_minimum_history() -> None:
    with pytest.raises(ValueError, match="At least 2730"):
        catboost_prediction.rank_numbers(patterned_draws(500), "2026-01-01", 65)
