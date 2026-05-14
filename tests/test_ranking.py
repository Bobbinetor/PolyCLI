from pathlib import Path

import pytest

from polymarket_cli.config import Settings
from polymarket_cli.domain.models import RankingResult
from polymarket_cli.services.ranking import RankingService
from polymarket_cli.storage.sqlite import SQLiteStore


@pytest.mark.asyncio
async def test_ranking_service_heuristic_mode(tmp_path: Path) -> None:
    settings = Settings(workdir=tmp_path)
    settings.ensure_directories()
    sqlite_store = SQLiteStore(settings.database_path)
    ranking_service = RankingService(settings, sqlite_store)

    sqlite_store.get_discovery_events = lambda run_id: [
        {"event_id": "1", "title": "BTC market", "volume": 4000, "liquidity": 800, "live": 1},
        {"event_id": "2", "title": "ETH market", "volume": 1000, "liquidity": 200, "live": 0},
    ]

    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Rank these events", encoding="utf-8")

    ranking = await ranking_service.rank_run(
        run_id="fake-run",
        prompt_path=prompt_path,
        provider="ollama",
        dry_run=True,
    )

    assert ranking.provider == "heuristic"
    assert ranking.shortlist[0].event_id == "1"


@pytest.mark.asyncio
async def test_ranking_service_falls_back_when_llm_returns_invalid_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(workdir=tmp_path)
    settings.ensure_directories()
    sqlite_store = SQLiteStore(settings.database_path)
    ranking_service = RankingService(settings, sqlite_store)

    sqlite_store.get_discovery_events = lambda run_id: [
        {"event_id": "1", "title": "BTC market", "volume": 4000, "liquidity": 800, "live": 1},
    ]
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Rank these events", encoding="utf-8")

    class DummyAdapter:
        provider_name = "ollama"
        model = "dummy"

        async def generate(self, prompt: str) -> str:
            del prompt
            return "not json"

    monkeypatch.setattr(
        "polymarket_cli.services.ranking.build_adapter",
        lambda settings, provider: DummyAdapter(),
    )

    ranking = await ranking_service.rank_run(
        run_id="fake-run",
        prompt_path=prompt_path,
        provider="ollama",
        dry_run=False,
    )

    assert isinstance(ranking, RankingResult)
    assert ranking.provider == "heuristic"
    assert "fell back to heuristic ranking" in ranking.summary
    assert ranking.raw_response == "not json"


@pytest.mark.asyncio
async def test_ranking_service_coerces_common_llm_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(workdir=tmp_path)
    settings.ensure_directories()
    sqlite_store = SQLiteStore(settings.database_path)
    ranking_service = RankingService(settings, sqlite_store)

    sqlite_store.get_discovery_events = lambda run_id: [
        {"event_id": "1", "title": "BTC market", "volume": 4000, "liquidity": 800, "live": 1},
    ]
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Rank these events", encoding="utf-8")

    class DummyAdapter:
        provider_name = "ollama"
        model = "dummy"

        async def generate(self, prompt: str) -> str:
            del prompt
            return (
                '{"summary":"ok","shortlist":[{"event_id":1,"title":"BTC market",'
                '"score":91,"confidence":0.85,"action":"monitor",'
                '"thesis":"Strong signal","risks":"Volatility"}]}'
            )

    monkeypatch.setattr(
        "polymarket_cli.services.ranking.build_adapter",
        lambda settings, provider: DummyAdapter(),
    )

    ranking = await ranking_service.rank_run(
        run_id="fake-run",
        prompt_path=prompt_path,
        provider="ollama",
        dry_run=False,
    )

    assert ranking.provider == "ollama"
    assert ranking.shortlist[0].event_id == "1"
    assert ranking.shortlist[0].confidence == 85
    assert ranking.shortlist[0].risks == ["Volatility"]
