from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import anyio
import httpx

from polymarket_cli.domain.models import EventSummary, normalize_event


class GammaClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": "polymarket-cli/0.1.0"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GammaClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            response = await self._client.get(path, params=params)
            if response.status_code < 400:
                return response.json()
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                await anyio.sleep(0.5 * (attempt + 1))
                continue
            response.raise_for_status()
        raise RuntimeError("Gamma request failed after retries")

    async def public_search(
        self,
        query: str,
        *,
        limit_per_type: int = 10,
        include_closed: bool = False,
        sort: str = "score",
    ) -> dict[str, Any]:
        params = {
            "q": query,
            "limit_per_type": limit_per_type,
            "sort": sort,
            "ascending": False,
            "search_tags": True,
            "search_profiles": False,
        }
        if include_closed:
            params["keep_closed_markets"] = 1
        else:
            params["events_status"] = "active"
        return await self._get("/public-search", params)

    async def list_events_keyset(
        self,
        *,
        limit: int = 50,
        after_cursor: str | None = None,
        ids: Iterable[str] | None = None,
        title_search: str | None = None,
        live: bool | None = None,
        closed: bool | None = None,
        tag_slug: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": min(limit, 500),
            "ascending": False,
            "order": "volume",
        }
        if after_cursor:
            params["after_cursor"] = after_cursor
        if ids:
            params["id"] = list(ids)
        if title_search:
            params["title_search"] = title_search
        if live is not None:
            params["live"] = live
        if closed is not None:
            params["closed"] = closed
        if tag_slug:
            params["tag_slug"] = tag_slug
        return await self._get("/events/keyset", params)

    async def discover_keywords(
        self,
        keywords: list[str],
        *,
        limit: int = 25,
        crawl_pages: int = 2,
        live_only: bool = True,
        include_closed: bool = False,
        tags: list[str] | None = None,
    ) -> list[EventSummary]:
        event_hits: dict[str, EventSummary] = {}
        keyword_index: dict[str, set[str]] = {}

        async def merge_payloads(payloads: list[dict[str, Any]], keyword: str) -> None:
            for payload in payloads:
                event_id = str(payload.get("id"))
                keyword_index.setdefault(event_id, set()).add(keyword)
                event = normalize_event(payload, keyword_hits=sorted(keyword_index[event_id]))
                event_hits[event_id] = event

        for keyword in keywords:
            search_payload = await self.public_search(
                keyword,
                limit_per_type=min(limit, 20),
                include_closed=include_closed,
            )
            search_events = search_payload.get("events") or []
            seed_ids = [str(item.get("id")) for item in search_events if item.get("id") is not None]
            if seed_ids:
                detail_payload = await self.list_events_keyset(
                    ids=seed_ids,
                    limit=min(len(seed_ids), 500),
                )
                await merge_payloads(detail_payload.get("events") or [], keyword)

            cursor: str | None = None
            for _ in range(crawl_pages):
                payload = await self.list_events_keyset(
                    limit=limit,
                    after_cursor=cursor,
                    title_search=keyword,
                    live=True if live_only else None,
                    closed=False if not include_closed and not live_only else None,
                    tag_slug=(tags or [None])[0],
                )
                page_events = payload.get("events") or []
                await merge_payloads(page_events, keyword)
                cursor = payload.get("next_cursor")
                if not cursor:
                    break

        events = list(event_hits.values())
        events.sort(key=lambda item: (item.volume or 0.0, item.liquidity or 0.0), reverse=True)
        return events[:limit]
