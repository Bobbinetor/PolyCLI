"""prompt_toolkit Completer for the Polymarket REPL.

Provides tab-completion for slash commands, subcommands, option keys,
and dynamic values (labels, watchlist names, providers, prompt files).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

# ── Command registry ─────────────────────────────────────────────────

COMMANDS: dict[str, dict[str, Any]] = {
    "help": {"summary": "Show available commands", "subs": []},
    "status": {"summary": "Show current session status", "subs": []},
    "label": {"summary": "Set or clear the active label", "subs": ["clear"]},
    "discover": {
        "summary": "Run keyword discovery",
        "options": ["label=", "limit="],
    },
    "rank": {
        "summary": "Rank the latest discovery snapshot",
        "options": ["label=", "provider=", "prompt=", "dry_run=", "max_rows="],
    },
    "data": {"summary": "Show saved snapshots and data runs", "subs": []},
    "watch": {
        "summary": "Manage configured watchlists",
        "subs": ["list", "add", "edit", "enable", "disable", "remove"],
    },
    "job": {
        "summary": "Inspect or run scheduler jobs",
        "subs": ["list", "run", "once"],
    },
    "paper": {
        "summary": "Manage paper-trading positions",
        "subs": ["positions", "enter", "close"],
    },
    "stream": {
        "summary": "Control the live websocket stream",
        "subs": ["start", "stop", "show"],
    },
    "export": {
        "summary": "Export SQLite data to CSV or JSON",
        "subs": ["events", "markets", "ranking"],
    },
    "clear": {"summary": "Clear the terminal screen", "subs": []},
    "quit": {"summary": "Exit the CLI", "subs": []},
}


class ReplCompleter(Completer):
    """Slash-command completer that understands subcommands and options."""

    def __init__(
        self,
        labels_provider: Callable[[], list[str]],
        watchlist_names_provider: Callable[[], list[str]],
        prompt_files_provider: Callable[[], list[str]],
    ) -> None:
        self._labels = labels_provider
        self._watchlist_names = watchlist_names_provider
        self._prompt_files = prompt_files_provider

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return

        body = text[1:]
        parts = body.split()
        # No parts yet — complete command names
        if not parts or (len(parts) == 1 and not text.endswith(" ")):
            fragment = parts[0] if parts else ""
            for name, meta in COMMANDS.items():
                if name.startswith(fragment.lower()):
                    yield Completion(
                        f"/{name}",
                        start_position=-len(text),
                        display=f"/{name}",
                        display_meta=meta["summary"],
                    )
            return

        cmd = parts[0].lower()
        if cmd not in COMMANDS:
            return

        spec = COMMANDS[cmd]
        trailing = text.endswith(" ")
        current = "" if trailing else parts[-1]

        # Subcommand completion
        subs = spec.get("subs", [])
        if subs and (len(parts) == 1 or (len(parts) == 2 and not trailing)):
            fragment = current if len(parts) == 2 else ""
            for sub in subs:
                if sub.startswith(fragment.lower()):
                    full = f"/{cmd} {sub}"
                    yield Completion(
                        full,
                        start_position=-len(text),
                        display=full,
                    )
            return

        # Dynamic value completions
        yield from self._complete_dynamic_values(cmd, parts, text, current, trailing)

    def _complete_dynamic_values(
        self,
        cmd: str,
        parts: list[str],
        full_text: str,
        current: str,
        trailing: bool,
    ):
        """Yield completions for option values like label=, provider=, etc."""
        prefix = full_text.rsplit(current, 1)[0] if current else full_text

        # label= completion (discover, rank, paper enter)
        if current.startswith("label="):
            fragment = current.split("=", 1)[1]
            for label in self._labels():
                if label.lower().startswith(fragment.lower()):
                    yield Completion(
                        f"{prefix}label={label}",
                        start_position=-len(full_text),
                        display=f"label={label}",
                    )
            return

        # provider= completion (rank)
        if current.startswith("provider="):
            fragment = current.split("=", 1)[1]
            for prov in ["ollama", "openrouter"]:
                if prov.startswith(fragment.lower()):
                    yield Completion(
                        f"{prefix}provider={prov}",
                        start_position=-len(full_text),
                        display=f"provider={prov}",
                    )
            return

        # prompt= completion (rank, watch add/edit)
        if current.startswith("prompt=") or current.startswith("prompt_file="):
            key = "prompt=" if current.startswith("prompt=") else "prompt_file="
            fragment = current.split("=", 1)[1]
            for pf in self._prompt_files():
                if pf.lower().startswith(fragment.lower()):
                    yield Completion(
                        f"{prefix}{key}{pf}",
                        start_position=-len(full_text),
                        display=f"{key}{pf}",
                    )
            return

        # dry_run= completion
        if current.startswith("dry_run="):
            fragment = current.split("=", 1)[1]
            for val in ["true", "false"]:
                if val.startswith(fragment.lower()):
                    yield Completion(
                        f"{prefix}dry_run={val}",
                        start_position=-len(full_text),
                        display=f"dry_run={val}",
                    )
            return

        # Watchlist name completion for watch enable/disable/remove/edit, job run
        watch_subs = {"enable", "disable", "remove", "edit"}
        if cmd == "watch" and len(parts) >= 2 and parts[1] in watch_subs:
            if (len(parts) == 2 and trailing) or (len(parts) == 3 and not trailing):
                fragment = "" if trailing else current
                for name in self._watchlist_names():
                    if name.lower().startswith(fragment.lower()):
                        base = f"/{cmd} {parts[1]} {name}"
                        yield Completion(
                            base,
                            start_position=-len(full_text),
                            display=base,
                        )
            return

        if cmd == "job" and len(parts) >= 2 and parts[1] in {"run", "once"}:
            if (len(parts) == 2 and trailing) or (len(parts) == 3 and not trailing):
                fragment = "" if trailing else current
                for name in self._watchlist_names():
                    if name.lower().startswith(fragment.lower()):
                        base = f"/{cmd} {parts[1]} {name}"
                        yield Completion(
                            base,
                            start_position=-len(full_text),
                            display=base,
                        )
            return

        # Label positional completion for /label or /rank
        if cmd in {"label", "rank"}:
            fragment = current
            for label in self._labels():
                if label.lower().startswith(fragment.lower()):
                    yield Completion(
                        f"/{cmd} {label}",
                        start_position=-len(full_text),
                        display=f"/{cmd} {label}",
                    )
            return

        # Default option hint if trailing space and command has options
        if trailing:
            options = COMMANDS.get(cmd, {}).get("options", [])
            for opt in options:
                existing = {p.split("=")[0] for p in parts if "=" in p}
                opt_name = opt.rstrip("=")
                if opt_name not in existing:
                    yield Completion(
                        f"{full_text}{opt}",
                        start_position=-len(full_text),
                        display=opt,
                    )
