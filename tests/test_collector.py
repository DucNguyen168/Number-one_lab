import hashlib
from datetime import date, datetime, timezone
from threading import Event
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.services.collector import (
    CollectedDraw,
    KqxsCollector,
    parse_kqxs_recent_html,
    parse_xosodaiphat_year_html,
    parse_year_html,
)


FIXTURE = Path(__file__).parent / "fixtures" / "kqxs_year_sample.html"


def test_parse_year_html_preserves_leading_zeroes() -> None:
    results = parse_year_html(FIXTURE.read_text(encoding="utf-8"), 2025)

    assert [(item.draw_date, item.special_prize, item.last_two) for item in results] == [
        ("2025-01-01", "00000", "00"),
        ("2025-01-02", "98706", "06"),
        ("2025-02-01", "12345", "45"),
    ]


def test_parse_year_html_rejects_non_five_digit_result() -> None:
    html = FIXTURE.read_text(encoding="utf-8").replace("12345", "12A45")

    with pytest.raises(ValueError, match="Invalid special prize"):
        parse_year_html(html, 2025)


def test_parse_year_html_rejects_duplicate_dates() -> None:
    html = FIXTURE.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate draw dates"):
        parse_year_html(html + html, 2025)


def test_parse_xosodaiphat_selects_exact_year_and_preserves_zeroes() -> None:
    empty_cells = "<td>" * 9
    html = f"""
    <table><tr><th>2024<th>Tháng 01</tr><tr><th>Ngày 01<td>99999</tr></table>
    <table class="table-tkgdb">
      <tr><th>2025<th>Tháng 01<th>Tháng 02<th>Tháng 03
          <th>Tháng 04<th>Tháng 05<th>Tháng 06<th>Tháng 07
          <th>Tháng 08<th>Tháng 09<th>Tháng 10<th>Tháng 11<th>Tháng 12
      <tr><th>Ngày 01
          <td><div class=fontDB>000<span>00</span></div>
          <td>TẾT
          <td><div class=fontDB>123<span>45</span></div>
          {empty_cells}
    </table>
    """

    results = parse_xosodaiphat_year_html(html, 2025)

    assert [(item.draw_date, item.special_prize) for item in results] == [
        ("2025-01-01", "00000"),
        ("2025-03-01", "12345"),
    ]


def test_parse_kqxs_recent_uses_caption_date_and_special_prize_only() -> None:
    html = """
    <table class="table-fixed table-result-lottery">
      <caption>Kết quả Xổ số Miền Bắc Thứ Hai 17-08-2026</caption>
      <tr><td>Đặc biệt</td><td><span data-value="01939" data-prize="1">01939</span></td></tr>
      <tr><td>Giải nhất</td><td><span data-value="77200" data-prize="2">77200</span></td></tr>
    </table>
    <table class="table-result-lottery">
      <caption>Kết quả Xổ số Miền Bắc 31-12-2025</caption>
      <tr><td>Đặc biệt</td><td><span data-value="12345" data-prize="1">12345</span></td></tr>
    </table>
    """

    results = parse_kqxs_recent_html(html, 2026)

    assert [(item.draw_date, item.special_prize, item.last_two) for item in results] == [
        ("2026-08-17", "01939", "39")
    ]


