from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from polymarket_cli.config import WatchlistConfig
from polymarket_cli.domain.models import DiscoverySnapshot, RankingResult, WatchJobState


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS watch_jobs (
                    name TEXT PRIMARY KEY,
                    schedule TEXT NOT NULL,
                    poll_minutes INTEGER NOT NULL,
                    keywords TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS discovery_runs (
                    run_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    slug TEXT,
                    description TEXT,
                    active INTEGER,
                    closed INTEGER,
                    live INTEGER,
                    category TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    volume REAL,
                    liquidity REAL,
                    open_interest REAL,
                    tags TEXT,
                    keyword_hits TEXT,
                    market_count INTEGER,
                    PRIMARY KEY (run_id, event_id),
                    FOREIGN KEY (run_id) REFERENCES discovery_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS markets (
                    run_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    slug TEXT,
                    condition_id TEXT,
                    active INTEGER,
                    closed INTEGER,
                    end_date TEXT,
                    volume REAL,
                    liquidity REAL,
                    best_bid REAL,
                    best_ask REAL,
                    last_trade_price REAL,
                    outcomes TEXT,
                    outcome_prices TEXT,
                    clob_token_ids TEXT,
                    tags TEXT,
                    PRIMARY KEY (run_id, market_id),
                    FOREIGN KEY (run_id) REFERENCES discovery_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS ranking_runs (
                    run_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    shortlist_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES discovery_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS paper_positions (
                    position_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    side TEXT NOT NULL,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL,
                    status TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    exit_price REAL
                );
                """
            )

    def sync_watchlists(self, watchlists: list[WatchlistConfig]) -> None:
        now = datetime.now(UTC).isoformat()
        names = {item.name for item in watchlists}
        with self._connect() as connection:
            for item in watchlists:
                connection.execute(
                    """
                    INSERT INTO watch_jobs (name, schedule, poll_minutes, keywords, enabled, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        schedule=excluded.schedule,
                        poll_minutes=excluded.poll_minutes,
                        keywords=excluded.keywords,
                        enabled=excluded.enabled,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item.name,
                        f"every {item.poll_minutes} minutes",
                        item.poll_minutes,
                        ",".join(item.keywords),
                        1 if item.enabled else 0,
                        now,
                    ),
                )
            if names:
                placeholders = ", ".join("?" for _ in names)
                connection.execute(
                    f"DELETE FROM watch_jobs WHERE name NOT IN ({placeholders})",
                    tuple(names),
                )
            else:
                connection.execute("DELETE FROM watch_jobs")

    def list_watch_jobs(self) -> list[WatchJobState]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name, schedule, enabled FROM watch_jobs ORDER BY name"
            ).fetchall()
        return [
            WatchJobState(name=row["name"], schedule=row["schedule"], enabled=bool(row["enabled"]))
            for row in rows
        ]

    def record_discovery_run(self, snapshot: DiscoverySnapshot) -> None:
        with self._connect() as connection:
            # 1. Insert run metadata
            connection.execute(
                """
                INSERT INTO discovery_runs (run_id, label, keywords, event_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.run_id,
                    snapshot.label,
                    ",".join(snapshot.keywords),
                    len(snapshot.events),
                    snapshot.created_at.isoformat(),
                ),
            )

            # 2. Insert events and markets
            for event in snapshot.events:
                connection.execute(
                    """
                    INSERT INTO events (
                        run_id, event_id, title, slug, description, active, closed, live, category,
                        start_date, end_date, volume, liquidity, open_interest, tags, keyword_hits, market_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.run_id,
                        event.id,
                        event.title,
                        event.slug,
                        event.description,
                        1 if event.active else 0,
                        1 if event.closed else 0,
                        1 if event.live else 0,
                        event.category,
                        event.start_date.isoformat() if event.start_date else None,
                        event.end_date.isoformat() if event.end_date else None,
                        event.volume,
                        event.liquidity,
                        event.open_interest,
                        ",".join(event.tags),
                        ",".join(event.keyword_hits),
                        event.market_count(),
                    )
                )

                for market in event.markets:
                    connection.execute(
                        """
                        INSERT INTO markets (
                            run_id, event_id, market_id, question, slug, condition_id, active, closed,
                            end_date, volume, liquidity, best_bid, best_ask, last_trade_price,
                            outcomes, outcome_prices, clob_token_ids, tags
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot.run_id,
                            event.id,
                            market.id,
                            market.question,
                            market.slug,
                            market.condition_id,
                            1 if market.active else 0,
                            1 if market.closed else 0,
                            market.end_date.isoformat() if market.end_date else None,
                            market.volume,
                            market.liquidity,
                            market.best_bid,
                            market.best_ask,
                            market.last_trade_price,
                            ",".join(market.outcomes),
                            ",".join(str(p) for p in market.outcome_prices),
                            ",".join(market.clob_token_ids),
                            ",".join(market.tags),
                        )
                    )

    def latest_discovery_run(self, label: str | None = None) -> sqlite3.Row | None:
        query = "SELECT * FROM discovery_runs"
        params: tuple[str, ...] = ()
        if label:
            query += " WHERE label = ?"
            params = (label,)
        query += " ORDER BY created_at DESC LIMIT 1"

        with self._connect() as connection:
            return connection.execute(query, params).fetchone()

    def get_discovery_events(self, run_id: str) -> list[sqlite3.Row]:
        query = "SELECT * FROM events WHERE run_id = ?"
        with self._connect() as connection:
            return connection.execute(query, (run_id,)).fetchall()

    def get_discovery_markets(self, run_id: str) -> list[sqlite3.Row]:
        query = "SELECT * FROM markets WHERE run_id = ?"
        with self._connect() as connection:
            return connection.execute(query, (run_id,)).fetchall()

    def list_discovery_runs(self, label: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT d.run_id, d.label, d.keywords, d.created_at, d.event_count,
                   (SELECT count(*) FROM ranking_runs r WHERE r.run_id = d.run_id) as has_ranking
            FROM discovery_runs d
        """
        params: tuple[str, ...] = ()
        if label:
            query += " WHERE label = ?"
            params = (label,)
        query += " ORDER BY created_at DESC"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def record_ranking_run(self, run_id: str, ranking: RankingResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ranking_runs (run_id, provider, model, summary, shortlist_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    provider=excluded.provider,
                    model=excluded.model,
                    summary=excluded.summary,
                    shortlist_json=excluded.shortlist_json,
                    created_at=excluded.created_at
                """,
                (
                    run_id,
                    ranking.provider,
                    ranking.model,
                    ranking.summary,
                    json.dumps([item.model_dump() for item in ranking.shortlist]),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def open_paper_position(
        self,
        *,
        position_id: str,
        event_id: str,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        entry_price: float,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_positions (
                    position_id, event_id, market_id, outcome, side, size,
                    entry_price, current_price, status, opened_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position_id,
                    event_id,
                    market_id,
                    outcome,
                    side,
                    size,
                    entry_price,
                    entry_price,
                    "open",
                    datetime.now(UTC).isoformat(),
                ),
            )

    def update_paper_price(self, position_id: str, price: float) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE paper_positions SET current_price = ? WHERE position_id = ?",
                (price, position_id),
            )

    def close_paper_position(self, position_id: str, exit_price: float) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE paper_positions
                SET status = 'closed', exit_price = ?, current_price = ?, closed_at = ?
                WHERE position_id = ?
                """,
                (exit_price, exit_price, datetime.now(UTC).isoformat(), position_id),
            )

    def list_paper_positions(self, include_closed: bool = False) -> list[sqlite3.Row]:
        query = "SELECT * FROM paper_positions"
        if not include_closed:
            query += " WHERE status = 'open'"
        query += " ORDER BY opened_at DESC"
        with self._connect() as connection:
            return connection.execute(query).fetchall()
