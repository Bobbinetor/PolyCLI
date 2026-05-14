from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import polars as pl
import websockets


def load_asset_ids(markets_csv_path: Path, limit: int = 20) -> list[str]:
    frame = pl.read_csv(markets_csv_path)
    if "clob_token_ids" not in frame.columns:
        return []
    asset_ids: list[str] = []
    for value in frame.get_column("clob_token_ids").fill_null("").to_list():
        for asset_id in str(value).split(","):
            normalized = asset_id.strip()
            if normalized and normalized not in asset_ids:
                asset_ids.append(normalized)
            if len(asset_ids) >= limit:
                return asset_ids
    return asset_ids


class MarketStreamClient:
    def __init__(self, url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market") -> None:
        self.url = url

    @staticmethod
    def decode_message(raw_message: str | bytes) -> list[dict[str, Any]]:
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode()
        payload = json.loads(raw_message)
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    async def stream_assets(
        self,
        asset_ids: list[str],
        on_message: Callable[[dict[str, Any]], Awaitable[None]],
        max_messages: int | None = None,
    ) -> None:
        subscription = {
            "assets_ids": asset_ids,
            "type": "market",
            "custom_feature_enabled": True,
        }
        async with websockets.connect(self.url, ping_interval=None, ping_timeout=None) as websocket:
            await websocket.send(json.dumps(subscription))
            received = 0
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                except asyncio.TimeoutError:
                    await websocket.send("PING")
                    continue

                if message == "PONG":
                    continue

                for payload in self.decode_message(message):
                    await on_message(payload)
                    received += 1
                    if max_messages is not None and received >= max_messages:
                        return
