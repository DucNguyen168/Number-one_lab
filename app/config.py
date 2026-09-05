from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    mongodb_uri: str
    mongodb_database: str
    timezone_name: str
    kqxs_base_url: str
    xosodaiphat_base_url: str
    http_timeout_seconds: int
    http_connect_timeout_seconds: int
    http_retries: int
    backfill_workers: int
    skip_completed_history: bool
    enable_scheduler: bool
    sync_on_startup: bool
    scheduler_retry_attempts: int
    scheduler_retry_delay_seconds: int
    auto_prediction: bool
    auto_prediction_count: int
    prediction_time: str
    result_sync_times: tuple[str, ...]
    ai_configured: bool

    @classmethod
    def from_env(cls) -> "Settings":
        selected_count = _as_int(os.getenv("AUTO_PREDICTION_COUNT"), 65)
        if not 60 <= selected_count <= 80:
            selected_count = 65
        sync_times = tuple(
            item.strip()
            for item in os.getenv("RESULT_SYNC_TIMES", "18:35,18:50,19:10").split(",")
            if item.strip()
        )
        return cls(
            mongodb_uri=os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "mongodb://127.0.0.1:27017",
            mongodb_database=os.getenv("MONGODB_DATABASE", "xsmb_research"),
            timezone_name=os.getenv("APP_TIMEZONE", "Asia/Ho_Chi_Minh"),
            kqxs_base_url=os.getenv("KQXS_BASE_URL", "https://www.kqxs.vn").rstrip("/"),
            xosodaiphat_base_url=os.getenv(
                "XOSODAIPHAT_BASE_URL", "https://xosodaiphat.com"
            ).rstrip("/"),
            http_timeout_seconds=max(
                5, _as_int(os.getenv("HTTP_TIMEOUT_SECONDS"), 12)
            ),
            http_connect_timeout_seconds=max(
                2, _as_int(os.getenv("HTTP_CONNECT_TIMEOUT_SECONDS"), 5)
            ),
            http_retries=max(0, min(3, _as_int(os.getenv("HTTP_RETRIES"), 1))),
            backfill_workers=max(
                1, min(6, _as_int(os.getenv("BACKFILL_WORKERS"), 4))
            ),
            skip_completed_history=_as_bool(
                os.getenv("SKIP_COMPLETED_HISTORY"), True
            ),
            enable_scheduler=_as_bool(os.getenv("ENABLE_SCHEDULER"), True),
            sync_on_startup=_as_bool(os.getenv("SYNC_ON_STARTUP"), True),
            scheduler_retry_attempts=max(
                1, min(5, _as_int(os.getenv("SCHEDULER_RETRY_ATTEMPTS"), 3))
            ),
            scheduler_retry_delay_seconds=max(
                1, min(60, _as_int(os.getenv("SCHEDULER_RETRY_DELAY_SECONDS"), 5))
            ),
            auto_prediction=_as_bool(os.getenv("AUTO_PREDICTION"), True),
            auto_prediction_count=selected_count,
            prediction_time=os.getenv("PREDICTION_TIME", "17:30"),
            result_sync_times=sync_times,
            ai_configured=bool(os.getenv("AI_API_KEY", "").strip()),
        )

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def local_now(self) -> datetime:
        return datetime.now(self.timezone)

    def local_today(self) -> date:
        return self.local_now().date()


settings = Settings.from_env()
