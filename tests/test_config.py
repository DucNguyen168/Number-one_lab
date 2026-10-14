import pytest

from app.config import Settings


def test_settings_reject_invalid_prediction_time(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_TIME", "25:00")

    with pytest.raises(ValueError, match="PREDICTION_TIME"):
        Settings.from_env()


def test_settings_reject_unsorted_sync_times(monkeypatch) -> None:
    monkeypatch.setenv("RESULT_SYNC_TIMES", "19:10,18:35")

    with pytest.raises(ValueError, match="unique and sorted"):
        Settings.from_env()


def test_vercel_ignores_removed_auth_configuration(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("REQUIRE_ADMIN_AUTH", "true")
    monkeypatch.setenv("ADMIN_API_KEY", "unused-legacy-key")
    monkeypatch.setenv("CRON_SECRET", "unused-legacy-key")
    settings = Settings.from_env()
    assert settings.is_vercel is True
    assert not hasattr(settings, "admin_api_key")
    assert not hasattr(settings, "require_admin_auth")


def test_result_poll_defaults_and_minimum_interval(monkeypatch) -> None:
    monkeypatch.delenv("RESULT_POLL_START_TIME", raising=False)
    monkeypatch.delenv("RESULT_POLL_INTERVAL_SECONDS", raising=False)
    assert Settings.from_env().result_poll_start_time == "18:30"
    assert Settings.from_env().result_poll_interval_seconds == 10
    monkeypatch.setenv("RESULT_POLL_INTERVAL_SECONDS", "1")
    assert Settings.from_env().result_poll_interval_seconds == 10


def test_result_poll_rejects_invalid_start_time(monkeypatch) -> None:
    monkeypatch.setenv("RESULT_POLL_START_TIME", "18:70")
    with pytest.raises(ValueError, match="RESULT_POLL_START_TIME"):
        Settings.from_env()
