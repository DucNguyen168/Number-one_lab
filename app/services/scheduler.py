from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from pymongo.database import Database

from app.config import Settings
from app.services.collector import KqxsCollector
from app.services.digit_prediction import create_digit_prediction
from app.services.evaluation import (
    evaluate_pending_digit_predictions,
    evaluate_pending_predictions,
)
from app.services.prediction import create_prediction


class DailyScheduler:
    def __init__(self, db: Database, config: Settings) -> None:
        self.db = db
        self.config = config
        self.collector = KqxsCollector(db, config)
        self.task: asyncio.Task[None] | None = None
        self._completed_tokens: set[str] = set()

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

    async def _sync_and_evaluate(self, target: date) -> dict[str, Any]:
        sync_result = await asyncio.to_thread(self.collector.sync_year, target.year)
        evaluation = await asyncio.to_thread(evaluate_pending_predictions, self.db)
        digit_evaluation = await asyncio.to_thread(
            evaluate_pending_digit_predictions, self.db
        )
        return {
            "sync": sync_result,
            "evaluation": evaluation,
            "digit_evaluation": digit_evaluation,
        }

    async def _generate_prediction(self, target: date) -> None:
        await asyncio.to_thread(
            create_prediction, self.db, target, self.config.auto_prediction_count
        )
        await asyncio.to_thread(create_digit_prediction, self.db, target)

    async def _run(self) -> None:
        if self.config.sync_on_startup:
            try:
                await self._sync_and_evaluate(self.config.local_today())
            except Exception:
                pass

        while True:
            now = self.config.local_now()
            today = now.date()
            current_time = now.strftime("%H:%M")

            prediction_token = f"prediction:{today.isoformat()}"
            first_sync = min(self.config.result_sync_times, default="18:35")
            if (
                self.config.auto_prediction
                and self.config.prediction_time <= current_time < first_sync
                and prediction_token not in self._completed_tokens
            ):
                try:
                    await self._generate_prediction(today)
                except Exception:
                    pass
                finally:
                    self._completed_tokens.add(prediction_token)

            if current_time in self.config.result_sync_times:
                sync_token = f"sync:{today.isoformat()}:{current_time}"
                if sync_token not in self._completed_tokens:
                    try:
                        await self._sync_and_evaluate(today)
                    except Exception:
                        pass
                    finally:
                        self._completed_tokens.add(sync_token)

            cutoff = today.isoformat()
            self._completed_tokens = {
                token for token in self._completed_tokens if cutoff in token
            }
            await asyncio.sleep(20)
