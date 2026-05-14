"""Slash command dispatch for the Polymarket REPL.

Each command handler receives the ``ReplApp`` host and renders results
inline via the ``renderer`` module.  This replaces the old TUI command
module with a design that fits the REPL interaction model.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from polymarket_cli.clients.gamma import GammaClient
from polymarket_cli.config import (
    WatchlistConfig,
    get_watchlist,
    load_watchlists,
    parse_csv_list,
    remove_watchlist,
    replace_watchlist,
    set_watchlist_enabled,
    upsert_watchlist,
)
from polymarket_cli.repl import renderer as R
from polymarket_cli.services.discovery import DiscoveryService
from polymarket_cli.services.paper_broker import PaperBroker, infer_market_price
from polymarket_cli.services.ranking import RankingService
from polymarket_cli.services.scheduler import SchedulerService

# ── Helpers ──────────────────────────────────────────────────────────

HELP_SPECS: list[tuple[str, str, str]] = [
    ("help", "/help", "Show available commands"),
    ("status", "/status", "Show current session status"),
    ("label", "/label <name|clear>", "Set or clear the active label"),
    ("discover", "/discover <kw...> [label= limit=]", "Run keyword discovery"),
    ("rank", "/rank [label= provider= dry_run=]", "Rank latest snapshot with LLM"),
    ("data", "/data [label=]", "Show saved snapshots and runs"),
    ("watch", "/watch <list|add|edit|enable|disable|remove>", "Manage watchlists"),
    ("job", "/job <list|run|once> [name]", "Inspect or run scheduler jobs"),
    ("paper", "/paper <positions|enter|close>", "Manage paper-trading positions"),
    ("stream", "/stream <start|stop|show>", "Control the live websocket stream"),
    ("clear", "/clear", "Clear the terminal screen"),
    ("quit", "/quit", "Exit the CLI"),
]

DETAILED_HELP = {
    "discover": {
        "desc": "Run keyword discovery against the Polymarket API.",
        "usage": "/discover <keywords...> [label=...] [limit=...]",
        "options": [
            ("keywords...", "One or more keywords to search for (e.g. bitcoin, fed)"),
            ("label=", "Optional label to group the discovered events. Defaults to 'interactive'"),
            ("limit=", "Max number of events to discover. Default is 25."),
        ],
        "examples": [
            "/discover bitcoin election",
            "/discover fed rates label=macro limit=10"
        ]
    },
    "rank": {
        "desc": "Rank the latest discovery snapshot with an LLM provider.",
        "usage": "/rank [label=...] [provider=...] [dry_run=true]",
        "options": [
            ("label=", "The snapshot label to rank. Defaults to active label."),
            ("provider=", "The LLM provider to use (ollama, openrouter). Defaults to ollama."),
            ("dry_run=", "If true, use heuristic ranking instead of LLM."),
            ("max_rows=", "Maximum number of events to send to the LLM."),
        ],
        "examples": [
            "/rank interactive",
            "/rank label=macro provider=openrouter"
        ]
    },
    "watch": {
        "desc": "Manage configured watchlists for recurring discovery.",
        "usage": "/watch <subcommand> [args...]",
        "options": [
            ("list", "List all configured watchlists."),
            ("add <name>", "Create a new watchlist. Provide keywords (space separated)."),
            ("edit <name>", "Modify an existing watchlist."),
            ("enable/disable", "Toggle the enabled state of a watchlist."),
            ("remove <name>", "Delete a watchlist entirely."),
        ],
        "examples": [
            "/watch list",
            "/watch add crypto bitcoin eth limit=10 every=15",
            "/watch disable crypto"
        ]
    },
    "job": {
        "desc": "Inspect or run scheduler jobs manually.",
        "usage": "/job <subcommand> [args...]",
        "options": [
            ("list", "List all active scheduler jobs."),
            ("run <name>", "Run a specific scheduler job manually."),
            ("once", "Run all enabled jobs once."),
        ],
        "examples": [
            "/job list",
            "/job run crypto"
        ]
    },
    "paper": {
        "desc": "Manage paper-trading positions.",
        "usage": "/paper <subcommand> [args...]",
        "options": [
            ("positions", "List all open paper positions."),
            ("enter", "Open a new position. Requires event=, market=, outcome=, size=."),
            ("close <id>", "Close an open position. Requires position ID and exit_price=."),
        ],
        "examples": [
            "/paper positions",
            "/paper enter event=1 market=2 outcome=Yes side=buy size=10 price=0.5",
            "/paper close 1 0.75"
        ]
    },
    "stream": {
        "desc": "Control the live websocket stream for the active snapshot.",
        "usage": "/stream <subcommand>",
        "options": [
            ("start", "Start streaming live updates for the current label's markets."),
            ("stop", "Stop the live stream."),
            ("show [limit]", "Show the most recent stream messages."),
        ],
        "examples": [
            "/stream start",
            "/stream show 50"
        ]
    },
    "label": {
        "desc": "Set or clear the active label for the session.",
        "usage": "/label <name|clear>",
        "options": [
            ("<name>", "Set the active label."),
            ("clear", "Clear the active label."),
        ],
        "examples": [
            "/label crypto",
            "/label clear"
        ]
    },
    "data": {
        "desc": "Show saved snapshots and data runs.",
        "usage": "/data [label=...]",
        "options": [
            ("label=", "Filter snapshots by label."),
        ],
        "examples": [
            "/data",
            "/data label=crypto"
        ]
    },
    "status": {
        "desc": "Show current session status.",
        "usage": "/status",
        "options": [],
        "examples": ["/status"]
    },
    "help": {
        "desc": "Show available commands.",
        "usage": "/help",
        "options": [],
        "examples": ["/help"]
    },
    "clear": {
        "desc": "Clear the terminal screen.",
        "usage": "/clear",
        "options": [],
        "examples": ["/clear"]
    },
    "quit": {
        "desc": "Exit the CLI.",
        "usage": "/quit",
        "options": [],
        "examples": ["/quit"]
    }
}

COMMAND_NAMES = {name for name, _, _ in HELP_SPECS}
ALIASES: dict[str, str] = {
    "?": "help", "exit": "help", "use": "label",
    "jobs": "job", "ls": "watch",
}


def _resolve(token: str) -> str | None:
    lowered = token.lower()
    if lowered in COMMAND_NAMES:
        return lowered
    if lowered in ALIASES:
        return ALIASES[lowered]
    matches = [n for n in COMMAND_NAMES if n.startswith(lowered)]
    return matches[0] if len(matches) == 1 else None


def _extract_options(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    options: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            key = token[2:].replace("-", "_")
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                options[key] = tokens[i + 1]
                i += 2
                continue
            options[key] = "true"
            i += 1
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            options[key.replace("-", "_").lower()] = value
        else:
            positional.append(token)
        i += 1
    return positional, options


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on", "y"}


def _int(v: str | None, default: int) -> int:
    return int(v) if v is not None else default


def _float(v: str | None, default: float | None = None) -> float | None:
    return float(v) if v is not None else default


def _sync_watchlists(host) -> list[WatchlistConfig]:
    watchlists = load_watchlists(host.settings.watchlists_path)
    host.sqlite_store.sync_watchlists(watchlists)
    return watchlists


def _build_watchlist(
    *, 
    name: str, 
    options: dict[str, str], 
    existing: WatchlistConfig | None, 
    extra_kws: list[str] | None = None
) -> WatchlistConfig:
    baseline = existing or WatchlistConfig(name=name, keywords=[])
    kw_raw = options.get("keywords")
    tags_raw = options.get("tags")
    
    kws = []
    if kw_raw is not None:
        kws.extend(parse_csv_list(kw_raw))
    elif not extra_kws:
        kws = baseline.keywords
        
    if extra_kws:
        kws.extend(extra_kws)

    return WatchlistConfig(
        name=options.get("name") or name,
        keywords=kws,
        poll_minutes=_int(
            options.get("every") or options.get("poll_minutes"),
            baseline.poll_minutes,
        ),
        limit=_int(options.get("limit"), baseline.limit),
        live_only=_bool(options.get("live"), baseline.live_only),
        include_closed=_bool(options.get("closed"), baseline.include_closed),
        enabled=_bool(options.get("enabled"), baseline.enabled),
        tags=parse_csv_list(tags_raw) if tags_raw is not None else baseline.tags,
        prompt_file=options.get("prompt") or options.get("prompt_file") or baseline.prompt_file,
    )


def _resolve_prompt_file(host, label: str | None, explicit: str | None) -> str:
    if explicit:
        return explicit
    if label:
        w = get_watchlist(host.settings.watchlists_path, label)
        if w is not None:
            return w.prompt_file
    return "default-ranking.md"


# ── Dispatch ─────────────────────────────────────────────────────────


async def dispatch(host, raw: str) -> None:
    """Parse and execute a slash command."""
    if not raw.startswith("/"):
        R.error("Commands must start with '/'. Try [pm.accent]/help[/].")
        return

    try:
        tokens = shlex.split(raw[1:])
    except ValueError as exc:
        R.error(f"Parse error: {exc}")
        return

    if not tokens:
        return

    name = _resolve(tokens[0])
    if name is None:
        R.error(f"Unknown command: {tokens[0]}. Try [pm.accent]/help[/].")
        return

    args = tokens[1:]

    # Intercept --help or -h for any command
    if "--help" in args or "-h" in args:
        if name in DETAILED_HELP:
            d = DETAILED_HELP[name]
            R.render_detailed_help(name, d["desc"], d["usage"], d["options"], d["examples"])
        else:
            spec = next((s for s in HELP_SPECS if s[0] == name), None)
            if spec:
                R.render_help([spec])
        return

    try:
        if name == "help":
            _cmd_help()
        elif name == "status":
            _cmd_status(host)
        elif name == "clear":
            _cmd_clear()
        elif name == "data":
            await _cmd_data(host, args)
        elif name == "quit":
            raise SystemExit
        elif name == "label":
            _cmd_label(host, args)
        elif name == "discover":
            await _cmd_discover(host, args)
        elif name == "rank":
            await _cmd_rank(host, args)
        elif name == "watch":
            _cmd_watch(host, args)
        elif name == "job":
            await _cmd_job(host, args)
        elif name == "paper":
            _cmd_paper(host, args)
        elif name == "stream":
            await _cmd_stream(host, args)
    except SystemExit:
        raise
    except Exception as exc:
        R.error(str(exc))


# ── Command implementations ─────────────────────────────────────────


def _cmd_help() -> None:
    R.render_help(HELP_SPECS)


def _cmd_status(host) -> None:
    R.render_status(
        label=host.current_label,
        stream_state=host.stream_status,
        stream_count=len(host.stream_messages),
        llm=host.llm_state,
        version="0.1.0",
    )


def _cmd_clear() -> None:
    R.console.clear()


def _cmd_label(host, args: list[str]) -> None:
    positional, options = _extract_options(args)
    if positional and positional[0].lower() == "clear":
        host.set_label(None)
        R.success("Label cleared. Following the latest run overall.")
        return
    next_label = options.get("label") or (positional[0] if positional else None)
    if not next_label:
        if host.current_label:
            R.info(f"Current label: [pm.label]{host.current_label}[/]")
        else:
            R.info(
                "No active label. Usage: [pm.accent]/label <name>[/]"
                " or [pm.accent]/label clear[/]"
            )
        return
    host.set_label(next_label)
    R.success(f"Active label set to [pm.label]{next_label}[/]")


async def _cmd_discover(host, args: list[str]) -> None:
    positional, options = _extract_options(args)
    keywords = positional
    if not keywords:
        R.error("Usage: [pm.accent]/discover <keywords...> [label=smoke] [limit=5][/]")
        return

    label = options.get("label") or host.current_label or "interactive"
    limit = _int(options.get("limit"), 25)

    kw_text = ', '.join(keywords)
    R.info(
        f"Discovering [pm.accent]{kw_text}[/]"
        f" → label=[pm.label]{label}[/] limit={limit}"
    )
    with R.spinner("Running discovery..."):
        async with GammaClient(host.settings.gamma_base_url) as gamma:
            discovery = DiscoveryService(gamma, host.csv_store, host.sqlite_store)
            snapshot = await discovery.run_keywords(label=label, keywords=keywords, limit=limit)

    host.set_label(label)
    R.success(
        f"Snapshot [pm.accent]{snapshot.run_id}[/] saved — "
        f"{len(snapshot.events)} events"
    )

    # Render the events table inline
    import polars as pl

    if snapshot.events_csv_path and Path(snapshot.events_csv_path).exists():
        frame = pl.read_csv(snapshot.events_csv_path).head(25)
        R.render_events_table(frame.to_dicts(), title=f"Discovery: {label}")


async def _cmd_data(host, args: list[str]) -> None:
    """Show saved snapshots and data runs."""
    positional, options = _extract_options(args)
    label = options.get("label") or (positional[0] if positional else None)

    runs = host.sqlite_store.list_discovery_runs(label=label)
    if not runs:
        R.warn("No snapshots found" + (f" for label {label}" if label else ""))
        return

    R.render_snapshots(runs)


async def _cmd_rank(host, args: list[str]) -> None:
    positional, options = _extract_options(args)
    label = options.get("label") or (positional[0] if positional else host.current_label)
    if not label:
        latest = host.sqlite_store.latest_discovery_run()
        label = str(latest["label"]) if latest is not None else None
    if not label:
        R.error("Usage: [pm.accent]/rank [label=smoke] [provider=ollama] [dry_run=true][/]")
        return

    provider = options.get("provider", "ollama")
    dry_run = _bool(options.get("dry_run") or options.get("dry"), False)
    max_rows = _int(options.get("max_rows"), host.settings.ranking_max_rows)
    explicit_prompt = options.get("prompt") or options.get("prompt_file")
    prompt_file = _resolve_prompt_file(host, label, explicit_prompt)
    prompt_path = host.settings.prompts_path / prompt_file
    if not prompt_path.exists():
        R.error(f"Prompt file not found: {prompt_file}")
        return

    latest = host.sqlite_store.latest_discovery_run(label)
    if latest is None or not latest["events_csv_path"]:
        R.error(f"No discovery snapshot found for label [pm.label]{label}[/]")
        return

    mode = "heuristic" if dry_run else f"{provider}"
    R.info(f"Ranking [pm.label]{label}[/] via [pm.accent]{mode}[/] (max_rows={max_rows})")

    with R.spinner(f"Ranking via {mode}..."):
        ranking_service = RankingService(host.settings, host.csv_store, host.sqlite_store)
        run_id, ranking, report_path = await ranking_service.rank_csv(
            label=label,
            csv_path=Path(latest["events_csv_path"]),
            prompt_path=prompt_path,
            provider=provider,
            dry_run=dry_run,
            max_rows=max_rows,
        )

    host.set_label(label)
    host.llm_state = f"{ranking.provider}:{ranking.model}"
    R.success(f"Ranking [pm.accent]{run_id}[/] complete")
    R.render_ranking_table(ranking.shortlist, ranking.summary, ranking.provider, ranking.model)
    R.muted(f"Report saved to {report_path}")


def _cmd_watch(host, args: list[str]) -> None:
    if not args:
        args = ["list"]
    sub = args[0].lower()
    positional, options = _extract_options(args[1:])

    if sub in {"list", "ls"}:
        watchlists = _sync_watchlists(host)
        R.render_watchlists(watchlists)
        return

    if sub == "add":
        name = positional[0] if positional else options.get("name")
        extra_kws = positional[1:] if positional else []
        if not name:
            R.error("Usage: [pm.accent]/watch add <name> [keywords...] [every=15][/]")
            return
        if get_watchlist(host.settings.watchlists_path, name) is not None:
            R.error(f"Watchlist [pm.label]{name}[/] already exists")
            return
        w = _build_watchlist(name=name, options=options, existing=None, extra_kws=extra_kws)
        if not w.keywords:
            R.error("Watchlists require at least one keyword")
            return
        upsert_watchlist(host.settings.watchlists_path, w)
        _sync_watchlists(host)
        R.success(f"Watchlist [pm.label]{w.name}[/] saved")
        return

    if sub == "edit":
        name = positional[0] if positional else options.get("name")
        extra_kws = positional[1:] if positional else []
        if not name:
            R.error("Usage: [pm.accent]/watch edit <name> [keywords...][/]")
            return
        existing = get_watchlist(host.settings.watchlists_path, name)
        if existing is None:
            R.error(f"Unknown watchlist: [pm.label]{name}[/]")
            return
        updated = _build_watchlist(
            name=name, options=options, existing=existing, extra_kws=extra_kws
        )
        replace_watchlist(host.settings.watchlists_path, name, updated)
        _sync_watchlists(host)
        R.success(f"Watchlist [pm.label]{name}[/] updated")
        return

    if sub in {"enable", "disable"}:
        name = positional[0] if positional else options.get("name")
        if not name:
            R.error(f"Usage: [pm.accent]/watch {sub} <name>[/]")
            return
        if not set_watchlist_enabled(host.settings.watchlists_path, name, sub == "enable"):
            R.error(f"Unknown watchlist: [pm.label]{name}[/]")
            return
        _sync_watchlists(host)
        R.success(f"Watchlist [pm.label]{name}[/] {'enabled' if sub == 'enable' else 'disabled'}")
        return

    if sub == "remove":
        name = positional[0] if positional else options.get("name")
        if not name:
            R.error("Usage: [pm.accent]/watch remove <name>[/]")
            return
        if not remove_watchlist(host.settings.watchlists_path, name):
            R.error(f"Unknown watchlist: [pm.label]{name}[/]")
            return
        _sync_watchlists(host)
        R.success(f"Watchlist [pm.label]{name}[/] removed")
        return

    R.error(f"Unknown subcommand: {sub}. Try [pm.accent]/watch list[/].")


async def _cmd_job(host, args: list[str]) -> None:
    if not args:
        args = ["list"]
    sub = args[0].lower()
    positional, _options = _extract_options(args[1:])

    if sub in {"list", "ls"}:
        _sync_watchlists(host)
        jobs = host.sqlite_store.list_watch_jobs()
        R.render_jobs(jobs)
        return

    if sub in {"run", "once"}:
        job_name = positional[0] if positional else None
        msg = "Running jobs" + (f" for [pm.label]{job_name}[/]" if job_name else "")
        R.info(msg)
        with R.spinner("Executing scheduler jobs..."):
            async with GammaClient(host.settings.gamma_base_url) as gamma:
                discovery = DiscoveryService(gamma, host.csv_store, host.sqlite_store)
                scheduler = SchedulerService(
                    host.settings.watchlists_path, discovery, host.sqlite_store,
                )
                completed = await scheduler.run_once(job_name=job_name)
        if not completed:
            R.warn("No jobs were executed.")
            return
        if len(completed) == 1:
            host.set_label(completed[0])
        R.success(f"Executed: {', '.join(completed)}")
        return

    R.error(f"Unknown subcommand: {sub}. Try [pm.accent]/job list[/].")


def _cmd_paper(host, args: list[str]) -> None:
    if not args:
        args = ["positions"]
    sub = args[0].lower()
    positional, options = _extract_options(args[1:])
    broker = PaperBroker(host.sqlite_store)

    if sub in {"positions", "list"}:
        rows = broker.list_positions(include_closed=_bool(options.get("all"), False))
        R.render_positions(rows)
        return

    if sub == "enter":
        event_id = options.get("event") or options.get("event_id")
        market_id = options.get("market") or options.get("market_id")
        outcome = options.get("outcome")
        side = options.get("side", "buy")
        size = _float(options.get("size"))
        price = _float(options.get("price"))
        if not event_id or not market_id or not outcome or size is None:
            R.error(
                "Usage: [pm.accent]/paper enter event=1 market=m1"
                " outcome=Yes side=buy size=10 [price=0.42][/]"
            )
            return
        if price is None:
            lbl = options.get("label") or host.current_label
            latest = host.sqlite_store.latest_discovery_run(lbl)
            if latest is None or not latest["markets_csv_path"]:
                R.error("No markets CSV available to infer a price.")
                return
            price = infer_market_price(Path(latest["markets_csv_path"]), market_id)
        if price is None:
            R.error(f"Unable to infer a price for market {market_id}")
            return
        position = broker.open_position(
            event_id=event_id,
            market_id=market_id,
            outcome=outcome,
            side=side,
            size=size,
            entry_price=price,
        )
        R.success(f"Opened paper position [pm.accent]{position.position_id}[/] at {price:.4f}")
        return

    if sub == "close":
        position_id = (
            positional[0] if positional
            else options.get("position") or options.get("id")
        )
        price_token = (
            positional[1] if len(positional) > 1
            else options.get("price") or options.get("exit_price")
        )
        exit_price = _float(price_token)
        if not position_id or exit_price is None:
            R.error("Usage: [pm.accent]/paper close POSITION_ID 0.55[/]")
            return
        broker.close_position(position_id, exit_price)
        R.success(f"Closed position [pm.accent]{position_id}[/] at {exit_price:.4f}")
        return

    R.error(f"Unknown subcommand: {sub}. Try [pm.accent]/paper positions[/].")


async def _cmd_stream(host, args: list[str]) -> None:
    sub = args[0].lower() if args else "show"

    if sub == "start":
        host.start_stream()
        return

    if sub == "stop":
        host.stop_stream()
        R.success("Live stream stopped.")
        return

    if sub == "show":
        positional, options = _extract_options(args[1:])
        limit = _int(positional[0] if positional else options.get("limit"), 20)
        R.render_stream_messages(list(host.stream_messages), limit=limit)
        if host.stream_messages:
            R.muted(f"Stream: {host.stream_status} · {len(host.stream_messages)} messages buffered")
        return

    R.error(f"Unknown subcommand: {sub}. Try [pm.accent]/stream show[/].")
