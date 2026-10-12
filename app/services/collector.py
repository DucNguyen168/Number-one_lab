from __future__ import annotations

import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from time import perf_counter
from typing import Any, Callable

import httpx
from pymongo import UpdateOne
from pymongo.database import Database

from app.config import Settings


FIVE_DIGITS = re.compile(r"^\d{5}$")


class CollectorSourcesUnavailable(RuntimeError):
    """Raised only when every configured source fails for a requested year."""


@dataclass(frozen=True, slots=True)
class CollectedDraw:
    draw_date: str
    special_prize: str
    last_two: str


class _YearTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[dict[str, str | None]]] = []
        self._row: list[dict[str, str | None]] | None = None
        self._cell: dict[str, str | None] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = {"text": "", "value": None}
        elif self._cell is not None and attributes.get("data-value") is not None:
            self._cell["value"] = attributes["data-value"]

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"] = f"{self._cell['text'] or ''}{data}"

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def parse_year_html(html: str, year: int) -> list[CollectedDraw]:
    parser = _YearTableParser()
    parser.feed(html)
    results: list[CollectedDraw] = []

    for row in parser.rows:
        if len(row) < 13:
            continue
        try:
            day = int((row[0]["text"] or "").strip())
        except ValueError:
            continue

        for month, cell in enumerate(row[1:13], start=1):
            value = cell["value"]
            if not value:
                continue
            if not FIVE_DIGITS.fullmatch(value):
                raise ValueError(
                    f"Invalid special prize for {year}-{month:02d}-{day:02d}: {value!r}"
                )
            try:
                draw_date = date(year, month, day)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid draw date in source: {year}-{month:02d}-{day:02d}"
                ) from exc
            results.append(
                CollectedDraw(
                    draw_date=draw_date.isoformat(),
                    special_prize=value,
                    last_two=value[-2:],
                )
            )

    unique_dates = {item.draw_date for item in results}
    if len(unique_dates) != len(results):
        raise ValueError(f"Duplicate draw dates detected for year {year}")
    return sorted(results, key=lambda item: item.draw_date)


