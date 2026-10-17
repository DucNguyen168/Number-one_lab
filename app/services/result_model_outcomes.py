"""Read compact model outcomes for a page of draw results, without training or writes."""
from typing import Any

from app.services import prediction_protocol as protocol
from app.services.catboost_prediction import MODEL_VERSION as CATBOOST_MODEL_VERSION
from app.services.logistic_prediction import MODEL_VERSION as LOGISTIC_MODEL_VERSION
from app.services.prediction import MODEL_VERSION as FREQUENCY_MODEL_VERSION


RESULT_MODELS = {
    "A": FREQUENCY_MODEL_VERSION,
    "B": LOGISTIC_MODEL_VERSION,
    "C": CATBOOST_MODEL_VERSION,
}


def _outcome(prediction: dict | None, draw: dict, count: int, *, replay: bool = False) -> dict:
    outcome = {"status": "missing", "prediction_kind": None, "selected_count": count}
    if prediction is None:
        return outcome
    outcome["prediction_kind"] = "retrospective" if replay else "live"
    outcome["status"] = "invalidated"
    numbers = prediction.get("numbers")
    if not protocol.valid_actual(draw) or not isinstance(numbers, list):
        return outcome
    if (len(numbers) != count or any(not isinstance(number, str) or len(number) != 2
                                   or not number.isascii() or not number.isdigit() for number in numbers)
            or len(set(numbers)) != count):
        return outcome
    hit = draw["last_two"] in numbers
    if not replay:
        evaluation = prediction.get("evaluation") or {}
        status = evaluation.get("status", "pending")
        if status != "evaluated":
            outcome["status"] = "invalidated" if status == "invalidated" else "pending"
            return outcome
        # A corrected draw must not retain the previous green/red evaluation.
        if (evaluation.get("actual_last_two") != draw["last_two"]
                or evaluation.get("actual_special_prize") != draw["special_prize"]
                or evaluation.get("hit") is not hit
                or (evaluation.get("actual_revision_hash")
                    and evaluation["actual_revision_hash"] != protocol.actual_revision_hash(draw))):
            return outcome
    outcome["status"] = "hit" if hit else "miss"
    return outcome


def attach_result_model_outcomes(db: Any, draws: list[dict], selected_count: int) -> list[dict]:
    if not draws:
        return draws
    query = {
        "prediction_date": {"$in": [draw["draw_date"] for draw in draws]},
        "model_version": {"$in": list(RESULT_MODELS.values())},
        "selected_count": selected_count,
    }
    projection = {"_id": 0, "prediction_date": 1, "model_version": 1, "numbers": 1, "evaluation": 1}
    # Two bounded reads for the entire visible page, never one read per cell.
    live = {(p["prediction_date"], p["model_version"]): p for p in db.predictions.find(query, projection)}
    replays = {(p["prediction_date"], p["model_version"]): p for p in db.prediction_replays.find(query, projection)}
    result = []
    for draw in draws:
        outcomes = {}
        for letter, version in RESULT_MODELS.items():
            key = (draw["draw_date"], version)
            prediction = live.get(key)
            is_replay = prediction is None and key in replays
            outcomes[letter] = _outcome(replays.get(key) if is_replay else prediction,
                                        draw, selected_count, replay=is_replay)
        result.append({**draw, "model_selected_count": selected_count, "model_outcomes": outcomes})
    return result
