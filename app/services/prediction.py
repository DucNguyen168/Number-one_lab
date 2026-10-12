from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date
from typing import Any, Iterable

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.services import prediction_protocol as protocol


MODEL_VERSION = "frequency_ensemble_v1"
WINDOW_WEIGHTS: tuple[tuple[int | None, float], ...] = (
    (30, 0.35),
    (90, 0.25),
    (180, 0.20),
    (365, 0.15),
    (None, 0.05),
)
SMOOTHING_ALPHA = 1.0
# Số ngày gần nhất bị coi là "vừa ra" — dùng để cảnh báo người dùng tránh
RECENT_HIT_DAYS = 3


def _history_before(draws: Iterable[dict[str, Any]], target_date: str) -> list[dict[str, Any]]:
    return sorted(
        (
            draw
            for draw in draws
            if draw.get("draw_date", "") < target_date
            and draw.get("status") != "conflict"
            and isinstance(draw.get("last_two"), str)
        ),
        key=lambda draw: draw["draw_date"],
    )


def _compute_days_since_last_hit(
    history: list[dict[str, Any]], target_date: str
) -> dict[str, int | None]:
    """
    Với mỗi số 00–99, tính số ngày kể từ lần cuối nó xuất hiện trong lịch sử.
    Trả về None nếu số chưa bao giờ xuất hiện.
    Ngày được so sánh theo ISO string (YYYY-MM-DD) nên cần parse đúng.
    """
    last_seen: dict[str, str] = {}
    for draw in history:
        last_seen[draw["last_two"]] = draw["draw_date"]

    # Parse target_date để tính delta
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        target = date.today()

    result: dict[str, int | None] = {}
    for number in (f"{n:02d}" for n in range(100)):
        if number in last_seen:
            try:
                last_date = date.fromisoformat(last_seen[number])
                result[number] = (target - last_date).days
            except ValueError:
                result[number] = None
        else:
            result[number] = None
    return result


def rank_numbers(
    draws: Iterable[dict[str, Any]], target_date: str, selected_count: int
) -> dict[str, Any]:
    if not 60 <= selected_count <= 80:
        raise ValueError("selected_count must be between 60 and 80")
    history = _history_before(draws, target_date)
    if len(history) < 30:
        raise ValueError("At least 30 earlier draw results are required")

    probabilities = {f"{number:02d}": 0.0 for number in range(100)}
    window_details: list[dict[str, Any]] = []
    for window, weight in WINDOW_WEIGHTS:
        sample = history if window is None else history[-window:]
        counts = Counter(draw["last_two"] for draw in sample)
        denominator = len(sample) + 100 * SMOOTHING_ALPHA
        for number in probabilities:
            probabilities[number] += weight * (
                counts[number] + SMOOTHING_ALPHA
            ) / denominator
        window_details.append(
            {
                "window": "all" if window is None else window,
                "weight": weight,
                "observations": len(sample),
            }
        )

    # Tính days_since_last_hit cho mỗi số
    days_since = _compute_days_since_last_hit(history, target_date)

    # Lấy danh sách các số xuất hiện trong RECENT_HIT_DAYS ngày gần nhất
    recent_numbers: set[str] = set()
    for draw in history[-RECENT_HIT_DAYS:]:
        recent_numbers.add(draw["last_two"])

    ranking = sorted(probabilities, key=lambda number: (-probabilities[number], number))
    scores = [
        {
            "number": number,
            "rank": rank,
            "probability": round(probabilities[number], 10),
            # Số ngày kể từ lần cuối xuất hiện (None = chưa bao giờ ra)
            "days_since_last_hit": days_since.get(number),
            # Cờ cảnh báo: số này đã ra trong RECENT_HIT_DAYS ngày gần nhất
            "recent_hit": number in recent_numbers,
        }
        for rank, number in enumerate(ranking, start=1)
    ]
    selected_numbers = ranking[:selected_count]
    trained_through = history[-1]["draw_date"]
    dataset_material = "|".join(
        f"{draw['draw_date']}:{draw['last_two']}" for draw in history
    )
    dataset_hash = hashlib.sha256(dataset_material.encode()).hexdigest()

    # Thống kê phân phối để giải thích lý do loại số
    cutoff_probability = probabilities[ranking[selected_count - 1]] if len(ranking) >= selected_count else 0.0

    return {
        "model_version": MODEL_VERSION,
        "selected_count": selected_count,
        "numbers": selected_numbers,
        "coverage_probability": round(
            sum(probabilities[number] for number in selected_numbers), 10
        ),
        "scores": scores,
        "window_details": window_details,
        "training_draw_count": len(history),
        "trained_through": trained_through,
        "dataset_hash": dataset_hash,
        # Ngưỡng điểm cut-off: số nào thấp hơn đây sẽ bị loại
        "cutoff_probability": round(cutoff_probability, 10),
        # Số ngày gần nhất được dùng để đánh dấu "vừa ra"
        "recent_hit_window_days": RECENT_HIT_DAYS,
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

    existing = db.predictions.find_one(
        {
            "prediction_date": target,
            "model_version": MODEL_VERSION,
            "selected_count": selected_count,
        }
    )
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
        existing = db.predictions.find_one(
            {
                "prediction_date": target,
                "model_version": MODEL_VERSION,
                "selected_count": selected_count,
            }
        )
        if existing is None:
            raise
        return existing, False
