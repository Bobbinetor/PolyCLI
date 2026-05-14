from pathlib import Path

from polymarket_cli.config import Settings, load_watchlists
from polymarket_cli.domain.models import normalize_event


def test_load_watchlists(tmp_path: Path) -> None:
    config_path = tmp_path / "watchlists.yaml"
    config_path.write_text(
        """
watchlists:
  - name: politics
    keywords: [trump, election]
    poll_minutes: 15
    limit: 10
    live_only: true
    include_closed: false
    enabled: true
    tags: [politics]
    prompt_file: default-ranking.md
        """,
        encoding="utf-8",
    )

    watchlists = load_watchlists(config_path)

    assert len(watchlists) == 1
    assert watchlists[0].name == "politics"
    assert watchlists[0].keywords == ["trump", "election"]
    assert watchlists[0].tags == ["politics"]


def test_settings_resolve_relative_paths(tmp_path: Path) -> None:
    settings = Settings(workdir=tmp_path, db_path=Path("db.sqlite3"), raw_dir=Path("raw-data"))

    assert settings.database_path == (tmp_path / "db.sqlite3").resolve()
    assert settings.raw_data_path == (tmp_path / "raw-data").resolve()


def test_normalize_event_parses_markets_and_keywords() -> None:
    payload = {
        "id": 123,
        "title": "Will BTC hit 150k in 2026?",
        "slug": "btc-150k-2026",
        "description": "Bitcoin threshold market",
        "active": True,
        "closed": False,
        "live": True,
        "category": "Crypto",
        "volume": 3210.5,
        "liquidity": 987.2,
        "openInterest": 450.1,
        "tags": [{"slug": "crypto"}, {"label": "bitcoin"}],
        "markets": [
            {
                "id": "m1",
                "question": "Will BTC hit 150k?",
                "conditionId": "0xabc",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.45", "0.55"]',
                "clobTokenIds": '["yes-token", "no-token"]',
                "bestBid": "0.44",
                "bestAsk": "0.46",
            }
        ],
    }

    event = normalize_event(payload, keyword_hits=["bitcoin"])

    assert event.id == "123"
    assert event.tags == ["crypto", "bitcoin"]
    assert event.keyword_hits == ["bitcoin"]
    assert event.market_count() == 1
    assert event.markets[0].outcomes == ["Yes", "No"]
    assert event.markets[0].outcome_prices == [0.45, 0.55]
    assert event.markets[0].clob_token_ids == ["yes-token", "no-token"]