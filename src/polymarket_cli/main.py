from __future__ import annotations

from pathlib import Path

import anyio
import polars as pl
import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

from polymarket_cli.clients.gamma import GammaClient
from polymarket_cli.config import (
    WatchlistConfig,
    get_settings,
    get_watchlist,
    load_watchlists,
    parse_csv_list,
    remove_watchlist,
    replace_watchlist,
    set_watchlist_enabled,
    upsert_watchlist,
)
from polymarket_cli.services.discovery import DiscoveryService
from polymarket_cli.services.launchd import LaunchdService
from polymarket_cli.services.paper_broker import PaperBroker, infer_market_price
from polymarket_cli.services.ranking import RankingService
from polymarket_cli.services.scheduler import SchedulerService
from polymarket_cli.storage.csv_store import CSVStore
from polymarket_cli.storage.sqlite import SQLiteStore
from polymarket_cli.streams.polymarket_ws import MarketStreamClient, load_asset_ids
from polymarket_cli.repl.app import ReplApp

app = typer.Typer(
    help="Polymarket discovery CLI",
    invoke_without_command=True,
    no_args_is_help=False,
)
watchlists_app = typer.Typer(help="Inspect configured watchlists")
discover_app = typer.Typer(help="Run discovery against Gamma")
scheduler_app = typer.Typer(help="Run and install recurring jobs")
rank_app = typer.Typer(help="Rank discovered events with an LLM provider")
paper_app = typer.Typer(help="Manage paper-trading positions")
stream_app = typer.Typer(help="Stream live public market updates")

app.add_typer(watchlists_app, name="watchlists")
app.add_typer(discover_app, name="discover")
app.add_typer(scheduler_app, name="scheduler")
app.add_typer(rank_app, name="rank")
app.add_typer(paper_app, name="paper")
app.add_typer(stream_app, name="stream")

console = Console()


@app.callback()
def main_callback(
    ctx: typer.Context,
    label: str | None = typer.Option(
        None, "--label", "-l",
        help="Start the REPL focused on a label.",
    ),
) -> None:
    """Polymarket CLI — launch without a subcommand to enter the interactive REPL."""
    if ctx.invoked_subcommand is None:
        launch_repl(label=label)

def build_runtime() -> tuple:
    settings = get_settings()
    sqlite_store = SQLiteStore(settings.database_path)
    csv_store = CSVStore(settings.raw_data_path, settings.processed_data_path, settings.exports_path)
    return settings, sqlite_store, csv_store


def build_discovery_service() -> tuple:
    settings, sqlite_store, csv_store = build_runtime()
    gamma = GammaClient(settings.gamma_base_url)
    discovery = DiscoveryService(gamma, csv_store, sqlite_store)
    return settings, sqlite_store, csv_store, gamma, discovery


def launch_repl(label: str | None = None) -> None:
    settings, sqlite_store, csv_store = build_runtime()
    sync_watchlists_to_store(settings, sqlite_store)
    repl = ReplApp(
        settings=settings,
        sqlite_store=sqlite_store,
        csv_store=csv_store,
        label=label,
    )
    repl.run()


def sync_watchlists_to_store(settings, sqlite_store: SQLiteStore) -> list[WatchlistConfig]:
    watchlists = load_watchlists(settings.watchlists_path)
    sqlite_store.sync_watchlists(watchlists)
    return watchlists


def prompt_text(value: str | None, label: str, default: str | None = None) -> str:
    if value is not None:
        return value
    if default is None:
        return typer.prompt(label)
    return typer.prompt(label, default=default)


def prompt_int(value: int | None, label: str, default: int) -> int:
    if value is not None:
        return value
    return typer.prompt(label, default=default, type=int)


def prompt_bool(value: bool | None, label: str, default: bool) -> bool:
    if value is not None:
        return value
    return typer.confirm(label, default=default)


