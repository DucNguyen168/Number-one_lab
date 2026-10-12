"""Shared locking and immutable training provenance, independent of model ranking."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROTOCOL_VERSION = "locked_before1730_v2"
TIMEZONE = "Asia/Ho_Chi_Minh"
DEADLINE_TIME = "17:30"
STRATEGY = "raw_top_n_v1"


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime):
        raise ValueError("Invalid timestamp")
    return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).astimezone(timezone.utc)


def deadline(target: str) -> datetime:
    day = date.fromisoformat(target)
    hour, minute = map(int, DEADLINE_TIME.split(":"))
    return datetime.combine(day, time(hour, minute), ZoneInfo(TIMEZONE)).astimezone(timezone.utc)


def ensure_open(target: str) -> datetime:
    now = as_utc(utc_now())
    if now >= deadline(target):
        raise ValueError(f"Prediction deadline has passed: {target} {DEADLINE_TIME} ({TIMEZONE})")
    return now


def valid_actual(draw: dict[str, Any] | None) -> bool:
    if not draw or draw.get("status") == "conflict":
        return False
    special, number = draw.get("special_prize"), draw.get("last_two")
    return (isinstance(special, str) and len(special) == 5 and special.isascii()
            and special.isdigit() and isinstance(number, str) and number == special[-2:])


def actual_revision_hash(draw: dict[str, Any] | None) -> str:
    return fingerprint({key: draw.get(key) if draw else None
                        for key in ("draw_date", "special_prize", "last_two", "status")})


def dataset_hash(draws: list[dict[str, Any]]) -> str:
    return hashlib.sha256("|".join(f"{d['draw_date']}:{d['last_two']}" for d in draws).encode()).hexdigest()


def code_hash(module_name: str) -> str:
    module = sys.modules[module_name]
    paths = [Path(module.__file__), Path(__file__)]
    if module_name.endswith("digit_prediction"):
        paths.append(Path(__file__).with_name("prediction.py"))
    return fingerprint({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def constants(module_name: str) -> dict[str, Any]:
    return {key: value for key, value in vars(sys.modules[module_name]).items()
            if key.isupper() and isinstance(value, (str, int, float, bool, tuple))}


def lock_metadata(db, draws, target, prediction, module_name, information_cutoff_at):
    """Deduplicate full historical records by content; never overwrite a saved dataset."""
    history = sorted(draws, key=lambda d: d["draw_date"])
    records = []
    for draw in history:
        record = {key: draw.get(key) for key in ("draw_date", "last_two", "special_prize", "status")}
        record["draw_id"] = str(draw["_id"]) if "_id" in draw else None
        record["revision_hash"] = actual_revision_hash(draw)
        records.append(record)
    snapshot_id = fingerprint(records)
    db.training_datasets.update_one({"_id": snapshot_id}, {"$setOnInsert": {
        "records": records, "dataset_hash": dataset_hash(history),
        "record_count": len(records), "trained_through": history[-1]["draw_date"],
        "created_at": information_cutoff_at,
    }}, upsert=True)
    # Check after the possibly long fit AND the snapshot write, immediately before locking.
    if db.draw_results.find_one({"draw_date": target}) is not None:
        raise ValueError("A result already exists for this date; retrospective predictions are not allowed")
    locked_at = ensure_open(target)
    config = prediction.get("model_config") or constants(module_name)
    libraries = {**prediction.get("library_versions", {}), "python": platform.python_version()}
    if module_name.endswith(("logistic_prediction", "catboost_prediction")):
        libraries.update({name: importlib.metadata.version(name) for name in ("numpy", "scipy")})
    count = prediction.get("selected_count", 1)
    strategy = STRATEGY if count != 1 else "raw_top_1_digit_v1"
    return {
        "model_config": config, "config_hash": fingerprint(config),
        "code_hash": code_hash(module_name),
        "library_versions": libraries,
        "training_snapshot_id": snapshot_id,
        "training_snapshot_dataset_hash": dataset_hash(history),
        "evaluation_protocol": PROTOCOL_VERSION,
        "prediction_timezone": TIMEZONE, "prediction_deadline_at": deadline(target),
        "strategy_id": strategy,
        "comparison_batch_id": fingerprint({"date": target, "count": count, "strategy": strategy,
                                             "protocol": PROTOCOL_VERSION, "snapshot": snapshot_id}),
        "information_cutoff_at": information_cutoff_at,
        "created_at": locked_at, "locked_at": locked_at,
    }


def eligibility_reasons(pred, draw, *, check_evaluation=True):
    reasons = []
    target = pred.get("prediction_date", "")
    try:
        cutoff = deadline(target)
        locked = as_utc(pred["locked_at"])
        if locked >= cutoff:
            reasons.append("locked_after_deadline")
        if as_utc(pred["information_cutoff_at"]) > locked:
            reasons.append("invalid_information_cutoff")
        if as_utc(pred["prediction_deadline_at"]) != cutoff or pred.get("prediction_timezone") != TIMEZONE:
            reasons.append("invalid_deadline_metadata")
    except (ValueError, TypeError, KeyError):
        reasons.append("missing_or_invalid_lock_metadata")
    if pred.get("evaluation_protocol") != PROTOCOL_VERSION:
        reasons.append("missing_or_different_protocol")
    if not isinstance(pred.get("trained_through"), str) or pred["trained_through"] >= target:
        reasons.append("invalid_training_cutoff")
    if not all(pred.get(k) for k in ("training_snapshot_id", "training_snapshot_dataset_hash",
                                    "code_hash", "config_hash", "model_config", "library_versions",
                                    "comparison_batch_id", "strategy_id", "dataset_hash")):
        reasons.append("missing_provenance")
    if pred.get("model_config") and fingerprint(pred["model_config"]) != pred.get("config_hash"):
        reasons.append("invalid_config_hash")
    if not valid_actual(draw):
        reasons.append("invalid_or_conflicting_actual")
    count = pred.get("selected_count", 1)
    numbers = pred.get("numbers", []) if count != 1 else [pred.get("predicted_digit")]
    width = 2 if count != 1 else 1
    valid_numbers = isinstance(numbers, list) and all(
        isinstance(n, str) and len(n) == width and n.isascii() and n.isdigit() for n in numbers)
    if not valid_numbers or len(numbers) != count or len(set(numbers)) != count:
        reasons.append("invalid_selection")
    expected_strategy = STRATEGY if count != 1 else "raw_top_1_digit_v1"
    if pred.get("strategy_id") != expected_strategy:
        reasons.append("different_strategy")
    if check_evaluation and valid_actual(draw):
        evaluation = pred.get("evaluation", {})
        actual = draw["last_two"] if count != 1 else draw["last_two"][-1]
        key = "actual_last_two" if count != 1 else "actual_digit"
        if (evaluation.get("status") != "evaluated" or evaluation.get(key) != actual
                or evaluation.get("actual_special_prize") != draw["special_prize"]
                or evaluation.get("hit") != (actual in numbers if valid_numbers else False)
                or evaluation.get("actual_revision_hash") != actual_revision_hash(draw)):
            reasons.append("stale_or_inconsistent_evaluation")
    return reasons
