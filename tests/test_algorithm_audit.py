from datetime import date, timedelta

import numpy as np
import pytest

import scripts.audit_algorithms as audit


def test_uniform_reference_and_shrinkage_preserve_top_n_ranking():
    uniform = audit.score_row("2026-10-12", "uniform", np.full(100, 0.01), 70)
    assert uniform["log_loss"] == pytest.approx(np.log(100))
    assert uniform["brier"] == pytest.approx(0.99)
    p = np.arange(1, 101, dtype=float)
    p /= p.sum()
    raw = audit.score_row("2026-10-12", "raw", p, 40)
    shrunk = audit.score_row("2026-10-12", "shrunk", 0.5*p+0.005, 40)
    assert raw["rank"] == shrunk["rank"]
    assert raw["hit_65"] == shrunk["hit_65"]


def test_holm_and_small_sample_bootstrap_do_not_claim_false_precision():
    assert audit.holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": 0.03, "c": 0.06, "b": 0.06}
    a = [{"date": str(i), "hit_65": i%2 == 0} for i in range(19)]
    b = [{"date": str(i), "hit_65": i%2 == 1} for i in range(19)]
    result = audit.paired_stats(a, b)
    assert result["block_bootstrap_delta_ci95"]["30"] is None
    assert result["mcnemar_exact_p"] == 1


def test_live_audit_excludes_late_snapshot_and_recomputes_hit():
    scores = [{"number": f"{n:02d}", "probability": 0.01} for n in range(100)]
    pred = {
        "model_version": audit.FREQUENCY, "prediction_date": "2026-10-12",
        "selected_count": 65, "numbers": [f"{n:02d}" for n in range(65)], "scores": scores,
        "locked_at": "2026-10-12T11:44:00", # Mongo naive UTC = 18:44 VN
        "trained_through": "2026-10-11", "dataset_hash": "same",
        "evaluation": {"status": "evaluated", "hit": False, "actual_last_two": "01"},
    }
    result = audit.audit_live({"predictions": [pred], "digit_predictions": []},
                              [{"draw_date": "2026-10-12", "last_two": "01"}])
    assert result["groups"][0]["raw_evaluated"]["hits"] == 1
    assert result["groups"][0]["eligible_evaluated"]["n"] == 0
    assert set(result["issues"][0]["reasons"]) == {"locked_after_1730", "stored_hit_disagrees_with_actual"}


def test_candidate_distributions_are_valid_even_with_sparse_classes():
    history = [{"last_two": "00"}] * 400
    candidates = audit.candidate_probabilities(history, np.full(100, 0.01))
    for p in candidates.values():
        assert len(p) == 100
        assert np.all(p > 0)
        assert p.sum() == pytest.approx(1)


def test_cached_catboost_fit_excludes_target_and_future_rows(monkeypatch):
    monkeypatch.setattr(audit.catboost, "LAG_COUNT", 3)
    draws = [{"draw_date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
              "last_two": f"{i:02d}"} for i in range(10)]
    features = [[i] for i in range(7)]
    labels = list(range(3, 10))

    class Classifier:
        classes_ = [0, 1]

        def predict_proba(self, x):
            assert x == [[5]]
            return [[0.6, 0.4]]

    def fit(x, y):
        assert x == [[i] for i in range(5)]
        assert y == list(range(3, 8))
        return Classifier()

    monkeypatch.setattr(audit.catboost, "_fit_classifier", fit)
    row = audit.catboost_row(8, draws, features, labels)
    assert row["trained_through"] < row["date"]
    assert sum(row["probabilities"]) == pytest.approx(1)


def test_dataset_validation_rejects_duplicate_dates_and_excludes_conflicts():
    draw = {"draw_date": "2026-10-12", "last_two": "00"}
    with pytest.raises(ValueError, match="Duplicate"):
        audit.validate_draws([draw, draw])
    valid, excluded = audit.validate_draws([{**draw, "status": "conflict"}])
    assert valid == []
    assert excluded == [{"date": "2026-10-12", "reason": "conflict"}]
