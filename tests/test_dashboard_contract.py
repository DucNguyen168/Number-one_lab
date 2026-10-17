import json
import re
import tomllib
from pathlib import Path



STATIC_DIR = Path(__file__).parents[1] / "app" / "static"


def test_vercel_framework_entrypoint_and_function_config_agree():
    root = STATIC_DIR.parents[1]
    config = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    module, variable = project["tool"]["vercel"]["entrypoint"].split(":")
    filename = module.replace(".", "/") + ".py"
    assert config["framework"] == "fastapi"
    assert set(config["functions"]) == {filename}
    assert (root / filename).is_file()
    assert "routes" not in config
    import importlib
    from app.main import app
    assert getattr(importlib.import_module(module), variable) is app


def _visible_html(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)


def test_every_javascript_element_id_exists_in_dashboard() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    referenced_ids = set(re.findall(r"\bel\(['\"]([^'\"]+)['\"]\)", javascript))
    html_ids = set(re.findall(r"\bid=['\"]([^'\"]+)['\"]", html))

    assert referenced_ids <= html_ids


def test_feature_pages_have_matching_links_views_and_server_routes() -> None:
    from app.main import app

    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    visible_html = _visible_html(html)
    page_names = {
        "overview",
        "results",
        "two-digit",
        "fortune-two-digit",
        "one-digit",
        "backtest",
    }
    link_pages = set(re.findall(r'data-page-link="([^"]+)"', visible_html))
    view_pages = set(re.findall(r'data-page-view="([^"]+)"', html))
    server_paths = {route.path for route in app.routes}

    assert link_pages == page_names - {"backtest"}
    assert view_pages == page_names
    assert {
        "/",
        "/ket-qua",
        "/du-doan-2-so",
        "/du-doan-n-1",
        "/du-doan-than-tai",
        "/du-doan-catboost-2-so",
        "/backtest",
    } <= server_paths
    assert "/api/model-comparison/rolling" in server_paths


def test_app_shell_has_button_navigation_and_versioned_assets() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    visible_html = _visible_html(html)

    assert 'class="app-brand"' in html
    assert len(re.findall(r'class="nav-icon(?:\s[^\"]*)?"', visible_html)) == 5
    assert visible_html.count('class="nav-label"') == 5
    assert '/static/styles.css?v=' in html
    assert '/static/app.js?v=' in html
    assert visible_html.count('class="nav-logo') == 4
    assert 'class="nav-icon n1-nav-icon"' in visible_html


def test_two_digit_form_always_uses_automatic_prediction_date() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    two_digit_handler = javascript.split("el('prediction-form')", 1)[1].split(
        "el('catboost-prediction-form')", 1
    )[0]

    assert 'id="prediction-date"' not in html
    assert "el('prediction-date')" not in javascript
    assert "payload.prediction_date" not in two_digit_handler
    assert "Ngày dự đoán được chọn tự động" in html


def test_catboost_form_always_uses_automatic_prediction_date() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    one_digit_handler = javascript.split("el('catboost-prediction-form')", 1)[1].split(
        "el('backtest-form')", 1
    )[0]

    assert 'id="catboost-prediction-date"' not in html
    assert "el('catboost-prediction-date')" not in javascript
    assert "payload.prediction_date" not in one_digit_handler
    assert "Ngày được chọn tự động" in html
    assert "/api/catboost-predictions/generate" in javascript


def test_fortune_page_uses_logistic_api_and_automatic_date() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'data-page-link="fortune-two-digit"' in html
    assert 'data-page-view="fortune-two-digit"' in html
    assert 'id="fortune-selected-count"' in html
    assert '/api/logistic-predictions/generate' in javascript
    assert '/api/results/recent-last-two?days=${days}' in javascript
    assert '/api/results/recent?days=${days}' not in javascript
    assert "getFortuneExcludedRecentSet()" in javascript
    assert "đã loại ${removedSelectedCount} số vừa ra" in javascript
    assert 'id="fortune-excluded-recent-chips"' in html
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
    assert '/img/travel.png' in html
    assert 'class="page-sticker sticker-fortune' in html
    assert '/api/model-comparison/rolling' in javascript


def test_catboost_page_has_structured_dashboard_and_cartoon_theme() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert 'class="catboost-workbench-grid"' in html
    assert 'class="catboost-grid-frame"' in html
    assert 'class="catboost-report-grid"' in html
    assert "chuỗi 2.000 kỳ trước" in html
    assert "<strong>2.000</strong> kỳ làm đặc trưng" in html
    assert 'class="catboost-legend"' in html
    assert 'id="catboost-comparison-cards"' in html
    assert 'id="catboost-prediction-history"' in html
    assert "/img/catboost-cat-mouse-hero.png" in css
    assert ".catboost-card-titlebar" in css
    assert ".catboost-number.selected.top-ten" in css
    assert "html[data-theme=\"dark\"] .catboost-card" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "Được chọn (${selected.size})" in javascript
    assert "Bị loại (${100 - selected.size})" in javascript


def test_vercel_cron_uses_get_compatible_reconciliation_endpoint() -> None:
    from app.main import app

    cron_route = next(route for route in app.routes if route.path == "/api/auto-daily")
    config = json.loads((STATIC_DIR.parents[1] / "vercel.json").read_text("utf-8"))

    assert {"GET", "POST"} <= cron_route.methods
    assert len(config["crons"]) == 4
    assert {job["path"] for job in config["crons"]} == {"/api/auto-daily"}
    assert config["crons"][0]["schedule"] == "0 9 * * *"


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
