from __future__ import annotations

import hashlib
import importlib.metadata
import math
import platform
import random
import time
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from app.services import prediction_protocol as protocol

from app.services.logistic_prediction import (
    MODEL_VERSION as LOGISTIC_MODEL_VERSION,
    rank_numbers as rank_logistic,
)
from app.services.prediction import (
    MODEL_VERSION as FREQUENCY_MODEL_VERSION,
    rank_numbers as rank_frequency,
)


SUPPORTED_COUNTS = (60, 65, 70, 75, 80)
ROLLING_WINDOW = 365
MINIMUM_HISTORY = 733
REPORT_ID = "rolling_factorized_logistic_v1_365"


def _wilson_interval(hits: int, total: int) -> list[float]:
    if total == 0:
        return [0.0, 0.0]
    z_score = 1.959963984540054
    observed = hits / total
    denominator = 1 + z_score * z_score / total
    center = (observed + z_score * z_score / (2 * total)) / denominator
    half_width = z_score * math.sqrt(
        observed * (1 - observed) / total + z_score * z_score / (4 * total * total)
    ) / denominator
    return [round(center - half_width, 8), round(center + half_width, 8)]


def _exact_mcnemar_p(frequency_only: int, logistic_only: int) -> float:
    disagreements = frequency_only + logistic_only
    if disagreements == 0:
        return 1.0
    lower = min(frequency_only, logistic_only)
    probability = sum(
        math.comb(disagreements, index) for index in range(lower + 1)
    ) / (2**disagreements)
    return min(1.0, 2 * probability)


def _paired_block_bootstrap(
    rows: list[dict[str, Any]],
    selected_count: int,
    *,
    repetitions: int = 1_000,
    block_size: int = 7,
    seed: int = 20260922,
) -> list[float]:
    differences = [
        int(row[f"logistic_hit_{selected_count}"])
        - int(row[f"frequency_hit_{selected_count}"])
        for row in rows
    ]
    total = len(differences)
    if total == 0:
        return [0.0, 0.0]

    random_generator = random.Random(seed)
    samples: list[float] = []
    for _ in range(repetitions):
        resampled: list[int] = []
        while len(resampled) < total:
            start = random_generator.randrange(total)
            for offset in range(block_size):
                resampled.append(differences[(start + offset) % total])
                if len(resampled) == total:
                    break
        samples.append(sum(resampled) / total)
    samples.sort()
    return [
        round(samples[int(0.025 * (repetitions - 1))], 8),
        round(samples[int(0.975 * (repetitions - 1))], 8),
    ]


def _probability_metrics(scores: list[dict[str, Any]], actual: str) -> tuple[float, float]:
    probabilities = {score["number"]: score["probability"] for score in scores}
    actual_probability = max(probabilities[actual], 1e-12)
    brier_score = sum(
        (probability - (1.0 if number == actual else 0.0)) ** 2
        for number, probability in probabilities.items()
    )
    return -math.log(actual_probability), brier_score


def _dataset_hash(draws: list[dict[str, Any]]) -> str:
    material = "|".join(f"{draw['draw_date']}:{draw['last_two']}" for draw in draws)
    return hashlib.sha256(material.encode()).hexdigest()


def _report_provenance(outer_periods: int) -> dict[str, Any]:
    from app.services import logistic_prediction, prediction
    from pathlib import Path

    return {
        "protocol": {"version": "expanding_walk_forward_v2", "outer_periods": outer_periods,
                     "counts": SUPPORTED_COUNTS, "minimum_history": MINIMUM_HISTORY,
                     "bootstrap": {"repetitions": 1000, "block_size": 7, "seed": 20260922}},
        "models": {m.MODEL_VERSION: {"constants": protocol.constants(m.__name__),
                                      "code_hash": protocol.code_hash(m.__name__)}
                   for m in (prediction, logistic_prediction)},
        "report_code_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "library_versions": {name: importlib.metadata.version(name)
                             for name in ("scikit-learn", "numpy", "scipy")},
        "python_version": platform.python_version(),
    }


