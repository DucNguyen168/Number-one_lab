from __future__ import annotations

from collections import defaultdict
from typing import Any

from pymongo.database import Database

from app.services.catboost_prediction import MODEL_VERSION as CATBOOST_MODEL_VERSION
from app.services.logistic_prediction import MODEL_VERSION as LOGISTIC_MODEL_VERSION
from app.services.prediction import MODEL_VERSION as FREQUENCY_MODEL_VERSION


def comparison_summary(db: Database, selected_count: int) -> dict[str, Any]:
    documents = list(
        db.predictions.find(
            {
                "selected_count": selected_count,
                "model_version": {
                    "$in": [FREQUENCY_MODEL_VERSION, LOGISTIC_MODEL_VERSION]
                },
                "evaluation.status": "evaluated",
            },
            {
                "_id": 0,
                "prediction_date": 1,
                "model_version": 1,
                "evaluation.actual_last_two": 1,
                "evaluation.hit": 1,
            },
        ).sort("prediction_date", 1)
    )
    by_date: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for document in documents:
        by_date[document["prediction_date"]][document["model_version"]] = document

    pairs: list[dict[str, Any]] = []
    for prediction_date, models in sorted(by_date.items()):
        if FREQUENCY_MODEL_VERSION not in models or LOGISTIC_MODEL_VERSION not in models:
            continue
        frequency = models[FREQUENCY_MODEL_VERSION]
        logistic = models[LOGISTIC_MODEL_VERSION]
        frequency_hit = bool(frequency["evaluation"].get("hit"))
        logistic_hit = bool(logistic["evaluation"].get("hit"))
        pairs.append(
            {
                "prediction_date": prediction_date,
                "actual_last_two": logistic["evaluation"].get("actual_last_two"),
                "frequency_hit": frequency_hit,
                "logistic_hit": logistic_hit,
            }
        )

    total = len(pairs)
    frequency_hits = sum(pair["frequency_hit"] for pair in pairs)
    logistic_hits = sum(pair["logistic_hit"] for pair in pairs)
    frequency_only = sum(
        pair["frequency_hit"] and not pair["logistic_hit"] for pair in pairs
    )
    logistic_only = sum(
        pair["logistic_hit"] and not pair["frequency_hit"] for pair in pairs
    )
    both_hit = sum(pair["frequency_hit"] and pair["logistic_hit"] for pair in pairs)
    both_miss = sum(
        not pair["frequency_hit"] and not pair["logistic_hit"] for pair in pairs
    )
    return {
        "selected_count": selected_count,
        "baseline": selected_count / 100,
        "paired_predictions": total,
        "frequency_model": {
            "model_version": FREQUENCY_MODEL_VERSION,
            "hits": frequency_hits,
            "hit_rate": round(frequency_hits / total, 8) if total else None,
        },
        "logistic_model": {
            "model_version": LOGISTIC_MODEL_VERSION,
            "hits": logistic_hits,
            "hit_rate": round(logistic_hits / total, 8) if total else None,
        },
        "lift_logistic_vs_frequency": (
            round((logistic_hits - frequency_hits) / total, 8) if total else None
        ),
        "disagreements": {
            "frequency_only_hit": frequency_only,
            "logistic_only_hit": logistic_only,
            "both_hit": both_hit,
            "both_miss": both_miss,
        },
        "recent_pairs": list(reversed(pairs[-30:])),
        "note": (
            "Chỉ ghép các dự đoán đã khóa và đã đối chiếu cùng ngày, cùng số lượng. "
            "Tỷ lệ quan sát chưa tự chứng minh mô hình vượt baseline."
        ),
    }


def three_way_comparison_summary(db: Database, selected_count: int) -> dict[str, Any]:
    versions = [FREQUENCY_MODEL_VERSION, LOGISTIC_MODEL_VERSION, CATBOOST_MODEL_VERSION]
    documents = list(
        db.predictions.find(
            {
                "selected_count": selected_count,
                "model_version": {"$in": versions},
                "evaluation.status": "evaluated",
            },
            {
                "_id": 0,
                "prediction_date": 1,
                "model_version": 1,
                "evaluation.actual_last_two": 1,
                "evaluation.hit": 1,
            },
        ).sort("prediction_date", 1)
    )
    by_date: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for document in documents:
        by_date[document["prediction_date"]][document["model_version"]] = document

    rows: list[dict[str, Any]] = []
    for prediction_date, models in sorted(by_date.items()):
        if any(version not in models for version in versions):
            continue
        rows.append(
            {
                "prediction_date": prediction_date,
                "actual_last_two": models[CATBOOST_MODEL_VERSION]["evaluation"].get(
                    "actual_last_two"
                ),
                "frequency_hit": bool(
                    models[FREQUENCY_MODEL_VERSION]["evaluation"].get("hit")
                ),
                "logistic_hit": bool(
                    models[LOGISTIC_MODEL_VERSION]["evaluation"].get("hit")
                ),
                "catboost_hit": bool(
                    models[CATBOOST_MODEL_VERSION]["evaluation"].get("hit")
                ),
            }
        )

    total = len(rows)

    def model_metrics(version: str, hit_key: str) -> dict[str, Any]:
        hits = sum(bool(row[hit_key]) for row in rows)
        return {
            "model_version": version,
            "hits": hits,
            "hit_rate": round(hits / total, 8) if total else None,
        }

    return {
        "selected_count": selected_count,
        "baseline": selected_count / 100,
        "paired_predictions": total,
        "frequency_model": model_metrics(FREQUENCY_MODEL_VERSION, "frequency_hit"),
        "logistic_model": model_metrics(LOGISTIC_MODEL_VERSION, "logistic_hit"),
        "catboost_model": model_metrics(CATBOOST_MODEL_VERSION, "catboost_hit"),
        "recent_pairs": list(reversed(rows[-30:])),
        "note": (
            "Chỉ so sánh các snapshot A/B/C đã khóa trước kỳ quay, cùng ngày, cùng Top N "
            "và đã có kết quả thực. Chưa có đủ kỳ ghép thì không kết luận mô hình thắng."
        ),
    }
