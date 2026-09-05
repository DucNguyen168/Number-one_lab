from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from app.config import Settings


class MongoDatabase:
    def __init__(self, config: Settings) -> None:
        self.client: MongoClient = MongoClient(
            config.mongodb_uri,
            appname="xsmb-research-lab",
            serverSelectionTimeoutMS=5_000,
        )
        self.db: Database = self.client[config.mongodb_database]

    def ping(self) -> bool:
        return self.client.admin.command("ping").get("ok") == 1.0

    def ensure_indexes(self) -> None:
        self.db.draw_results.create_index(
            [("draw_date", ASCENDING)], unique=True, name="uq_draw_date"
        )
        self.db.draw_results.create_index(
            [("draw_date", DESCENDING), ("status", ASCENDING)],
            name="draw_date_status",
        )
        self.db.predictions.create_index(
            [
                ("prediction_date", ASCENDING),
                ("model_version", ASCENDING),
                ("selected_count", ASCENDING),
            ],
            unique=True,
            name="uq_prediction_snapshot",
        )
        self.db.predictions.create_index(
            [("prediction_date", DESCENDING), ("evaluation.status", ASCENDING)],
            name="prediction_date_evaluation",
        )
        self.db.backtest_runs.create_index(
            [("created_at", DESCENDING)], name="backtest_created_at"
        )
        self.db.digit_predictions.create_index(
            [("prediction_date", ASCENDING), ("model_version", ASCENDING)],
            unique=True,
            name="uq_digit_prediction_snapshot",
        )
        self.db.digit_predictions.create_index(
            [("prediction_date", DESCENDING), ("evaluation.status", ASCENDING)],
            name="digit_prediction_date_evaluation",
        )
        self.db.digit_backtest_runs.create_index(
            [("created_at", DESCENDING)], name="digit_backtest_created_at"
        )
        self.db.collector_runs.create_index(
            [("started_at", DESCENDING)], name="collector_started_at"
        )
        self.db.collector_runs.create_index(
            [
                ("source", ASCENDING),
                ("type", ASCENDING),
                ("status", ASCENDING),
                ("year", ASCENDING),
            ],
            name="collector_completed_years",
        )

    def close(self) -> None:
        self.client.close()


def serialize_document(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: serialize_document(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_document(item) for item in value]
    return value
