"""Rich rendering utilities for the inline REPL.

Every command renders its output inline using Rich Tables, Panels, and
markup.  This module collects the reusable renderers so that command
handlers stay lean.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Generator
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ── Shared console ───────────────────────────────────────────────────

THEME = Theme(
    {
        "pm.accent": "bold #d8a03a",
        "pm.muted": "#6b7280",
        "pm.success": "bold #22c55e",
        "pm.error": "bold #ef4444",
        "pm.warn": "bold #f59e0b",
        "pm.info": "bold #3b82f6",
        "pm.label": "bold #a78bfa",
        "pm.cmd": "bold #f472b6",
        "pm.dim": "dim",
        "pm.header": "bold #f4ead6",
    }
)

console = Console(theme=THEME, highlight=False, force_terminal=True)


# ── Micro-helpers ────────────────────────────────────────────────────


def success(message: str) -> None:
    console.print(f"  [pm.success]✓[/] {message}")


def error(message: str) -> None:
    console.print(f"  [pm.error]✗[/] {message}")


def warn(message: str) -> None:
    console.print(f"  [pm.warn]⚠[/] {message}")


def info(message: str) -> None:
    console.print(f"  [pm.muted]→[/] {message}")


def muted(message: str) -> None:
    console.print(f"  [pm.muted]{escape(message)}[/]")


def blank() -> None:
    console.print()


# ── Animated spinner (Claude Code-style) ─────────────────────────────

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class _TimerSpinnerRenderable:
    def __init__(self, message: str):
        from rich.spinner import Spinner
        self.message = message
        self.start_time = time.monotonic()
        self.spinner = Spinner("dots")

    def __rich__(self) -> Text:
        elapsed = time.monotonic() - self.start_time
        return Text.assemble(
            "  ", self.spinner.render(time.monotonic()), " ",
            (self.message, "pm.muted"),
            (f" ({elapsed:.0f}s)", "pm.dim")
        )

@contextlib.contextmanager
def spinner(message: str) -> Generator[None, None, None]:
    """Animated inline spinner using Rich Live for maximum reliability."""
    from rich.live import Live
    
    renderable = _TimerSpinnerRenderable(message)
    with Live(renderable, refresh_per_second=12, transient=True, console=console):
        yield


# ── Welcome ──────────────────────────────────────────────────────────


LOGO = r"""
[pm.accent]    ____       _        [pm.header]____ _     ___ [/]
[pm.accent]   |  _ \ ___ | |_   _  [pm.header]/ ___| |   |_ _|[/]
[pm.accent]   | |_) / _ \| | | | | [pm.header]| |   | |    | | [/]
[pm.accent]   |  __/ (_) | | |_| | [pm.header]| |___| |___ | | [/]
[pm.accent]   |_|   \___/|_|\__, | [pm.header]\____|_____|___|[/]
[pm.accent]                 |___/  [/]"""


def render_welcome(
    version: str,
    label: str | None,
    llm: str,
) -> None:
    label_text = label or "none"
    console.print()
    console.print(LOGO)
    console.print()
    console.print(f"  [pm.header]Polymarket Observatory[/] [pm.muted]v{version}[/]")
    console.print(f"  [pm.muted]Label:[/] [pm.label]{label_text}[/] [pm.muted]· LLM:[/] {llm}")
    console.print()
    _render_commands_compact()
    console.print()


def _render_commands_compact() -> None:
    """Render a compact command overview shown on startup."""
    cmds = [
        ("/discover", "Run keyword discovery"),
        ("/rank", "Rank snapshot with LLM"),
        ("/watch", "Manage watchlists"),
        ("/job", "Run scheduler jobs"),
        ("/paper", "Paper trading"),
        ("/stream", "Live websocket feed"),
        ("/status", "Session status"),
        ("/label", "Set active label"),
        ("/help", "Full command reference"),
        ("/quit", "Exit"),
    ]
    left = cmds[:5]
    right = cmds[5:]

    for i in range(max(len(left), len(right))):
        line = "  "
        if i < len(left):
            cmd, desc = left[i]
            line += f"[pm.accent]{cmd:<14}[/][pm.muted]{desc:<26}[/]"
        else:
            line += " " * 40
        if i < len(right):
            cmd, desc = right[i]
            line += f"[pm.accent]{cmd:<14}[/][pm.muted]{desc}[/]"
        console.print(line)


# ── /help ────────────────────────────────────────────────────────────


def render_help(specs: list[tuple[str, str, str]]) -> None:
    """Render full command reference with usage examples."""
    console.print()
    console.print("  [pm.header]Available Commands[/]")
    console.print()
    for name, usage, summary in specs:
        console.print(
            f"  [pm.accent]{name:<14}[/]"
            f"[pm.muted]{summary}[/]"
        )
        console.print(
            f"  {'':14}[dim]{usage}[/]"
        )
    console.print()


def render_detailed_help(
    name: str,
    desc: str,
    usage: str,
    options: list[tuple[str, str]],
    examples: list[str],
) -> None:
    console.print()
    console.print(f"  [pm.header]Command:[/] [pm.accent]/{name}[/]")
    console.print(f"  [pm.muted]{desc}[/]")
    console.print()
    console.print("  [pm.header]Syntax:[/]")
    console.print(f"  [pm.success]{usage}[/]")
    
    if options:
        console.print()
        console.print("  [pm.header]Options & Arguments:[/]")
        for opt, opt_desc in options:
            console.print(f"    [pm.accent]{opt:<15}[/] [pm.muted]{opt_desc}[/]")
            
    if examples:
        console.print()
        console.print("  [pm.header]Examples:[/]")
        for ex in examples:
            console.print(f"    [dim]{ex}[/]")
    console.print()


# ── /status ──────────────────────────────────────────────────────────


def render_status(
    *,
    label: str | None,
    stream_state: str,
    stream_count: int,
    llm: str,
    version: str,
) -> None:
    label_text = label or "—"
    console.print()
    console.print("  [pm.header]Session Status[/]")
    console.print()
    console.print(
        f"  [pm.muted]Label    [/] [pm.label]{label_text}[/]"
    )
    console.print(
        f"  [pm.muted]Stream   [/] {stream_state}"
        f" · {stream_count} messages"
    )
    console.print(f"  [pm.muted]LLM      [/] {llm}")
    console.print(f"  [pm.muted]Version  [/] {version}")
    console.print()


# ── /data ────────────────────────────────────────────────────────────


def render_snapshots(runs: list[dict[str, Any]]) -> None:
    """Render list of saved discovery snapshots."""
    table = Table(
        title="[pm.accent]Saved Snapshots[/]",
        border_style="#3b4a5c",
        title_style="pm.accent",
        header_style="bold #e5e7eb",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Run ID", style="pm.accent")
    table.add_column("Label", style="pm.label")
    table.add_column("Keywords")
    table.add_column("Events", justify="right")
    table.add_column("Created At", style="pm.muted")

    for run in runs:
        kws = run["keywords"]
        kw_text = ", ".join(kws) if isinstance(kws, list) else str(kws)
        table.add_row(
            run["run_id"],
            run["label"],
            kw_text,
            str(run["event_count"]),
            run["created_at"],
        )
    console.print()
    console.print(table)
    console.print()


# ── /discover ────────────────────────────────────────────────────────


def render_events_table(
    events: list[dict[str, Any]],
    title: str = "Events Discovered",
) -> None:
    if not events:
        muted("No events to display.")
        return
    table = Table(
        title=f"[pm.accent]{title}[/]",
        border_style="#3b4a5c",
        title_style="pm.accent",
        header_style="bold #e5e7eb",
        expand=True,
        padding=(0, 1),
    )
    table.add_column(
        "Title", ratio=4, no_wrap=True, overflow="ellipsis",
    )
    table.add_column("Category", ratio=1, style="pm.muted")
    table.add_column("Volume", ratio=1, justify="right")
    table.add_column("Liquidity", ratio=1, justify="right")
    table.add_column("Live", ratio=0, justify="center")
    for row in events[:25]:
        volume = row.get("volume")
        liquidity = row.get("liquidity")
        live = row.get("live", False)
        table.add_row(
            str(row.get("title", ""))[:60],
            str(row.get("category", "-")),
            _format_number(volume),
            _format_number(liquidity),
            "[pm.success]●[/]" if live else "[pm.muted]○[/]",
        )
    console.print()
    console.print(table)
    console.print()


# ── /rank ────────────────────────────────────────────────────────────


def render_ranking_table(
    shortlist: list[Any],
    summary: str,
    provider: str,
    model: str,
) -> None:
    if not shortlist:
        muted("No ranking items to display.")
        return
    table = Table(
        title="[pm.accent]Ranking Results[/]",
        border_style="#3b4a5c",
        title_style="pm.accent",
        header_style="bold #e5e7eb",
        expand=True,
        padding=(0, 1),
    )
    table.add_column(
        "Event", ratio=4, no_wrap=True, overflow="ellipsis",
    )
    table.add_column(
        "Score", ratio=0, justify="right", style="pm.accent",
    )
    table.add_column("Action", ratio=1)
    table.add_column("Confidence", ratio=0, justify="right")
    for item in shortlist:
        conf = item.confidence
        conf_text = f"{conf}%" if conf is not None else "-"
        table.add_row(
            item.title[:60],
            str(item.score),
            _colorize_action(item.action),
            conf_text,
        )
    console.print()
    console.print(table)
    console.print()
    console.print(Panel(
        Markdown(summary),
        title=f"[pm.accent]{provider}:{model}[/]",
        border_style="#3b4a5c"
    ))
    console.print()


# ── /watch list ──────────────────────────────────────────────────────


def render_watchlists(watchlists: list[Any]) -> None:
    if not watchlists:
        muted("No watchlists configured. Use /watch add")
        return
    table = Table(
        title="[pm.accent]Watchlists[/]",
        border_style="#3b4a5c",
        title_style="pm.accent",
        header_style="bold #e5e7eb",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Name", style="pm.label")
    table.add_column("Keywords")
    table.add_column("Every", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("On", justify="center")
    table.add_column("Prompt", style="pm.muted")
    for w in watchlists:
        table.add_row(
            w.name,
            ", ".join(w.keywords),
            f"{w.poll_minutes}m",
            str(w.limit),
            "[pm.success]●[/]" if w.enabled else "[pm.muted]○[/]",
            w.prompt_file,
        )
    console.print()
    console.print(table)
    console.print()


# ── /job list ────────────────────────────────────────────────────────


def render_jobs(jobs: list[Any]) -> None:
    if not jobs:
        muted("No scheduler jobs. Use /watch add first.")
        return
    table = Table(
        title="[pm.accent]Scheduler Jobs[/]",
        border_style="#3b4a5c",
        title_style="pm.accent",
        header_style="bold #e5e7eb",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Name", style="pm.label")
    table.add_column("Schedule")
    table.add_column("On", justify="center")
    for job in jobs:
        table.add_row(
            job.name,
            job.schedule,
            "[pm.success]●[/]" if job.enabled else "[pm.muted]○[/]",
        )
    console.print()
    console.print(table)
    console.print()


# ── /paper positions ─────────────────────────────────────────────────


def render_positions(positions: list[dict[str, Any]]) -> None:
    if not positions:
        muted("No paper positions.")
        return
    table = Table(
        title="[pm.accent]Paper Positions[/]",
        border_style="#3b4a5c",
        title_style="pm.accent",
        header_style="bold #e5e7eb",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Position")
    table.add_column("Market")
    table.add_column("Side")
    table.add_column("Entry", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("PnL", justify="right")
    table.add_column("Status", justify="center")
    for row in positions:
        pnl = row["pnl"]
        pnl_style = "pm.success" if pnl >= 0 else "pm.error"
        table.add_row(
            row["position_id"],
            row["market_id"],
            row["side"],
            f"{row['entry_price']:.4f}",
            f"{row['current_price']:.4f}",
            f"[{pnl_style}]{pnl:+.4f}[/]",
            row["status"],
        )
    console.print()
    console.print(table)
    console.print()


# ── /stream show ─────────────────────────────────────────────────────


def render_stream_messages(
    messages: list[dict[str, str]],
    limit: int = 20,
) -> None:
    if not messages:
        muted("No stream messages yet. Use /stream start")
        return
    table = Table(
        title="[pm.accent]Live Stream[/]",
        border_style="#3b4a5c",
        title_style="pm.accent",
        header_style="bold #e5e7eb",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Time", style="pm.muted", width=8)
    table.add_column("Type", width=12)
    table.add_column("Asset", width=20)
    table.add_column(
        "Details", ratio=1, no_wrap=True, overflow="ellipsis",
    )
    for row in list(messages)[:limit]:
        table.add_row(
            row["time"], row["type"], row["asset"], row["details"],
        )
    console.print()
    console.print(table)
    console.print()


# ── Private helpers ──────────────────────────────────────────────────


def _format_number(value: Any) -> str:
    if value is None:
        return "-"
    try:
        num = float(value)
    except (ValueError, TypeError):
        return str(value)
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return f"{num:.0f}"


def _colorize_action(action: str) -> str:
    lowered = action.lower()
    if "buy" in lowered or "enter" in lowered:
        return f"[pm.success]{escape(action)}[/]"
    if "sell" in lowered or "close" in lowered:
        return f"[pm.error]{escape(action)}[/]"
    if "monitor" in lowered or "watch" in lowered:
        return f"[pm.warn]{escape(action)}[/]"
    return action