def build_watchlist_from_inputs(
    *,
    existing: WatchlistConfig | None,
    name: str | None,
    keywords: str | None,
    poll_minutes: int | None,
    limit: int | None,
    live_only: bool | None,
    include_closed: bool | None,
    enabled: bool | None,
    tags: str | None,
    prompt_file: str | None,
) -> WatchlistConfig:
    baseline = existing or WatchlistConfig(name="", keywords=[])
    resolved_name = prompt_text(name, "Watchlist name", baseline.name or None)
    resolved_keywords = parse_csv_list(
        prompt_text(
            keywords,
            "Keywords (comma-separated)",
            ", ".join(baseline.keywords) or None,
        )
    )
    return WatchlistConfig(
        name=resolved_name,
        keywords=resolved_keywords,
        poll_minutes=prompt_int(poll_minutes, "Poll interval in minutes", baseline.poll_minutes),
        limit=prompt_int(limit, "Discovery limit", baseline.limit),
        live_only=prompt_bool(live_only, "Restrict to live events?", baseline.live_only),
        include_closed=prompt_bool(
            include_closed,
            "Include closed events?",
            baseline.include_closed,
        ),
        enabled=prompt_bool(enabled, "Enable this job?", baseline.enabled),
        tags=parse_csv_list(prompt_text(tags, "Tags (comma-separated)", ", ".join(baseline.tags))),
        prompt_file=prompt_text(prompt_file, "Prompt file", baseline.prompt_file),
    )


def render_stream_table(messages: list[dict]) -> Table:
    table = Table(title="Polymarket Live Feed", expand=True)
    table.add_column("Type", style="bold cyan")
    table.add_column("Asset/Market", style="yellow")
    table.add_column("Details", style="white")
    for payload in messages[-20:]:
        table.add_row(
            str(payload.get("event_type") or payload.get("type") or "message"),
            str(payload.get("asset_id") or payload.get("market") or payload.get("condition_id") or "-"),
            str(payload)[:160],
        )
    return table


@app.command()
def version() -> None:
    """Print the application version."""
    console.print("polymarket-cli 0.1.0")


@app.command()
def tui(label: str | None = typer.Option(None, help="Limit dashboard to one watchlist label.")) -> None:
    """Launch the interactive CLI."""
    launch_repl(label=label)


@app.command("console")
def console_app(label: str | None = typer.Option(None, help="Limit dashboard to one watchlist label.")) -> None:
    """Launch the interactive CLI (alias of tui)."""
    launch_repl(label=label)


@watchlists_app.command("list")
def list_watchlists() -> None:
    """List watchlists from configuration and sync them to SQLite."""
    settings, sqlite_store, _csv_store = build_runtime()
    watchlists = sync_watchlists_to_store(settings, sqlite_store)
    table = Table(title="Configured Watchlists")
    table.add_column("Name")
    table.add_column("Keywords")
    table.add_column("Every")
    table.add_column("Enabled")
    for watchlist in watchlists:
        table.add_row(
            watchlist.name,
            ", ".join(watchlist.keywords),
            f"{watchlist.poll_minutes}m",
            "yes" if watchlist.enabled else "no",
        )
    console.print(table)


@watchlists_app.command("add")
def add_watchlist(
    name: str | None = typer.Option(None, "--name", help="Watchlist name."),
    keywords: str | None = typer.Option(None, "--keywords", help="Comma-separated keywords."),
    poll_minutes: int | None = typer.Option(None, "--poll-minutes", min=1, help="Polling cadence in minutes."),
    limit: int | None = typer.Option(None, "--limit", min=1, max=200, help="Discovery limit."),
    live_only: bool | None = typer.Option(None, "--live-only/--all-events", help="Restrict to live events."),
    include_closed: bool | None = typer.Option(None, "--include-closed/--exclude-closed", help="Include closed events."),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Enable the watchlist job."),
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated tags."),
    prompt_file: str | None = typer.Option(None, "--prompt-file", help="Prompt template filename."),
) -> None:
    """Create a watchlist interactively and persist it to YAML."""
    settings, sqlite_store, _csv_store = build_runtime()
    watchlist = build_watchlist_from_inputs(
        existing=None,
        name=name,
        keywords=keywords,
        poll_minutes=poll_minutes,
        limit=limit,
        live_only=live_only,
        include_closed=include_closed,
        enabled=enabled,
        tags=tags,
        prompt_file=prompt_file,
    )
    if get_watchlist(settings.watchlists_path, watchlist.name) is not None:
        raise typer.BadParameter(f"Watchlist already exists: {watchlist.name}")
    upsert_watchlist(settings.watchlists_path, watchlist)
    sync_watchlists_to_store(settings, sqlite_store)
    console.print(f"Saved watchlist {watchlist.name}")


