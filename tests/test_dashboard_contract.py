import re
from pathlib import Path


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
    page_names = {"overview", "results", "two-digit", "one-digit", "backtest"}
    link_pages = set(re.findall(r'data-page-link="([^"]+)"', html))
    view_pages = set(re.findall(r'data-page-view="([^"]+)"', html))
    server_paths = {route.path for route in app.routes}

    assert link_pages == page_names
    assert view_pages == page_names
    assert {"/", "/ket-qua", "/du-doan-2-so", "/du-doan-1-so", "/backtest"} <= server_paths


def test_app_shell_has_button_navigation_and_versioned_assets() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'class="app-brand"' in html
    assert html.count('class="nav-icon"') == 5
    assert html.count('class="nav-label"') == 5
    assert '/static/styles.css?v=' in html
    assert '/static/app.js?v=' in html


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
