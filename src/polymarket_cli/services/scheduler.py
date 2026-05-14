from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio

from polymarket_cli.config import WatchlistConfig, load_watchlists
from polymarket_cli.services.discovery import DiscoveryService
from polymarket_cli.storage.sqlite import SQLiteStore


class SchedulerService:
    def __init__(self, watchlists_path, discovery_service: DiscoveryService, sqlite_store: SQLiteStore) -> None:
        self.watchlists_path = watchlists_path
        self.discovery_service = discovery_service
        self.sqlite_store = sqlite_store

    def load(self) -> list[WatchlistConfig]:
        watchlists = load_watchlists(self.watchlists_path)
        self.sqlite_store.sync_watchlists(watchlists)
        return watchlists

    async def run_once(self, job_name: str | None = None) -> list[str]:
        watchlists = self.load()
        selected = [item for item in watchlists if item.enabled]
        if job_name:
            selected = [item for item in selected if item.name == job_name]

        completed = []
        for watchlist in selected:
            await self.discovery_service.run_watchlist(watchlist)
            completed.append(watchlist.name)
        return completed

    async def run_loop(
        self,
        *,
        job_name: str | None = None,
        tick_seconds: int = 15,
        cycles: int | None = None,
    ) -> None:
        watchlists = self.load()
        selected = [item for item in watchlists if item.enabled]
        if job_name:
            selected = [item for item in selected if item.name == job_name]

        due_at = {item.name: datetime.now(UTC) for item in selected}
        cycle_count = 0

        while True:
            now = datetime.now(UTC)
            for watchlist in selected:
                if now >= due_at[watchlist.name]:
                    await self.discovery_service.run_watchlist(watchlist)
                    due_at[watchlist.name] = now + timedelta(minutes=watchlist.poll_minutes)
            cycle_count += 1
            if cycles is not None and cycle_count >= cycles:
                return
            await anyio.sleep(tick_seconds)
