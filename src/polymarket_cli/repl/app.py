"""Polymarket interactive REPL — Claude Code-style experience.

This module implements the main REPL loop using ``prompt_toolkit`` for
input (with history, tab-completion, key bindings) and ``rich`` for
inline rendering of all command output.

Key design: Rich output must happen OUTSIDE prompt_toolkit's rendering
context to avoid ANSI escape code conflicts.  We achieve this by NOT
using ``patch_stdout`` and instead flushing Rich output before each
prompt.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory

from polymarket_cli.config import Settings, load_watchlists
from polymarket_cli.repl import renderer as R
from polymarket_cli.repl.commands import dispatch
from polymarket_cli.repl.completions import ReplCompleter
from polymarket_cli.storage.sqlite import SQLiteStore
from polymarket_cli.streams.polymarket_ws import (
    MarketStreamClient,
    load_asset_ids,
)


class ReplApp:
    """Interactive REPL host — Claude Code-style inline experience."""

    def __init__(
        self,
        settings: Settings,
        sqlite_store: SQLiteStore,
        label: str | None = None,
    ) -> None:
        self.settings = settings
        self.sqlite_store = sqlite_store
        self.current_label = label
        self.llm_state = f"ollama:{settings.ollama_model}"
        self.stream_client = MarketStreamClient()
        self.stream_messages: deque[dict[str, str]] = deque(maxlen=50)
        self.stream_status = "idle"
        self._stream_task: asyncio.Task[None] | None = None
        self._stream_source: str | None = None

        # History file in .local/
        history_path = settings.resolve_path(
            Path(".local/repl_history"),
        )
        history_path.parent.mkdir(parents=True, exist_ok=True)

        self._completer = ReplCompleter(
            labels_provider=self._list_labels,
            watchlist_names_provider=self._list_watchlist_names,
            prompt_files_provider=self._list_prompt_files,
        )

        self._session: PromptSession[str] = PromptSession(
            history=FileHistory(str(history_path)),
            completer=self._completer,
            complete_while_typing=False,
            enable_history_search=True,
            bottom_toolbar=self._build_bottom_toolbar,
        )

    # ── Public API (used by command handlers) ────────────────────────

    def set_label(self, label: str | None) -> None:
        self.current_label = label

    def start_stream(self) -> None:
        """Start or restart the background websocket stream."""
        latest = self.sqlite_store.latest_discovery_run(self.current_label)
        if latest is None:
            R.warn("No snapshots available. Run /discover first.")
            return
            
        markets = self.sqlite_store.get_discovery_markets(latest["run_id"])
        if not markets:
            R.warn("No markets found in this snapshot.")
            return
            
        source = f"sqlite:{latest['run_id']}"
        if (
            self._stream_source == source
            and self._stream_task
            and not self._stream_task.done()
        ):
            R.info("Stream already running for this snapshot.")
            return
            
        self._stop_stream_task()
        self._stream_source = source
        asset_ids = [m["condition_id"] for m in markets if m["condition_id"]][:12]
        if not asset_ids:
            R.warn("No valid condition IDs found in the markets.")
            return
        self.stream_status = f"streaming {len(asset_ids)} assets"
        R.success(
            f"Stream started — {len(asset_ids)} assets subscribed",
        )
        self._stream_task = asyncio.get_event_loop().create_task(
            self._run_stream(asset_ids)
        )

    def stop_stream(self) -> None:
        self._stop_stream_task()
        self.stream_messages.clear()
        self.stream_status = "idle"

    # ── REPL main loop ───────────────────────────────────────────────

    def run(self) -> None:
        """Blocking entry point — runs the async REPL loop."""
        try:
            asyncio.run(self._loop())
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            R.blank()
            R.muted("Goodbye.")

    async def _loop(self) -> None:
        R.render_welcome(
            version="0.1.0",
            label=self.current_label,
            llm=self.llm_state,
        )

        # Auto-start stream if we already have data
        self._auto_start_stream()

        while True:
            try:
                raw = await self._session.prompt_async(
                    self._build_prompt(),
                )
            except KeyboardInterrupt:
                continue
            except EOFError:
                break

            text = raw.strip()
            if not text:
                continue

            try:
                await dispatch(self, text)
            except SystemExit:
                break

    # ── Prompt ───────────────────────────────────────────────────────

    def _build_prompt(self) -> HTML:
        # Stream indicator in prompt
        stream_part = ""
        if self._stream_task and not self._stream_task.done():
            count = len(self.stream_messages)
            stream_part = (
                f' <style fg="#3b4a5c">·</style>'
                f' <style fg="#22c55e">⚡{count}</style>'
            )

        if self.current_label:
            return HTML(
                f'<style fg="#d8a03a" bold="true">'
                f"{self.current_label}</style>"
                f"{stream_part}"
                f' <style fg="#6b7280">❯</style> '
            )
        return HTML(
            '<style fg="#d8a03a" bold="true">polymarket</style>'
            f"{stream_part}"
            ' <style fg="#6b7280">❯</style> '
        )

    def _build_bottom_toolbar(self) -> HTML | None:
        text = self._session.default_buffer.text
        if not text.startswith("/"):
            return None
        parts = text[1:].split()
        if not parts:
            return None
        cmd = parts[0].lower()
        from polymarket_cli.repl.commands import HELP_SPECS, _resolve
        resolved = _resolve(cmd)
        if not resolved:
            return None
        spec = next((s for s in HELP_SPECS if s[0] == resolved), None)
        if spec:
            import html
            safe_syntax = html.escape(spec[1])
            return HTML(f'<style fg="#6b7280"> Syntax: {safe_syntax}</style>')
        return None

    # ── Data providers for completions ───────────────────────────────

    def _list_labels(self) -> list[str]:
        labels: set[str] = set()
        for w in load_watchlists(self.settings.watchlists_path):
            labels.add(w.name)
        if self.current_label:
            labels.add(self.current_label)
        latest = self.sqlite_store.latest_discovery_run()
        if latest is not None:
            labels.add(str(latest["label"]))
        if self.settings.processed_data_path.exists():
            for p in self.settings.processed_data_path.iterdir():
                if p.is_dir():
                    labels.add(p.name)
        return sorted(lbl for lbl in labels if lbl)

    def _list_watchlist_names(self) -> list[str]:
        return sorted(
            w.name
            for w in load_watchlists(self.settings.watchlists_path)
        )

    def _list_prompt_files(self) -> list[str]:
        if not self.settings.prompts_path.exists():
            return ["default-ranking.md"]
        return sorted(
            p.name for p in self.settings.prompts_path.glob("*.md")
        )

    # ── Stream background task ───────────────────────────────────────

    def _auto_start_stream(self) -> None:
        """Silently start the stream if data is available."""
        latest = self.sqlite_store.latest_discovery_run(self.current_label)
        if latest is None:
            return
            
        markets = self.sqlite_store.get_discovery_markets(latest["run_id"])
        if not markets:
            return
            
        asset_ids = [m["condition_id"] for m in markets if m["condition_id"]][:12]
        if not asset_ids:
            return
            
        self._stream_source = f"sqlite:{latest['run_id']}"
        self.stream_status = f"streaming {len(asset_ids)} assets"
        self._stream_task = asyncio.get_event_loop().create_task(
            self._run_stream(asset_ids)
        )

    async def _run_stream(self, asset_ids: list[str]) -> None:
        async def on_message(payload: dict) -> None:
            self.stream_messages.appendleft(
                {
                    "time": datetime.now(UTC).strftime("%H:%M:%S"),
                    "type": str(
                        payload.get("event_type")
                        or payload.get("type")
                        or "message"
                    ),
                    "asset": str(
                        payload.get("asset_id")
                        or payload.get("market")
                        or payload.get("condition_id")
                        or payload.get("asset")
                        or "-"
                    ),
                    "details": json.dumps(
                        payload, default=str,
                    )[:100],
                    "full": json.dumps(
                        payload, default=str, indent=2,
                    )[:1200],
                }
            )
            # Live update the prompt/rprompt
            if hasattr(self, "_session") and self._session.app:
                self._session.app.invalidate()

        try:
            await self.stream_client.stream_assets(
                asset_ids, on_message=on_message,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.stream_status = f"error: {exc}"

    def _stop_stream_task(self) -> None:
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = None
