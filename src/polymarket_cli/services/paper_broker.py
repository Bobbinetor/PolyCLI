from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import polars as pl

from polymarket_cli.domain.models import PaperPosition
from polymarket_cli.storage.sqlite import SQLiteStore


def infer_market_price(markets_csv_path: Path, market_id: str) -> float | None:
    frame = pl.read_csv(markets_csv_path)
    filtered = frame.filter(pl.col("market_id") == market_id)
    if filtered.is_empty():
        return None
    row = filtered.to_dicts()[0]
    last_trade = row.get("last_trade_price")
    best_bid = row.get("best_bid")
    best_ask = row.get("best_ask")
    if last_trade not in (None, ""):
        return float(last_trade)
    if best_bid not in (None, "") and best_ask not in (None, ""):
        return (float(best_bid) + float(best_ask)) / 2
    return None


class PaperBroker:
    def __init__(self, sqlite_store: SQLiteStore) -> None:
        self.sqlite_store = sqlite_store

    def open_position(
        self,
        *,
        event_id: str,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        entry_price: float,
    ) -> PaperPosition:
        position = PaperPosition(
            position_id=uuid4().hex[:12],
            event_id=event_id,
            market_id=market_id,
            outcome=outcome,
            side=side,
            size=size,
            entry_price=entry_price,
            current_price=entry_price,
        )
        self.sqlite_store.open_paper_position(
            position_id=position.position_id,
            event_id=position.event_id,
            market_id=position.market_id,
            outcome=position.outcome,
            side=position.side,
            size=position.size,
            entry_price=position.entry_price,
        )
        return position

    def mark_position(self, position_id: str, price: float) -> None:
        self.sqlite_store.update_paper_price(position_id, price)

    def close_position(self, position_id: str, exit_price: float) -> None:
        self.sqlite_store.close_paper_position(position_id, exit_price)

    def list_positions(self, include_closed: bool = False) -> list[dict]:
        rows = self.sqlite_store.list_paper_positions(include_closed=include_closed)
        results = []
        for row in rows:
            current_price = row["current_price"] if row["current_price"] is not None else row["entry_price"]
            side_multiplier = 1 if row["side"].lower() == "buy" else -1
            pnl = (current_price - row["entry_price"]) * row["size"] * side_multiplier
            results.append(
                {
                    "position_id": row["position_id"],
                    "event_id": row["event_id"],
                    "market_id": row["market_id"],
                    "outcome": row["outcome"],
                    "side": row["side"],
                    "size": row["size"],
                    "entry_price": row["entry_price"],
                    "current_price": current_price,
                    "status": row["status"],
                    "pnl": pnl,
                }
            )
        return results