class _TableMatrixParser(HTMLParser):
    """Collect table cell text, including HTML that omits optional closing tags."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def _close_cell(self) -> None:
        if self._cell_parts is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell_parts).split()))
        self._cell_parts = None

    def _close_row(self) -> None:
        self._close_cell()
        if self._row is not None and self._table is not None and self._row:
            self._table.append(self._row)
        self._row = None

    def _close_table(self) -> None:
        self._close_row()
        if self._table:
            self.tables.append(self._table)
        self._table = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._close_table()
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._close_row()
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._close_cell()
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"}:
            self._close_cell()
        elif tag == "tr":
            self._close_row()
        elif tag == "table":
            self._close_table()

    def close(self) -> None:
        super().close()
        self._close_table()


def parse_xosodaiphat_year_html(html: str, year: int) -> list[CollectedDraw]:
    parser = _TableMatrixParser()
    parser.feed(html)
    parser.close()
    target_table = next(
        (
            table
            for table in parser.tables
            if table and table[0] and table[0][0].strip() == str(year)
        ),
        None,
    )
    if target_table is None:
        raise ValueError(f"xosodaiphat.com did not return the table for year {year}")

    results: list[CollectedDraw] = []
    for row in target_table[1:]:
        if len(row) < 13:
            continue
        day_match = re.fullmatch(r"Ngày\s*(\d{1,2})", row[0].strip(), re.IGNORECASE)
        if day_match is None:
            continue
        day = int(day_match.group(1))
        for month, raw_cell in enumerate(row[1:13], start=1):
            value = "".join(raw_cell.split())
            if not value or value.upper() in {"TẾT", "TET"}:
                continue
            if not FIVE_DIGITS.fullmatch(value):
                raise ValueError(
                    f"Invalid xosodaiphat special prize for "
                    f"{year}-{month:02d}-{day:02d}: {value!r}"
                )
            try:
                draw_date = date(year, month, day)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid xosodaiphat draw date: {year}-{month:02d}-{day:02d}"
                ) from exc
            results.append(
                CollectedDraw(
                    draw_date=draw_date.isoformat(),
                    special_prize=value,
                    last_two=value[-2:],
                )
            )

    unique_dates = {item.draw_date for item in results}
    if len(unique_dates) != len(results):
        raise ValueError(f"Duplicate xosodaiphat draw dates detected for year {year}")
    return sorted(results, key=lambda item: item.draw_date)


class _KqxsRecentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[CollectedDraw] = []
        self._in_table = False
        self._in_caption = False
        self._caption_parts: list[str] = []
        self._special_prize: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "table" and "table-result-lottery" in classes:
            self._in_table = True
            self._caption_parts = []
            self._special_prize = None
        elif self._in_table and tag == "caption":
            self._in_caption = True
        elif (
            self._in_table
            and tag == "span"
            and attributes.get("data-prize") == "1"
            and FIVE_DIGITS.fullmatch(attributes.get("data-value") or "")
        ):
            self._special_prize = attributes["data-value"]

    def handle_data(self, data: str) -> None:
        if self._in_caption:
            self._caption_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "caption":
            self._in_caption = False
        elif tag == "table" and self._in_table:
            caption = " ".join("".join(self._caption_parts).split())
            date_match = re.search(r"(\d{2})-(\d{2})-(\d{4})", caption)
            if date_match and self._special_prize:
                day, month, year = map(int, date_match.groups())
                draw_date = date(year, month, day)
                self.results.append(
                    CollectedDraw(
                        draw_date=draw_date.isoformat(),
                        special_prize=self._special_prize,
                        last_two=self._special_prize[-2:],
                    )
                )
            self._in_table = False
            self._in_caption = False


def parse_kqxs_recent_html(html: str, year: int) -> list[CollectedDraw]:
    parser = _KqxsRecentParser()
    parser.feed(html)
    by_date: dict[str, CollectedDraw] = {}
    for item in parser.results:
        if not item.draw_date.startswith(f"{year}-"):
            continue
        existing = by_date.get(item.draw_date)
        if existing and existing.special_prize != item.special_prize:
            raise ValueError(f"Conflicting kqxs.vn recent result for {item.draw_date}")
        by_date[item.draw_date] = item
    return sorted(by_date.values(), key=lambda item: item.draw_date)


class KqxsCollector:
    source_name = "multi_source"
    _year_locks_guard = threading.Lock()
    _year_locks: dict[int, threading.Lock] = {}

    def __init__(self, db: Database, config: Settings) -> None:
        self.db = db
        self.config = config

    def _url(self) -> str:
        return f"{self.config.kqxs_base_url}/"

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
        }

    def _fetch_html(
        self, url: str, params: dict[str, str] | None = None
    ) -> tuple[str, str]:
        timeout = httpx.Timeout(
            self.config.http_timeout_seconds,
            connect=min(
                self.config.http_timeout_seconds,
                self.config.http_connect_timeout_seconds,
            ),
        )
        transport = httpx.HTTPTransport(retries=self.config.http_retries)
        with httpx.Client(
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
            headers=self._headers(),
        ) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "html" not in content_type:
                raise ValueError(
                    f"{response.url.host} returned unexpected content type {content_type!r}"
                )
            if not response.text.strip():
                raise ValueError(f"{response.url.host} returned an empty response")
            return response.text, str(response.url)

    @classmethod
    def _lock_for_year(cls, year: int) -> threading.Lock:
        with cls._year_locks_guard:
            return cls._year_locks.setdefault(year, threading.Lock())

    def fetch_year(self, year: int) -> tuple[str, str]:
        params = {
            "com": "lotterystatistic",
            "act": "specialbyyear",
            "ajax": "1",
            "view": "specialbyyearshort",
            "year": str(year),
            "lottery_id": "1",
        }
        return self._fetch_html(self._url(), params)

    def fetch_xosodaiphat_year(self, year: int) -> tuple[str, str]:
        url = (
            f"{self.config.xosodaiphat_base_url}"
            "/XSDPThongKeAjax/AjaxTKGiaiDBTheoNam"
        )
        return self._fetch_html(
            url, {"year": str(year), "lotteryId": "0"}
        )

    def fetch_kqxs_recent(self) -> tuple[str, str]:
        return self._fetch_html(f"{self.config.kqxs_base_url}/mien-bac")

    def _store_source_draws(
        self,
        *,
        draws: list[CollectedDraw],
        source_name: str,
        source_key: str,
        source_url: str,
        page_checksum: str,
        fetched_at: datetime,
    ) -> dict[str, int]:
        counters = {
            "inserted": 0,
            "matched": 0,
            "conflicts": 0,
            "unchanged": 0,
            "write_operations": 0,
        }
        if not draws:
            return counters

        draw_dates = [draw.draw_date for draw in draws]
        existing_by_date = {
            item["draw_date"]: item
            for item in self.db.draw_results.find(
                {"draw_date": {"$in": draw_dates}},
                {
                    "draw_date": 1,
                    "special_prize": 1,
                    "status": 1,
                    "sources": 1,
                    "conflicts": 1,
                },
            )
        }
        operations: list[UpdateOne] = []
        for draw in draws:
            row_checksum = hashlib.sha256(
                f"{draw.draw_date}|{draw.special_prize}".encode()
            ).hexdigest()
            existing = existing_by_date.get(draw.draw_date)
            source_snapshot = {
                "name": source_name,
                "url": source_url,
                "last_fetched_at": fetched_at,
                "page_checksum": page_checksum,
                "record_checksum": row_checksum,
            }
            if existing is None:
                document = {
                    "draw_date": draw.draw_date,
                    "special_prize": draw.special_prize,
                    "last_two": draw.last_two,
                    "status": "observed",
                    "sources": {source_key: source_snapshot},
                    "created_at": fetched_at,
                    "updated_at": fetched_at,
                }
                operations.append(
                    UpdateOne(
                        {"draw_date": draw.draw_date},
                        {"$setOnInsert": document},
                        upsert=True,
                    )
                )
                existing_by_date[draw.draw_date] = document
                counters["inserted"] += 1
                continue

            if existing.get("special_prize") == draw.special_prize:
                counters["matched"] += 1
                existing_snapshot = (existing.get("sources") or {}).get(source_key)
                if (
                    existing_snapshot
                    and existing_snapshot.get("record_checksum") == row_checksum
                ):
                    counters["unchanged"] += 1
                    continue
                operations.append(
                    UpdateOne(
                        {"draw_date": draw.draw_date},
                        {
                            "$set": {
                                f"sources.{source_key}": source_snapshot,
                                "updated_at": fetched_at,
                            }
                        },
                    )
                )
                existing.setdefault("sources", {})[source_key] = source_snapshot
                continue

            conflict = {
                "source": source_name,
                "observed_special_prize": draw.special_prize,
                "observed_at": fetched_at,
                "record_checksum": row_checksum,
            }
            already_recorded = any(
                item.get("source") == source_name
                and item.get("observed_special_prize") == draw.special_prize
                for item in existing.get("conflicts", [])
            )
            existing_snapshot = (existing.get("sources") or {}).get(source_key)
            if (
                already_recorded
                and existing.get("status") == "conflict"
                and existing_snapshot
                and existing_snapshot.get("record_checksum") == row_checksum
            ):
                counters["conflicts"] += 1
                counters["unchanged"] += 1
                continue
            update: dict[str, Any] = {
                "$set": {
                    "status": "conflict",
                    "updated_at": fetched_at,
                    f"sources.{source_key}": source_snapshot,
                }
            }
            if not already_recorded:
                update["$push"] = {"conflicts": conflict}
                existing.setdefault("conflicts", []).append(conflict)
            operations.append(
                UpdateOne({"draw_date": draw.draw_date}, update)
            )
            existing["status"] = "conflict"
            existing.setdefault("sources", {})[source_key] = source_snapshot
            counters["conflicts"] += 1

        if operations:
            self.db.draw_results.bulk_write(operations, ordered=True)
        counters["write_operations"] = len(operations)
        return counters

    def _source_specs(
        self, year: int
    ) -> list[
        tuple[
            str,
            str,
            Callable[[], tuple[str, str]],
            Callable[[str, int], list[CollectedDraw]],
        ]
    ]:
        specs = [
            (
                "KQXS yearly",
                "kqxs_year",
                lambda: self.fetch_year(year),
                parse_year_html,
            ),
            (
                "Xổ Số Đại Phát yearly",
                "xosodaiphat_year",
                lambda: self.fetch_xosodaiphat_year(year),
                parse_xosodaiphat_year_html,
            ),
        ]
        if year == self.config.local_today().year:
            specs.append(
                (
                    "KQXS recent",
                    "kqxs_recent",
                    self.fetch_kqxs_recent,
                    parse_kqxs_recent_html,
                )
            )
        return specs

    @staticmethod
    def _collect_source(
        index: int,
        year: int,
        spec: tuple[
            str,
            str,
            Callable[[], tuple[str, str]],
            Callable[[str, int], list[CollectedDraw]],
        ],
    ) -> tuple[int, dict[str, Any] | None, dict[str, Any]]:
        source_name, source_key, fetcher, parser = spec
        source_started_at = datetime.now(timezone.utc)
        timer = perf_counter()
        try:
            html, source_url = fetcher()
            page_checksum = hashlib.sha256(html.encode("utf-8")).hexdigest()
            draws = parser(html, year)
            if not draws:
                raise ValueError(
                    f"{source_name} returned no draw results for year {year}"
                )
            payload = {
                "name": source_name,
                "key": source_key,
                "url": source_url,
                "checksum": page_checksum,
                "draws": draws,
            }
            summary = {
                "name": source_name,
                "key": source_key,
                "status": "completed",
                "source_url": source_url,
                "records_received": len(draws),
                "page_checksum": page_checksum,
                "duration_ms": round((perf_counter() - timer) * 1_000),
                "started_at": source_started_at,
                "finished_at": datetime.now(timezone.utc),
            }
            return index, payload, summary
        except Exception as exc:
            summary = {
                "name": source_name,
                "key": source_key,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "duration_ms": round((perf_counter() - timer) * 1_000),
                "started_at": source_started_at,
                "finished_at": datetime.now(timezone.utc),
            }
            return index, None, summary

    def sync_year(self, year: int) -> dict[str, Any]:
        with self._lock_for_year(year):
            return self._sync_year_locked(year)

    def sync_latest(self, target: date) -> dict[str, Any]:
        """Poll only the requested draw; persist each source as soon as it returns."""
        with self._lock_for_year(target.year):
            if self.db.draw_results.find_one(
                {"draw_date": target.isoformat(), "status": {"$ne": "conflict"}},
                {"_id": 1},
            ):
                return {"draw_date": target.isoformat(), "status": "already_available"}
            return self._sync_year_locked(target.year, target=target)

    def _sync_year_locked(
        self, year: int, *, target: date | None = None
    ) -> dict[str, Any]:
        timer = perf_counter()
        started_at = datetime.now(timezone.utc)
        run = {
            "type": "latest_sync" if target else "year_sync",
            "draw_date": target.isoformat() if target else None,
            "year": year,
            "source": self.source_name,
            "started_at": started_at,
            "status": "running",
        }
        run_id = self.db.collector_runs.insert_one(run).inserted_id
        source_summaries: list[dict[str, Any]] = []
        counters = {
            "inserted": 0,
            "matched": 0,
            "conflicts": 0,
            "unchanged": 0,
            "write_operations": 0,
        }
        write_seconds = 0.0

        def store_payload(payload: dict[str, Any]) -> None:
            nonlocal write_seconds
            write_started = perf_counter()
            source_counters = self._store_source_draws(
                draws=payload["draws"],
                source_name=payload["name"],
                source_key=payload["key"],
                source_url=payload["url"],
                page_checksum=payload["checksum"],
                fetched_at=datetime.now(timezone.utc),
            )
            for key in counters:
                counters[key] += source_counters.get(key, 0)
            write_seconds += perf_counter() - write_started

        try:
            source_specs = self._source_specs(year)
            ordered_results: list[
                tuple[dict[str, Any] | None, dict[str, Any]] | None
            ] = [None] * len(source_specs)
            with ThreadPoolExecutor(
                max_workers=len(source_specs),
                thread_name_prefix=f"xsmb-source-{year}",
            ) as executor:
                futures = [
                    executor.submit(self._collect_source, index, year, spec)
                    for index, spec in enumerate(source_specs)
                ]
                for future in as_completed(futures):
                    index, payload, summary = future.result()
                    if target is not None and payload is not None:
                        payload["draws"] = [
                            draw for draw in payload["draws"]
                            if draw.draw_date == target.isoformat()
                        ]
                        # A slow or failed source must not delay a faster source's write.
                        store_payload(payload)
                    ordered_results[index] = (payload, summary)

            payloads: list[dict[str, Any]] = []
            for result in ordered_results:
                if result is None:
                    continue
                payload, summary = result
                source_summaries.append(summary)
                if payload is not None:
                    payloads.append(payload)

            if not payloads:
                errors = "; ".join(
                    f"{item['name']}: {item.get('error', 'unknown error')}"
                    for item in source_summaries
                )
                raise CollectorSourcesUnavailable(
                    f"All result sources failed for {year}. {errors}"
                )

            fetch_seconds = perf_counter() - timer - write_seconds
            unique_dates: set[str] = set()
            for payload in payloads:
                unique_dates.update(draw.draw_date for draw in payload["draws"])
                if target is None:
                    store_payload(payload)

            finished_at = datetime.now(timezone.utc)
            source_failures = sum(
                item["status"] == "failed" for item in source_summaries
            )
            checksum_material = "|".join(
                sorted(payload["checksum"] for payload in payloads)
            )
            summary = {
                "year": year,
                "source": self.source_name,
                "records_received": len(unique_dates),
                "source_records_received": sum(
                    len(payload["draws"]) for payload in payloads
                ),
                **counters,
                "source_successes": len(payloads),
                "source_failures": source_failures,
                "fallback_used": source_failures > 0,
                "sources": source_summaries,
                "fetch_duration_ms": round(fetch_seconds * 1_000),
                "write_duration_ms": round(write_seconds * 1_000),
                "duration_ms": round((perf_counter() - timer) * 1_000),
                "page_checksum": hashlib.sha256(
                    checksum_material.encode("utf-8")
                ).hexdigest(),
                "started_at": started_at,
                "finished_at": finished_at,
                "status": "partial" if source_failures else "completed",
            }
            self.db.collector_runs.update_one({"_id": run_id}, {"$set": summary})
            return summary
        except Exception as exc:
            self.db.collector_runs.update_one(
                {"_id": run_id},
                {
                    "$set": {
                        "status": "failed",
                        "error": str(exc),
                        "sources": source_summaries,
                        "finished_at": datetime.now(timezone.utc),
                    }
                },
            )
            raise

    def _completed_historical_years(self, years: list[int]) -> set[int]:
        if not years or not self.config.skip_completed_history:
            return set()
        documents = self.db.collector_runs.find(
            {
                "type": "year_sync",
                "source": self.source_name,
                "year": {"$in": years},
                "status": "completed",
            },
            {"_id": 0, "year": 1},
        )
        return {
            int(document["year"])
            for document in documents
            if isinstance(document.get("year"), int)
        }

    @staticmethod
    def _skipped_year(year: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "year": year,
            "source": "cache",
            "records_received": 0,
            "source_records_received": 0,
            "inserted": 0,
            "matched": 0,
            "conflicts": 0,
            "unchanged": 0,
            "write_operations": 0,
            "source_successes": 0,
            "source_failures": 0,
            "fallback_used": False,
            "sources": [],
            "started_at": now,
            "finished_at": now,
            "duration_ms": 0,
            "status": "skipped",
            "skip_reason": "historical year already synchronized",
        }

    def _failed_year(self, year: int, exc: Exception) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "year": year,
            "source": "multi_source",
            "records_received": 0,
            "source_records_received": 0,
            "inserted": 0,
            "matched": 0,
            "conflicts": 0,
            "unchanged": 0,
            "write_operations": 0,
            "source_successes": 0,
            "source_failures": len(self._source_specs(year)),
            "fallback_used": True,
            "sources": [],
            "started_at": now,
            "finished_at": now,
            "duration_ms": 0,
            "status": "failed",
            "error": str(exc),
        }

    def sync_range(
        self, start_year: int, end_year: int, *, force: bool = False
    ) -> list[dict[str, Any]]:
        if start_year > end_year:
            raise ValueError("start_year must be before or equal to end_year")
        years = list(range(start_year, end_year + 1))
        current_year = self.config.local_today().year
        historical_years = [year for year in years if year < current_year]
        completed = (
            set()
            if force
            else self._completed_historical_years(historical_years)
        )
        results: dict[int, dict[str, Any]] = {
            year: self._skipped_year(year) for year in completed
        }
        pending = [year for year in years if year not in completed]

        if pending:
            with ThreadPoolExecutor(
                max_workers=min(self.config.backfill_workers, len(pending)),
                thread_name_prefix="xsmb-backfill",
            ) as executor:
                futures = {
                    executor.submit(self.sync_year, year): year for year in pending
                }
                for future in as_completed(futures):
                    year = futures[future]
                    try:
                        results[year] = future.result()
                    except Exception as exc:
                        results[year] = self._failed_year(year, exc)

        ordered = [results[year] for year in years]
        if ordered and all(item["status"] == "failed" for item in ordered):
            errors = "; ".join(
                f"{item['year']}: {item.get('error', 'unknown error')}"
                for item in ordered
            )
            raise CollectorSourcesUnavailable(
                f"All requested years failed. {errors}"
            )
        return ordered
