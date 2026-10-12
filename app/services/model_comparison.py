from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from typing import Any

from pymongo.database import Database
from scipy.stats import binomtest

from app.services import prediction_protocol as protocol
from app.services.catboost_prediction import MODEL_VERSION as CATBOOST_MODEL_VERSION
from app.services.logistic_prediction import MODEL_VERSION as LOGISTIC_MODEL_VERSION
from app.services.prediction import MODEL_VERSION as FREQUENCY_MODEL_VERSION
from app.services.rolling_comparison import _exact_mcnemar_p, _paired_block_bootstrap, _wilson_interval

MODULES = {
    FREQUENCY_MODEL_VERSION: "app.services.prediction",
    LOGISTIC_MODEL_VERSION: "app.services.logistic_prediction",
    CATBOOST_MODEL_VERSION: "app.services.catboost_prediction",
}
HIT_KEYS = {FREQUENCY_MODEL_VERSION: "frequency_hit", LOGISTIC_MODEL_VERSION: "logistic_hit",
            CATBOOST_MODEL_VERSION: "catboost_hit"}


def _matched_rows(db, count, versions):
    documents = list(db.predictions.find({
        "selected_count": count, "model_version": {"$in": versions},
        "evaluation.status": {"$in": ["evaluated", "invalidated"]},
    }, {"scores": 0, "window_details": 0, "evaluation_history": 0}).sort("prediction_date", 1))
    days = sorted({p["prediction_date"] for p in documents})
    draws = {d["draw_date"]: d for d in db.draw_results.find(
        {"draw_date": {"$in": days}},
        {"draw_date": 1, "special_prize": 1, "last_two": 1, "status": 1},
    )}
    ids = list({p["training_snapshot_id"] for p in documents if p.get("training_snapshot_id")})
    snapshots = {s["_id"]: s for s in db.training_datasets.find({"_id": {"$in": ids}}, {"records": 0})}
    expected_code = {v: protocol.code_hash(MODULES[v]) for v in versions}
    candidates, excluded, reasons = [], 0, Counter()
    for pred in documents:
        issues = protocol.eligibility_reasons(pred, draws.get(pred["prediction_date"]))
        if pred.get("code_hash") != expected_code[pred["model_version"]]:
            issues.append("different_model_code")
        snapshot = snapshots.get(pred.get("training_snapshot_id"))
        if (not snapshot or snapshot.get("dataset_hash") != pred.get("dataset_hash")
                or snapshot.get("dataset_hash") != pred.get("training_snapshot_dataset_hash")
                or snapshot.get("record_count") != pred.get("training_draw_count")
                or snapshot.get("trained_through") != pred.get("trained_through")):
            issues.append("missing_or_inconsistent_training_snapshot")
        expected_batch = protocol.fingerprint({
            "date": pred["prediction_date"], "count": count, "strategy": protocol.STRATEGY,
            "protocol": protocol.PROTOCOL_VERSION, "snapshot": pred.get("training_snapshot_id"),
        })
        if pred.get("comparison_batch_id") != expected_batch:
            issues.append("invalid_comparison_batch")
        if issues:
            excluded += 1
            reasons.update(set(issues))
        else:
            candidates.append(pred)
    # Freeze one configuration/library signature per version: the latest valid one.
    signatures = {}
    for pred in sorted(candidates, key=lambda p: protocol.as_utc(p["locked_at"])):
        signatures[pred["model_version"]] = (pred["config_hash"], protocol.fingerprint(pred["library_versions"]))
    by_date = defaultdict(lambda: defaultdict(list))
    for pred in candidates:
        signature = (pred["config_hash"], protocol.fingerprint(pred["library_versions"]))
        if signature != signatures[pred["model_version"]]:
            excluded += 1
            reasons["different_configuration_or_libraries"] += 1
            continue
        by_date[pred["prediction_date"]][pred["model_version"]].append(pred)
    rows, incompatible = [], 0
    for day, models in sorted(by_date.items()):
        if any(len(models[v]) != 1 for v in versions):
            continue
        group = [models[v][0] for v in versions]
        if (len({p["dataset_hash"] for p in group}) != 1
                or len({p["training_snapshot_id"] for p in group}) != 1
                or len({p["comparison_batch_id"] for p in group}) != 1
                or len({p["strategy_id"] for p in group}) != 1):
            incompatible += 1
            continue
        actual = draws[day]["last_two"]
        rows.append({"prediction_date": day, "actual_last_two": actual,
                     **{HIT_KEYS[v]: actual in models[v][0]["numbers"] for v in versions}})
    return rows, {"candidate_snapshots": len(documents), "excluded_snapshots": excluded,
                  "excluded_reasons": dict(reasons), "incompatible_days": incompatible,
                  "configuration_hashes": {v: sig[0] for v, sig in signatures.items()}}


