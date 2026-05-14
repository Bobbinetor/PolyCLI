from __future__ import annotations

from unittest.mock import MagicMock

from prompt_toolkit.document import Document

from polymarket_cli.repl.completions import ReplCompleter


def test_command_completion() -> None:
    host = MagicMock()
    completer = ReplCompleter(
        host,
        watchlist_names_provider=lambda: [],
        prompt_files_provider=lambda: [],
    )
    
    # Slash start -> yield all commands
    doc = Document("/")
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert "/discover" in texts
    assert "/rank" in texts
    assert "/help" in texts
    assert "/export" in texts
