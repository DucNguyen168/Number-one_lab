from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator
from uuid import uuid4

from pymongo.errors import DuplicateKeyError
from pymongo.database import Database


class CronAlreadyRunning(RuntimeError):
    """Raised when another serverless invocation owns the same cron lease."""


@contextmanager
def mongo_cron_lease(
    db: Database,
    name: str,
    *,
    lease_seconds: int = 240,
) -> Iterator[str]:
    """Acquire a short MongoDB lease so duplicate Vercel invocations stay harmless."""
    owner = uuid4().hex
    acquired_at = datetime.now(timezone.utc)
    expires_at = acquired_at + timedelta(seconds=lease_seconds)
    document = {
        "_id": name,
        "owner": owner,
        "acquired_at": acquired_at,
        "expires_at": expires_at,
    }

    try:
        db.cron_locks.insert_one(document)
    except DuplicateKeyError:
        takeover = db.cron_locks.update_one(
            {"_id": name, "expires_at": {"$lte": acquired_at}},
            {
                "$set": {
                    "owner": owner,
                    "acquired_at": acquired_at,
                    "expires_at": expires_at,
                }
            },
        )
        if takeover.modified_count != 1:
            raise CronAlreadyRunning(
                f"Cron job {name!r} is already running"
            ) from None

    try:
        yield owner
    finally:
        db.cron_locks.delete_one({"_id": name, "owner": owner})
