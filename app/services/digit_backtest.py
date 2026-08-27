from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

from pymongo.database import Database

from app.services.digit_prediction import (
    DIGIT_MODEL_VERSION,
    RANDOM_BASELINE,
    rank_last_digits,
)


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
            observed * (1 - observed) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return center - half, center + half


def run_digit_walk_forward_backtest(
    db: Database,
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
    brier_sum = 0.0
    log_loss_sum = 0.0

    for index in range(minimum_training_draws, len(draws)):
        actual_draw = draws[index]
        target = actual_draw["draw_date"]
        if start and target < start:
            continue
        if end and target > end:
            continue

        prediction = rank_last_digits(draws[:index], target)
        actual_digit = actual_draw["last_two"][-1]
        probabilities = {
            item["digit"]: item["probability"] for item in prediction["scores"]
        }
        actual_probability = max(probabilities[actual_digit], 1e-12)
        brier_sum += sum(
            (probability - (1.0 if digit == actual_digit else 0.0)) ** 2
            for digit, probability in probabilities.items()
        )
        log_loss_sum += -math.log(actual_probability)
        outcomes.append(
            {
                "prediction_date": target,
                "predicted_digit": prediction["predicted_digit"],
                "prediction_probability": prediction["prediction_probability"],
                "actual_digit": actual_digit,
                "hit": prediction["predicted_digit"] == actual_digit,
                "trained_through": prediction["trained_through"],
            }
        )

    if not outcomes:
        raise ValueError("No draw results fall inside the requested test range")

    hits = sum(1 for outcome in outcomes if outcome["hit"])
    total = len(outcomes)
    hit_rate = hits / total
    lower, upper = _wilson_interval(hits, total)
    summary = {
        "model_version": DIGIT_MODEL_VERSION,
        "minimum_training_draws": minimum_training_draws,
        "start_date": outcomes[0]["prediction_date"],
        "end_date": outcomes[-1]["prediction_date"],
        "total_predictions": total,
        "hits": hits,
        "misses": total - hits,
        "hit_rate": round(hit_rate, 8),
        "random_baseline": RANDOM_BASELINE,
        "lift_vs_random": round(hit_rate - RANDOM_BASELINE, 8),
        "confidence_interval_95": {
            "lower": round(lower, 8),
            "upper": round(upper, 8),
        },
        "mean_brier_score": round(brier_sum / total, 8),
        "mean_log_loss": round(log_loss_sum / total, 8),
        "created_at": datetime.now(timezone.utc),
        "outcomes": outcomes,
    }
    result = db.digit_backtest_runs.insert_one(summary)
    summary["_id"] = result.inserted_id
    return summary