@watchlists_app.command("edit")
def edit_watchlist(
    name: str = typer.Argument(..., help="Existing watchlist name."),
    new_name: str | None = typer.Option(None, "--name", help="New watchlist name."),
    keywords: str | None = typer.Option(None, "--keywords", help="Comma-separated keywords."),
    poll_minutes: int | None = typer.Option(None, "--poll-minutes", min=1, help="Polling cadence in minutes."),
    limit: int | None = typer.Option(None, "--limit", min=1, max=200, help="Discovery limit."),
    live_only: bool | None = typer.Option(None, "--live-only/--all-events", help="Restrict to live events."),
    include_closed: bool | None = typer.Option(None, "--include-closed/--exclude-closed", help="Include closed events."),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Enable the watchlist job."),
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated tags."),
    prompt_file: str | None = typer.Option(None, "--prompt-file", help="Prompt template filename."),
) -> None:
    """Edit a watchlist interactively and persist the update to YAML."""
    settings, sqlite_store, _csv_store = build_runtime()
    existing = get_watchlist(settings.watchlists_path, name)
    if existing is None:
        raise typer.BadParameter(f"Unknown watchlist: {name}")
    updated = build_watchlist_from_inputs(
        existing=existing,
        name=new_name,
        keywords=keywords,
        poll_minutes=poll_minutes,
        limit=limit,
        live_only=live_only,
        include_closed=include_closed,
        enabled=enabled,
        tags=tags,
        prompt_file=prompt_file,
    )
    replace_watchlist(settings.watchlists_path, name, updated)
    sync_watchlists_to_store(settings, sqlite_store)
    console.print(f"Updated watchlist {name} -> {updated.name}")


@watchlists_app.command("remove")
def delete_watchlist(
    name: str = typer.Argument(..., help="Watchlist name to remove."),
    yes: bool = typer.Option(False, "--yes", help="Remove without confirmation."),
) -> None:
    """Remove a watchlist and delete the corresponding scheduled job state."""
    settings, sqlite_store, _csv_store = build_runtime()
    if not yes and not typer.confirm(f"Remove watchlist {name}?", default=False):
        raise typer.Exit(code=0)
    if not remove_watchlist(settings.watchlists_path, name):
        raise typer.BadParameter(f"Unknown watchlist: {name}")
    sync_watchlists_to_store(settings, sqlite_store)
    console.print(f"Removed watchlist {name}")


@watchlists_app.command("enable")
def enable_watchlist(name: str = typer.Argument(..., help="Watchlist name.")) -> None:
    """Enable a configured watchlist/job."""
    settings, sqlite_store, _csv_store = build_runtime()
    if not set_watchlist_enabled(settings.watchlists_path, name, True):
        raise typer.BadParameter(f"Unknown watchlist: {name}")
    sync_watchlists_to_store(settings, sqlite_store)
    console.print(f"Enabled watchlist {name}")


@watchlists_app.command("disable")
def disable_watchlist(name: str = typer.Argument(..., help="Watchlist name.")) -> None:
    """Disable a configured watchlist/job."""
    settings, sqlite_store, _csv_store = build_runtime()
    if not set_watchlist_enabled(settings.watchlists_path, name, False):
        raise typer.BadParameter(f"Unknown watchlist: {name}")
    sync_watchlists_to_store(settings, sqlite_store)
    console.print(f"Disabled watchlist {name}")


@discover_app.command("keywords")
def discover_keywords(
    keywords: list[str] = typer.Argument(..., help="Keyword list for discovery."),
    label: str = typer.Option("adhoc", help="Label used for snapshot output folders."),
    limit: int = typer.Option(25, min=1, max=200, help="Maximum events to keep."),
) -> None:
    """Run discovery for an ad-hoc keyword set and persist CSV snapshots."""

    async def _run() -> None:
        settings, sqlite_store, csv_store, gamma, discovery = build_discovery_service()
        del settings, sqlite_store, csv_store
        try:
            snapshot = await discovery.run_keywords(label=label, keywords=keywords, limit=limit)
            console.print(f"Saved discovery snapshot {snapshot.run_id}")
            console.print(f"Events CSV: {snapshot.events_csv_path}")
            console.print(f"Markets CSV: {snapshot.markets_csv_path}")
            console.print(f"Raw JSON: {snapshot.raw_path}")
        finally:
            await gamma.close()

    anyio.run(_run)


@app.command("run-job")
def run_job(name: str = typer.Argument(..., help="Watchlist name to execute once.")) -> None:
    """Run a configured watchlist once."""

    async def _run() -> None:
        settings, sqlite_store, csv_store, gamma, discovery = build_discovery_service()
        scheduler = SchedulerService(settings.watchlists_path, discovery, sqlite_store)
        try:
            completed = await scheduler.run_once(job_name=name)
            if not completed:
                raise typer.Exit(code=1)
            console.print(f"Completed watchlist: {', '.join(completed)}")
        finally:
            await gamma.close()

    anyio.run(_run)


