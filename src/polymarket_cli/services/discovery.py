from __future__ import annotations

import uuid
from datetime import UTC, datetime

from polymarket_cli.clients.gamma import GammaClient
from polymarket_cli.config import WatchlistConfig
from polymarket_cli.domain.models import DiscoverySnapshot
from polymarket_cli.storage.sqlite import SQLiteStore


class DiscoveryService:
    def __init__(self, gamma: GammaClient, sqlite_store: SQLiteStore) -> None:
        self.gamma = gamma
        self.sqlite_store = sqlite_store

    def _generate_run_id(self) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{uuid.uuid4().hex[:8]}"

    async def run_watchlist(self, watchlist: WatchlistConfig) -> DiscoverySnapshot:
        events = await self.gamma.discover_keywords(
            watchlist.keywords,
            limit=watchlist.limit,
            live_only=watchlist.live_only,
            include_closed=watchlist.include_closed,
            tags=watchlist.tags,
        )
        snapshot = DiscoverySnapshot(
            run_id=self._generate_run_id(),
            label=watchlist.name,
            keywords=watchlist.keywords,
            events=events,
        )
        self.sqlite_store.record_discovery_run(snapshot)
        return snapshot

    async def run_keywords(
        self,
        label: str,
        keywords: list[str],
        limit: int = 25,
    ) -> DiscoverySnapshot:
        events = await self.gamma.discover_keywords(keywords, limit=limit)
        snapshot = DiscoverySnapshot(
            run_id=self._generate_run_id(),
            label=label,
            keywords=keywords,
            events=events,
        )
        self.sqlite_store.record_discovery_run(snapshot)
        return snapshot
