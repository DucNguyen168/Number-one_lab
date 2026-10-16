from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import catboost_prediction, digit_prediction, logistic_prediction, prediction
from app.services import evaluation, model_comparison, prediction_protocol as protocol, rolling_comparison


def _value(document, key):
    value = document
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _matches(document, query):
    for key, expected in query.items():
        value = _value(document, key)
        if isinstance(expected, dict) and any(k.startswith("$") for k in expected):
            for op, arg in expected.items():
                if op == "$in" and value not in arg:
                    return False
                if op == "$ne" and value == arg:
                    return False
                if op == "$lt" and not value < arg:
                    return False
        elif value != expected:
            return False
    return True


class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda d: _value(d, key), reverse=direction < 0))


class Collection:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))

    def find(self, query, projection=None):
        return Cursor(deepcopy([d for d in self.rows if _matches(d, query)]))

    def find_one(self, query, projection=None):
        return next(iter(self.find(query)), None)

    def insert_one(self, document):
        document = deepcopy(document)
        document.setdefault("_id", len(self.rows) + 1)
        self.rows.append(document)
        return SimpleNamespace(inserted_id=document["_id"])

    def update_one(self, query, update, upsert=False):
        row = next((d for d in self.rows if _matches(d, query)), None)
        if row is None:
            if upsert:
                self.insert_one({**query, **deepcopy(update.get("$setOnInsert", {}))})
            return SimpleNamespace(modified_count=0)
        old = deepcopy(row)
        row.update(deepcopy(update.get("$set", {})))
        for key, value in update.get("$push", {}).items():
            row.setdefault(key, []).append(deepcopy(value))
        return SimpleNamespace(modified_count=int(row != old))

    def replace_one(self, query, document, upsert=False):
        self.rows = [r for r in self.rows if not _matches(r, query)]
        self.insert_one(document)


@pytest.fixture
def db():
    start = date(2026, 9, 3)
    draws = [{"_id": f"draw-{i}", "draw_date": (start+timedelta(days=i)).isoformat(),
              "last_two": f"{i % 100:02d}", "special_prize": f"{i:05d}", "status": "observed"}
             for i in range(40)]
    return SimpleNamespace(draw_results=Collection(draws), predictions=Collection(),
                           digit_predictions=Collection(), training_datasets=Collection(),
                           model_comparison_reports=Collection())