@scheduler_app.command("once")
def scheduler_once(name: str | None = typer.Option(None, help="Optional watchlist name filter.")) -> None:
    """Run enabled watchlists once."""

    async def _run() -> None:
        settings, sqlite_store, csv_store, gamma, discovery = build_discovery_service()
        scheduler = SchedulerService(settings.watchlists_path, discovery, sqlite_store)
        try:
            completed = await scheduler.run_once(job_name=name)
            console.print(f"Executed {len(completed)} jobs")
        finally:
            await gamma.close()

    anyio.run(_run)


@scheduler_app.command("start")
def scheduler_start(
    name: str | None = typer.Option(None, help="Optional watchlist name filter."),
    cycles: int | None = typer.Option(None, help="Stop after N scheduler ticks for local testing."),
    tick_seconds: int = typer.Option(15, min=5, help="Scheduler wakeup interval."),
) -> None:
    """Start the internal recurring scheduler."""

    async def _run() -> None:
        settings, sqlite_store, csv_store, gamma, discovery = build_discovery_service()
        scheduler = SchedulerService(settings.watchlists_path, discovery, sqlite_store)
        try:
            await scheduler.run_loop(job_name=name, cycles=cycles, tick_seconds=tick_seconds)
        finally:
            await gamma.close()

    anyio.run(_run)


@scheduler_app.command("install")
def scheduler_install(name: str = typer.Argument(..., help="Watchlist name to install into launchd.")) -> None:
    """Install a watchlist as a macOS launchd job."""
    settings, sqlite_store, _csv_store = build_runtime()
    watchlists = sync_watchlists_to_store(settings, sqlite_store)
    watchlist = next((item for item in watchlists if item.name == name), None)
    if watchlist is None:
        raise typer.BadParameter(f"Unknown watchlist: {name}")
    service = LaunchdService(settings.workdir.resolve())
    path = service.install(watchlist)
    console.print(f"Installed launchd job: {path}")


@scheduler_app.command("jobs")
def scheduler_jobs() -> None:
    """List the scheduler jobs currently synced into SQLite."""
    settings, sqlite_store, _csv_store = build_runtime()
    sync_watchlists_to_store(settings, sqlite_store)
    rows = sqlite_store.list_watch_jobs()
    table = Table(title="Scheduler Jobs")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Enabled")
    for row in rows:
        table.add_row(row.name, row.schedule, "yes" if row.enabled else "no")
    console.print(table)


@scheduler_app.command("remove")
def scheduler_remove(name: str = typer.Argument(..., help="Watchlist name to remove from launchd.")) -> None:
    """Remove a launchd job for a watchlist."""
    settings, _sqlite_store, _csv_store = build_runtime()
    service = LaunchdService(settings.workdir.resolve())
    path = service.remove(name)
    console.print(f"Removed launchd job: {path}")


@rank_app.command("latest")
def rank_latest(
    label: str = typer.Argument(..., help="Watchlist/discovery label."),
    provider: str = typer.Option("ollama", help="ollama or openrouter"),
    prompt_file: str | None = typer.Option(
        None,
        help="Prompt file inside config/prompts. Defaults to the watchlist prompt_file when available.",
    ),
    dry_run: bool = typer.Option(False, help="Use heuristic ranking without calling an LLM."),
    max_rows: int | None = typer.Option(
        None,
        min=1,
        help="Maximum CSV rows to send to the ranking prompt. Defaults to POLYMARKET_RANKING_MAX_ROWS.",
    ),
) -> None:
    """Rank the latest discovery CSV for a label."""

    async def _run() -> None:
        settings, sqlite_store, csv_store = build_runtime()
        latest = sqlite_store.latest_discovery_run(label)
        if latest is None or not latest["events_csv_path"]:
            raise typer.BadParameter(f"No discovery run found for label: {label}")
        ranking_service = RankingService(settings, csv_store, sqlite_store)
        watchlist = get_watchlist(settings.watchlists_path, label)
        resolved_prompt_file = prompt_file or (
            watchlist.prompt_file if watchlist is not None else "default-ranking.md"
        )
        prompt_path = settings.prompts_path / resolved_prompt_file
        if not prompt_path.exists():
            raise typer.BadParameter(f"Prompt file not found: {resolved_prompt_file}")
        run_id, ranking, report_path = await ranking_service.rank_csv(
            label=label,
            csv_path=Path(latest["events_csv_path"]),
            prompt_path=prompt_path,
            provider=provider,
            dry_run=dry_run,
            max_rows=max_rows,
        )
        table = Table(title=f"Ranking {label}")
        table.add_column("Event")
        table.add_column("Score")
        table.add_column("Action")
        table.add_column("Confidence")
        for item in ranking.shortlist:
            table.add_row(item.title[:60], str(item.score), item.action, str(item.confidence or ""))
        console.print(table)
        console.print(f"Run ID: {run_id}")
        console.print(f"Provider: {ranking.provider} ({ranking.model})")
        console.print(f"Prompt: {resolved_prompt_file}")
        console.print(f"Summary: {ranking.summary}")
        console.print(f"Report: {report_path}")

    anyio.run(_run)


