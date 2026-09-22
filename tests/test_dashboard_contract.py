import json
import re
from pathlib import Path

import pytest
from fastapi import HTTPException


STATIC_DIR = Path(__file__).parents[1] / "app" / "static"


def test_every_javascript_element_id_exists_in_dashboard() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    referenced_ids = set(re.findall(r"\bel\(['\"]([^'\"]+)['\"]\)", javascript))
    html_ids = set(re.findall(r"\bid=['\"]([^'\"]+)['\"]", html))

    assert referenced_ids <= html_ids


def test_feature_pages_have_matching_links_views_and_server_routes() -> None:
    from app.main import app

    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    page_names = {
        "overview",
        "results",
        "two-digit",
        "fortune-two-digit",
        "one-digit",
        "backtest",
    }
    link_pages = set(re.findall(r'data-page-link="([^"]+)"', html))
    view_pages = set(re.findall(r'data-page-view="([^"]+)"', html))
    server_paths = {route.path for route in app.routes}

    assert link_pages == page_names
    assert view_pages == page_names
    assert {
        "/",
        "/ket-qua",
        "/du-doan-2-so",
        "/du-doan-than-tai",
        "/du-doan-1-so",
        "/backtest",
    } <= server_paths
    assert "/api/model-comparison/rolling" in server_paths


def test_app_shell_has_button_navigation_and_versioned_assets() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'class="app-brand"' in html
    assert html.count('class="nav-icon"') == 6
    assert html.count('class="nav-label"') == 6
    assert '/static/styles.css?v=' in html
    assert '/static/app.js?v=' in html
    assert html.count('class="nav-logo') == 6


def test_two_digit_form_always_uses_automatic_prediction_date() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    two_digit_handler = javascript.split("el('prediction-form')", 1)[1].split(
        "el('digit-prediction-form')", 1
    )[0]

    assert 'id="prediction-date"' not in html
    assert "el('prediction-date')" not in javascript
    assert "payload.prediction_date" not in two_digit_handler
    assert "Ngày dự đoán được chọn tự động" in html


def test_one_digit_form_always_uses_automatic_prediction_date() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    one_digit_handler = javascript.split("el('digit-prediction-form')", 1)[1].split(
        "el('backtest-form')", 1
    )[0]

    assert 'id="digit-prediction-date"' not in html
    assert "el('digit-prediction-date')" not in javascript
    assert "payload.prediction_date" not in one_digit_handler
    assert "Ngày được tự động chọn là hôm nay" in html


def test_fortune_page_uses_logistic_api_and_automatic_date() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'data-page-link="fortune-two-digit"' in html
    assert 'data-page-view="fortune-two-digit"' in html
    assert 'id="fortune-selected-count"' in html
    assert '/api/logistic-predictions/generate' in javascript
    assert 'id="fortune-prediction-date"' not in html


def test_fortune_page_has_local_art_glitter_and_center_out_highlight() -> None:
    from app.main import app

    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    mounted_paths = {route.path for route in app.routes}

    assert "/img" in mounted_paths
    assert '/img/Than_tai2.jpg' in html
    assert '/img/Than_tai.jpg' in html
    assert 'id="fortune-glitter-rain"' in html
    assert "function initFortuneGlitter()" in javascript
    assert "function updateFortuneRippleDelays()" in javascript
    assert "--fortune-ripple-delay" in css
    assert "prefers-reduced-motion: reduce" in css
    assert '[data-theme="dark"] .fortune-number.selected' in css
    assert "max-width: 720px" in css
    assert '/img/icon_nav_home_active.svg' in html
    assert 'class="page-sticker sticker-fortune' in html
    assert '/api/model-comparison/rolling' in javascript


def test_vercel_cron_uses_get_compatible_reconciliation_endpoint() -> None:
    from app.main import app

    cron_route = next(route for route in app.routes if route.path == "/api/auto-daily")
    config = json.loads((STATIC_DIR.parents[1] / "vercel.json").read_text("utf-8"))

    assert {"GET", "POST"} <= cron_route.methods
    assert len(config["crons"]) == 4
    assert {job["path"] for job in config["crons"]} == {"/api/auto-daily"}
    assert config["crons"][0]["schedule"] == "30 10 * * *"


def test_cron_secret_is_checked_when_configured(monkeypatch) -> None:
    import app.main as app_main

    monkeypatch.setenv("CRON_SECRET", "a-secure-test-secret")

    with pytest.raises(HTTPException) as error:
        app_main._authorize_cron_request(
            type("Request", (), {"headers": {}})()
        )

    assert error.value.status_code == 401
    app_main._authorize_cron_request(
        type(
            "Request",
            (),
            {"headers": {"authorization": "Bearer a-secure-test-secret"}},
        )()
    )


def test_in_process_scheduler_is_disabled_on_vercel(monkeypatch) -> None:
    import app.main as app_main

    monkeypatch.setattr(
        app_main,
        "settings",
        type("Settings", (), {"enable_scheduler": True, "is_vercel": True})(),
    )

    assert app_main._in_process_scheduler_enabled() is False


def test_settings_detect_vercel_runtime(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("VERCEL", "1")

    assert Settings.from_env().is_vercel is True