@pytest.fixture
def clock(monkeypatch):
    current = [datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(protocol, "utc_now", lambda: current[0])
    return current


def _rank(module, *, alpha=1):
    def rank(history, target, count=65):
        version = getattr(module, "MODEL_VERSION", getattr(module, "DIGIT_MODEL_VERSION", None))
        return {"model_version": version,
                **({"predicted_digit": "1"} if module is digit_prediction else
                   {"selected_count": count, "numbers": [f"{i:02d}" for i in range(count)]}),
                "training_draw_count": len(history),
                "trained_through": history[-1]["draw_date"], "dataset_hash": protocol.dataset_hash(history),
                "model_config": {"version": version, "alpha": alpha}}
    return rank


MODULES = (prediction, logistic_prediction, catboost_prediction, digit_prediction)


@pytest.mark.parametrize("module", [prediction, digit_prediction])
def test_provenance_preserves_real_ranking_and_never_relocks_existing_snapshot(db, clock, module):
    is_digit = module is digit_prediction
    ranker = module.rank_last_digits if is_digit else module.rank_numbers
    creator = module.create_digit_prediction if is_digit else module.create_prediction
    args = [] if is_digit else [65]
    expected = ranker(db.draw_results.rows, "2026-10-13", *args)
    saved, created = creator(db, "2026-10-13", *args)
    assert created and saved["scores"] == expected["scores"]
    assert saved["dataset_hash"] == expected["dataset_hash"]
    assert saved["config_hash"] == protocol.fingerprint(saved["model_config"])
    assert saved["training_snapshot_dataset_hash"] == protocol.dataset_hash(db.draw_results.rows)
    clock[0] = protocol.deadline("2026-10-13") + timedelta(hours=1)
    existing, created = creator(db, "2026-10-13", *args)
    assert not created and existing["locked_at"] == saved["locked_at"]


@pytest.mark.parametrize("module", MODULES)
def test_all_model_creators_reject_deadline_even_without_collected_result(db, clock, module):
    clock[0] = protocol.deadline("2026-10-13")
    creator = getattr(module, "create_prediction", getattr(module, "create_digit_prediction", None))
    with pytest.raises(ValueError, match="deadline has passed"):
        creator(db, "2026-10-13", *([] if module is digit_prediction else [65]))
    assert db.predictions.rows == db.digit_predictions.rows == []


@pytest.mark.parametrize("module", MODULES)
def test_fit_crossing_deadline_cannot_lock_a_prediction(db, clock, monkeypatch, module):
    fake = _rank(module)
    def slow_rank(*args):
        result = fake(*args)
        clock[0] = protocol.deadline("2026-10-13")
        return result
    monkeypatch.setattr(module, "rank_last_digits" if module is digit_prediction else "rank_numbers", slow_rank)
    creator = getattr(module, "create_prediction", getattr(module, "create_digit_prediction", None))
    with pytest.raises(ValueError, match="deadline has passed"):
        creator(db, "2026-10-13", *([] if module is digit_prediction else [65]))
    assert db.predictions.rows == db.digit_predictions.rows == []


def _create_three(db, clock, monkeypatch, target="2026-10-13", *, logistic_alpha=1):
    clock[0] = protocol.deadline(target) - timedelta(hours=1)
    for module in MODULES[:3]:
        monkeypatch.setattr(module, "rank_numbers", _rank(module, alpha=logistic_alpha if module is logistic_prediction else 1))
        module.create_prediction(db, target, 65)
    db.draw_results.insert_one({"draw_date": target, "last_two": "01", "special_prize": "00001", "status": "observed"})
    evaluation.evaluate_pending_predictions(db)


def test_training_snapshot_is_shared_immutable_and_replayable(db, clock, monkeypatch):
    _create_three(db, clock, monkeypatch)
    assert len(db.training_datasets.rows) == 1
    saved = deepcopy(db.training_datasets.rows[0])
    assert len(saved["records"]) == 40
    assert all(p["training_snapshot_id"] == saved["_id"] for p in db.predictions.rows)
    assert all(p["information_cutoff_at"] <= p["locked_at"] < p["prediction_deadline_at"] for p in db.predictions.rows)
    db.draw_results.rows[0].update(last_two="99", special_prize="00099")
    _create_three(db, clock, monkeypatch, "2026-10-14")
    assert len(db.training_datasets.rows) == 2
    assert db.training_datasets.rows[0] == saved
    assert db.training_datasets.rows[1]["records"][0]["last_two"] == "99"


def test_valid_three_way_pair_reports_ci_and_statistics(db, clock, monkeypatch):
    _create_three(db, clock, monkeypatch)
    result = model_comparison.three_way_comparison_summary(db, 65)
    assert result["paired_predictions"] == 1
    assert result["frequency_model"]["confidence_interval_95"][0] < 0.65
    assert result["frequency_model"]["hit_rate"] == 1
    assert result["evidence_status"] == "insufficient_sample"
    assert all(p["mcnemar_holm_p"] == 1 for p in result["comparisons"])
    assert all(p["paired_block_bootstrap_delta_ci95"] is None for p in result["comparisons"])


@pytest.mark.parametrize("writer,reader", [
    ("mixed", "lf"), ("lf", "crlf"), ("crlf", "mixed"), ("mixed", "crlf"),
])
def test_live_comparison_is_portable_between_windows_and_linux(db, clock, monkeypatch, writer, reader):
    read_bytes = Path.read_bytes

    def source_bytes(style):
        def read(path):
            raw = read_bytes(path)
            if path.suffix != ".py":
                return raw
            lf = raw.replace(b"\r\n", b"\n")
            crlf = style == "crlf" or (style == "mixed" and path.name != "prediction_protocol.py")
            return lf.replace(b"\n", b"\r\n") if crlf else lf
        return read

    # Real locking metadata, written with the first environment's source bytes.
    monkeypatch.setattr(Path, "read_bytes", source_bytes(writer))
    _create_three(db, clock, monkeypatch)
    saved = deepcopy(db.predictions.rows)
    expected = model_comparison.three_way_comparison_summary(db, 65)
    monkeypatch.setattr(Path, "read_bytes", source_bytes(reader))
    assert any(p["code_hash"] != protocol.code_hash(model_comparison.MODULES[p["model_version"]])
               for p in saved)  # The old exact-byte check really would exclude a snapshot.
    assert model_comparison.three_way_comparison_summary(db, 65) == expected
    assert model_comparison.comparison_summary(db, 65)["paired_predictions"] == 1
    assert db.predictions.rows == saved  # Never rewrite historical lock provenance.


@pytest.mark.parametrize("changed_file,excluded", [("prediction.py", 1), ("prediction_protocol.py", 3)])
def test_portable_hash_matching_still_rejects_changed_source(db, clock, monkeypatch, changed_file, excluded):
    _create_three(db, clock, monkeypatch)
    read_bytes = Path.read_bytes

    def changed_source(path):
        raw = read_bytes(path).replace(b"\r\n", b"\n")
        if path.name == changed_file:
            raw += b"\nNEW_ALGORITHM_PARAMETER = 1\n"
        return raw

    monkeypatch.setattr(Path, "read_bytes", changed_source)
    result = model_comparison.three_way_comparison_summary(db, 65)
    assert result["paired_predictions"] == 0
    assert result["eligibility"]["excluded_reasons"]["different_model_code"] == excluded


@pytest.mark.parametrize("change,reason", [
    (lambda p: p.update(locked_at=protocol.deadline(p["prediction_date"])), "locked_after_deadline"),
    (lambda p: p.update(dataset_hash="wrong"), "missing_or_inconsistent_training_snapshot"),
    (lambda p: p.update(comparison_batch_id="wrong"), "invalid_comparison_batch"),
    (lambda p: p.update(strategy_id="exclude_recent"), "different_strategy"),
    (lambda p: p["evaluation"].update(hit=False), "stale_or_inconsistent_evaluation"),
    (lambda p: p.pop("evaluation_protocol"), "missing_or_different_protocol"),
    (lambda p: p.update(code_hash="old-code"), "different_model_code"),
])
def test_comparison_rejects_ineligible_snapshot(db, clock, monkeypatch, change, reason):
    _create_three(db, clock, monkeypatch)
    change(db.predictions.rows[0])
    result = model_comparison.three_way_comparison_summary(db, 65)
    assert result["paired_predictions"] == 0
    assert result["eligibility"]["excluded_reasons"][reason] == 1
    assert result["frequency_model"]["confidence_interval_95"] is None


def test_comparison_never_combines_two_configs_under_one_version(db, clock, monkeypatch):
    _create_three(db, clock, monkeypatch)
    _create_three(db, clock, monkeypatch, "2026-10-14", logistic_alpha=2)
    result = model_comparison.comparison_summary(db, 65)
    assert result["paired_predictions"] == 1
    assert result["recent_pairs"][0]["prediction_date"] == "2026-10-14"
    assert result["eligibility"]["excluded_reasons"]["different_configuration_or_libraries"] == 1


def test_same_day_with_different_valid_training_data_is_not_paired(db, clock, monkeypatch):
    _create_three(db, clock, monkeypatch)
    item = db.predictions.rows[1]
    history = deepcopy(db.draw_results.rows[:39])
    clock[0] = protocol.deadline("2026-10-13") - timedelta(hours=1)
    item.update(_rank(logistic_prediction)(history, "2026-10-13", 65))
    # Build legitimate provenance for another input, without allowing retrospective locking.
    actual = db.draw_results.rows.pop()
    item.update(protocol.lock_metadata(db, history, "2026-10-13", item, logistic_prediction.__name__, clock[0]))
    db.draw_results.rows.append(actual)
    evaluation.evaluate_pending_predictions(db)
    result = model_comparison.three_way_comparison_summary(db, 65)
    assert result["paired_predictions"] == 0
    assert result["eligibility"]["incompatible_days"] == 1


def test_actual_corrections_invalidate_restore_and_preserve_previous_scores(db, clock, monkeypatch):
    _create_three(db, clock, monkeypatch)
    actual = db.draw_results.rows[-1]
    actual.update(last_two="87", special_prize="38287")
    assert model_comparison.comparison_summary(db, 65)["paired_predictions"] == 0
    counters = evaluation.evaluate_pending_predictions(db)
    assert counters["reevaluated"] == 3 and counters["misses"] == 3
    assert all(p["evaluation_history"][0]["previous"]["hit"] for p in db.predictions.rows)
    assert model_comparison.comparison_summary(db, 65)["frequency_model"]["hits"] == 0
    assert evaluation.evaluate_pending_predictions(db)["evaluated"] == 0
    actual["status"] = "conflict"
    assert evaluation.evaluate_pending_predictions(db)["invalidated"] == 3
    assert all(p["evaluation"]["status"] == "invalidated" for p in db.predictions.rows)
    actual["status"] = "observed"
    assert evaluation.evaluate_pending_predictions(db)["reevaluated"] == 3
    assert all(len(p["evaluation_history"]) == 3 for p in db.predictions.rows)


def test_digit_scores_are_reconciled_when_actual_changes(db, clock, monkeypatch):
    monkeypatch.setattr(digit_prediction, "rank_last_digits", _rank(digit_prediction))
    digit_prediction.create_digit_prediction(db, "2026-10-13")
    actual = {"draw_date": "2026-10-13", "last_two": "01", "special_prize": "00001", "status": "observed"}
    db.draw_results.insert_one(actual)
    assert evaluation.evaluate_pending_digit_predictions(db)["hits"] == 1
    assert db.digit_predictions.rows[0]["evaluation"]["eligible_for_comparison"] is True
    db.draw_results.rows[-1].update(last_two="87", special_prize="38287")
    assert evaluation.evaluate_pending_digit_predictions(db)["reevaluated"] == 1
    assert db.digit_predictions.rows[0]["evaluation"]["actual_digit"] == "7"
    assert db.digit_predictions.rows[0]["evaluation"]["hit"] is False


def test_rolling_cache_invalidates_for_config_libraries_and_dataset(db, monkeypatch):
    calls = []
    monkeypatch.setattr(rolling_comparison, "run_rolling_comparison",
                        lambda draws, **kw: (calls.append(len(draws)) or {"counts": {}}, []))
    _, rebuilt = rolling_comparison.load_or_build_rolling_comparison(db)
    assert rebuilt
    assert not rolling_comparison.load_or_build_rolling_comparison(db)[1]
    monkeypatch.setattr(logistic_prediction, "REGULARIZATION_C", 0.2)
    assert rolling_comparison.load_or_build_rolling_comparison(db)[1]
    old_version = rolling_comparison.importlib.metadata.version
    monkeypatch.setattr(rolling_comparison.importlib.metadata, "version", lambda name: old_version(name)+"-changed")
    assert rolling_comparison.load_or_build_rolling_comparison(db)[1]
    db.draw_results.rows[0].update(last_two="99", special_prize="00099")
    assert rolling_comparison.load_or_build_rolling_comparison(db)[1]
    assert len(calls) == 4


def test_read_only_rolling_never_trains_on_missing_or_stale_cache(db, monkeypatch):
    calls = []
    monkeypatch.setattr(rolling_comparison, "run_rolling_comparison",
                        lambda draws, **kw: (calls.append(len(draws)) or {"counts": {}}, []))
    with pytest.raises(rolling_comparison.RollingReportNotReady):
        rolling_comparison.load_or_build_rolling_comparison(db, allow_build=False)
    assert calls == []
    report, _ = rolling_comparison.load_or_build_rolling_comparison(db)
    assert rolling_comparison.load_or_build_rolling_comparison(db, allow_build=False) == (report, False)
    db.draw_results.rows[0].update(last_two="99")
    with pytest.raises(rolling_comparison.RollingReportNotReady):
        rolling_comparison.load_or_build_rolling_comparison(db, allow_build=False)
    assert len(calls) == 1
