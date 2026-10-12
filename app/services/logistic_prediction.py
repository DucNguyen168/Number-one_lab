from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Iterable

import sklearn
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.services import prediction_protocol as protocol
from sklearn.linear_model import LogisticRegression


MODEL_ID = "factorized-logistic"
MODEL_VERSION = "factorized_logistic_v1"
FEATURE_VERSION = "lag3_digits_weekday_gap_v1"
REGULARIZATION_C = 0.1
MINIMUM_TRAINING_SAMPLES = 730
MAX_ITERATIONS = 1_000
TOLERANCE = 1e-6
RECENT_HIT_DRAWS = 3


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


def _one_hot(value: int, size: int) -> list[float]:
    result = [0.0] * size
    result[value] = 1.0
    return result


def _features(previous_three: list[dict[str, Any]], target_date: str) -> list[float]:
    if len(previous_three) != 3:
        raise ValueError("Exactly three previous draw results are required")

    vector: list[float] = []
    for draw in reversed(previous_three):
        number = draw["last_two"]
        vector.extend(_one_hot(int(number[0]), 10))
        vector.extend(_one_hot(int(number[1]), 10))

    target = date.fromisoformat(target_date)
    vector.extend(_one_hot(target.weekday(), 7))
    previous_date = date.fromisoformat(previous_three[-1]["draw_date"])
    gap_days = max(0, min((target - previous_date).days, 31))
    vector.append(gap_days / 31.0)
    return vector


def _training_data(
    history: list[dict[str, Any]],
) -> tuple[list[list[float]], list[int], list[int]]:
    features: list[list[float]] = []
    tens: list[int] = []
    units: list[int] = []
    for index in range(3, len(history)):
        number = history[index]["last_two"]
        features.append(_features(history[index - 3 : index], history[index]["draw_date"]))
        tens.append(int(number[0]))
        units.append(int(number[1]))
    return features, tens, units


def _fit_classifier(features: list[list[float]], labels: list[int]) -> LogisticRegression:
    if set(labels) != set(range(10)):
        raise ValueError("Training data must contain all digits from 0 to 9")
    classifier = LogisticRegression(
        C=REGULARIZATION_C,
        solver="lbfgs",
        max_iter=MAX_ITERATIONS,
        tol=TOLERANCE,
        random_state=0,
    )
    classifier.fit(features, labels)
    return classifier


def _days_since_last_hit(
    history: list[dict[str, Any]], target_date: str
) -> dict[str, int | None]:
    target = date.fromisoformat(target_date)
    last_seen: dict[str, date] = {}
    for draw in history:
        last_seen[draw["last_two"]] = date.fromisoformat(draw["draw_date"])
    return {
        f"{number:02d}": (
            (target - last_seen[f"{number:02d}"]).days
            if f"{number:02d}" in last_seen
            else None
        )
        for number in range(100)
    }


def rank_numbers(
    draws: Iterable[dict[str, Any]],
    target_date: str,
    selected_count: int,
    *,
    minimum_training_samples: int = MINIMUM_TRAINING_SAMPLES,
) -> dict[str, Any]:
    if not 60 <= selected_count <= 80:
        raise ValueError("selected_count must be between 60 and 80")

    history = _history_before(draws, target_date)
    features, tens_labels, units_labels = _training_data(history)
    if len(features) < minimum_training_samples:
        raise ValueError(
            f"At least {minimum_training_samples + 3} earlier draw results are required"
        )

    tens_model = _fit_classifier(features, tens_labels)
    units_model = _fit_classifier(features, units_labels)
    target_features = [_features(history[-3:], target_date)]
    tens_probability = dict(
        zip(tens_model.classes_, tens_model.predict_proba(target_features)[0], strict=True)
    )
    units_probability = dict(
        zip(units_model.classes_, units_model.predict_proba(target_features)[0], strict=True)
    )

    probabilities = {
        f"{tens}{units}": float(tens_probability[tens] * units_probability[units])
        for tens in range(10)
        for units in range(10)
    }
    probability_total = sum(probabilities.values())
    if probability_total <= 0:
        raise ValueError("The logistic model produced an invalid probability distribution")
    probabilities = {
        number: probability / probability_total
        for number, probability in probabilities.items()
    }

    ranking = sorted(probabilities, key=lambda number: (-probabilities[number], number))
    selected_numbers = ranking[:selected_count]
    days_since = _days_since_last_hit(history, target_date)
    recent_numbers = {draw["last_two"] for draw in history[-RECENT_HIT_DRAWS:]}
    scores = [
        {
            "number": number,
            "rank": rank,
            "probability": round(probabilities[number], 10),
            "days_since_last_hit": days_since[number],
            "recent_hit": number in recent_numbers,
        }
        for rank, number in enumerate(ranking, start=1)
    ]

    dataset_material = "|".join(
        f"{draw['draw_date']}:{draw['last_two']}" for draw in history
    )
    config = {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "regularization_c": REGULARIZATION_C,
        "solver": "lbfgs",
        "penalty": "l2",
        "max_iter": MAX_ITERATIONS,
        "tolerance": TOLERANCE,
        "minimum_training_samples": minimum_training_samples,
    }
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "config_hash": config_hash,
        "model_config": config,
        "selected_count": selected_count,
        "numbers": selected_numbers,
        "coverage_probability": round(
            sum(probabilities[number] for number in selected_numbers), 10
        ),
        "scores": scores,
        "training_draw_count": len(history),
        "training_sample_count": len(features),
        "trained_through": history[-1]["draw_date"],
        "dataset_hash": hashlib.sha256(dataset_material.encode()).hexdigest(),
        "training_dataset_hash": hashlib.sha256(dataset_material.encode()).hexdigest(),
        "cutoff_probability": round(probabilities[ranking[selected_count - 1]], 10),
        "recent_hit_window_days": RECENT_HIT_DRAWS,
        "library_versions": {"scikit_learn": sklearn.__version__},
        "model_explanation": (
            "Hai Logistic Regression L2 học riêng hàng chục và hàng đơn vị từ "
            "ba kỳ trước, thứ trong tuần và khoảng cách ngày; 100 xác suất được "
            "ghép bằng tích hai phân phối chữ số."
        ),
    }


def create_prediction(
    db: Database, prediction_date: date | str, selected_count: int
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

    key = {
        "prediction_date": target,
        "model_version": MODEL_VERSION,
        "selected_count": selected_count,
    }
    existing = db.predictions.find_one(key)
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
    prediction = rank_numbers(draws, target, selected_count)
    metadata = protocol.lock_metadata(db, draws, target, prediction, __name__, information_cutoff_at)
    document = {
        "prediction_date": target,
        **prediction,
        "status": "locked",
        **metadata,
        "evaluation": {"status": "pending"},
    }
    try:
        result = db.predictions.insert_one(document)
        document["_id"] = result.inserted_id
        return document, True
    except DuplicateKeyError:
        existing = db.predictions.find_one(key)
        if existing is None:
            raise
        return existing, False