@paper_app.command("enter")
def paper_enter(
    event_id: str = typer.Option(..., help="Event id."),
    market_id: str = typer.Option(..., help="Market id."),
    outcome: str = typer.Option(..., help="Outcome label, e.g. Yes/No."),
    side: str = typer.Option("buy", help="buy or sell."),
    size: float = typer.Option(..., min=0.0, help="Position size."),
    price: float | None = typer.Option(None, help="Entry price. If omitted, infer from latest markets CSV."),
    label: str | None = typer.Option(None, help="Label used to infer price from latest discovery CSV."),
) -> None:
    """Open a paper position."""
    settings, sqlite_store, _csv_store = build_runtime()
    if price is None:
        latest = sqlite_store.latest_discovery_run(label)
        if latest is None or not latest["markets_csv_path"]:
            raise typer.BadParameter("Price not provided and no markets CSV available to infer it")
        price = infer_market_price(Path(latest["markets_csv_path"]), market_id)
    if price is None:
        raise typer.BadParameter("Unable to infer a market price for the provided market_id")

    broker = PaperBroker(sqlite_store)
    position = broker.open_position(
        event_id=event_id,
        market_id=market_id,
        outcome=outcome,
        side=side,
        size=size,
        entry_price=price,
    )
    console.print(f"Opened paper position {position.position_id} at {price:.4f}")


@paper_app.command("positions")
def paper_positions(include_closed: bool = typer.Option(False, help="Include closed positions.")) -> None:
    """List paper positions and current PnL."""
    settings, sqlite_store, _csv_store = build_runtime()
    del settings
    broker = PaperBroker(sqlite_store)
    rows = broker.list_positions(include_closed=include_closed)
    table = Table(title="Paper Positions")
    table.add_column("Position")
    table.add_column("Market")
    table.add_column("Side")
    table.add_column("Entry")
    table.add_column("Current")
    table.add_column("PnL")
    table.add_column("Status")
    for row in rows:
        table.add_row(
            row["position_id"],
            row["market_id"],
            row["side"],
            f"{row['entry_price']:.4f}",
            f"{row['current_price']:.4f}",
            f"{row['pnl']:.4f}",
            row["status"],
        )
    console.print(table)


@paper_app.command("close")
def paper_close(
    position_id: str = typer.Argument(..., help="Paper position id."),
    exit_price: float = typer.Option(..., help="Exit price."),
) -> None:
    """Close an existing paper position."""
    settings, sqlite_store, _csv_store = build_runtime()
    del settings
    broker = PaperBroker(sqlite_store)
    broker.close_position(position_id, exit_price)
    console.print(f"Closed position {position_id} at {exit_price:.4f}")


@stream_app.command("latest")
def stream_latest(
    label: str = typer.Argument(..., help="Watchlist/discovery label."),
    limit: int = typer.Option(20, min=1, max=200, help="Max asset ids to subscribe to."),
    max_messages: int | None = typer.Option(None, help="Stop after N messages."),
) -> None:
    """Stream public websocket updates for the latest discovery snapshot."""

    async def _run() -> None:
        settings, sqlite_store, _csv_store = build_runtime()
        del settings
        latest = sqlite_store.latest_discovery_run(label)
        if latest is None or not latest["markets_csv_path"]:
            raise typer.BadParameter(f"No discovery markets CSV found for label: {label}")
        asset_ids = load_asset_ids(Path(latest["markets_csv_path"]), limit=limit)
        if not asset_ids:
            raise typer.BadParameter("No asset ids found in the latest markets CSV")

        client = MarketStreamClient()
        messages: list[dict] = []

        async def on_message(payload: dict) -> None:
            messages.append(payload)
            live.update(render_stream_table(messages))

        with Live(render_stream_table(messages), console=console, refresh_per_second=4) as live:
            await client.stream_assets(asset_ids, on_message=on_message, max_messages=max_messages)

    anyio.run(_run)


if __name__ == "__main__":
    app()
