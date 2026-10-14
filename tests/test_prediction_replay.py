from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import prediction_replay as replay
from app.services import prediction_protocol as protocol
from test_prediction_integrity import Collection, Cursor, _value


class ReplayCursor(Cursor):
    def sort(self, key, direction=None):
        rows = list(self)
        for field, order in reversed(key if isinstance(key, list) else [(key, direction)]):
            rows.sort(key=lambda row: str(_value(row, field) or ""), reverse=order < 0)
        return ReplayCursor(rows)

    def limit(self, count):
        return ReplayCursor(self[:count])


class ReplayCollection(Collection):
    def find(self, query, projection=None):
        return ReplayCursor(super().find(query, projection))

    def update_one(self, query, update, upsert=False):
        existed = self.find_one(query)
        super().update_one(query, update, upsert)
        return SimpleNamespace(upserted_id=None if existed else query["_id"])


@pytest.fixture
def replay_db(monkeypatch):
    monkeypatch.setattr(protocol, "utc_now", lambda: datetime(2026, 10, 14, 13, tzinfo=timezone.utc))
    draws = [
        {"draw_date": "2026-10-12", "last_two": "87", "special_prize": "38287", "status": "observed"},
        {"draw_date": "2026-10-13", "last_two": "18", "special_prize": "53618", "status": "observed"},
        {"draw_date": "2026-10-14", "last_two": "59", "special_prize": "28259", "status": "observed"},
        {"draw_date": "2026-10-15", "last_two": "99", "special_prize": "99999", "status": "observed"},
    ]
    return SimpleNamespace(draw_results=ReplayCollection(draws), predictions=ReplayCollection(),
                           prediction_replays=ReplayCollection(), training_datasets=ReplayCollection())


def fake_models(monkeypatch, calls):
    for model in replay.MODELS:
        def rank(history, target, count, version=model.MODEL_VERSION):
            calls.append((version, deepcopy(history)))
            assert [draw["draw_date"] for draw in history] == ["2026-10-12", "2026-10-13"]
            assert "59" not in [draw["last_two"] for draw in history]
            return {"model_version": version, "numbers": [f"{n:02d}" for n in range(count)],
                    "trained_through": history[-1]["draw_date"], "selected_count": count,
                    "dataset_hash": protocol.dataset_hash(history), "training_draw_count": len(history)}
        monkeypatch.setattr(model, "rank_numbers", rank)


def test_replays_all_models_without_target_leakage_or_live_predictions(replay_db, monkeypatch):
    calls = []
    fake_models(monkeypatch, calls)
    result = replay.create_missing_replays(replay_db, "2026-10-14", 65)
    assert result["status"] == "completed"
    assert len(calls) == len(replay_db.prediction_replays.rows) == 3
    assert replay_db.predictions.rows == []
    assert len(replay_db.training_datasets.rows) == 1
    assert [d["draw_date"] for d in replay_db.training_datasets.rows[0]["records"]] == ["2026-10-12", "2026-10-13"]
    for item in result["models"]:
        prediction = item["prediction"]
        assert item["created"] is True
        assert prediction["locked_at"] is None
        assert prediction["created_at"].date().isoformat() == "2026-10-14"
        assert prediction["excluded_from_live_metrics"] is True
        assert prediction["prediction_kind"] == "retrospective"
        assert prediction["evaluation"]["actual_last_two"] == "59"
        assert prediction["evaluation"]["hit"] is True
        reasons = protocol.eligibility_reasons(prediction, replay_db.draw_results.rows[2])
        assert "missing_or_different_protocol" in reasons


def test_repeated_replay_is_immutable_and_skips_training(replay_db, monkeypatch):
    calls = []
    fake_models(monkeypatch, calls)
    replay.create_missing_replays(replay_db, "2026-10-14")
    stored = deepcopy(replay_db.prediction_replays.rows)
    result = replay.create_missing_replays(replay_db, "2026-10-14")
    assert len(calls) == 3
    assert not any(item["created"] for item in result["models"])
    assert replay_db.prediction_replays.rows == stored


