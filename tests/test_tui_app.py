"""Tests for the REPL command dispatch and completions."""

from pathlib import Path

import pytest

from polymarket_cli.config import Settings
from polymarket_cli.repl.commands import dispatch, HELP_SPECS, _resolve, _extract_options
from polymarket_cli.repl.completions import ReplCompleter, COMMANDS
from polymarket_cli.storage.csv_store import CSVStore
from polymarket_cli.storage.sqlite import SQLiteStore


def test_resolve_known_commands() -> None:
    assert _resolve("help") == "help"
    assert _resolve("discover") == "discover"
    assert _resolve("rank") == "rank"
    assert _resolve("watch") == "watch"
    assert _resolve("quit") == "quit"


def test_resolve_prefix_match() -> None:
    assert _resolve("dis") == "discover"
    assert _resolve("ra") == "rank"
    assert _resolve("he") == "help"


def test_resolve_unknown() -> None:
    assert _resolve("xyzzy") is None


def test_extract_options_positional() -> None:
    positional, options = _extract_options(["bitcoin", "election", "label=smoke", "limit=5"])
    assert positional == ["bitcoin", "election"]
    assert options == {"label": "smoke", "limit": "5"}


def test_extract_options_double_dash() -> None:
    positional, options = _extract_options(["--dry-run", "--provider", "ollama"])
    assert positional == []
    assert options == {"dry_run": "true", "provider": "ollama"}


def test_help_specs_are_complete() -> None:
    for name, usage, summary in HELP_SPECS:
        assert name, "Command name must not be empty"
        assert usage.startswith("/"), f"Usage must start with /: {usage}"
        assert summary, f"Summary must not be empty for {name}"


def test_completer_commands_are_registered() -> None:
    assert "help" in COMMANDS
    assert "discover" in COMMANDS
    assert "rank" in COMMANDS
    assert "watch" in COMMANDS
    assert "quit" in COMMANDS


def test_completer_produces_completions() -> None:
    from prompt_toolkit.document import Document
    from prompt_toolkit.completion import CompleteEvent

    completer = ReplCompleter(
        labels_provider=lambda: ["smoke", "demo"],
        watchlist_names_provider=lambda: ["alpha"],
        prompt_files_provider=lambda: ["default-ranking.md"],
    )
    doc = Document("/dis")
    event = CompleteEvent()
    results = list(completer.get_completions(doc, event))
    texts = [c.text for c in results]
    assert any("/discover" in t for t in texts)