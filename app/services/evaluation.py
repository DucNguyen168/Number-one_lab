from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from app.services.prediction import MODEL_VERSION
from app.services import prediction_protocol as protocol


def _evaluate_snapshots(db, collection, *, digit=False):
    counters = {"evaluated": 0, "hits": 0, "misses": 0, "skipped": 0,
                "reevaluated": 0, "invalidated": 0}
    predictions = list(collection.find(
        {"evaluation.status": {"$in": ["pending", "evaluated", "invalidated"]}},
        {"scores": 0, "window_details": 0, "evaluation_history": 0},
    ))
    days = sorted({p["prediction_date"] for p in predictions})
    draws = {d["draw_date"]: d for d in db.draw_results.find(
        {"draw_date": {"$in": days}},
        {"draw_date": 1, "special_prize": 1, "last_two": 1, "status": 1},
    )}
    for prediction in predictions:
        draw = draws.get(prediction["prediction_date"])
        previous = prediction["evaluation"]
        revision = protocol.actual_revision_hash(draw)
        if not protocol.valid_actual(draw):
            counters["skipped"] += 1
            if previous["status"] == "pending":
                continue
            current = {"status": "invalidated", "actual_revision_hash": revision,
                       "reason": "actual_unavailable_invalid_or_conflicting", "eligible_for_comparison": False}
            if all(previous.get(k) == v for k, v in current.items()):
                continue
        else:
            actual = draw["last_two"][-1] if digit else draw["last_two"]
            hit = actual == prediction.get("predicted_digit") if digit else actual in prediction.get("numbers", [])
            issues = protocol.eligibility_reasons(prediction, draw, check_evaluation=False)
            current = {"status": "evaluated", "actual_special_prize": draw["special_prize"],
                       "actual_digit" if digit else "actual_last_two": actual, "hit": hit,
                       "actual_revision_hash": revision, "eligible_for_comparison": not issues,
                       "eligibility_reasons": issues}
            if all(previous.get(k) == v for k, v in current.items()):
                continue
        current["evaluated_at"] = datetime.now(timezone.utc)
        update = {"$set": {"evaluation": current,
                           "status": "evaluated" if current["status"] == "evaluated" else "evaluation_invalidated"}}
        if previous["status"] != "pending":
            update["$push"] = {"evaluation_history": {
                "previous": previous, "changed_at": current["evaluated_at"],
                "reason": "actual_revision_or_evaluation_changed",
            }}
        # Compare-and-set prevents two collectors from appending the same correction.
        updated = collection.update_one({"_id": prediction["_id"], "evaluation": previous}, update)
        if not updated.modified_count:
            continue
        if current["status"] == "invalidated":
            counters["invalidated"] += 1
        else:
            counters["evaluated"] += 1
            counters["hits" if current["hit"] else "misses"] += 1
            counters["reevaluated"] += int(previous["status"] != "pending")
    return counters


def evaluate_pending_predictions(db: Database) -> dict[str, int]:
    """Score pending snapshots and reconcile saved scores with the current actual revision."""
    return _evaluate_snapshots(db, db.predictions)


def evaluate_pending_digit_predictions(db: Database) -> dict[str, int]:
    return _evaluate_snapshots(db, db.digit_predictions, digit=True)


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