def run_rolling_comparison(
    draws: list[dict[str, Any]],
    *,
    outer_periods: int = ROLLING_WINDOW,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate both rankings with a strict walk-forward cutoff for each draw.

    The current result is only evaluated using the draws before its own date.
    A single run ranks all supported Top-N choices, keeping A/B comparisons paired.
    """
    ordered_draws = sorted(draws, key=lambda draw: draw["draw_date"])
    if len(ordered_draws) <= MINIMUM_HISTORY:
        raise ValueError(
            f"At least {MINIMUM_HISTORY + 1} valid draw results are required "
            "for a rolling Logistic comparison"
        )

    start_index = max(MINIMUM_HISTORY, len(ordered_draws) - outer_periods)
    daily: list[dict[str, Any]] = []
    started_at = time.perf_counter()

    for index in range(start_index, len(ordered_draws)):
        actual = ordered_draws[index]
        history = ordered_draws[:index]
        frequency = rank_frequency(history, actual["draw_date"], max(SUPPORTED_COUNTS))
        logistic = rank_logistic(history, actual["draw_date"], max(SUPPORTED_COUNTS))
        frequency_ranks = {
            score["number"]: score["rank"] for score in frequency["scores"]
        }
        logistic_ranks = {
            score["number"]: score["rank"] for score in logistic["scores"]
        }
        actual_number = actual["last_two"]
        frequency_log_loss, frequency_brier = _probability_metrics(
            frequency["scores"], actual_number
        )
        logistic_log_loss, logistic_brier = _probability_metrics(
            logistic["scores"], actual_number
        )
        row: dict[str, Any] = {
            "prediction_date": actual["draw_date"],
            "actual_last_two": actual_number,
            "frequency_log_loss": round(frequency_log_loss, 10),
            "logistic_log_loss": round(logistic_log_loss, 10),
            "frequency_brier": round(frequency_brier, 10),
            "logistic_brier": round(logistic_brier, 10),
        }
        for selected_count in SUPPORTED_COUNTS:
            row[f"frequency_hit_{selected_count}"] = (
                frequency_ranks[actual_number] <= selected_count
            )
            row[f"logistic_hit_{selected_count}"] = (
                logistic_ranks[actual_number] <= selected_count
            )
        daily.append(row)

    total = len(daily)
    counts: dict[str, Any] = {}
    for selected_count in SUPPORTED_COUNTS:
        frequency_hits = sum(row[f"frequency_hit_{selected_count}"] for row in daily)
        logistic_hits = sum(row[f"logistic_hit_{selected_count}"] for row in daily)
        frequency_only = sum(
            row[f"frequency_hit_{selected_count}"]
            and not row[f"logistic_hit_{selected_count}"]
            for row in daily
        )
        logistic_only = sum(
            row[f"logistic_hit_{selected_count}"]
            and not row[f"frequency_hit_{selected_count}"]
            for row in daily
        )
        counts[str(selected_count)] = {
            "baseline": selected_count / 100,
            "frequency": {
                "hits": frequency_hits,
                "hit_rate": round(frequency_hits / total, 8),
                "confidence_interval_95": _wilson_interval(frequency_hits, total),
            },
            "logistic": {
                "hits": logistic_hits,
                "hit_rate": round(logistic_hits / total, 8),
                "confidence_interval_95": _wilson_interval(logistic_hits, total),
            },
            "delta_logistic_vs_frequency": round(
                (logistic_hits - frequency_hits) / total, 8
            ),
            "frequency_only_hit": frequency_only,
            "logistic_only_hit": logistic_only,
            "mcnemar_exact_p": round(
                _exact_mcnemar_p(frequency_only, logistic_only), 8
            ),
            "paired_block_bootstrap_delta_ci95": _paired_block_bootstrap(
                daily, selected_count
            ),
        }

    summary = {
        "study_type": "rolling_walk_forward_current",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frequency_model_version": FREQUENCY_MODEL_VERSION,
        "logistic_model_version": LOGISTIC_MODEL_VERSION,
        "start_date": daily[0]["prediction_date"],
        "end_date": daily[-1]["prediction_date"],
        "paired_predictions": total,
        "window_periods": outer_periods,
        "counts": counts,
        "probability_metrics": {
            "frequency_mean_log_loss": round(
                sum(row["frequency_log_loss"] for row in daily) / total, 8
            ),
            "logistic_mean_log_loss": round(
                sum(row["logistic_log_loss"] for row in daily) / total, 8
            ),
            "frequency_mean_brier": round(
                sum(row["frequency_brier"] for row in daily) / total, 8
            ),
            "logistic_mean_brier": round(
                sum(row["logistic_brier"] for row in daily) / total, 8
            ),
        },
        "runtime_seconds": round(time.perf_counter() - started_at, 3),
        "interpretation": (
            "Đối chiếu rolling walk-forward: mỗi ngày chỉ dùng dữ liệu trước ngày đó. "
            "Tỷ lệ lịch sử không phải cam kết cho kỳ tiếp theo."
        ),
    }
    return summary, daily


class RollingReportNotReady(RuntimeError):
    """No report matches the current dataset and training protocol."""


def load_or_build_rolling_comparison(
    db: Database,
    *,
    outer_periods: int = ROLLING_WINDOW,
    allow_build: bool = True,
) -> tuple[dict[str, Any], bool]:
    """Read a current report; only explicit offline callers may rebuild it."""
    draws = list(
        db.draw_results.find(
            {"status": {"$ne": "conflict"}},
            {"_id": 0, "draw_date": 1, "last_two": 1},
        ).sort("draw_date", 1)
    )
    draws = [
        draw
        for draw in draws
        if isinstance(draw.get("draw_date"), str)
        and isinstance(draw.get("last_two"), str)
        and len(draw["last_two"]) == 2
        and draw["last_two"].isdigit()
    ]
    fingerprint = _dataset_hash(draws)
    provenance = _report_provenance(outer_periods)
    provenance_hash = protocol.fingerprint(provenance)
    cache_key = f"{REPORT_ID}:{outer_periods}:{provenance_hash}"
    cached = db.model_comparison_reports.find_one({"_id": cache_key})
    if (cached and cached.get("dataset_hash") == fingerprint
            and cached.get("provenance_hash") == provenance_hash):
        return cached, False

    if not allow_build:
        raise RollingReportNotReady("A current rolling report has not been generated")

    summary, daily = run_rolling_comparison(draws, outer_periods=outer_periods)
    document = {
        "_id": cache_key,
        "dataset_hash": fingerprint,
        "provenance_hash": provenance_hash,
        "provenance": provenance,
        "dataset": {
            "draws": len(draws),
            "first_date": draws[0]["draw_date"],
            "last_date": draws[-1]["draw_date"],
        },
        "summary": summary,
        "daily": daily,
        "updated_at": datetime.now(timezone.utc),
    }
    db.model_comparison_reports.replace_one({"_id": cache_key}, document, upsert=True)
    return document, True


def report_for_selected_count(
    report: dict[str, Any], selected_count: int
) -> dict[str, Any]:
    metrics = report["summary"]["counts"].get(str(selected_count))
    if metrics is None:
        raise ValueError(f"Top {selected_count} is not supported by the rolling report")

    daily_rows = []
    for row in reversed(report["daily"]):
        daily_rows.append(
            {
                "prediction_date": row["prediction_date"],
                "actual_last_two": row["actual_last_two"],
                "frequency_hit": bool(row[f"frequency_hit_{selected_count}"]),
                "logistic_hit": bool(row[f"logistic_hit_{selected_count}"]),
                "frequency_log_loss": row["frequency_log_loss"],
                "logistic_log_loss": row["logistic_log_loss"],
                "frequency_brier": row["frequency_brier"],
                "logistic_brier": row["logistic_brier"],
            }
        )
    return {
        "study_type": report["summary"]["study_type"],
        "generated_at": report["summary"]["generated_at"],
        "start_date": report["summary"]["start_date"],
        "end_date": report["summary"]["end_date"],
        "paired_predictions": report["summary"]["paired_predictions"],
        "window_periods": report["summary"]["window_periods"],
        "selected_count": selected_count,
        "metrics": metrics,
        "probability_metrics": report["summary"]["probability_metrics"],
        "dataset": report["dataset"],
        "interpretation": report["summary"]["interpretation"],
        "daily": daily_rows,
    }
