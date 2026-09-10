from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError

from app.services.cron_lock import CronAlreadyRunning, mongo_cron_lease


class _CronLocks:
    def __init__(self, *, duplicate: bool = False, takeover: bool = False) -> None:
        self.duplicate = duplicate
        self.takeover = takeover
        self.deleted: list[dict[str, str]] = []

    def insert_one(self, document):
        if self.duplicate:
            raise DuplicateKeyError("duplicate lock")
        return SimpleNamespace(inserted_id=document["_id"])

    def update_one(self, query, update):
        return SimpleNamespace(modified_count=1 if self.takeover else 0)

    def delete_one(self, query):
        self.deleted.append(query)
        return SimpleNamespace(deleted_count=1)


def test_cron_lease_releases_only_the_owned_lock() -> None:
    locks = _CronLocks()

    with mongo_cron_lease(SimpleNamespace(cron_locks=locks), "auto-daily") as owner:
        assert owner

    assert locks.deleted == [{"_id": "auto-daily", "owner": owner}]


def test_cron_lease_rejects_overlapping_invocation() -> None:
    locks = _CronLocks(duplicate=True, takeover=False)

    with pytest.raises(CronAlreadyRunning):
        with mongo_cron_lease(SimpleNamespace(cron_locks=locks), "auto-daily"):
            pass


def test_cron_lease_can_take_over_an_expired_lock() -> None:
    locks = _CronLocks(duplicate=True, takeover=True)

    with mongo_cron_lease(SimpleNamespace(cron_locks=locks), "auto-daily") as owner:
        assert owner

    assert locks.deleted == [{"_id": "auto-daily", "owner": owner}]
