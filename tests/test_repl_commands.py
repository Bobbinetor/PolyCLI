from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from polymarket_cli.repl.commands import _extract_options, dispatch


def test_extract_options() -> None:
    args = ["interactive", "limit=50", "foo", "bar=baz"]
    pos, opts = _extract_options(args)
    assert pos == ["interactive", "foo"]
    assert opts == {"limit": "50", "bar": "baz"}


@pytest.mark.asyncio
async def test_dispatch_help() -> None:
    host = MagicMock()
    # dispatch directly catches and logs, so we just ensure it doesn't crash
    await dispatch(host, "/help")

    # testing a specific help
    await dispatch(host, "/discover --help")


@pytest.mark.asyncio
async def test_dispatch_unknown_command() -> None:
    host = MagicMock()
    await dispatch(host, "/nonexistentcommand")


@pytest.mark.asyncio
async def test_dispatch_missing_slash() -> None:
    host = MagicMock()
    await dispatch(host, "help")
