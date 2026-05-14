import json

from polymarket_cli.streams.polymarket_ws import MarketStreamClient


def test_decode_message_accepts_single_dict() -> None:
    payload = {"event_type": "book", "asset_id": "asset-1"}

    decoded = MarketStreamClient.decode_message(json.dumps(payload))

    assert decoded == [payload]


def test_decode_message_flattens_list_payloads() -> None:
    payload = [
        {"event_type": "book", "asset_id": "asset-1"},
        {"event_type": "price_change", "asset_id": "asset-2"},
    ]

    decoded = MarketStreamClient.decode_message(json.dumps(payload))

    assert decoded == payload
