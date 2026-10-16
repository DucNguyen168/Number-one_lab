"""Low-concurrency entry point for a persistent Python host.

Run from the repository root: python scripts/run_host.py [web|worker|rolling-report]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
import signal
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def configure_runtime() -> None:
    # Must happen before numpy/scipy/sklearn (including indirect imports).
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(name, "1")


def host_port() -> int:
    value = os.getenv("PORT") or os.getenv("SERVER_PORT") or "8000"
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("PORT / SERVER_PORT must be between 1 and 65535")
    return port


async def run_worker(db, settings) -> None:
    from app.services.scheduler import DailyScheduler

    if settings.is_vercel or not settings.enable_scheduler:
        raise RuntimeError("Worker requires ENABLE_SCHEDULER=true and no VERCEL environment")
    scheduler = DailyScheduler(db, settings)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows development; Ctrl+C uses asyncio cancellation.
            pass
    scheduler.start()
    stop_task = asyncio.create_task(stop.wait())
    try:
        # A failed scheduler must exit the process, not leave an idle worker alive.
        done, _ = await asyncio.wait(
            [scheduler.task, stop_task], return_when=asyncio.FIRST_COMPLETED
        )
        if scheduler.task in done:
            await scheduler.task
    finally:
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)
        await scheduler.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="web",
                        choices=("web", "worker", "rolling-report"))
    args = parser.parse_args()
    configure_runtime()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.mode == "web":
        import uvicorn

        uvicorn.run("app.main:app", host="0.0.0.0", port=host_port(), workers=1,
                    reload=False, access_log=False)
        return

    from app.config import settings
    from app.database import MongoDatabase

    mongo = MongoDatabase(settings)
    try:
        mongo.ping()
        mongo.ensure_indexes()
        if args.mode == "worker":
            asyncio.run(run_worker(mongo.db, settings))
        else:
            from app.services.cron_lock import mongo_cron_lease
            from app.services.rolling_comparison import load_or_build_rolling_comparison

            # This lease prevents accidental duplicate operator jobs for up to six hours.
            with mongo_cron_lease(mongo.db, "offline-rolling-report", lease_seconds=21600):
                report, rebuilt = load_or_build_rolling_comparison(mongo.db)
            logging.info("Rolling report ready: rebuilt=%s, dataset through %s",
                         rebuilt, report["dataset"]["last_date"])
    finally:
        mongo.close()


if __name__ == "__main__":
    main()
