from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from datetime import date, datetime, timezone
from typing import Any, Iterable, Protocol

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError


MODEL_ID = "direct-catboost"
MODEL_VERSION = "direct_catboost_multiclass_v2_context2000"
FEATURE_VERSION = "context2000_compact_v2"
MINIMUM_TRAINING_SAMPLES = 730
LAG_COUNT = 2_000
RAW_LAG_COUNT = 14
FREQUENCY_WINDOWS = (365, 2_000)
SUMMARY_WINDOWS = (7, 14, 30, 90, 365, 730, 2_000)
ITERATIONS = 48
DEPTH = 4
LEARNING_RATE = 0.06
L2_LEAF_REG = 12.0
UNIFORM_SHRINKAGE = 0.15
RANDOM_SEED = 20260923
RECENT_HIT_DRAWS = 3


class _ProbabilityClassifier(Protocol):
    classes_: Any

    def predict_proba(self, features: list[list[float]]) -> Any: ...


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


def _cyclic(value: int, period: int) -> tuple[float, float]:
    angle = 2 * math.pi * value / period
    return math.sin(angle), math.cos(angle)


def _features(previous: list[dict[str, Any]], target_date: str) -> list[float]:
    if len(previous) != LAG_COUNT:
        raise ValueError(f"Exactly {LAG_COUNT} previous draw results are required")

    numbers = [int(draw["last_two"]) for draw in previous]
    vector: list[float] = []

    # Keep the latest 14 draws as ordered raw lags. The full 2,000-draw context
    # is represented by stable frequency and rolling-summary features below;
    # feeding all 6,000 raw value/tens/units columns is too slow for serverless.
    for number in reversed(numbers[-RAW_LAG_COUNT:]):
        vector.extend((number / 99.0, (number // 10) / 9.0, (number % 10) / 9.0))

    for window in FREQUENCY_WINDOWS:
        sample = numbers[-window:]
        counts = [0] * 100
        for number in sample:
            counts[number] += 1
        vector.extend(count / len(sample) for count in counts)

    for window in SUMMARY_WINDOWS:
        sample = numbers[-window:]
        mean = sum(sample) / len(sample)
        variance = sum((number - mean) ** 2 for number in sample) / len(sample)
        changes = sum(left != right for left, right in zip(sample, sample[1:]))
        vector.extend(
            (
                mean / 99.0,
                math.sqrt(variance) / 99.0,
                len(set(sample)) / min(100, len(sample)),
                changes / max(1, len(sample) - 1),
            )
        )

    target = date.fromisoformat(target_date)
    weekday = [0.0] * 7
    weekday[target.weekday()] = 1.0
    vector.extend(weekday)
    vector.extend(_cyclic(target.timetuple().tm_yday - 1, 366))
    vector.extend(_cyclic(target.month - 1, 12))

    previous_date = date.fromisoformat(previous[-1]["draw_date"])
    vector.append(max(0, min((target - previous_date).days, 31)) / 31.0)
    vector.extend(
        (
            len(set(numbers[-7:])) / 7.0,
            sum(numbers[-7:]) / (7 * 99.0),
            abs(numbers[-1] - numbers[-2]) / 99.0,
            float(numbers[-1] // 10 == numbers[-2] // 10),
            float(numbers[-1] % 10 == numbers[-2] % 10),
        )
    )
    return vector


def _training_data(history: list[dict[str, Any]]) -> tuple[list[list[float]], list[int]]:
    features: list[list[float]] = []
    labels: list[int] = []
    for index in range(LAG_COUNT, len(history)):
        features.append(
            _features(history[index - LAG_COUNT : index], history[index]["draw_date"])
        )
        labels.append(int(history[index]["last_two"]))
    return features, labels


def _fit_classifier(features: list[list[float]], labels: list[int]) -> _ProbabilityClassifier:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:  # pragma: no cover - depends on deployment image
        raise RuntimeError(
            "CatBoost is not installed. Run: pip install -r requirements.txt"
        ) from exc

    if len(set(labels)) < 2:
        raise ValueError("Training data must contain at least two result classes")
    classifier = CatBoostClassifier(
        loss_function="MultiClass",
        iterations=ITERATIONS,
        depth=DEPTH,
        learning_rate=LEARNING_RATE,
        l2_leaf_reg=L2_LEAF_REG,
        random_seed=RANDOM_SEED,
        has_time=True,
        bootstrap_type="Bayesian",
        bagging_temperature=0.5,
        allow_writing_files=False,
        verbose=False,
        thread_count=2,
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
    available_training_samples = max(0, len(history) - LAG_COUNT)
    if available_training_samples < minimum_training_samples:
        raise ValueError(
            f"At least {minimum_training_samples + LAG_COUNT} earlier draw results are required"
        )
    features, labels = _training_data(history)

    classifier = _fit_classifier(features, labels)
    raw = classifier.predict_proba([_features(history[-LAG_COUNT:], target_date)])[0]
    observed = {
        int(label): float(probability)
        for label, probability in zip(classifier.classes_, raw, strict=True)
    }
    probabilities = {
        f"{number:02d}": (
            (1.0 - UNIFORM_SHRINKAGE) * observed.get(number, 0.0)
            + UNIFORM_SHRINKAGE / 100.0
        )
        for number in range(100)
    }
    total = sum(probabilities.values())
    probabilities = {number: value / total for number, value in probabilities.items()}
    ranking = sorted(probabilities, key=lambda number: (-probabilities[number], number))
    selected_numbers = ranking[:selected_count]
    days_since = _days_since_last_hit(history, target_date)
    recent_numbers = {draw["last_two"] for draw in history[-RECENT_HIT_DRAWS:]}

    dataset_material = "|".join(
        f"{draw['draw_date']}:{draw['last_two']}" for draw in history
    )
    config = {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "objective": "MultiClass",
        "iterations": ITERATIONS,
        "depth": DEPTH,
        "learning_rate": LEARNING_RATE,
        "l2_leaf_reg": L2_LEAF_REG,
        "has_time": True,
        "uniform_shrinkage": UNIFORM_SHRINKAGE,
        "lag_count": LAG_COUNT,
        "raw_lag_count": RAW_LAG_COUNT,
        "frequency_windows": FREQUENCY_WINDOWS,
        "summary_windows": SUMMARY_WINDOWS,
        "feature_count": len(features[0]),
        "minimum_training_samples": minimum_training_samples,
        "random_seed": RANDOM_SEED,
    }
    try:
        catboost_version = importlib.metadata.version("catboost")
    except importlib.metadata.PackageNotFoundError:
        catboost_version = "unavailable"

    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "config_hash": hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "model_config": config,
        "selected_count": selected_count,
        "numbers": selected_numbers,
        "coverage_probability": round(
            sum(probabilities[number] for number in selected_numbers), 10
        ),
        "scores": [
            {
                "number": number,
                "rank": rank,
                "probability": round(probabilities[number], 10),
                "days_since_last_hit": days_since[number],
                "recent_hit": number in recent_numbers,
            }
            for rank, number in enumerate(ranking, start=1)
        ],
        "training_draw_count": len(history),
        "training_sample_count": len(features),
        "feature_lookback_draw_count": LAG_COUNT,
        "trained_through": history[-1]["draw_date"],
        "dataset_hash": hashlib.sha256(dataset_material.encode()).hexdigest(),
        "training_dataset_hash": hashlib.sha256(dataset_material.encode()).hexdigest(),
        "cutoff_probability": round(probabilities[ranking[selected_count - 1]], 10),
        "recent_hit_window_days": RECENT_HIT_DRAWS,
        "library_versions": {"catboost": catboost_version},
        "model_explanation": (
            "CatBoost đa lớp học trực tiếp 100 nhãn 00-99 từ ngữ cảnh 2.000 kỳ: "
            "14 kỳ gần nhất theo đúng thứ tự, tần suất 00-99 ở cửa sổ 365/2.000 "
            "kỳ, thống kê nhiều cửa sổ, lịch và khoảng cách ngày. has_time giữ "
            "nguyên thứ tự thời gian; phân phối được co 15% về đều để hạn chế "
            "quá tự tin."
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

    draws = list(
        db.draw_results.find(
            {"draw_date": {"$lt": target}, "status": {"$ne": "conflict"}},
            {"_id": 0, "draw_date": 1, "last_two": 1, "status": 1},
        ).sort("draw_date", 1)
    )
    prediction = rank_numbers(draws, target, selected_count)
    now = datetime.now(timezone.utc)
    document = {
        "prediction_date": target,
        **prediction,
        "strategy_id": "raw_top_n_v1",
        "information_cutoff_at": now,
        "status": "locked",
        "created_at": now,
        "locked_at": now,
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
