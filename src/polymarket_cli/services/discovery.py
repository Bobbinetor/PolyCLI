from __future__ import annotations

from polymarket_cli.clients.gamma import GammaClient
from polymarket_cli.config import WatchlistConfig
from polymarket_cli.domain.models import DiscoverySnapshot
from polymarket_cli.storage.csv_store import CSVStore
from polymarket_cli.storage.sqlite import SQLiteStore


class DiscoveryService:
    def __init__(self, gamma: GammaClient, csv_store: CSVStore, sqlite_store: SQLiteStore) -> None:
        self.gamma = gamma
        self.csv_store = csv_store
        self.sqlite_store = sqlite_store

    async def run_watchlist(self, watchlist: WatchlistConfig) -> DiscoverySnapshot:
        events = await self.gamma.discover_keywords(
            watchlist.keywords,
            limit=watchlist.limit,
            live_only=watchlist.live_only,
            include_closed=watchlist.include_closed,
            tags=watchlist.tags,
        )
        snapshot = self.csv_store.write_snapshot(
            label=watchlist.name,
            keywords=watchlist.keywords,
            events=events,
        )
        self.sqlite_store.record_discovery_run(snapshot)
        return snapshot

    async def run_keywords(self, label: str, keywords: list[str], limit: int = 25) -> DiscoverySnapshot:
        events = await self.gamma.discover_keywords(keywords, limit=limit)
        snapshot = self.csv_store.write_snapshot(label=label, keywords=keywords, events=events)
        self.sqlite_store.record_discovery_run(snapshot)
        return snapshot
