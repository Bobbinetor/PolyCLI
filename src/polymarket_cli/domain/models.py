from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class MarketSummary(BaseModel):
    id: str
    question: str
    slug: str | None = None
    condition_id: str | None = None
    active: bool = False
    closed: bool = False
    end_date: datetime | None = None
    volume: float | None = None
    liquidity: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    last_trade_price: float | None = None
    outcomes: list[str] = Field(default_factory=list)
    outcome_prices: list[float] = Field(default_factory=list)
    clob_token_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class EventSummary(BaseModel):
    id: str
    title: str
    slug: str | None = None
    description: str | None = None
    active: bool = False
    closed: bool = False
    live: bool = False
    category: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    volume: float | None = None
    liquidity: float | None = None
    open_interest: float | None = None
    tags: list[str] = Field(default_factory=list)
    markets: list[MarketSummary] = Field(default_factory=list)
    keyword_hits: list[str] = Field(default_factory=list)

    def market_count(self) -> int:
        return len(self.markets)


class DiscoverySnapshot(BaseModel):
    run_id: str
    label: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    keywords: list[str] = Field(default_factory=list)
    events: list[EventSummary] = Field(default_factory=list)


class RankingItem(BaseModel):
    event_id: str
    title: str
    score: int
    confidence: int | None = None
    action: str
    thesis: str
    risks: list[str] = Field(default_factory=list)


class RankingResult(BaseModel):
    provider: str
    model: str
    summary: str
    shortlist: list[RankingItem] = Field(default_factory=list)
    raw_response: str | None = None


class WatchJobState(BaseModel):
    name: str
    schedule: str
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: str = "idle"
    enabled: bool = True


class PaperPosition(BaseModel):
    position_id: str
    event_id: str
    market_id: str
    outcome: str
    side: str
    size: float
    entry_price: float
    current_price: float | None = None


def parse_jsonish_list(value: Any) -> list[Any]:
    import json

    if value is None:
        return []
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return [value]

    text = value.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        return parsed if isinstance(parsed, list) else [parsed]
    return [text]


def parse_optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_market(payload: dict[str, Any]) -> MarketSummary:
    tags = payload.get("tags") or []
    tag_labels = [tag.get("slug") or tag.get("label") for tag in tags if isinstance(tag, dict)]
    return MarketSummary(
        id=str(payload.get("id")),
        question=payload.get("question") or payload.get("title") or "Untitled market",
        slug=payload.get("slug"),
        condition_id=payload.get("conditionId") or payload.get("condition_id"),
        active=bool(payload.get("active")),
        closed=bool(payload.get("closed")),
        end_date=parse_optional_datetime(payload.get("endDate") or payload.get("end_date")),
        volume=parse_optional_float(payload.get("volumeNum") or payload.get("volume")),
        liquidity=parse_optional_float(payload.get("liquidityNum") or payload.get("liquidity")),
        best_bid=parse_optional_float(payload.get("bestBid") or payload.get("best_bid")),
        best_ask=parse_optional_float(payload.get("bestAsk") or payload.get("best_ask")),
        last_trade_price=parse_optional_float(
            payload.get("lastTradePrice") or payload.get("last_trade_price")
        ),
        outcomes=[str(item) for item in parse_jsonish_list(payload.get("outcomes"))],
        outcome_prices=[
            float(item)
            for item in parse_jsonish_list(payload.get("outcomePrices") or payload.get("outcome_prices"))
            if parse_optional_float(item) is not None
        ],
        clob_token_ids=[
            str(item)
            for item in parse_jsonish_list(payload.get("clobTokenIds") or payload.get("clob_token_ids"))
        ],
        tags=[item for item in tag_labels if item],
    )


def normalize_event(payload: dict[str, Any], keyword_hits: list[str] | None = None) -> EventSummary:
    tags = payload.get("tags") or []
    tag_labels = [tag.get("slug") or tag.get("label") for tag in tags if isinstance(tag, dict)]
    markets = [normalize_market(item) for item in payload.get("markets") or [] if isinstance(item, dict)]

    return EventSummary(
        id=str(payload.get("id")),
        title=payload.get("title") or "Untitled event",
        slug=payload.get("slug"),
        description=payload.get("description"),
        active=bool(payload.get("active")),
        closed=bool(payload.get("closed")),
        live=bool(payload.get("live")),
        category=payload.get("category"),
        start_date=parse_optional_datetime(payload.get("startDate") or payload.get("start_date")),
        end_date=parse_optional_datetime(payload.get("endDate") or payload.get("end_date")),
        volume=parse_optional_float(payload.get("volume")),
        liquidity=parse_optional_float(payload.get("liquidity")),
        open_interest=parse_optional_float(payload.get("openInterest") or payload.get("open_interest")),
        tags=[item for item in tag_labels if item],
        markets=markets,
        keyword_hits=keyword_hits or [],
    )
