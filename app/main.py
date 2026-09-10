from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

import httpx
from bson import ObjectId
from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
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
from app.services.cron_lock import CronAlreadyRunning, mongo_cron_lease
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


def _in_process_scheduler_enabled() -> bool:
    return settings.enable_scheduler and not settings.is_vercel


def _authorize_cron_request(request: Request) -> None:
    cron_secret = os.getenv("CRON_SECRET", "").strip()
    if not cron_secret:
        return
    authorization = request.headers.get("authorization", "")
    expected = f"Bearer {cron_secret}"
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid cron authorization")


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo = MongoDatabase(settings)
    mongo.ping()
    mongo.ensure_indexes()
    scheduler = DailyScheduler(mongo.db, settings)
    app.state.mongo = mongo
    app.state.scheduler = scheduler
    if _in_process_scheduler_enabled():
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
        "scheduler_enabled": _in_process_scheduler_enabled(),
        "automation_mode": "vercel_cron" if settings.is_vercel else "scheduler",
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
    force: Annotated[bool, Query()] = False,
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
        runs = collector.sync_range(start_year, final_year, force=force)
        evaluation = evaluate_pending_predictions(db)
        digit_evaluation = evaluate_pending_digit_predictions(db)
        return serialize_document(
            {
                "years": len(runs),
                "completed_years": sum(
                    run["status"] == "completed" for run in runs
                ),
                "partial_years": sum(run["status"] == "partial" for run in runs),
                "skipped_years": sum(run["status"] == "skipped" for run in runs),
                "failed_years": sum(run["status"] == "failed" for run in runs),
                "records_received": sum(
                    run.get("records_received", 0) for run in runs
                ),
                "inserted": sum(run.get("inserted", 0) for run in runs),
                "matched": sum(run.get("matched", 0) for run in runs),
                "unchanged": sum(run.get("unchanged", 0) for run in runs),
                "write_operations": sum(
                    run.get("write_operations", 0) for run in runs
                ),
                "conflicts": sum(run.get("conflicts", 0) for run in runs),
                "source_successes": sum(
                    run.get("source_successes", 0) for run in runs
                ),
                "source_failures": sum(
                    run.get("source_failures", 0) for run in runs
                ),
                "fallback_used": any(
                    run.get("fallback_used", False) for run in runs
                ),
                "force": force,
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


@app.api_route("/api/auto-daily", methods=["GET", "POST"])
def auto_daily(request: Request, response: Response) -> dict[str, Any]:
    _authorize_cron_request(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    db = _db(request)
    try:
        with mongo_cron_lease(db, "auto-daily"):
            result = _run_auto_daily(db)
    except CronAlreadyRunning:
        return {
            "ok": True,
            "status": "already_running",
            "message": "Another automatic reconciliation is still running.",
        }
    if result.get("sync_error"):
        response.status_code = 502
    return result


def _run_auto_daily(db: Any) -> dict[str, Any]:
    """Endpoint tổng hợp dùng cho Vercel Cron Jobs:
    1. Đồng bộ kết quả năm hiện tại
    2. Đánh giá tất cả prediction pending
    3. Tạo dự đoán 2 số cho ngày tiếp theo (nếu chưa có)
    4. Tạo dự đoán 1 số cho ngày tiếp theo (nếu chưa có)
    """
    today = settings.local_today()

    # Bước 1: Sync kết quả
    collector = KqxsCollector(db, settings)
    sync_result: dict[str, Any] = {}
    sync_error: str | None = None
    try:
        sync_result = collector.sync_year(today.year)
    except CollectorSourcesUnavailable as exc:
        sync_error = str(exc)
    except httpx.HTTPError as exc:
        sync_error = f"Source request failed: {exc}"

    # Bước 2: Đánh giá prediction pending
    evaluation = evaluate_pending_predictions(db)
    digit_evaluation = evaluate_pending_digit_predictions(db)

    # Bước 3 & 4: Tạo dự đoán cho ngày tiếp theo
    # Nếu hôm nay đã có kết quả → dự đoán cho ngày mai
    target: date | None = today
    today_result = db.draw_results.find_one(
        {
            "draw_date": today.isoformat(),
            "status": {"$ne": "conflict"},
        },
        {"_id": 1},
    )
    if today_result:
        target = today + timedelta(days=1)
    else:
        first_sync = min(settings.result_sync_times, default="18:35")
        if settings.local_now().strftime("%H:%M") >= first_sync:
            target = None

    pred_result: dict[str, Any] = {}
    pred_error: str | None = None
    digit_pred_result: dict[str, Any] = {}
    digit_pred_error: str | None = None

    if target is None:
        pred_error = "Today's result is not available; waiting for the next cron run."
        digit_pred_error = pred_error
    elif settings.auto_prediction:
        try:
            prediction, pred_created = create_prediction(
                db, target, settings.auto_prediction_count
            )
            pred_result = {
                "created": pred_created,
                "prediction_date": str(target),
                "selected_count": settings.auto_prediction_count,
            }
        except ValueError as exc:
            pred_error = str(exc)

        try:
            digit_prediction, digit_created = create_digit_prediction(db, target)
            digit_pred_result = {
                "created": digit_created,
                "prediction_date": str(target),
            }
        except ValueError as exc:
            digit_pred_error = str(exc)
    else:
        pred_error = "Automatic prediction is disabled."
        digit_pred_error = pred_error

    return serialize_document({
        "ok": sync_error is None,
        "status": "completed" if sync_error is None else "source_failed",
        "target_date": str(target) if target else None,
        "sync": sync_result,
        "sync_error": sync_error,
        "evaluation": evaluation,
        "digit_evaluation": digit_evaluation,
        "prediction": pred_result,
        "prediction_error": pred_error,
        "digit_prediction": digit_pred_result,
        "digit_prediction_error": digit_pred_error,
    })


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
