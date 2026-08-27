from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

import httpx
from bson import ObjectId
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.database import MongoDatabase, serialize_document
from app.models import (
    BacktestRequest,
    DigitBacktestRequest,
    GenerateDigitPredictionRequest,
    GeneratePredictionRequest,
)
from app.services.backtest import run_walk_forward_backtest
from app.services.collector import CollectorSourcesUnavailable, KqxsCollector
from app.services.digit_backtest import run_digit_walk_forward_backtest
from app.services.digit_prediction import (
    DIGIT_MODEL_VERSION,
    create_digit_prediction,
)
from app.services.evaluation import (
    evaluate_pending_digit_predictions,
    evaluate_pending_predictions,
    metrics_summary,
)
from app.services.prediction import MODEL_VERSION, create_prediction
from app.services.scheduler import DailyScheduler


STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo = MongoDatabase(settings)
    mongo.ping()
    mongo.ensure_indexes()
    scheduler = DailyScheduler(mongo.db, settings)
    app.state.mongo = mongo
    app.state.scheduler = scheduler
    if settings.enable_scheduler:
        scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        mongo.close()


app = FastAPI(
    title="XSMB Research Lab",
    version=__version__,
    description="Personal draw-data collection, immutable predictions, and evaluation.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _db(request: Request):
    return request.app.state.mongo.db


@app.get("/backtest", include_in_schema=False)
@app.get("/du-doan-1-so", include_in_schema=False)
@app.get("/du-doan-2-so", include_in_schema=False)
@app.get("/ket-qua", include_in_schema=False)
@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    try:
        mongo_ok = request.app.state.mongo.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {exc}") from exc
    return {
        "status": "ok" if mongo_ok else "degraded",
        "version": __version__,
        "mongodb": mongo_ok,
        "database": settings.mongodb_database,
        "scheduler_enabled": settings.enable_scheduler,
        "model_version": MODEL_VERSION,
        "digit_model_version": DIGIT_MODEL_VERSION,
    }


@app.get("/api/settings/public")
def public_settings() -> dict[str, Any]:
    return {
        "timezone": settings.timezone_name,
        "auto_prediction": settings.auto_prediction,
        "auto_prediction_count": settings.auto_prediction_count,
        "prediction_time": settings.prediction_time,
        "result_sync_times": settings.result_sync_times,
        "ai_required": False,
        "ai_configured": settings.ai_configured,
        "ai_note": (
            "The current frequency ensemble runs locally. AI is optional and disabled."
        ),
    }


@app.post("/api/sync/current")
def sync_current(request: Request) -> dict[str, Any]:
    db = _db(request)
    collector = KqxsCollector(db, settings)
    try:
        result = collector.sync_year(settings.local_today().year)
        evaluation = evaluate_pending_predictions(db)
        digit_evaluation = evaluate_pending_digit_predictions(db)
        return serialize_document(
            {
                "sync": result,
                "evaluation": evaluation,
                "digit_evaluation": digit_evaluation,
            }
        )
    except CollectorSourcesUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Source request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/sync/backfill")
def sync_backfill(
    request: Request,
    start_year: Annotated[int, Query(ge=2019)] = 2019,
    end_year: Annotated[int | None, Query(ge=2019)] = None,
) -> dict[str, Any]:
    current_year = settings.local_today().year
    final_year = end_year or current_year
    if final_year > current_year:
        raise HTTPException(status_code=400, detail="end_year cannot be in the future")
    if start_year > final_year:
        raise HTTPException(status_code=400, detail="start_year must be <= end_year")
    db = _db(request)
    collector = KqxsCollector(db, settings)
    try:
        runs = collector.sync_range(start_year, final_year)
        evaluation = evaluate_pending_predictions(db)
        digit_evaluation = evaluate_pending_digit_predictions(db)
        return serialize_document(
            {
                "years": len(runs),
                "records_received": sum(run["records_received"] for run in runs),
                "inserted": sum(run["inserted"] for run in runs),
                "matched": sum(run["matched"] for run in runs),
                "conflicts": sum(run["conflicts"] for run in runs),
                "source_successes": sum(run["source_successes"] for run in runs),
                "source_failures": sum(run["source_failures"] for run in runs),
                "fallback_used": any(run["fallback_used"] for run in runs),
                "runs": runs,
                "evaluation": evaluation,
                "digit_evaluation": digit_evaluation,
            }
        )
    except CollectorSourcesUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Source request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/results")
def list_results(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 30,
) -> list[dict[str, Any]]:
    documents = _db(request).draw_results.find({}).sort("draw_date", -1).limit(limit)
    return serialize_document(list(documents))


@app.get("/api/results/latest")
def latest_result(request: Request) -> dict[str, Any] | None:
    result = _db(request).draw_results.find_one(sort=[("draw_date", -1)])
    return serialize_document(result) if result else None


@app.get("/api/results/recent-last-two")
def recent_last_two(
    request: Request,
    days: Annotated[int, Query(ge=1, le=30)] = 3,
) -> dict[str, Any]:
    """Trả về danh sách last_two (hai số cuối) của N ngày gần nhất."""
    docs = (
        _db(request)
        .draw_results.find({}, {"last_two": 1, "draw_date": 1, "_id": 0})
        .sort("draw_date", -1)
        .limit(days)
    )
    records = list(docs)
    return {
        "days": days,
        "results": [
            {"draw_date": r["draw_date"], "last_two": r["last_two"]}
            for r in records
        ],
        "numbers": [r["last_two"] for r in records],
    }


@app.post("/api/predictions/generate")
def generate_prediction(
    request: Request,
    payload: Annotated[GeneratePredictionRequest, Body()],
) -> dict[str, Any]:
    db = _db(request)
    target = payload.prediction_date or settings.local_today()
    if payload.prediction_date is None and db.draw_results.find_one(
        {"draw_date": target.isoformat()}
    ):
        target += timedelta(days=1)
    try:
        prediction, created = create_prediction(db, target, payload.selected_count)
        return serialize_document({"created": created, "prediction": prediction})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/predictions")
def list_predictions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 30,
) -> list[dict[str, Any]]:
    projection = {
        "numbers": 0,
        "scores": 0,
        "window_details": 0,
        "dataset_hash": 0,
    }
    documents = (
        _db(request)
        .predictions.find({}, projection)
        .sort([("prediction_date", -1), ("locked_at", -1)])
        .limit(limit)
    )
    return serialize_document(list(documents))


