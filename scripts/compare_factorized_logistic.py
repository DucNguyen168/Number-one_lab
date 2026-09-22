from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.logistic_prediction import (
    MODEL_VERSION as LOGISTIC_MODEL_VERSION,
    rank_numbers as rank_logistic,
)
from app.services.prediction import (
    MODEL_VERSION as FREQUENCY_MODEL_VERSION,
    rank_numbers as rank_frequency,
)


COUNTS = (60, 65, 70, 75, 80)


def wilson_interval(hits: int, total: int) -> list[float]:
    if total == 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    observed = hits / total
    denominator = 1 + z * z / total
    center = (observed + z * z / (2 * total)) / denominator
    half = z * math.sqrt(
        observed * (1 - observed) / total + z * z / (4 * total * total)
    ) / denominator
    return [round(center - half, 8), round(center + half, 8)]


def exact_mcnemar_p(frequency_only: int, logistic_only: int) -> float:
    disagreements = frequency_only + logistic_only
    if disagreements == 0:
        return 1.0
    lower = min(frequency_only, logistic_only)
    probability = sum(
        math.comb(disagreements, index) for index in range(lower + 1)
    ) / (2**disagreements)
    return min(1.0, 2 * probability)


def paired_block_bootstrap(
    outcomes: list[dict[str, Any]],
    selected_count: int,
    *,
    repetitions: int = 1_000,
    block_size: int = 7,
    seed: int = 20260922,
) -> list[float]:
    rng = random.Random(seed)
    differences = [
        int(row[f"logistic_hit_{selected_count}"])
        - int(row[f"frequency_hit_{selected_count}"])
        for row in outcomes
    ]
    total = len(differences)
    if total == 0:
        return [0.0, 0.0]
    samples: list[float] = []
    for _ in range(repetitions):
        resampled: list[int] = []
        while len(resampled) < total:
            start = rng.randrange(total)
            for offset in range(block_size):
                resampled.append(differences[(start + offset) % total])
                if len(resampled) == total:
                    break
        samples.append(sum(resampled) / total)
    samples.sort()
    lower = samples[int(0.025 * (repetitions - 1))]
    upper = samples[int(0.975 * (repetitions - 1))]
    return [round(lower, 8), round(upper, 8)]


def probability_metrics(scores: list[dict[str, Any]], actual: str) -> tuple[float, float]:
    probabilities = {score["number"]: score["probability"] for score in scores}
    actual_probability = max(probabilities[actual], 1e-12)
    brier = sum(
        (probability - (1.0 if number == actual else 0.0)) ** 2
        for number, probability in probabilities.items()
    )
    return -math.log(actual_probability), brier


def run_comparison(
    draws: list[dict[str, Any]], outer_periods: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start_index = max(733, len(draws) - outer_periods)
    daily: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index in range(start_index, len(draws)):
        actual = draws[index]
        history = draws[:index]
        frequency = rank_frequency(history, actual["draw_date"], 80)
        logistic = rank_logistic(history, actual["draw_date"], 80)
        frequency_ranks = {
            score["number"]: score["rank"] for score in frequency["scores"]
        }
        logistic_ranks = {
            score["number"]: score["rank"] for score in logistic["scores"]
        }
        actual_number = actual["last_two"]
        frequency_log_loss, frequency_brier = probability_metrics(
            frequency["scores"], actual_number
        )
        logistic_log_loss, logistic_brier = probability_metrics(
            logistic["scores"], actual_number
        )
        row: dict[str, Any] = {
            "prediction_date": actual["draw_date"],
            "actual_last_two": actual_number,
            "frequency_log_loss": frequency_log_loss,
            "logistic_log_loss": logistic_log_loss,
            "frequency_brier": frequency_brier,
            "logistic_brier": logistic_brier,
        }
        for count in COUNTS:
            row[f"frequency_hit_{count}"] = frequency_ranks[actual_number] <= count
            row[f"logistic_hit_{count}"] = logistic_ranks[actual_number] <= count
        daily.append(row)

    total = len(daily)
    counts: dict[str, Any] = {}
    for selected_count in COUNTS:
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
                "confidence_interval_95": wilson_interval(frequency_hits, total),
            },
            "logistic": {
                "hits": logistic_hits,
                "hit_rate": round(logistic_hits / total, 8),
                "confidence_interval_95": wilson_interval(logistic_hits, total),
            },
            "delta_logistic_vs_frequency": round(
                (logistic_hits - frequency_hits) / total, 8
            ),
            "frequency_only_hit": frequency_only,
            "logistic_only_hit": logistic_only,
            "mcnemar_exact_p": round(
                exact_mcnemar_p(frequency_only, logistic_only), 8
            ),
            "paired_block_bootstrap_delta_ci95": paired_block_bootstrap(
                daily, selected_count
            ),
        }

    summary = {
        "study_type": "historical_fixed_protocol",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frequency_model_version": FREQUENCY_MODEL_VERSION,
        "logistic_model_version": LOGISTIC_MODEL_VERSION,
        "start_date": daily[0]["prediction_date"],
        "end_date": daily[-1]["prediction_date"],
        "paired_predictions": total,
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
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "interpretation": (
            "Đây là backtest lịch sử của cấu hình đã khóa, không phải bằng chứng xác "
            "nhận tương lai. Delta dương mới chỉ mô tả Logistic tốt hơn mô hình tần suất."
        ),
    }
    return summary, daily


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("reports/recent5_pause/input_snapshot.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/logistic_comparison"),
    )
    parser.add_argument("--outer-periods", type=int, default=365)
    args = parser.parse_args()

    input_bytes = args.input.read_bytes()
    draws = json.loads(input_bytes)
    summary, daily = run_comparison(draws, args.outer_periods)
    summary["dataset"] = {
        "path": args.input.as_posix(),
        "sha256": hashlib.sha256(input_bytes).hexdigest(),
        "draws": len(draws),
        "first_date": draws[0]["draw_date"],
        "last_date": draws[-1]["draw_date"],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (args.output_dir / "daily.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(daily[0]))
        writer.writeheader()
        writer.writerows(daily)
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
