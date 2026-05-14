"""Thin async client for the Polymarket Data API (data-api.polymarket.com).

All endpoints hit here are **public and unauthenticated**. They power the
forensic investigation layer of PolyCLI.
"""

from __future__ import annotations

from typing import Any

import httpx


class DataAPIClient:
    """Read-only wrapper around Polymarket's public Data API."""

    def __init__(
        self,
        data_base_url: str = "https://data-api.polymarket.com",
        gamma_base_url: str = "https://gamma-api.polymarket.com",
        clob_base_url: str = "https://clob.polymarket.com",
        timeout: int = 30,
    ) -> None:
        self._data_url = data_base_url.rstrip("/")
        self._gamma_url = gamma_base_url.rstrip("/")
        self._clob_url = clob_base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Wallet investigation
    # ------------------------------------------------------------------

    async def get_profile(self, address: str) -> dict[str, Any]:
        """GET /public-profile?address=... (Gamma API)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._gamma_url}/public-profile",
                params={"address": address},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_positions(
        self,
        address: str,
        *,
        event_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "CURRENT",
        sort_direction: str = "DESC",
    ) -> list[dict[str, Any]]:
        """GET /positions?user=... (Data API)."""
        params: dict[str, Any] = {
            "user": address,
            "limit": min(limit, 500),
            "offset": offset,
            "sortBy": sort_by,
            "sortDirection": sort_direction,
        }
        if event_id:
            params["eventId"] = event_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._data_url}/positions", params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_trades(
        self,
        *,
        address: str | None = None,
        market: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """GET /trades?user=...&market=... (Data API)."""
        params: dict[str, Any] = {
            "limit": min(limit, 500),
            "offset": offset,
        }
        if address:
            params["user"] = address
        if market:
            params["market"] = market
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._data_url}/trades", params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_portfolio_value(self, address: str) -> dict[str, Any]:
        """GET /value?user=... (Data API)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._data_url}/value",
                params={"user": address},
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Market intelligence
    # ------------------------------------------------------------------

    async def get_top_holders(
        self,
        condition_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """GET /holders?market=... (Data API)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._data_url}/holders",
                params={"market": condition_id, "limit": min(limit, 20)},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_price_history(
        self,
        clob_token_id: str,
        *,
        interval: str = "1d",
        fidelity: int = 60,
    ) -> list[dict[str, Any]]:
        """GET /prices-history?market=...&interval=... (CLOB API)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._clob_url}/prices-history",
                params={
                    "market": clob_token_id,
                    "interval": interval,
                    "fidelity": fidelity,
                },
            )
            resp.raise_for_status()
            return resp.json()
