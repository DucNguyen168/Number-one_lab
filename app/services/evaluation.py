from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from app.services.prediction import MODEL_VERSION


def evaluate_pending_predictions(db: Database) -> dict[str, int]:
    counters = {"evaluated": 0, "hits": 0, "misses": 0, "skipped": 0}
    pending = db.predictions.find({"evaluation.status": "pending"})
    for prediction in pending:
        draw = db.draw_results.find_one(
            {"draw_date": prediction["prediction_date"], "status": {"$ne": "conflict"}}
        )
        if draw is None:
            counters["skipped"] += 1
            continue
        actual = draw["last_two"]
        hit = actual in prediction.get("numbers", [])
        evaluation = {
            "status": "evaluated",
            "actual_special_prize": draw["special_prize"],
            "actual_last_two": actual,
            "hit": hit,
            "evaluated_at": datetime.now(timezone.utc),
        }
        db.predictions.update_one(
            {"_id": prediction["_id"], "evaluation.status": "pending"},
            {"$set": {"evaluation": evaluation, "status": "evaluated"}},
        )
        counters["evaluated"] += 1
        counters["hits" if hit else "misses"] += 1
    return counters


def evaluate_pending_digit_predictions(db: Database) -> dict[str, int]:
    counters = {"evaluated": 0, "hits": 0, "misses": 0, "skipped": 0}
    pending = db.digit_predictions.find({"evaluation.status": "pending"})
    for prediction in pending:
        draw = db.draw_results.find_one(
            {"draw_date": prediction["prediction_date"], "status": {"$ne": "conflict"}}
        )
        if draw is None:
            counters["skipped"] += 1
            continue
        actual = draw["special_prize"][-1]
        hit = actual == prediction.get("predicted_digit")
        evaluation = {
            "status": "evaluated",
            "actual_special_prize": draw["special_prize"],
            "actual_digit": actual,
            "hit": hit,
            "evaluated_at": datetime.now(timezone.utc),
        }
        updated = db.digit_predictions.update_one(
            {"_id": prediction["_id"], "evaluation.status": "pending"},
            {"$set": {"evaluation": evaluation, "status": "evaluated"}},
        )
        if updated.modified_count:
            counters["evaluated"] += 1
            counters["hits" if hit else "misses"] += 1
    return counters


def metrics_summary(db: Database) -> dict[str, Any]:
    total_draws = db.draw_results.count_documents({"status": {"$ne": "conflict"}})
    conflicts = db.draw_results.count_documents({"status": "conflict"})
    model_filter = {"model_version": MODEL_VERSION}
    total_predictions = db.predictions.count_documents(model_filter)
    evaluated = list(
        db.predictions.find({**model_filter, "evaluation.status": "evaluated"})
    )
    hits = sum(1 for item in evaluated if item.get("evaluation", {}).get("hit"))

    by_count: dict[str, dict[str, Any]] = {}
    for item in evaluated:
        key = str(item["selected_count"])
        bucket = by_count.setdefault(key, {"evaluated": 0, "hits": 0})
        bucket["evaluated"] += 1
        bucket["hits"] += int(bool(item.get("evaluation", {}).get("hit")))
    for key, bucket in by_count.items():
        bucket["hit_rate"] = round(bucket["hits"] / bucket["evaluated"], 6)
        bucket["random_baseline"] = int(key) / 100
        bucket["lift_vs_random"] = round(
            bucket["hit_rate"] - bucket["random_baseline"], 6
        )

    skipped = db.predictions.count_documents(
        {**model_filter, "evaluation.status": "pending"}
    )
    latest_draw = db.draw_results.find_one(
        {"status": {"$ne": "conflict"}}, sort=[("draw_date", -1)]
    )
    latest_prediction = db.predictions.find_one(
        model_filter, sort=[("prediction_date", -1)]
    )
    digit_total = db.digit_predictions.count_documents({})
    digit_evaluated = list(
        db.digit_predictions.find({"evaluation.status": "evaluated"})
    )
    digit_hits = sum(
        1 for item in digit_evaluated if item.get("evaluation", {}).get("hit")
    )
    latest_digit_prediction = db.digit_predictions.find_one(
        sort=[("prediction_date", -1)]
    )
    return {
        "draws": total_draws,
        "conflicts": conflicts,
        "predictions": total_predictions,
        "evaluated": len(evaluated),
        "hits": hits,
        "misses": len(evaluated) - hits,
        "skipped": skipped,
        "hit_rate": round(hits / len(evaluated), 6) if evaluated else None,
        "by_selected_count": by_count,
        "latest_draw_date": latest_draw.get("draw_date") if latest_draw else None,
        "latest_prediction_date": (
            latest_prediction.get("prediction_date") if latest_prediction else None
        ),
        "last_digit": {
            "predictions": digit_total,
            "evaluated": len(digit_evaluated),
            "hits": digit_hits,
            "misses": len(digit_evaluated) - digit_hits,
            "pending": db.digit_predictions.count_documents(
                {"evaluation.status": "pending"}
            ),
            "hit_rate": (
                round(digit_hits / len(digit_evaluated), 6)
                if digit_evaluated
                else None
            ),
            "random_baseline": 0.1,
            "latest_prediction_date": (
                latest_digit_prediction.get("prediction_date")
                if latest_digit_prediction
                else None
            ),
        },
    }
