from pathlib import Path

import pytest

from polymarket_cli.config import Settings
from polymarket_cli.domain.models import RankingResult
from polymarket_cli.services.ranking import RankingService
from polymarket_cli.storage.csv_store import CSVStore
from polymarket_cli.storage.sqlite import SQLiteStore


@pytest.mark.asyncio
async def test_ranking_service_heuristic_mode(tmp_path: Path) -> None:
    settings = Settings(workdir=tmp_path)
    settings.ensure_directories()
    csv_store = CSVStore(settings.raw_data_path, settings.processed_data_path, settings.exports_path)
    sqlite_store = SQLiteStore(settings.database_path)
    ranking_service = RankingService(settings, csv_store, sqlite_store)

    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "event_id,title,volume,liquidity,live\n1,BTC market,4000,800,true\n2,ETH market,1000,200,false\n",
        encoding="utf-8",
    )
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Rank these events", encoding="utf-8")

    run_id, ranking, report_path = await ranking_service.rank_csv(
        label="crypto",
        csv_path=csv_path,
        prompt_path=prompt_path,
        provider="ollama",
        dry_run=True,
    )

    assert run_id
    assert ranking.provider == "heuristic"
    assert ranking.shortlist[0].event_id == "1"
    assert report_path.exists()


@pytest.mark.asyncio
async def test_ranking_service_falls_back_when_llm_returns_invalid_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(workdir=tmp_path)
    settings.ensure_directories()
    csv_store = CSVStore(settings.raw_data_path, settings.processed_data_path, settings.exports_path)
    sqlite_store = SQLiteStore(settings.database_path)
    ranking_service = RankingService(settings, csv_store, sqlite_store)

    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "event_id,title,volume,liquidity,live\n1,BTC market,4000,800,true\n2,ETH market,1000,200,false\n",
        encoding="utf-8",
    )
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Rank these events", encoding="utf-8")

    class DummyAdapter:
        provider_name = "ollama"
        model = "dummy"

        async def generate(self, prompt: str) -> str:
            del prompt
            return "not json"

    monkeypatch.setattr("polymarket_cli.services.ranking.build_adapter", lambda settings, provider: DummyAdapter())

    _run_id, ranking, report_path = await ranking_service.rank_csv(
        label="crypto",
        csv_path=csv_path,
        prompt_path=prompt_path,
        provider="ollama",
        dry_run=False,
    )

    assert isinstance(ranking, RankingResult)
    assert ranking.provider == "heuristic"
    assert "fell back to heuristic ranking" in ranking.summary
    assert ranking.raw_response == "not json"
    assert report_path.exists()


@pytest.mark.asyncio
async def test_ranking_service_coerces_common_llm_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(workdir=tmp_path)
    settings.ensure_directories()
    csv_store = CSVStore(settings.raw_data_path, settings.processed_data_path, settings.exports_path)
    sqlite_store = SQLiteStore(settings.database_path)
    ranking_service = RankingService(settings, csv_store, sqlite_store)

    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "event_id,title,volume,liquidity,live\n1,BTC market,4000,800,true\n",
        encoding="utf-8",
    )
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

    monkeypatch.setattr("polymarket_cli.services.ranking.build_adapter", lambda settings, provider: DummyAdapter())

    _run_id, ranking, report_path = await ranking_service.rank_csv(
        label="crypto",
        csv_path=csv_path,
        prompt_path=prompt_path,
        provider="ollama",
        dry_run=False,
    )

    assert ranking.provider == "ollama"
    assert ranking.shortlist[0].event_id == "1"
    assert ranking.shortlist[0].confidence == 85
    assert ranking.shortlist[0].risks == ["Volatility"]
    assert report_path.exists()
