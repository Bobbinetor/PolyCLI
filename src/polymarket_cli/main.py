import asyncio
import logging
from typing import Annotated

import typer
from rich.console import Console

from polymarket_cli.clients.gamma import GammaClient
from polymarket_cli.config import Settings, get_settings, load_watchlists
from polymarket_cli.repl.app import ReplApp
from polymarket_cli.services.discovery import DiscoveryService
from polymarket_cli.services.ranking import RankingService
from polymarket_cli.storage.sqlite import SQLiteStore


logging.basicConfig(level=logging.INFO, format="%(message)s")
console = Console()
app = typer.Typer(
    help="PolyCLI — Investigative observatory for Polymarket.",
    invoke_without_command=True,
    add_completion=False,
)


def version_callback(value: bool) -> None:
    if value:
        console.print("polycli 0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    label: Annotated[
        str | None,
        typer.Option(
            "--label", "-l",
            help="Start the REPL focused on a label.",
        ),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """PolyCLI — launch without a subcommand to enter the interactive REPL."""
    if ctx.invoked_subcommand is None:
        launch_repl(label=label)


def build_runtime() -> tuple[Settings, SQLiteStore]:
    settings = get_settings()
    sqlite_store = SQLiteStore(settings.database_path)
    return settings, sqlite_store


def launch_repl(label: str | None = None) -> None:
    settings, sqlite_store = build_runtime()
    watchlists = load_watchlists(settings.watchlists_path)
    sqlite_store.sync_watchlists(watchlists)
    repl = ReplApp(
        settings=settings,
        sqlite_store=sqlite_store,
        label=label,
    )
    repl.run()


@app.command()
def discover(
    keywords: Annotated[list[str], typer.Argument(help="Keywords to search for")],
    label: Annotated[str, typer.Option("--label", "-l", help="Label for this discovery run")] = "cli",
    limit: Annotated[int, typer.Option("--limit", help="Max events to fetch")] = 25,
) -> None:
    """Run a one-off discovery and save the snapshot to the database."""
    settings, sqlite_store = build_runtime()
    gamma = GammaClient(settings.gamma_base_url)
    discovery = DiscoveryService(gamma, sqlite_store)
    
    with console.status(f"Discovering '{', '.join(keywords)}'..."):
        snapshot = asyncio.run(discovery.run_keywords(label, keywords, limit=limit))
    
    console.print(f"[green]✓[/green] Saved snapshot [bold]{snapshot.run_id}[/bold] with {len(snapshot.events)} events.")


@app.command()
def rank(
    run_id: Annotated[str, typer.Argument(help="Run ID of the discovery to rank")],
    provider: Annotated[str, typer.Option("--provider", "-p", help="LLM provider (ollama, openrouter)")] = "ollama",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Use heuristic ranking without LLM")] = False,
) -> None:
    """Rank a discovery snapshot using an LLM provider."""
    settings, sqlite_store = build_runtime()
    ranking_service = RankingService(settings, sqlite_store)
    
    with console.status(f"Ranking snapshot {run_id} via {provider}..."):
        result = asyncio.run(
            ranking_service.rank_run(
                run_id=run_id,
                prompt_path=settings.prompts_dir / "prompt-example.md",
                provider=provider,
                dry_run=dry_run,
            )
        )
    
    console.print(f"[green]✓[/green] Ranked via {result.provider} ({result.model})")
    console.print(f"\n[bold]Summary:[/bold] {result.summary}")
    console.print("\n[bold]Top Picks:[/bold]")
    for item in result.shortlist[:5]:
        color = "red" if item.action.endswith("no") else "green" if item.action.endswith("yes") else "yellow"
        console.print(f"- [bold]{item.score}[/bold] | [{color}]{item.action}[/{color}] | {item.title}")


if __name__ == "__main__":
    app()
