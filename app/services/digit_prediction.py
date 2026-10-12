from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date
from typing import Any, Iterable

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.services import prediction_protocol as protocol

from app.services.prediction import SMOOTHING_ALPHA, WINDOW_WEIGHTS


DIGIT_MODEL_VERSION = "last_digit_frequency_ensemble_v1"
RANDOM_BASELINE = 0.10


def _history_before(
    draws: Iterable[dict[str, Any]], target_date: str
) -> list[dict[str, Any]]:
    return sorted(
        (
            draw
            for draw in draws
            if draw.get("draw_date", "") < target_date
            and draw.get("status") != "conflict"
            and isinstance(draw.get("last_two"), str)
            and len(draw["last_two"]) == 2
            and draw["last_two"].isdigit()
        ),
        key=lambda draw: draw["draw_date"],
    )


def rank_last_digits(
    draws: Iterable[dict[str, Any]], target_date: str
) -> dict[str, Any]:
    """Rank 0-9 using only draws strictly earlier than target_date."""
    history = _history_before(draws, target_date)
    if len(history) < 30:
        raise ValueError("At least 30 earlier draw results are required")

    probabilities = {str(digit): 0.0 for digit in range(10)}
    window_details: list[dict[str, Any]] = []
    for window, weight in WINDOW_WEIGHTS:
        sample = history if window is None else history[-window:]
        counts = Counter(draw["last_two"][-1] for draw in sample)
        denominator = len(sample) + 10 * SMOOTHING_ALPHA
        for digit in probabilities:
            probabilities[digit] += weight * (
                counts[digit] + SMOOTHING_ALPHA
            ) / denominator
        window_details.append(
            {
                "window": "all" if window is None else window,
                "weight": weight,
                "observations": len(sample),
            }
        )

    ranking = sorted(
        probabilities, key=lambda digit: (-probabilities[digit], digit)
    )
    scores = [
        {
            "digit": digit,
            "rank": rank,
            "probability": round(probabilities[digit], 10),
        }
        for rank, digit in enumerate(ranking, start=1)
    ]
    trained_through = history[-1]["draw_date"]
    dataset_material = "|".join(
        f"{draw['draw_date']}:{draw['last_two'][-1]}" for draw in history
    )

    return {
        "model_version": DIGIT_MODEL_VERSION,
        "predicted_digit": ranking[0],
        "prediction_probability": round(probabilities[ranking[0]], 10),
        "random_baseline": RANDOM_BASELINE,
        "scores": scores,
        "window_details": window_details,
        "training_draw_count": len(history),
        "trained_through": trained_through,
        "dataset_hash": hashlib.sha256(dataset_material.encode()).hexdigest(),
        "probability_note": (
            "Raw model score; it is not a calibrated guarantee of the chance of winning."
        ),
    }


def create_digit_prediction(
    db: Database, prediction_date: date | str
) -> tuple[dict[str, Any], bool]:
    target = (
        prediction_date.isoformat()
        if isinstance(prediction_date, date)
        else prediction_date
    )
    if db.draw_results.find_one({"draw_date": target}) is not None:
        raise ValueError(
            "A result already exists for this date; retrospective predictions are not allowed"
        )

    lookup = {
        "prediction_date": target,
        "model_version": DIGIT_MODEL_VERSION,
    }
    existing = db.digit_predictions.find_one(lookup)
    if existing is not None:
        return existing, False

    protocol.ensure_open(target)
    draws = list(
        db.draw_results.find(
            {"draw_date": {"$lt": target}, "status": {"$ne": "conflict"}},
            {"_id": 1, "draw_date": 1, "last_two": 1, "special_prize": 1, "status": 1},
        ).sort("draw_date", 1)
    )
    draws = _history_before(draws, target)
    information_cutoff_at = protocol.ensure_open(target)
    prediction = rank_last_digits(draws, target)
    metadata = protocol.lock_metadata(db, draws, target, prediction, __name__, information_cutoff_at)
    document = {
        "prediction_date": target,
        **prediction,
        "status": "locked",
        **metadata,
        "evaluation": {"status": "pending"},
    }
    try:
        result = db.digit_predictions.insert_one(document)
        document["_id"] = result.inserted_id
        return document, True
    except DuplicateKeyError:
        existing = db.digit_predictions.find_one(lookup)
        if existing is None:
            raise
        return existing, False