class _CollectorRuns:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []

    def insert_one(self, document: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(inserted_id="run-1")

    def update_one(
        self, query: dict[str, object], update: dict[str, object]
    ) -> None:
        self.updates.append(update)


class _DrawResults:
    def __init__(self, existing: list[dict[str, object]] | None = None) -> None:
        self.existing = existing or []
        self.find_calls: list[tuple[dict[str, object], dict[str, object]]] = []
        self.bulk_calls: list[tuple[list[object], bool]] = []

    def find(
        self,
        query: dict[str, object],
        projection: dict[str, object],
    ) -> list[dict[str, object]]:
        self.find_calls.append((query, projection))
        return self.existing

    def bulk_write(self, operations: list[object], ordered: bool) -> None:
        self.bulk_calls.append((operations, ordered))


def test_sync_year_uses_fallback_when_one_source_times_out(monkeypatch) -> None:
    collector_runs = _CollectorRuns()
    config = SimpleNamespace(local_today=lambda: SimpleNamespace(year=2026))
    collector = KqxsCollector(
        SimpleNamespace(collector_runs=collector_runs),
        config,
    )

    def timeout() -> tuple[str, str]:
        raise httpx.ConnectTimeout("KQXS handshake timed out")

    xosodaiphat_html = """
    <table><tr><th>2025<th>Tháng 01<th>Tháng 02<th>Tháng 03
      <th>Tháng 04<th>Tháng 05<th>Tháng 06<th>Tháng 07
      <th>Tháng 08<th>Tháng 09<th>Tháng 10<th>Tháng 11<th>Tháng 12
      <tr><th>Ngày 01<td>12345<td><td><td><td><td><td><td><td><td><td><td>
    </table>
    """
    monkeypatch.setattr(collector, "fetch_year", lambda year: timeout())
    monkeypatch.setattr(
        collector,
        "fetch_xosodaiphat_year",
        lambda year: (xosodaiphat_html, "https://xosodaiphat.test/2025"),
    )
    monkeypatch.setattr(
        collector,
        "_store_source_draws",
        lambda **kwargs: {"inserted": 1, "matched": 0, "conflicts": 0},
    )

    result = collector.sync_year(2025)

    assert result["status"] == "partial"
    assert result["fallback_used"] is True
    assert result["source_successes"] == 1
    assert result["source_failures"] == 1
    assert [source["status"] for source in result["sources"]] == [
        "failed",
        "completed",
    ]
    assert collector_runs.updates[-1]["$set"]["status"] == "partial"


def test_store_source_draws_reads_once_and_writes_one_batch() -> None:
    draw_results = _DrawResults()
    collector = KqxsCollector(SimpleNamespace(draw_results=draw_results), SimpleNamespace())
    fetched_at = datetime.now(timezone.utc)

    result = collector._store_source_draws(
        draws=[
            CollectedDraw("2026-09-01", "12345", "45"),
            CollectedDraw("2026-09-02", "00006", "06"),
        ],
        source_name="KQXS yearly",
        source_key="kqxs_year",
        source_url="https://example.test/results",
        page_checksum="page-checksum",
        fetched_at=fetched_at,
    )

    assert len(draw_results.find_calls) == 1
    assert len(draw_results.bulk_calls) == 1
    assert len(draw_results.bulk_calls[0][0]) == 2
    assert result == {
        "inserted": 2,
        "matched": 0,
        "conflicts": 0,
        "unchanged": 0,
        "write_operations": 2,
    }


def test_store_source_draws_does_not_rewrite_unchanged_snapshot() -> None:
    row_checksum = hashlib.sha256(b"2026-09-01|12345").hexdigest()
    draw_results = _DrawResults(
        [
            {
                "draw_date": "2026-09-01",
                "special_prize": "12345",
                "status": "observed",
                "sources": {
                    "kqxs_year": {"record_checksum": row_checksum},
                },
            }
        ]
    )
    collector = KqxsCollector(SimpleNamespace(draw_results=draw_results), SimpleNamespace())

    result = collector._store_source_draws(
        draws=[CollectedDraw("2026-09-01", "12345", "45")],
        source_name="KQXS yearly",
        source_key="kqxs_year",
        source_url="https://example.test/results",
        page_checksum="page-checksum",
        fetched_at=datetime.now(timezone.utc),
    )

    assert draw_results.bulk_calls == []
    assert result == {
        "inserted": 0,
        "matched": 1,
        "conflicts": 0,
        "unchanged": 1,
        "write_operations": 0,
    }


def test_sync_range_skips_completed_history_unless_forced(monkeypatch) -> None:
    config = SimpleNamespace(
        local_today=lambda: SimpleNamespace(year=2026),
        skip_completed_history=True,
        backfill_workers=2,
    )
    collector = KqxsCollector(SimpleNamespace(), config)
    called: list[int] = []

    monkeypatch.setattr(
        collector,
        "_completed_historical_years",
        lambda years: {2019, 2020},
    )

    def sync_year(year: int) -> dict[str, object]:
        called.append(year)
        return {"year": year, "status": "completed"}

    monkeypatch.setattr(collector, "sync_year", sync_year)

    incremental = collector.sync_range(2019, 2021)

    assert [item["status"] for item in incremental] == [
        "skipped",
        "skipped",
        "completed",
    ]
    assert called == [2021]

    called.clear()
    forced = collector.sync_range(2019, 2021, force=True)

    assert [item["status"] for item in forced] == [
        "completed",
        "completed",
        "completed",
    ]
    assert sorted(called) == [2019, 2020, 2021]


def test_latest_sync_stores_fast_source_before_slow_source_and_only_target(monkeypatch):
    stored = Event()
    draws = [CollectedDraw("2026-10-11", "11111", "11"),
             CollectedDraw("2026-10-12", "00123", "23")]
    collector = KqxsCollector(SimpleNamespace(
        collector_runs=_CollectorRuns(),
        draw_results=SimpleNamespace(find_one=lambda *args: None),
    ), SimpleNamespace())
    writes = []

    def slow_fetch():
        assert stored.wait(2), "Fast source was blocked by the slower source"
        raise httpx.ConnectTimeout("slow source")

    monkeypatch.setattr(collector, "_source_specs", lambda year: [
        ("fast", "fast", lambda: ("html", "https://fast.test"), lambda *args: draws),
        ("slow", "slow", slow_fetch, lambda *args: draws),
    ])

    def store(**kwargs):
        writes.extend(kwargs["draws"])
        stored.set()
        return {"inserted": len(kwargs["draws"])}

    monkeypatch.setattr(collector, "_store_source_draws", store)
    result = collector.sync_latest(date(2026, 10, 12))
    assert writes == [draws[1]]
    assert result["status"] == "partial"
    assert result["records_received"] == 1
    assert result["sources"][1]["error_type"] == "ConnectTimeout"


def test_latest_sync_skips_sources_if_valid_result_already_exists(monkeypatch):
    queries = []

    def find(query, projection):
        queries.append(query)
        return {"_id": "today"}

    collector = KqxsCollector(SimpleNamespace(
        draw_results=SimpleNamespace(find_one=find),
    ), SimpleNamespace())
    result = collector.sync_latest(date(2026, 10, 12))
    assert result["status"] == "already_available"
    assert queries == [{"draw_date": "2026-10-12", "status": {"$ne": "conflict"}}]
