"""Recover missing historical days without fabricating pre-draw predictions."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.services import catboost_prediction, logistic_prediction, prediction
from app.services import prediction_protocol as protocol

MODELS = (prediction, logistic_prediction, catboost_prediction)
REPLAY_NOTE = "Hồi kiểm sau khi có kết quả; không tính vào tỷ lệ dự đoán trực tiếp."


def replay_evaluation(document: dict, actual: dict | None) -> dict:
    result = dict(document)
    if protocol.valid_actual(actual):
        result["evaluation"] = {
            "status": "evaluated", "actual_last_two": actual["last_two"],
            "actual_special_prize": actual["special_prize"],
            "actual_revision_hash": protocol.actual_revision_hash(actual),
            "hit": actual["last_two"] in document["numbers"],
        }
    else:
        result["evaluation"] = {"status": "invalidated"}
    return result


def create_missing_replays(db: Any, target: str, selected_count: int = 65) -> dict:
    target = date.fromisoformat(target).isoformat()
    if not 60 <= selected_count <= 80:
        raise ValueError("selected_count must be between 60 and 80")
    if target > protocol.utc_now().astimezone(ZoneInfo(protocol.TIMEZONE)).date().isoformat():
        raise ValueError("Chỉ hồi kiểm ngày đã có kết quả.")
    actual = db.draw_results.find_one({"draw_date": target})
    if not protocol.valid_actual(actual):
        raise ValueError("Ngày này chưa có kết quả hợp lệ hoặc kết quả đang xung đột.")

    history = None
    snapshot_id = None
    outcomes = []
    for model in MODELS:
        key = {"prediction_date": target, "model_version": model.MODEL_VERSION,
               "selected_count": selected_count}
        if db.predictions.find_one(key, {"_id": 1}):
            outcomes.append({**key, "status": "live_exists", "created": False})
            continue
        replay_id = ObjectId(protocol.fingerprint(["retrospective_replay_v1", key])[:24])
        existing = db.prediction_replays.find_one({"_id": replay_id})
        if existing:
            outcomes.append({**key, "status": "replay_exists", "created": False,
                             "prediction": replay_evaluation(existing, actual)})
            continue
        if history is None:
            history = [draw for draw in db.draw_results.find(
                {"draw_date": {"$lt": target}, "status": {"$ne": "conflict"}},
                {"draw_date": 1, "last_two": 1, "special_prize": 1, "status": 1},
            ).sort("draw_date", 1) if protocol.valid_actual(draw) and draw["draw_date"] < target]
            if not history:
                raise ValueError("Không có dữ liệu huấn luyện trước ngày hồi kiểm.")
            records = [{**{k: d.get(k) for k in ("draw_date", "last_two", "special_prize", "status")},
                        "draw_id": str(d["_id"]) if "_id" in d else None,
                        "revision_hash": protocol.actual_revision_hash(d)} for d in history]
            snapshot_id = protocol.fingerprint(records)
            db.training_datasets.update_one({"_id": snapshot_id}, {"$setOnInsert": {
                "records": records, "record_count": len(records),
                "dataset_hash": protocol.dataset_hash(history),
                "trained_through": history[-1]["draw_date"], "created_at": protocol.utc_now(),
            }}, upsert=True)
        try:
            # Every model receives the same strictly pre-target history, never the target result.
            ranked = model.rank_numbers(deepcopy(history), target, selected_count)
            if ranked["trained_through"] >= target:
                raise ValueError("Training history crosses the replay cutoff")
            config = ranked.get("model_config") or protocol.constants(model.__name__)
            document = {
                **ranked, **key, "_id": replay_id,
                "prediction_kind": "retrospective", "status": "replayed",
                "evaluation_protocol": "retrospective_replay_v1",
                "excluded_from_live_metrics": True, "note": REPLAY_NOTE,
                "created_at": protocol.utc_now(), "locked_at": None,
                "training_snapshot_id": snapshot_id,
                "model_config": config, "config_hash": protocol.fingerprint(config),
                "code_hash": protocol.code_hash(model.__name__),
            }
            actual = db.draw_results.find_one({"draw_date": target})
            document = replay_evaluation(document, actual)
            saved = db.prediction_replays.update_one(
                {"_id": replay_id}, {"$setOnInsert": document}, upsert=True)
            # A concurrent request may have saved the same immutable replay first.
            document = db.prediction_replays.find_one({"_id": replay_id})
            outcomes.append({**key, "status": "replayed", "created": saved.upserted_id is not None,
                             "prediction": replay_evaluation(document, actual)})
        except (ValueError, RuntimeError) as exc:
            outcomes.append({**key, "status": "failed", "created": False, "error": str(exc)})
    return {"prediction_date": target, "selected_count": selected_count,
            "status": "partial_failure" if any(item["status"] == "failed" for item in outcomes) else "completed",
            "models": outcomes, "note": REPLAY_NOTE}


def history_with_replays(db: Any, model_version: str, limit: int) -> list[dict]:
    projection = {"scores": 0, "window_details": 0}
    live = list(db.predictions.find({"model_version": model_version}, projection)
                .sort([("prediction_date", -1), ("locked_at", -1)]).limit(limit))
    replays = list(db.prediction_replays.find({"model_version": model_version}, projection)
                   .sort("prediction_date", -1).limit(limit))
    live_keys = {(item["prediction_date"], item["selected_count"]) for item in live}
    actuals = {draw["draw_date"]: draw for draw in db.draw_results.find(
        {"draw_date": {"$in": list({item["prediction_date"] for item in replays})}}
    )} if replays else {}
    combined = live + [replay_evaluation(item, actuals.get(item["prediction_date"]))
                       for item in replays if (item["prediction_date"], item["selected_count"]) not in live_keys]
    combined.sort(key=lambda item: (item["prediction_date"], item["selected_count"]), reverse=True)
    return [{k: v for k, v in item.items() if k not in ("numbers", "dataset_hash", "training_dataset_hash")}
            for item in combined[:limit]]
