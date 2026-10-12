"""Offline algorithm audit. Reads an exported snapshot; never writes to MongoDB."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import math
import platform
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as daytime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import binomtest, chisquare

from app.services import catboost_prediction as catboost
from app.services.digit_prediction import rank_last_digits
from app.services.logistic_prediction import MODEL_VERSION as LOGISTIC, rank_numbers as logistic_rank
from app.services.prediction import MODEL_VERSION as FREQUENCY, rank_numbers as frequency_rank
from app.services.rolling_comparison import _wilson_interval


COUNTS = (60, 65, 70, 75, 80)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PROTOCOL = {
    "type": "exploratory_audit_not_untouched_holdout",
    "primary_count": 65,
    "live_deadline_local": "17:30",
    "naive_mongodb_timestamps": "UTC",
    "validation": "one-step expanding walk-forward, only dates before target",
    "candidates": {
        "bayes365_a1000": {"window": 365, "total_prior_mass": 1000},
        "bayes_joint_digit_mix": {"joint_weight": 0.5, "digit_prior_mass": 100},
        "markov_shrunk_a100": {"order": 1, "row_prior_mass": 100, "base": "bayes365_a1000"},
        "logistic_bayes_mix": {"logistic_weight": 0.5, "bayes_joint_digit_weight": 0.5},
        "logistic_uniform_half": {"logistic_weight": 0.5, "note": "ranking unchanged; probability diagnostic only"},
    },
    "selection": "fixed candidates; no parameter search; all results retained",
    "statistics": "Wilson 95%, one-sided binomial vs N/100, Holm across candidate Top65 tests; descriptive only",
}


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def digest(draws) -> str:
    return hashlib.sha256("|".join(f"{d['draw_date']}:{d['last_two']}" for d in draws).encode()).hexdigest()


def validate_draws(raw):
    draws, excluded = [], []
    seen = set()
    for draw in sorted(raw, key=lambda d: d["draw_date"]):
        day = draw["draw_date"]
        date.fromisoformat(day)
        if day in seen:
            raise ValueError(f"Duplicate draw date: {day}")
        seen.add(day)
        number = draw.get("last_two")
        reason = None
        if draw.get("status") == "conflict":
            reason = "conflict"
        elif not isinstance(number, str) or len(number) != 2 or not number.isascii() or not number.isdigit():
            reason = "invalid_last_two"
        elif draw.get("special_prize") and draw["special_prize"][-2:] != number:
            reason = "inconsistent_special_prize"
        if reason:
            excluded.append({"date": day, "reason": reason})
        else:
            draws.append(draw)
    return draws, excluded


def probabilities(scores, *, digit=False):
    key = "digit" if digit else "number"
    labels = [str(i) if digit else f"{i:02d}" for i in range(10 if digit else 100)]
    values = {s[key]: s["probability"] for s in scores}
    if len(scores) != len(labels) or set(values) != set(labels):
        raise ValueError("Incomplete or duplicate scores")
    p = np.array([values[label] for label in labels], dtype=float)
    if not np.all(np.isfinite(p)) or np.any(p < 0) or not np.isclose(p.sum(), 1, atol=1e-6):
        raise ValueError("Invalid probability distribution")
    return p / p.sum()


def score_row(day, model, p, actual):
    p = np.asarray(p, dtype=float)
    p = p / p.sum()
    rank = np.lexsort((np.arange(len(p)), -p))
    actual_rank = int(np.where(rank == actual)[0][0]) + 1
    row = {
        "date": day, "model": model, "actual": actual,
        "log_loss": float(-np.log(max(p[actual], 1e-12))),
        "brier": float(np.square(p).sum() - 2 * p[actual] + 1),
        "rank": actual_rank,
    }
    for n in COUNTS if len(p) == 100 else (1,):
        row[f"hit_{n}"] = actual_rank <= n
        row[f"coverage_{n}"] = float(p[rank[:n]].sum())
    return row


def metrics(rows, n=65, baseline=None):
    if not rows:
        return {"n": 0}
    rows = sorted(rows, key=lambda row: row["date"])
    baseline = baseline if baseline is not None else n / 100
    hits = sum(row[f"hit_{n}"] for row in rows)
    total = len(rows)
    return {
        "n": total, "hits": hits, "hit_rate": hits / total,
        "baseline": baseline, "lift": hits / total - baseline,
        "ci95": _wilson_interval(hits, total),
        "binomial_p_greater": float(binomtest(hits, total, baseline, alternative="greater").pvalue),
        "mean_log_loss": float(np.mean([row["log_loss"] for row in rows])),
        "mean_brier": float(np.mean([row["brier"] for row in rows])),
        "mean_coverage": float(np.mean([row[f"coverage_{n}"] for row in rows])),
        "start": rows[0]["date"], "end": rows[-1]["date"],
    }


def holm(pvalues):
    result, running = {}, 0.0
    for index, (key, p) in enumerate(sorted(pvalues.items(), key=lambda item: item[1])):
        running = max(running, min(1, (len(pvalues) - index) * p))
        result[key] = running
    return result


def paired_stats(a, b, n=65):
    assert [r["date"] for r in a] == [r["date"] for r in b]
    a_only = sum(x[f"hit_{n}"] and not y[f"hit_{n}"] for x, y in zip(a, b))
    b_only = sum(y[f"hit_{n}"] and not x[f"hit_{n}"] for x, y in zip(a, b))
    disagreements = a_only + b_only
    diffs = np.array([int(y[f"hit_{n}"]) - int(x[f"hit_{n}"]) for x, y in zip(a, b)])
    rng = np.random.default_rng(20261012)
    intervals = {}
    for block in (7, 30):
        # Descriptive circular block bootstrap; short live series are very uncertain.
        if len(diffs) < 2 * block:
            intervals[str(block)] = None
            continue
        starts = rng.integers(0, len(diffs), size=(2000, math.ceil(len(diffs) / block)))
        idx = ((starts[..., None] + np.arange(block)) % len(diffs)).reshape(2000, -1)[:, :len(diffs)]
        intervals[str(block)] = np.quantile(diffs[idx].mean(axis=1), [0.025, 0.975]).tolist()
    return {
        "n": len(a), "a_only": a_only, "b_only": b_only,
        "delta_b_minus_a": float(diffs.mean()),
        "mcnemar_exact_p": float(binomtest(min(a_only, b_only), disagreements).pvalue) if disagreements else 1.0,
        "block_bootstrap_delta_ci95": intervals,
    }


def audit_live(snapshot, draws):
    by_date = {d["draw_date"]: d for d in draws}
    rows, issues, summaries = [], [], []
    groups = defaultdict(list)
    for kind in ("predictions", "digit_predictions"):
        digit = kind == "digit_predictions"
        for pred in snapshot[kind]:
            target = pred["prediction_date"]
            n = pred.get("selected_count", 1)
            model = pred["model_version"]
            group_key = (model, n, pred.get("config_hash", "legacy_unspecified"))
            groups[group_key].append(pred)
            if pred.get("evaluation", {}).get("status") != "evaluated":
                continue
            reasons = []
            draw = by_date.get(target)
            if not draw:
                issues.append({"date": target, "model": model, "reasons": ["missing_valid_actual"]})
                continue
            try:
                locked = datetime.fromisoformat(pred["locked_at"])
                if locked.tzinfo is None:
                    locked = locked.replace(tzinfo=timezone.utc)
                deadline = datetime.combine(date.fromisoformat(target), daytime(17, 30), TZ)
                if locked >= deadline:
                    reasons.append("locked_after_1730")
            except (ValueError, KeyError):
                reasons.append("invalid_lock_timestamp")
            if not pred.get("trained_through") or pred["trained_through"] >= target:
                reasons.append("invalid_training_cutoff")
            actual = int(draw["last_two"][-1] if digit else draw["last_two"])
            try:
                p = probabilities(pred["scores"], digit=digit)
            except (ValueError, KeyError):
                issues.append({"date": target, "model": model, "reasons": ["invalid_scores"]})
                continue
            row = score_row(target, model, p, actual)
            selected = [pred["predicted_digit"]] if digit else pred["numbers"]
            if len(set(selected)) != n or len(selected) != n:
                reasons.append("invalid_selection")
            actual_label = str(actual) if digit else f"{actual:02d}"
            row[f"hit_{n}"] = actual_label in selected
            row[f"coverage_{n}"] = sum(p[int(label)] for label in selected)
            if pred["evaluation"].get("hit") != row[f"hit_{n}"]:
                reasons.append("stored_hit_disagrees_with_actual")
            actual_key = "actual_digit" if digit else "actual_last_two"
            if pred["evaluation"].get(actual_key) != actual_label:
                reasons.append("stored_actual_disagrees")
            row.update(selected_count=n, config_hash=group_key[2], dataset_hash=pred.get("dataset_hash"),
                       eligible=not reasons, issues=reasons, kind=kind)
            rows.append(row)
            if reasons:
                issues.append({"date": target, "model": model, "reasons": reasons})
    for (model, n, config_hash), preds in sorted(groups.items()):
        observed = [r for r in rows if (r["model"], r["selected_count"], r["config_hash"]) == (model, n, config_hash)]
        eligible = [r for r in observed if r["eligible"]]
        summaries.append({"model": model, "selected_count": n, "config_hash": config_hash,
                          "total_snapshots": len(preds), "raw_evaluated": metrics(observed, n, 0.1 if n == 1 else n/100),
                          "eligible_evaluated": metrics(eligible, n, 0.1 if n == 1 else n/100)})
    versions = (FREQUENCY, LOGISTIC, catboost.MODEL_VERSION)
    matched = defaultdict(dict)
    for row in rows:
        if row["model"] in versions and row["selected_count"] == 65 and row["eligible"]:
            matched[row["date"]][row["model"]] = row
    dates = [d for d, models in sorted(matched.items()) if set(models) == set(versions)
             and len({models[m]["dataset_hash"] for m in versions}) == 1
             and all(models[m]["dataset_hash"] for m in versions)]
    common = {m: [matched[d][m] for d in dates] for m in versions}
    pairs = {f"{a} -> {b}": paired_stats(common[a], common[b])
             for a, b in itertools.combinations(versions, 2)} if dates else {}
    return {"groups": summaries, "issues": issues, "rows": rows,
            "paired_top65": {"dates": dates, "metrics": {m: metrics(r) for m, r in common.items()}, "comparisons": pairs},
            "eligibility_note": "Reconstructed from saved timestamps, not proof of immutable pre-registration; legacy snapshots lack batch/deadline metadata."}


def candidate_probabilities(history, logistic):
    values = np.array([int(d["last_two"]) for d in history], dtype=int)
    sample = values[-365:]
    direct = (np.bincount(sample, minlength=100) + 10) / (len(sample) + 1000)
    tens = (np.bincount(sample // 10, minlength=10) + 10) / (len(sample) + 100)
    units = (np.bincount(sample % 10, minlength=10) + 10) / (len(sample) + 100)
    mixed = 0.5 * direct + 0.5 * np.outer(tens, units).ravel()
    followers = values[1:][values[:-1] == values[-1]]
    markov = (np.bincount(followers, minlength=100) + 100 * direct) / (len(followers) + 100)
    return {"bayes365_a1000": direct, "bayes_joint_digit_mix": mixed,
            "markov_shrunk_a100": markov, "logistic_bayes_mix": 0.5 * logistic + 0.5 * mixed,
            "logistic_uniform_half": 0.5 * logistic + 0.005}


def summarize_backtest(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["model"]].append(row)
    result = {}
    for model, group in grouped.items():
        counts = (1,) if model == "digit_frequency" else COUNTS
        result[model] = {
            "counts": {str(n): metrics(group, n, 0.1 if n == 1 else n / 100) for n in counts},
            "after_previous_snapshot": metrics([r for r in group if r["date"] > "2026-09-05"], counts[0] if len(counts) == 1 else 65, 0.1 if len(counts) == 1 else 0.65),
        }
    pvalues = {m: stats["counts"]["65"]["binomial_p_greater"] for m, stats in result.items() if "65" in stats["counts"]}
    return {"models": result, "top65_holm_p": holm(pvalues),
            "uniform_reference": {"mean_log_loss": math.log(100), "mean_brier": 0.99, "top65_expected": 0.65}}


def catboost_row(index, draws, features, labels):
    train_end = index - catboost.LAG_COUNT
    classifier = catboost._fit_classifier(features[:train_end], labels[:train_end])
    raw = classifier.predict_proba([features[train_end]])[0]
    p = np.full(100, catboost.UNIFORM_SHRINKAGE / 100)
    for label, value in zip(classifier.classes_, raw):
        p[int(label)] += (1 - catboost.UNIFORM_SHRINKAGE) * value
    row = score_row(draws[index]["draw_date"], catboost.MODEL_VERSION, p, int(draws[index]["last_two"]))
    row["trained_through"] = draws[index-1]["draw_date"]
    row["probabilities"] = [round(float(v), 12) for v in p]
    return row


def backtest(draws, output, *, periods=365, catboost_only=False, workers=1):
    rows = []
    start = max(733, len(draws) - periods)
    features = labels = None
    if catboost_only:
        start = max(start, catboost.LAG_COUNT + catboost.MINIMUM_TRAINING_SAMPLES)
        # Each feature row uses only its preceding draws; each fit uses X[:target].
        features, labels = catboost._training_data(draws)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(catboost_row, i, draws, features, labels)
                       for i in range(start, len(draws))]
            for future in as_completed(futures):
                rows.append(future.result())
                print(f"CatBoost: {len(rows)}/{len(futures)} completed", flush=True)
        rows.sort(key=lambda r: r["date"])
        save(output / "catboost_backtest_daily.json", rows)
        save(output / "catboost_backtest_summary.json", summarize_backtest(rows))
        return
    for index in range(start, len(draws)):
        target = draws[index]["draw_date"]
        actual = int(draws[index]["last_two"])
        history = draws[:index]
        tick = time.perf_counter()
        frequency = probabilities(frequency_rank(history, target, 65)["scores"])
        logistic = probabilities(logistic_rank(history, target, 65)["scores"])
        distributions = {FREQUENCY: frequency, LOGISTIC: logistic, **candidate_probabilities(history, logistic)}
        digit = probabilities(rank_last_digits(history, target)["scores"], digit=True)
        rows.append(score_row(target, "digit_frequency", digit, actual % 10))
        for model, p in distributions.items():
            row = score_row(target, model, p, actual)
            row["trained_through"] = history[-1]["draw_date"]
            row["probabilities"] = [round(float(v), 12) for v in p]
            rows.append(row)
        if (index - start) % 50 == 0:
            print(f"{target}: {index-start+1}/{len(draws)-start}, last fit {time.perf_counter()-tick:.2f}s", flush=True)
    stem = "backtest"
    save(output / f"{stem}_daily.json", rows)
    save(output / f"{stem}_summary.json", summarize_backtest(rows))


def summarize_saved_backtests(snapshot, output):
    """Compare saved daily rows without refitting or changing live snapshots."""
    rows = json.loads((output / "backtest_daily.json").read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["model"]].append(row)
    pairs = ((FREQUENCY, LOGISTIC), (LOGISTIC, "logistic_bayes_mix"),
             (FREQUENCY, "logistic_bayes_mix"))
    save(output / "backtest_comparisons.json",
         {f"{a} -> {b}": paired_stats(grouped[a], grouped[b]) for a, b in pairs})
    cat_path = output / "catboost_backtest_daily.json"
    if cat_path.exists():
        cat_rows = json.loads(cat_path.read_text(encoding="utf-8"))
        dates = {r["date"] for r in cat_rows}
        versions = (FREQUENCY, LOGISTIC, catboost.MODEL_VERSION)
        common = {m: sorted([r for r in rows + cat_rows
                             if r["model"] == m and r["date"] in dates],
                            key=lambda r: r["date"]) for m in versions}
        save(output / "catboost_matched_comparison.json", {
            "common_dates": sorted(dates),
            "metrics": {m: metrics(group) for m, group in common.items()},
            "comparisons": {f"{a} -> {b}": paired_stats(common[a], common[b])
                            for a, b in itertools.combinations(versions, 2)},
        })
        rows += cat_rows
    lookup = {(r["date"], r["model"]): r for r in rows}
    checks = []
    for pred in snapshot["predictions"]:
        key = pred["prediction_date"], pred["model_version"]
        if key not in lookup or pred["selected_count"] != 65:
            continue
        saved = probabilities(pred["scores"])
        replay = np.asarray(lookup[key]["probabilities"])
        rank = np.lexsort((np.arange(100), -replay))
        checks.append({
            "date": key[0], "model": key[1],
            "max_absolute_probability_difference": float(np.abs(saved - replay).max()),
            "same_selected_numbers": set(pred["numbers"]) == {f"{n:02d}" for n in rank[:65]},
            "saved_training_draw_count": pred.get("training_draw_count"),
            "note": "Replay uses the current full historical dataset; an older live snapshot may have had less history.",
        })
    save(output / "replay_checks.json", checks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("reports/algorithm_audit_20261012/database_snapshot.json"))
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--catboost-only", action="store_true")
    parser.add_argument("--summarize", action="store_true", help="Compare existing backtest files without refitting")
    parser.add_argument("--periods", type=int, default=365)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()
    output = args.input.parent
    snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    draws, excluded = validate_draws(snapshot["draws"])
    first, last = date.fromisoformat(draws[0]["draw_date"]), date.fromisoformat(draws[-1]["draw_date"])
    observed = {d["draw_date"] for d in draws}
    gaps = [(first + timedelta(days=i)).isoformat() for i in range((last - first).days+1)
            if (first + timedelta(days=i)).isoformat() not in observed]
    counts = np.bincount([int(d["last_two"]) for d in draws], minlength=100)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "library_versions": {name: importlib.metadata.version(name)
                             for name in ("numpy", "scipy", "scikit-learn", "catboost")},
        "snapshot_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(), "dataset_hash": digest(draws),
        "draws": len(draws), "first": first.isoformat(), "last": last.isoformat(), "excluded": excluded,
        "missing_calendar_dates": gaps, "chi_square_uniform_p": float(chisquare(counts).pvalue),
        "protocol": PROTOCOL,
        "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__), *Path("app/services").glob("*prediction.py")]},
    }
    save(output / "manifest.json", manifest)
    save(output / "live_audit.json", audit_live(snapshot, draws))
    if args.backtest or args.catboost_only:
        backtest(draws, output, periods=args.periods, catboost_only=args.catboost_only, workers=args.workers)
    if args.summarize:
        summarize_saved_backtests(snapshot, output)
    print(f"Audit saved in {output}", flush=True)


if __name__ == "__main__":
    main()
