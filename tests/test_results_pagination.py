from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as app_main


def client_with_results(monkeypatch):
    rows = [{"draw_date": f"2026-10-{day:02d}", "special_prize": "00100"} for day in range(1, 21)]
    queries = []

    class Cursor(list):
        def sort(self, key, direction):
            return Cursor(sorted(self, key=lambda row: row[key], reverse=direction < 0))

        def limit(self, count):
            return self[:count]

    def find(query):
        queries.append(query)
        before = query.get("draw_date", {}).get("$lt")
        return Cursor(row for row in rows if not before or row["draw_date"] < before)

    monkeypatch.setattr(app_main, "_db", lambda request: SimpleNamespace(draw_results=SimpleNamespace(find=find)))
    return TestClient(app_main.app), rows, queries


def test_results_cursor_is_exclusive_and_new_draws_do_not_shift_older_pages(monkeypatch):
    client, rows, queries = client_with_results(monkeypatch)
    first = client.get("/api/results", params={"limit": 7}).json()
    assert len(first) == 7
    assert first[0]["draw_date"] == "2026-10-20"
    cursor = first[5]["draw_date"]
    rows.append({"draw_date": "2026-10-21", "special_prize": "12345"})
    older = client.get("/api/results", params={"limit": 7, "before": cursor}).json()
    assert older[0]["draw_date"] == "2026-10-14"
    assert older[5]["draw_date"] == "2026-10-09"
    assert not {row["draw_date"] for row in first[:6]} & {row["draw_date"] for row in older[:6]}
    assert queries[-1] == {"draw_date": {"$lt": "2026-10-15"}}


def test_results_cursor_handles_end_and_preserves_default_query(monkeypatch):
    client, _, queries = client_with_results(monkeypatch)
    assert len(client.get("/api/results").json()) == 20
    assert queries[-1] == {}
    assert client.get("/api/results?limit=7&before=2026-10-01").json() == []


def test_results_cursor_rejects_invalid_dates_before_reading_database(monkeypatch):
    client, _, queries = client_with_results(monkeypatch)
    for value in ("invalid", "2026-02-30", "2026-13-01"):
        assert client.get("/api/results", params={"before": value}).status_code == 422
    assert not queries


def test_model_outcomes_are_opt_in_and_use_configured_selection_count(monkeypatch):
    client, _, _ = client_with_results(monkeypatch)
    calls = []

    def attach(db, draws, count):
        calls.append((draws, count))
        return [{**draw, "model_selected_count": count, "model_outcomes": {"A": {"status": "hit"}}}
                for draw in draws]

    monkeypatch.setattr(app_main, "attach_result_model_outcomes", attach)
    assert "model_outcomes" not in client.get("/api/results?limit=6").json()[0]
    assert not calls
    response = client.get("/api/results?limit=6&include_models=true&before=2026-10-15")
    assert response.status_code == 200
    assert len(response.json()) == 6
    assert response.json()[0]["draw_date"] == "2026-10-14"
    assert response.json()[0]["model_outcomes"]["A"]["status"] == "hit"
    assert calls[0][1] == app_main.settings.auto_prediction_count
