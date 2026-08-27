from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

from pymongo.database import Database

from app.services.prediction import MODEL_VERSION, rank_numbers


def _wilson_interval(hits: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.959963984540054
    observed = hits / total
    denominator = 1 + z * z / total
    center = (observed + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(
            observed * (1 - observed) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return center - half, center + half


def _compute_drawdown_stats(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute max drawdown (longest consecutive miss streak and capital trough)."""
    # Longest consecutive miss streak
    current_streak = 0
    longest_miss_streak = 0
    current_win_streak = 0
    longest_win_streak = 0

    # Capital drawdown (in units of stake per period)
    # Win: +1 unit net (950k - 600k = 350k → simplified as +1 unit)
    # Loss: -1 unit (lose 600k → simplified as -1 unit, ratio ≈ -1.714 real)
    WIN_UNIT = 350_000
    LOSS_UNIT = -600_000
    capital = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for outcome in outcomes:
        if outcome["hit"]:
            capital += WIN_UNIT
            current_win_streak += 1
            current_streak = 0
            longest_win_streak = max(longest_win_streak, current_win_streak)
        else:
            capital += LOSS_UNIT
            current_streak += 1
            current_win_streak = 0
            longest_miss_streak = max(longest_miss_streak, current_streak)
        peak = max(peak, capital)
        drawdown = peak - capital
        max_drawdown = max(max_drawdown, drawdown)

    return {
        "longest_miss_streak": longest_miss_streak,
        "longest_win_streak": longest_win_streak,
        "max_drawdown_vnd": round(max_drawdown),
        "final_capital_vnd": round(capital),
    }


def run_walk_forward_backtest(
    db: Database,
    selected_count: int,
    start_date: date | None = None,
    end_date: date | None = None,
    minimum_training_draws: int = 365,
) -> dict[str, Any]:
    draws = list(
        db.draw_results.find(
            {"status": {"$ne": "conflict"}},
            {"_id": 0, "draw_date": 1, "last_two": 1, "status": 1},
        ).sort("draw_date", 1)
    )
    if len(draws) <= minimum_training_draws:
        raise ValueError("Not enough data for the requested training period")

    start = start_date.isoformat() if start_date else None
    end = end_date.isoformat() if end_date else None
    outcomes: list[dict[str, Any]] = []
    probability_error_sum = 0.0
    log_loss_sum = 0.0

    for index in range(minimum_training_draws, len(draws)):
        actual = draws[index]
        target = actual["draw_date"]
        if start and target < start:
            continue
        if end and target > end:
            continue
        prediction = rank_numbers(draws[:index], target, selected_count)
        actual_number = actual["last_two"]
        hit = actual_number in prediction["numbers"]
        probabilities = {
            item["number"]: item["probability"] for item in prediction["scores"]
        }
        actual_probability = max(probabilities[actual_number], 1e-12)
        brier = sum(
            (probability - (1.0 if number == actual_number else 0.0)) ** 2
            for number, probability in probabilities.items()
        )
        probability_error_sum += brier
        log_loss_sum += -math.log(actual_probability)
        outcomes.append(
            {
                "prediction_date": target,
                "actual_last_two": actual_number,
                "hit": hit,
                "coverage_probability": prediction["coverage_probability"],
                "trained_through": prediction["trained_through"],
            }
        )

    if not outcomes:
        raise ValueError("No draw results fall inside the requested test range")

    hits = sum(1 for outcome in outcomes if outcome["hit"])
    total = len(outcomes)
    hit_rate = hits / total
    lower, upper = _wilson_interval(hits, total)
    drawdown_stats = _compute_drawdown_stats(outcomes)

    summary = {
        "model_version": MODEL_VERSION,
        "selected_count": selected_count,
        "minimum_training_draws": minimum_training_draws,
        "start_date": outcomes[0]["prediction_date"],
        "end_date": outcomes[-1]["prediction_date"],
        "total_predictions": total,
        "hits": hits,
        "misses": total - hits,
        "hit_rate": round(hit_rate, 8),
        "random_baseline": selected_count / 100,
        "lift_vs_random": round(hit_rate - selected_count / 100, 8),
        "confidence_interval_95": {
            "lower": round(lower, 8),
            "upper": round(upper, 8),
        },
        "mean_brier_score": round(probability_error_sum / total, 8),
        "mean_log_loss": round(log_loss_sum / total, 8),
        **drawdown_stats,
        "created_at": datetime.now(timezone.utc),
        "outcomes": outcomes,
    }
    result = db.backtest_runs.insert_one(summary)
    summary["_id"] = result.inserted_id
    return summary
