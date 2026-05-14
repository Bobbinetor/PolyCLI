"""Tests for watchlist CLI commands and REPL slash command dispatch."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from polymarket_cli.config import Settings, load_watchlists
from polymarket_cli.main import app
from polymarket_cli.repl.commands import dispatch, _extract_options
from polymarket_cli.storage.csv_store import CSVStore
from polymarket_cli.storage.sqlite import SQLiteStore


def cli_env(tmp_path: Path) -> dict[str, str]:
    return {
        "POLYMARKET_WORKDIR": str(tmp_path),
        "POLYMARKET_DB_PATH": ".local/state.db",
        "POLYMARKET_WATCHLIST_CONFIG": "config/watchlists.yaml",
        "POLYMARKET_PROMPTS_DIR": "config/prompts",
        "POLYMARKET_RAW_DIR": "data/raw",
        "POLYMARKET_PROCESSED_DIR": "data/processed",
        "POLYMARKET_EXPORTS_DIR": "exports",
    }


def test_watchlists_add_edit_and_remove(tmp_path: Path) -> None:
    runner = CliRunner()
    env = cli_env(tmp_path)

    add_result = runner.invoke(
        app,
        ["watchlists", "add"],
        input="alpha\nbitcoin, fed\n15\n12\ny\nn\ny\ncrypto,macro\ndefault-ranking.md\n",
        env=env,
    )

    assert add_result.exit_code == 0
    assert "Saved watchlist alpha" in add_result.stdout

    edit_result = runner.invoke(
        app,
        ["watchlists", "edit", "alpha"],
        input="alpha-live\nbitcoin, fed, election\n20\n30\ny\nn\ny\ncrypto\ndefault-ranking.md\n",
        env=env,
    )

    assert edit_result.exit_code == 0
    assert "Updated watchlist alpha -> alpha-live" in edit_result.stdout

    disable_result = runner.invoke(app, ["watchlists", "disable", "alpha-live"], env=env)
    assert disable_result.exit_code == 0

    sqlite_store = SQLiteStore((tmp_path / ".local" / "state.db").resolve())
    jobs = sqlite_store.list_watch_jobs()
    assert len(jobs) == 1
    assert jobs[0].name == "alpha-live"
    assert jobs[0].enabled is False

    remove_result = runner.invoke(app, ["watchlists", "remove", "alpha-live", "--yes"], env=env)
    assert remove_result.exit_code == 0

    sqlite_store = SQLiteStore((tmp_path / ".local" / "state.db").resolve())
    assert sqlite_store.list_watch_jobs() == []


class _FakeHost:
    """Minimal host stub for testing slash command dispatch."""

    def __init__(self, tmp_path: Path) -> None:
        self.settings = Settings(workdir=tmp_path)
        self.settings.ensure_directories()
        self.sqlite_store = SQLiteStore(self.settings.database_path)
        self.csv_store = CSVStore(
            self.settings.raw_data_path,
            self.settings.processed_data_path,
            self.settings.exports_path,
        )
        self.current_label: str | None = None
        self.llm_state = "ollama:test"
        self.stream_status = "idle"
        self.stream_messages: list[dict] = []

    def set_label(self, label: str | None) -> None:
        self.current_label = label


@pytest.mark.asyncio
async def test_slash_watch_add_creates_watchlist(tmp_path: Path) -> None:
    host = _FakeHost(tmp_path)
    await dispatch(
        host,
        "/watch add alpha keywords=bitcoin,fed every=15 limit=12 live=true enabled=true",
    )

    watchlists = load_watchlists(host.settings.watchlists_path)
    jobs = host.sqlite_store.list_watch_jobs()

    assert len(watchlists) == 1
    assert watchlists[0].name == "alpha"
    assert watchlists[0].keywords == ["bitcoin", "fed"]
    assert len(jobs) == 1
    assert jobs[0].name == "alpha"


@pytest.mark.asyncio
async def test_slash_label_sets_current_label(tmp_path: Path) -> None:
    host = _FakeHost(tmp_path)
    await dispatch(host, "/label demo")
    assert host.current_label == "demo"


@pytest.mark.asyncio
async def test_slash_label_clear(tmp_path: Path) -> None:
    host = _FakeHost(tmp_path)
    host.current_label = "demo"
    await dispatch(host, "/label clear")
    assert host.current_label is None