from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.services.collector import (
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