def _metrics(rows, version, count):
    total = len(rows)
    hits = sum(row[HIT_KEYS[version]] for row in rows)
    return {
        "model_version": version, "hits": hits, "sample_size": total,
        "hit_rate": round(hits / total, 8) if total else None,
        "confidence_interval_95": _wilson_interval(hits, total) if total else None,
        "baseline": count / 100,
        "binomial_p_greater": float(binomtest(hits, total, count / 100, alternative="greater").pvalue) if total else None,
    }


def _pair(rows, a, b, count):
    a_only = sum(r[HIT_KEYS[a]] and not r[HIT_KEYS[b]] for r in rows)
    b_only = sum(r[HIT_KEYS[b]] and not r[HIT_KEYS[a]] for r in rows)
    bootstrap_rows = [{f"frequency_hit_{count}": r[HIT_KEYS[a]],
                       f"logistic_hit_{count}": r[HIT_KEYS[b]]} for r in rows]
    return {
        "model_a": a, "model_b": b, "sample_size": len(rows),
        "a_only_hit": a_only, "b_only_hit": b_only,
        "delta_b_minus_a": round((b_only-a_only)/len(rows), 8) if rows else None,
        "mcnemar_exact_p": _exact_mcnemar_p(a_only, b_only) if rows else None,
        "paired_block_bootstrap_delta_ci95": _paired_block_bootstrap(bootstrap_rows, count) if len(rows) >= 14 else None,
    }


def _summary(db, count, versions):
    rows, eligibility = _matched_rows(db, count, versions)
    comparisons = [_pair(rows, a, b, count) for a, b in itertools.combinations(versions, 2)]
    running = 0.0
    if rows:
        for index, pair in enumerate(sorted(comparisons, key=lambda p: p["mcnemar_exact_p"])):
            running = max(running, min(1.0, (len(comparisons)-index)*pair["mcnemar_exact_p"]))
            pair["mcnemar_holm_p"] = running
    else:
        for pair in comparisons:
            pair["mcnemar_holm_p"] = None
    return {
        "selected_count": count, "baseline": count/100, "paired_predictions": len(rows),
        "frequency_model": _metrics(rows, FREQUENCY_MODEL_VERSION, count),
        "logistic_model": _metrics(rows, LOGISTIC_MODEL_VERSION, count),
        **({"catboost_model": _metrics(rows, CATBOOST_MODEL_VERSION, count)} if CATBOOST_MODEL_VERSION in versions else {}),
        "recent_pairs": list(reversed(rows[-30:])), "comparisons": comparisons,
        "eligibility": eligibility, "evaluation_protocol": protocol.PROTOCOL_VERSION,
        "evidence_status": "insufficient_sample" if len(rows) < 365 else "requires_review",
        "note": (f"{len(rows)} kỳ cùng dữ liệu và số lượng, khóa trước {protocol.DEADLINE_TIME}. "
                 f"Loại {eligibility['excluded_snapshots']} snapshot không đủ điều kiện; "
                 f"{eligibility['incompatible_days']} ngày khác dữ liệu giữa các mô hình. "
                 "Bộ dự đoán cũ thiếu dấu vết được giữ trong lịch sử. "
                 + ("Mẫu dưới 365 kỳ; chưa đủ bằng chứng xác nhận mô hình chính xác hơn. " if len(rows) < 365
                    else "Cần xem chênh lệch và mức bất định trước khi kết luận mô hình chính xác hơn. ")
                 + "Khoảng tin cậy và kiểm định là thống kê quan sát."),
    }


def comparison_summary(db: Database, selected_count: int) -> dict[str, Any]:
    result = _summary(db, selected_count, [FREQUENCY_MODEL_VERSION, LOGISTIC_MODEL_VERSION])
    pair = result["comparisons"][0]
    both_hit = result["frequency_model"]["hits"] - pair["a_only_hit"]
    result.update(lift_logistic_vs_frequency=pair["delta_b_minus_a"],
                  mcnemar_exact_p=pair["mcnemar_exact_p"],
                  paired_block_bootstrap_delta_ci95=pair["paired_block_bootstrap_delta_ci95"],
                  disagreements={"frequency_only_hit": pair["a_only_hit"], "logistic_only_hit": pair["b_only_hit"],
                                 "both_hit": both_hit,
                                 "both_miss": result["paired_predictions"] - both_hit - pair["a_only_hit"] - pair["b_only_hit"]})
    return result


def three_way_comparison_summary(db: Database, selected_count: int) -> dict[str, Any]:
    return _summary(db, selected_count, [FREQUENCY_MODEL_VERSION, LOGISTIC_MODEL_VERSION, CATBOOST_MODEL_VERSION])
