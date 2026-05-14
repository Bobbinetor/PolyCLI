from pathlib import Path

from polymarket_cli.config import Settings
from polymarket_cli.services.paper_broker import PaperBroker, infer_market_price
from polymarket_cli.storage.sqlite import SQLiteStore


def test_infer_market_price_uses_last_trade(tmp_path: Path) -> None:
    csv_path = tmp_path / "markets.csv"
    csv_path.write_text(
        "market_id,last_trade_price,best_bid,best_ask\nm1,0.62,0.61,0.63\n",
        encoding="utf-8",
    )

    assert infer_market_price(csv_path, "m1") == 0.62


def test_paper_broker_open_and_list_position(tmp_path: Path) -> None:
    settings = Settings(workdir=tmp_path)
    settings.ensure_directories()
    sqlite_store = SQLiteStore(settings.database_path)
    broker = PaperBroker(sqlite_store)

    broker.open_position(
        event_id="1",
        market_id="m1",
        outcome="Yes",
        side="buy",
        size=10,
        entry_price=0.4,
    )

    positions = broker.list_positions()

    assert len(positions) == 1
    assert positions[0]["market_id"] == "m1"
    assert positions[0]["pnl"] == 0.0
