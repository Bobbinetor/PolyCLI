"""PolyCLI MCP Server — Forensic Investigation Toolkit for Polymarket.

Exposes PolyCLI capabilities as MCP tools so AI assistants (Claude Desktop,
Cursor, etc.) can autonomously discover markets, rank them, and investigate
wallets on Polymarket.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from polymarket_cli.clients.data_api import DataAPIClient
from polymarket_cli.clients.gamma import GammaClient
from polymarket_cli.main import build_runtime
from polymarket_cli.services.discovery import DiscoveryService
from polymarket_cli.services.ranking import RankingService


mcp = FastMCP(
    "polycli",
    instructions=(
        "PolyCLI is an investigative observatory for Polymarket prediction markets. "
        "Use these tools to discover markets, rank them with LLMs, and perform "
        "forensic wallet investigations. A typical workflow is: "
        "1) discover_markets → 2) rank_snapshot → 3) investigate interesting wallets "
        "with profile_wallet / get_wallet_positions / get_wallet_trades."
    ),
)

# ---------------------------------------------------------------------------
# Lazy-initialized global state
# ---------------------------------------------------------------------------
_runtime_initialized = False
_settings: Any = None
_sqlite_store: Any = None
_gamma: Any = None
_discovery: Any = None
_ranking: Any = None
_data_api: Any = None


def _ensure_runtime() -> None:
    global _runtime_initialized, _settings, _sqlite_store
    global _gamma, _discovery, _ranking, _data_api
    if not _runtime_initialized:
        _settings, _sqlite_store = build_runtime()
        _gamma = GammaClient(_settings.gamma_base_url)
        _discovery = DiscoveryService(_gamma, _sqlite_store)
        _ranking = RankingService(_settings, _sqlite_store)
        _data_api = DataAPIClient(
            data_base_url=_settings.data_api_base_url,
            gamma_base_url=_settings.gamma_base_url,
            clob_base_url=_settings.clob_base_url,
        )
        _runtime_initialized = True


# ===================================================================
# SECTION 1 — Discovery & Ranking (existing tools)
# ===================================================================


@mcp.tool()
async def discover_markets(
    keywords: list[str],
    limit: int = 25,
    label: str = "mcp",
) -> dict[str, Any]:
    """Search Polymarket for live events matching keywords and save a snapshot.

    Returns the run_id which can be passed to rank_snapshot.
    """
    _ensure_runtime()
    snapshot = await _discovery.run_keywords(
        label=label, keywords=keywords, limit=limit
    )
    return {
        "status": "success",
        "run_id": snapshot.run_id,
        "label": snapshot.label,
        "events_count": len(snapshot.events),
        "message": f"Discovered {len(snapshot.events)} events for '{', '.join(keywords)}'.",
    }


@mcp.tool()
async def list_snapshots(label: str | None = None) -> list[dict[str, Any]]:
    """List past discovery snapshots, optionally filtered by label."""
    _ensure_runtime()
    runs = _sqlite_store.list_discovery_runs(label=label)
    return [
        {
            "run_id": r["run_id"],
            "label": r["label"],
            "keywords": r["keywords"].split(",") if r["keywords"] else [],
            "event_count": r["event_count"],
            "created_at": r["created_at"],
        }
        for r in runs
    ]


@mcp.tool()
async def get_snapshot_events(run_id: str) -> list[dict[str, Any]]:
    """Get all events with raw data from a discovery snapshot."""
    _ensure_runtime()
    events = _sqlite_store.get_discovery_events(run_id)
    return [dict(e) for e in events]


@mcp.tool()
async def rank_snapshot(
    run_id: str,
    provider: str = "ollama",
    dry_run: bool = False,
    max_rows: int = 20,
) -> dict[str, Any]:
    """Rank a discovery snapshot using the LLM investigative engine.

    Providers: 'ollama' (local) or 'openrouter' (cloud).
    Set dry_run=True for fast heuristic ranking without an LLM call.
    """
    _ensure_runtime()
    prompt_path = _settings.prompts_dir / "prompt-example.md"

    ranking = await _ranking.rank_run(
        run_id=run_id,
        prompt_path=prompt_path,
        provider=provider,
        dry_run=dry_run,
        max_rows=max_rows,
    )

    return {
        "status": "success",
        "provider": ranking.provider,
        "model": ranking.model,
        "summary": ranking.summary,
        "shortlist": [
            {
                "event_id": item.event_id,
                "title": item.title,
                "score": item.score,
                "action": item.action,
                "confidence": item.confidence,
                "thesis": item.thesis,
                "risks": item.risks,
            }
            for item in ranking.shortlist
        ],
    }


# ===================================================================
# SECTION 2 — Forensic Wallet Investigation (NEW)
# ===================================================================


@mcp.tool()
async def profile_wallet(address: str) -> dict[str, Any]:
    """Look up the public profile for a Polymarket wallet address.

    Returns the user's pseudonym, bio, creation date, verified badge,
    and linked X/Twitter handle. This is the starting point for any
    wallet investigation.
    """
    _ensure_runtime()
    return await _data_api.get_profile(address)


@mcp.tool()
async def get_wallet_positions(
    address: str,
    event_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get all current open positions for a wallet address.

    Each position includes: market title, outcome, size, avg price,
    current value, realized/unrealized P&L, and whether the position
    is redeemable. Use this to understand what a wallet is betting on.
    """
    _ensure_runtime()
    return await _data_api.get_positions(
        address, event_id=event_id, limit=limit
    )


@mcp.tool()
async def get_wallet_trades(
    address: str,
    market: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get the full trade history for a wallet address.

    Each trade includes: side (BUY/SELL), size, price, timestamp,
    market title, outcome, and transaction hash. Use this to detect
    suspicious timing patterns, wash trading, or front-running.
    """
    _ensure_runtime()
    return await _data_api.get_trades(
        address=address, market=market, limit=limit
    )


@mcp.tool()
async def get_wallet_portfolio_value(address: str) -> dict[str, Any]:
    """Get the total portfolio value for a wallet address.

    Quickly assess whether this is a whale or retail trader.
    """
    _ensure_runtime()
    return await _data_api.get_portfolio_value(address)


# ===================================================================
# SECTION 3 — Market Intelligence (NEW)
# ===================================================================


@mcp.tool()
async def get_market_top_holders(
    condition_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get the top holders of a specific market by condition ID.

    Returns up to 20 holders per token with their wallet, pseudonym,
    amount, and outcome. Use this to detect market concentration and
    identify whales controlling a market.
    """
    _ensure_runtime()
    return await _data_api.get_top_holders(condition_id, limit=limit)


@mcp.tool()
async def get_price_history(
    clob_token_id: str,
    interval: str = "1d",
    fidelity: int = 60,
) -> list[dict[str, Any]]:
    """Get historical price data for a market token.

    Use this to detect suspicious price movements, volume spikes,
    or front-running patterns before key events. The interval
    parameter controls the lookback window (e.g., '1d', '1w', 'max').
    """
    _ensure_runtime()
    return await _data_api.get_price_history(
        clob_token_id, interval=interval, fidelity=fidelity
    )


# ===================================================================
# Entry point
# ===================================================================


def main() -> None:
    """Entry point for the polycli-mcp script."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
