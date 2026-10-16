from app.services import model_comparison as comparison


def test_bootstrap_reused_only_for_identical_ordered_outcomes_and_count(monkeypatch):
    calls = []
    monkeypatch.setattr(comparison, "_paired_block_bootstrap",
                        lambda rows, count: calls.append((rows, count)) or [0, 1])
    comparison._cached_bootstrap.cache_clear()
    try:
        outcomes = ((True, False), (False, True))
        comparison._cached_bootstrap(outcomes, 65)
        comparison._cached_bootstrap(outcomes, 65)
        assert len(calls) == 1
        comparison._cached_bootstrap(tuple(reversed(outcomes)), 65)
        comparison._cached_bootstrap(outcomes, 70)
        assert len(calls) == 3
    finally:
        comparison._cached_bootstrap.cache_clear()