@app.get("/api/predictions/latest")
def latest_prediction(request: Request) -> dict[str, Any] | None:
    prediction = _db(request).predictions.find_one(sort=[("prediction_date", -1)])
    return serialize_document(prediction) if prediction else None


@app.get("/api/predictions/{prediction_id}")
def prediction_detail(request: Request, prediction_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(prediction_id):
        raise HTTPException(status_code=400, detail="Invalid prediction ID")
    prediction = _db(request).predictions.find_one({"_id": ObjectId(prediction_id)})
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return serialize_document(prediction)


@app.post("/api/evaluations/run")
def evaluate_predictions(request: Request) -> dict[str, Any]:
    db = _db(request)
    evaluation = evaluate_pending_predictions(db)
    return {
        **evaluation,
        "digit_evaluation": evaluate_pending_digit_predictions(db),
    }


@app.get("/api/metrics/summary")
def get_metrics(request: Request) -> dict[str, Any]:
    return serialize_document(metrics_summary(_db(request)))


@app.post("/api/backtests/run")
def run_backtest(
    request: Request,
    payload: Annotated[BacktestRequest, Body()],
) -> dict[str, Any]:
    try:
        result = run_walk_forward_backtest(
            _db(request),
            selected_count=payload.selected_count,
            start_date=payload.start_date,
            end_date=payload.end_date,
            minimum_training_draws=payload.minimum_training_draws,
        )
        result = {**result, "outcomes": result["outcomes"][-120:]}
        return serialize_document(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/backtests")
def list_backtests(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[dict[str, Any]]:
    projection = {"outcomes": 0}
    documents = (
        _db(request)
        .backtest_runs.find({}, projection)
        .sort("created_at", -1)
        .limit(limit)
    )
    return serialize_document(list(documents))


@app.post("/api/digit-predictions/generate")
def generate_digit_prediction(
    request: Request,
    payload: Annotated[GenerateDigitPredictionRequest, Body()],
) -> dict[str, Any]:
    db = _db(request)
    target = payload.prediction_date or settings.local_today()
    if payload.prediction_date is None and db.draw_results.find_one(
        {"draw_date": target.isoformat()}
    ):
        target += timedelta(days=1)
    try:
        prediction, created = create_digit_prediction(db, target)
        return serialize_document({"created": created, "prediction": prediction})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/digit-predictions")
def list_digit_predictions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 30,
) -> list[dict[str, Any]]:
    projection = {"scores": 0, "window_details": 0, "dataset_hash": 0}
    documents = (
        _db(request)
        .digit_predictions.find({}, projection)
        .sort([("prediction_date", -1), ("locked_at", -1)])
        .limit(limit)
    )
    return serialize_document(list(documents))


@app.get("/api/digit-predictions/latest")
def latest_digit_prediction(request: Request) -> dict[str, Any] | None:
    prediction = _db(request).digit_predictions.find_one(
        sort=[("prediction_date", -1)]
    )
    return serialize_document(prediction) if prediction else None


@app.get("/api/digit-predictions/{prediction_id}")
def digit_prediction_detail(request: Request, prediction_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(prediction_id):
        raise HTTPException(status_code=400, detail="Invalid digit prediction ID")
    prediction = _db(request).digit_predictions.find_one(
        {"_id": ObjectId(prediction_id)}
    )
    if prediction is None:
        raise HTTPException(status_code=404, detail="Digit prediction not found")
    return serialize_document(prediction)


@app.post("/api/digit-backtests/run")
def run_digit_backtest(
    request: Request,
    payload: Annotated[DigitBacktestRequest, Body()],
) -> dict[str, Any]:
    try:
        result = run_digit_walk_forward_backtest(
            _db(request),
            start_date=payload.start_date,
            end_date=payload.end_date,
            minimum_training_draws=payload.minimum_training_draws,
        )
        result = {**result, "outcomes": result["outcomes"][-120:]}
        return serialize_document(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/digit-backtests")
def list_digit_backtests(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[dict[str, Any]]:
    documents = (
        _db(request)
        .digit_backtest_runs.find({}, {"outcomes": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return serialize_document(list(documents))
