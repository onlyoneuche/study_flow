import asyncio
import fcntl
import logging
from pathlib import Path

import anyio

from app.core.calendar import lagos_week_start
from app.services.streaks import catch_up

logger = logging.getLogger(__name__)


class SingleInstanceLock:
    """An OS-held lock beside the SQLite file; process crashes release it automatically."""

    def __init__(self, database_path):
        self.path = Path(f"{database_path}.jobs.lock")
        self.file = None

    def acquire(self):
        handle = self.path.open("a")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise RuntimeError(
                "Another StudyFlow instance owns this database's scheduled jobs."
            ) from None
        self.file = handle

    def release(self):
        if self.file:
            fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close()
            self.file = None


class ScheduledJobs:
    def __init__(self, app):
        self.app = app
        self.lock = SingleInstanceLock(app.state.database.engine.url.database)
        self.running = asyncio.Lock()

    async def nightly(self):
        async with self.running:
            # Finish overdue time-only participations before evaluating their Lagos day.
            # Keep transactions alive through scheduler shutdown cancellation.
            with anyio.CancelScope(shield=True):
                await self.app.state.presence.tick()
                await catch_up(self.app.state.database, self.app.state.clock())

    async def weekly(self):
        # Reads switch week at Monday midnight without rewriting a single ledger row.
        logger.info("Lagos weekly ledger window: %s", lagos_week_start(self.app.state.clock()))

    async def start(self):
        self.lock.acquire()
        await self.nightly()
        scheduler = self.app.state.presence.scheduler
        scheduler.add_job(
            self.nightly,
            "cron",
            hour=2,
            minute=0,
            id="nightly_streaks",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=None,
        )
        scheduler.add_job(
            self.weekly,
            "cron",
            day_of_week="mon",
            hour=0,
            minute=0,
            id="weekly_boundary",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=None,
        )

    async def stop(self):
        async with self.running:
            self.lock.release()
