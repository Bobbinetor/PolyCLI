from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WatchlistConfig(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    poll_minutes: int = 30
    limit: int = 25
    live_only: bool = True
    include_closed: bool = False
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    prompt_file: str = "default-ranking.md"


class WatchlistsDocument(BaseModel):
    watchlists: list[WatchlistConfig] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POLYMARKET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "polymarket-cli"
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    data_api_base_url: str = "https://data-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"
    log_level: str = "INFO"
    workdir: Path = Path(".")
    db_path: Path = Path(".local/state.db")
    watchlist_config: Path = Path("config/watchlists.yaml")
    prompts_dir: Path = Path("config/prompts")
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    exports_dir: Path = Path("exports")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "kwangsuklee/gemma4-e4b-abliterated-Q8:latest"
    ollama_timeout: int = 300
    ranking_max_rows: int = 20
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4.1-mini"
    openrouter_api_key: str | None = None

    def resolve_path(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.workdir / path).resolve()

    @property
    def database_path(self) -> Path:
        return self.resolve_path(self.db_path)

    @property
    def watchlists_path(self) -> Path:
        return self.resolve_path(self.watchlist_config)

    @property
    def prompts_path(self) -> Path:
        return self.resolve_path(self.prompts_dir)

    @property
    def raw_data_path(self) -> Path:
        return self.resolve_path(self.raw_dir)

    @property
    def processed_data_path(self) -> Path:
        return self.resolve_path(self.processed_dir)

    @property
    def exports_path(self) -> Path:
        return self.resolve_path(self.exports_dir)

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.watchlists_path.parent.mkdir(parents=True, exist_ok=True)
        self.prompts_path.mkdir(parents=True, exist_ok=True)
        self.raw_data_path.mkdir(parents=True, exist_ok=True)
        self.processed_data_path.mkdir(parents=True, exist_ok=True)
        self.exports_path.mkdir(parents=True, exist_ok=True)


def load_watchlists(path: Path) -> list[WatchlistConfig]:
    if not path.exists():
        return []

    content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    document = WatchlistsDocument.model_validate(content)
    return document.watchlists


def save_watchlists(path: Path, watchlists: list[WatchlistConfig]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"watchlists": [watchlist.model_dump(mode="python") for watchlist in watchlists]}
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def get_watchlist(path: Path, name: str) -> WatchlistConfig | None:
    for watchlist in load_watchlists(path):
        if watchlist.name == name:
            return watchlist
    return None


def upsert_watchlist(path: Path, watchlist: WatchlistConfig) -> None:
    watchlists = load_watchlists(path)
    for index, current in enumerate(watchlists):
        if current.name == watchlist.name:
            watchlists[index] = watchlist
            save_watchlists(path, watchlists)
            return

    watchlists.append(watchlist)
    save_watchlists(path, watchlists)


def replace_watchlist(path: Path, original_name: str, watchlist: WatchlistConfig) -> None:
    watchlists = load_watchlists(path)
    replaced = False
    for index, current in enumerate(watchlists):
        if current.name == original_name:
            watchlists[index] = watchlist
            replaced = True
            break

    if not replaced:
        watchlists.append(watchlist)

    deduped: list[WatchlistConfig] = []
    seen: set[str] = set()
    for current in watchlists:
        if current.name in seen:
            continue
        deduped.append(current)
        seen.add(current.name)
    save_watchlists(path, deduped)


def remove_watchlist(path: Path, name: str) -> bool:
    watchlists = load_watchlists(path)
    filtered = [watchlist for watchlist in watchlists if watchlist.name != name]
    if len(filtered) == len(watchlists):
        return False
    save_watchlists(path, filtered)
    return True


def set_watchlist_enabled(path: Path, name: str, enabled: bool) -> bool:
    watchlists = load_watchlists(path)
    updated = False
    for index, watchlist in enumerate(watchlists):
        if watchlist.name == name:
            watchlists[index] = watchlist.model_copy(update={"enabled": enabled})
            updated = True
            break

    if updated:
        save_watchlists(path, watchlists)
    return updated


def parse_csv_list(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
