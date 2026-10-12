from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import Any

from pymongo.database import Database

from app.config import Settings
from app.services.catboost_prediction import create_prediction as create_catboost_prediction
from app.services.collector import KqxsCollector
from app.services.evaluation import (
    evaluate_pending_digit_predictions,
    evaluate_pending_predictions,
)
from app.services.logistic_prediction import create_prediction as create_logistic_prediction
from app.services.prediction import create_prediction


logger = logging.getLogger(__name__)


class DailyScheduler:
    def __init__(self, db: Database, config: Settings) -> None:
        self.db = db
        self.config = config
        self.collector = KqxsCollector(db, config)
        self.task: asyncio.Task[None] | None = None
        self._completed_tokens: set[str] = set()
        self._next_result_poll_at: datetime | None = None
        self._result_ready_date: date | None = None

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run(), name="xsmb-daily-scheduler")

    async def stop(self) -> None:
        if self.task is None:
            return
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.task = None

    async def _sync_and_evaluate(
        self, target: date, *, latest_only: bool = False
    ) -> dict[str, Any]:
        sync_result = await asyncio.to_thread(
            self.collector.sync_latest if latest_only else self.collector.sync_year,
            target if latest_only else target.year,
        )
        evaluation = await asyncio.to_thread(evaluate_pending_predictions, self.db)
        digit_evaluation = await asyncio.to_thread(
            evaluate_pending_digit_predictions, self.db
        )
        next_prediction: dict[str, Any] | None = None
        result_exists = await asyncio.to_thread(
            self.db.draw_results.find_one,
            {"draw_date": target.isoformat(), "status": {"$ne": "conflict"}},
            {"_id": 1},
        )
        if self.config.auto_prediction and result_exists is not None:
            next_prediction = await self._generate_prediction(
                target + timedelta(days=1)
            )
        return {
            "sync": sync_result,
            "evaluation": evaluation,
            "digit_evaluation": digit_evaluation,
            "next_prediction": next_prediction,
            "result_available": result_exists is not None,
        }

    async def _generate_prediction(self, target: date) -> dict[str, Any]:
        _, two_digit_created = await asyncio.to_thread(
            create_prediction, self.db, target, self.config.auto_prediction_count
        )
        logistic_created = False
        logistic_error: str | None = None
        try:
            _, logistic_created = await asyncio.to_thread(
                create_logistic_prediction,
                self.db,
                target,
                self.config.auto_prediction_count,
            )
        except (ValueError, RuntimeError) as exc:
            logistic_error = str(exc)
        catboost_created = False
        catboost_error: str | None = None
        try:
            _, catboost_created = await asyncio.to_thread(
                create_catboost_prediction,
                self.db,
                target,
                self.config.auto_prediction_count,
            )
        except (ValueError, RuntimeError) as exc:
            catboost_error = str(exc)
        outcome = {
            "prediction_date": target.isoformat(),
            "selected_count": self.config.auto_prediction_count,
            "two_digit_created": two_digit_created,
            "logistic_two_digit_created": logistic_created,
            "logistic_two_digit_error": logistic_error,
            "catboost_two_digit_created": catboost_created,
            "catboost_two_digit_error": catboost_error,
        }
        logger.info(
            "automatic prediction %s ready (frequency=%s, logistic=%s, catboost=%s)",
            target.isoformat(),
            two_digit_created,
            logistic_created,
            catboost_created,
        )
        return outcome

    async def _run_with_retries(
        self,
        label: str,
        operation: Callable[[], Awaitable[Any]],
    ) -> bool:
        for attempt in range(1, self.config.scheduler_retry_attempts + 1):
            try:
                await operation()
                return True
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "%s failed (attempt %s/%s)",
                    label,
                    attempt,
                    self.config.scheduler_retry_attempts,
                )
                if attempt < self.config.scheduler_retry_attempts:
                    await asyncio.sleep(
                        self.config.scheduler_retry_delay_seconds * attempt
                    )
        return False

    async def _run_once(self, now: datetime) -> None:
        today = now.date()
        current_time = now.strftime("%H:%M")
        self._completed_tokens = {
            token for token in self._completed_tokens if today.isoformat() in token
        }
        prediction_token = f"prediction:{today.isoformat()}"
        first_sync = min(self.config.result_poll_start_time, *self.config.result_sync_times)
        if (
            self.config.auto_prediction
            and self.config.prediction_time <= current_time < first_sync
            and prediction_token not in self._completed_tokens
        ):
            succeeded = await self._run_with_retries(
                f"prediction {today.isoformat()}",
                lambda: self._generate_prediction(today),
            )
            if succeeded:
                self._completed_tokens.add(prediction_token)

        poll_due = (
            current_time >= self.config.result_poll_start_time
            and self._result_ready_date != today
            and (self._next_result_poll_at is None or now >= self._next_result_poll_at)
        )
        # Catch up once if a slow request or restart missed a scheduled minute.
        due_times = [
            time for time in self.config.result_sync_times
            if time <= current_time
            and f"sync:{today.isoformat()}:{time}" not in self._completed_tokens
        ]
        if (poll_due or due_times) and (
            self._next_result_poll_at is None or now >= self._next_result_poll_at
        ):
            async def sync() -> None:
                outcome = await self._sync_and_evaluate(today, latest_only=poll_due)
                if outcome["result_available"]:
                    self._result_ready_date = today
                else:
                    self._result_ready_date = None

            succeeded = await self._run_with_retries(
                f"result sync {today.isoformat()} {current_time}", sync,
            )
            self._next_result_poll_at = self.config.local_now() + timedelta(
                seconds=self.config.result_poll_interval_seconds
            )
            if succeeded:
                self._completed_tokens.update(
                    f"sync:{today.isoformat()}:{time}" for time in due_times
                )

    async def _run(self) -> None:
        if self.config.sync_on_startup:
            await self._run_with_retries(
                "startup result sync",
                lambda: self._sync_and_evaluate(
                    self.config.local_today(),
                    latest_only=(self.config.local_now().strftime("%H:%M")
                                 >= self.config.result_poll_start_time),
                ),
            )

        while True:
            await self._run_once(self.config.local_now())
            await asyncio.sleep(1)
