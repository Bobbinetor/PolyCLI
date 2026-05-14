from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import polars as pl

from polymarket_cli.domain.models import DiscoverySnapshot, EventSummary, RankingResult


class CSVStore:
    def __init__(self, raw_dir: Path, processed_dir: Path, exports_dir: Path) -> None:
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.exports_dir = exports_dir

    def _snapshot_paths(self, label: str) -> tuple[str, Path, Path, Path]:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        run_id = f"{stamp}-{uuid4().hex[:8]}"
        base = self.processed_dir / label / run_id
        base.mkdir(parents=True, exist_ok=True)
        raw_dir = self.raw_dir / label
        raw_dir.mkdir(parents=True, exist_ok=True)
        return run_id, raw_dir / f"{run_id}.json", base / "events.csv", base / "markets.csv"

    def write_snapshot(
        self,
        *,
        label: str,
        keywords: list[str],
        events: list[EventSummary],
    ) -> DiscoverySnapshot:
        run_id, raw_path, events_path, markets_path = self._snapshot_paths(label)

        raw_payload = {
            "run_id": run_id,
            "label": label,
            "keywords": keywords,
            "events": [event.model_dump(mode="json") for event in events],
        }
        raw_path.write_text(json.dumps(raw_payload, indent=2), encoding="utf-8")

        event_rows = []
        market_rows = []
        for event in events:
            event_rows.append(
                {
                    "run_id": run_id,
                    "event_id": event.id,
                    "title": event.title,
                    "slug": event.slug,
                    "description": event.description,
                    "active": event.active,
                    "closed": event.closed,
                    "live": event.live,
                    "category": event.category,
                    "start_date": event.start_date.isoformat() if event.start_date else None,
                    "end_date": event.end_date.isoformat() if event.end_date else None,
                    "volume": event.volume,
                    "liquidity": event.liquidity,
                    "open_interest": event.open_interest,
                    "tags": ",".join(event.tags),
                    "keyword_hits": ",".join(event.keyword_hits),
                    "market_count": event.market_count(),
                }
            )

            for market in event.markets:
                market_rows.append(
                    {
                        "run_id": run_id,
                        "event_id": event.id,
                        "event_title": event.title,
                        "market_id": market.id,
                        "question": market.question,
                        "slug": market.slug,
                        "condition_id": market.condition_id,
                        "active": market.active,
                        "closed": market.closed,
                        "end_date": market.end_date.isoformat() if market.end_date else None,
                        "volume": market.volume,
                        "liquidity": market.liquidity,
                        "best_bid": market.best_bid,
                        "best_ask": market.best_ask,
                        "last_trade_price": market.last_trade_price,
                        "outcomes": ",".join(market.outcomes),
                        "outcome_prices": ",".join(str(item) for item in market.outcome_prices),
                        "clob_token_ids": ",".join(market.clob_token_ids),
                        "tags": ",".join(market.tags),
                    }
                )

        pl.DataFrame(event_rows or [{"run_id": run_id}]).write_csv(events_path)
        pl.DataFrame(market_rows or [{"run_id": run_id}]).write_csv(markets_path)

        latest_dir = self.exports_dir / label
        latest_dir.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(event_rows or [{"run_id": run_id}]).write_csv(latest_dir / "latest-events.csv")
        pl.DataFrame(market_rows or [{"run_id": run_id}]).write_csv(latest_dir / "latest-markets.csv")

        return DiscoverySnapshot(
            run_id=run_id,
            label=label,
            keywords=keywords,
            events=events,
            raw_path=str(raw_path),
            events_csv_path=str(events_path),
            markets_csv_path=str(markets_path),
        )

    def write_ranking_report(self, label: str, ranking: RankingResult) -> Path:
        destination = self.exports_dir / label
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / "ranking.json"
        path.write_text(ranking.model_dump_json(indent=2), encoding="utf-8")
        return path
