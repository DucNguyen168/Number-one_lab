from datetime import date, timedelta

import app.services.rolling_comparison as rolling


def _draws(total: int = 734) -> list[dict[str, str]]:
    start = date(2024, 1, 1)
    return [
        {
            "draw_date": (start + timedelta(days=index)).isoformat(),
            "last_two": "00",
        }
        for index in range(total)
    ]


def _rank_with_zero_first(*_args, **_kwargs) -> dict[str, object]:
    scores = [
        {"number": f"{number:02d}", "rank": number + 1, "probability": 0.01}
        for number in range(100)
    ]
    return {"scores": scores}


def test_rolling_comparison_uses_only_prior_draws_and_pairs_both_models(
    monkeypatch,
) -> None:
    frequency_histories: list[int] = []
    logistic_histories: list[int] = []

    def frequency(draws, target_date, selected_count):
        frequency_histories.append(len(draws))
        return _rank_with_zero_first(draws, target_date, selected_count)

    def logistic(draws, target_date, selected_count):
        logistic_histories.append(len(draws))
        return _rank_with_zero_first(draws, target_date, selected_count)

    monkeypatch.setattr(rolling, "rank_frequency", frequency)
    monkeypatch.setattr(rolling, "rank_logistic", logistic)

    summary, daily = rolling.run_rolling_comparison(_draws(), outer_periods=365)

    assert summary["study_type"] == "rolling_walk_forward_current"
    assert summary["paired_predictions"] == 1
    assert summary["end_date"] == "2026-01-03"
    assert frequency_histories == [733]
    assert logistic_histories == [733]
    assert daily[0]["frequency_hit_65"] is True
    assert daily[0]["logistic_hit_65"] is True


def test_report_for_selected_count_returns_latest_rows_first(monkeypatch) -> None:
    monkeypatch.setattr(rolling, "rank_frequency", _rank_with_zero_first)
    monkeypatch.setattr(rolling, "rank_logistic", _rank_with_zero_first)
    summary, daily = rolling.run_rolling_comparison(
        _draws(), outer_periods=365
    )
    report = {
        "summary": summary,
        "daily": daily,
        "dataset": {"draws": 734, "first_date": "2024-01-01", "last_date": "2026-01-03"},
    }

    payload = rolling.report_for_selected_count(report, 65)

    assert payload["selected_count"] == 65
    assert payload["daily"][0]["prediction_date"] == "2026-01-03"
    assert payload["daily"][0]["frequency_hit"] is True
    assert payload["daily"][0]["logistic_hit"] is True