def test_existing_live_prediction_is_never_replaced(replay_db, monkeypatch):
    calls = []
    fake_models(monkeypatch, calls)
    original = {"_id": "existing", "prediction_date": "2026-10-14", "selected_count": 65,
                "model_version": replay.MODELS[0].MODEL_VERSION, "locked_at": "2026-10-13T12:00:00Z"}
    replay_db.predictions.insert_one(original)
    result = replay.create_missing_replays(replay_db, "2026-10-14")
    assert result["models"][0]["status"] == "live_exists"
    assert len(calls) == len(replay_db.prediction_replays.rows) == 2
    assert replay_db.predictions.rows == [original]


@pytest.mark.parametrize("problem", ["missing", "conflict", "bad_digits", "future"])
def test_unavailable_or_invalid_actual_cannot_be_replayed(replay_db, monkeypatch, problem):
    calls = []
    fake_models(monkeypatch, calls)
    target = "2026-10-14"
    if problem == "missing":
        replay_db.draw_results.rows.pop(2)
    elif problem == "conflict":
        replay_db.draw_results.rows[2]["status"] = "conflict"
    elif problem == "bad_digits":
        replay_db.draw_results.rows[2]["special_prize"] = "59"
    else:
        target = "2026-10-15"
    with pytest.raises(ValueError):
        replay.create_missing_replays(replay_db, target)
    assert calls == replay_db.prediction_replays.rows == []


def test_model_failure_keeps_other_replays_and_reports_partial_failure(replay_db, monkeypatch):
    calls = []
    fake_models(monkeypatch, calls)

    def fail(*args):
        raise ValueError("not enough training history")

    monkeypatch.setattr(replay.MODELS[1], "rank_numbers", fail)
    result = replay.create_missing_replays(replay_db, "2026-10-14")
    assert result["status"] == "partial_failure"
    assert len(replay_db.prediction_replays.rows) == 2
    assert result["models"][1]["error"] == "not enough training history"


def test_history_combines_replays_and_live_with_clear_type_and_current_actual(replay_db, monkeypatch):
    fake_models(monkeypatch, [])
    replay.create_missing_replays(replay_db, "2026-10-14")
    version = replay.MODELS[0].MODEL_VERSION
    replay_db.predictions.insert_one({"_id": "live", "prediction_date": "2026-10-15",
                                     "model_version": version, "selected_count": 65})
    history = replay.history_with_replays(replay_db, version, 50)
    assert [item["prediction_date"] for item in history] == ["2026-10-15", "2026-10-14"]
    assert history[1]["prediction_kind"] == "retrospective"
    assert history[1]["evaluation"]["hit"] is True
    assert "numbers" not in history[1]
    replay_db.draw_results.rows[2].update(special_prize="28299", last_two="99")
    changed = replay.history_with_replays(replay_db, version, 50)[1]
    assert changed["evaluation"]["actual_last_two"] == "99"
    assert changed["evaluation"]["hit"] is False
    replay_db.draw_results.rows[2]["status"] = "conflict"
    assert replay.history_with_replays(replay_db, version, 50)[1]["evaluation"]["status"] == "invalidated"
    assert len(replay.history_with_replays(replay_db, version, 1)) == 1


def test_history_prefers_live_record_if_both_collections_have_same_day(replay_db, monkeypatch):
    fake_models(monkeypatch, [])
    replay.create_missing_replays(replay_db, "2026-10-14")
    version = replay.MODELS[0].MODEL_VERSION
    replay_db.predictions.insert_one({"_id": "live", "prediction_date": "2026-10-14",
                                     "model_version": version, "selected_count": 65})
    history = replay.history_with_replays(replay_db, version, 50)
    assert len(history) == 1
    assert history[0]["_id"] == "live"
