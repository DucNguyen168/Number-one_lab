from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.prediction_protocol import actual_revision_hash
from app.services.result_model_outcomes import RESULT_MODELS, attach_result_model_outcomes


DRAW = {"draw_date": "2026-10-16", "special_prize": "00100", "last_two": "00", "status": "observed"}


def prediction(letter="A", hit=True, **overrides):
    return {
        "prediction_date": DRAW["draw_date"], "model_version": RESULT_MODELS[letter],
        "selected_count": 65, "numbers": [f"{n:02d}" for n in range(0 if hit else 1, 65 if hit else 66)],
        "evaluation": {"status": "evaluated", "hit": hit, "actual_special_prize": "00100",
                       "actual_last_two": "00", "actual_revision_hash": actual_revision_hash(DRAW)},
        **overrides,
    }


def database(live=(), replays=()):
    queries = []

    def collection(rows):
        def find(query, projection):
            queries.append((query, projection))
            return [deepcopy(row) for row in rows
                    if row["prediction_date"] in query["prediction_date"]["$in"]
                    and row["model_version"] in query["model_version"]["$in"]
                    and row["selected_count"] == query["selected_count"]]
        return SimpleNamespace(find=find)

    return SimpleNamespace(predictions=collection(live), prediction_replays=collection(replays)), queries


def test_outcomes_use_matching_day_model_and_count_with_two_reads_and_no_mutation():
    draws = [deepcopy(DRAW), {**DRAW, "draw_date": "2026-10-15"}]
    live = [prediction(), prediction("B", hit=False), prediction("C", selected_count=70),
            prediction("C", prediction_date="2026-10-14")]
    original = deepcopy((draws, live))
    db, queries = database(live)
    result = attach_result_model_outcomes(db, draws, 65)
    assert {k: v["status"] for k, v in result[0]["model_outcomes"].items()} == {
        "A": "hit", "B": "miss", "C": "missing"}
    assert all(v["status"] == "missing" for v in result[1]["model_outcomes"].values())
    assert result[0]["model_selected_count"] == 65
    assert len(queries) == 2
    assert queries[0][0]["prediction_date"] == {"$in": ["2026-10-16", "2026-10-15"]}
    assert (draws, live) == original


def test_live_pending_takes_precedence_and_replays_are_recomputed_and_marked():
    db, _ = database([prediction(evaluation={"status": "pending"})],
                     [prediction(), prediction("B", hit=False, evaluation={"status": "evaluated", "hit": True})])
    outcomes = attach_result_model_outcomes(db, [DRAW], 65)[0]["model_outcomes"]
    assert outcomes["A"]["status"] == "pending"
    assert outcomes["A"]["prediction_kind"] == "live"
    assert outcomes["B"]["status"] == "miss"
    assert outcomes["B"]["prediction_kind"] == "retrospective"


@pytest.mark.parametrize("change", [
    {"actual_special_prize": "00200"}, {"actual_last_two": "01"},
    {"actual_revision_hash": "outdated"}, {"hit": False}, {"status": "invalidated"},
])
def test_stale_or_inconsistent_live_evaluation_is_neutral(change):
    doc = prediction()
    doc["evaluation"].update(change)
    db, _ = database([doc])
    assert attach_result_model_outcomes(db, [DRAW], 65)[0]["model_outcomes"]["A"]["status"] == "invalidated"


@pytest.mark.parametrize("replay", [False, True])
def test_conflicting_draws_never_show_hit_or_miss(replay):
    db, _ = database([] if replay else [prediction()], [prediction()] if replay else [])
    draw = {**DRAW, "status": "conflict"}
    assert attach_result_model_outcomes(db, [draw], 65)[0]["model_outcomes"]["A"]["status"] == "invalidated"


@pytest.mark.parametrize("numbers", [["00"] * 65, ["00"], [None] * 65, ["ab"] * 65])
def test_malformed_selection_cannot_produce_a_hit(numbers):
    db, _ = database([prediction(numbers=numbers)])
    assert attach_result_model_outcomes(db, [DRAW], 65)[0]["model_outcomes"]["A"]["status"] == "invalidated"


def test_empty_page_does_not_query_models():
    db, queries = database()
    assert attach_result_model_outcomes(db, [], 65) == []
    assert queries == []
