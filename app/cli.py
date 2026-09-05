from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any

import uvicorn

from app.config import settings
from app.database import MongoDatabase, serialize_document
from app.services.backtest import run_walk_forward_backtest
from app.services.collector import KqxsCollector
from app.services.digit_backtest import run_digit_walk_forward_backtest
from app.services.digit_prediction import create_digit_prediction
from app.services.evaluation import (
    evaluate_pending_digit_predictions,
    evaluate_pending_predictions,
)
from app.services.prediction import create_prediction


def _json_print(value: Any) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(serialize_document(value), ensure_ascii=False, indent=2))


def _date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XSMB Research Lab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the API and dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    serve.add_argument("--reload", action="store_true")

    backfill = subparsers.add_parser("backfill", help="Import yearly results")
    backfill.add_argument("--start-year", type=int, default=2019)
    backfill.add_argument("--end-year", type=int, default=settings.local_today().year)
    backfill.add_argument(
        "--force",
        action="store_true",
        help="Re-download completed historical years instead of using the sync cache",
    )

    subparsers.add_parser("sync", help="Sync the current year and evaluate predictions")

    predict = subparsers.add_parser("predict", help="Create an immutable prediction")
    predict.add_argument("--date", type=_date, default=settings.local_today())
    predict.add_argument("--count", type=int, default=65)

    digit_predict = subparsers.add_parser(
        "digit-predict", help="Predict and lock one final digit from 0 to 9"
    )
    digit_predict.add_argument("--date", type=_date, default=settings.local_today())

    subparsers.add_parser("evaluate", help="Evaluate pending predictions")

    backtest = subparsers.add_parser("backtest", help="Run a walk-forward backtest")
    backtest.add_argument("--count", type=int, default=65)
    backtest.add_argument("--start-date", type=_date)
    backtest.add_argument("--end-date", type=_date)
    backtest.add_argument("--minimum-training-draws", type=int, default=365)

    digit_backtest = subparsers.add_parser(
        "digit-backtest", help="Run a Top-1 final-digit walk-forward backtest"
    )
    digit_backtest.add_argument("--start-date", type=_date)
    digit_backtest.add_argument("--end-date", type=_date)
    digit_backtest.add_argument("--minimum-training-draws", type=int, default=365)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
        return

    mongo = MongoDatabase(settings)
    mongo.ping()
    mongo.ensure_indexes()
    try:
        if args.command == "backfill":
            result = KqxsCollector(mongo.db, settings).sync_range(
                args.start_year, args.end_year, force=args.force
            )
        elif args.command == "sync":
            result = {
                "sync": KqxsCollector(mongo.db, settings).sync_year(
                    settings.local_today().year
                ),
                "evaluation": evaluate_pending_predictions(mongo.db),
                "digit_evaluation": evaluate_pending_digit_predictions(mongo.db),
            }
        elif args.command == "predict":
            prediction, created = create_prediction(mongo.db, args.date, args.count)
            result = {"created": created, "prediction": prediction}
        elif args.command == "evaluate":
            result = {
                "two_digit": evaluate_pending_predictions(mongo.db),
                "last_digit": evaluate_pending_digit_predictions(mongo.db),
            }
        elif args.command == "digit-predict":
            prediction, created = create_digit_prediction(mongo.db, args.date)
            result = {"created": created, "prediction": prediction}
        elif args.command == "backtest":
            result = run_walk_forward_backtest(
                mongo.db,
                selected_count=args.count,
                start_date=args.start_date,
                end_date=args.end_date,
                minimum_training_draws=args.minimum_training_draws,
            )
        elif args.command == "digit-backtest":
            result = run_digit_walk_forward_backtest(
                mongo.db,
                start_date=args.start_date,
                end_date=args.end_date,
                minimum_training_draws=args.minimum_training_draws,
            )
        else:
            raise RuntimeError(f"Unknown command: {args.command}")
        _json_print(result)
    finally:
        mongo.close()


if __name__ == "__main__":
    main()
