import httpx
import pytest
import respx

from polymarket_cli.clients.gamma import GammaClient


@pytest.mark.asyncio
@respx.mock
async def test_discover_keywords_merges_search_and_keyset_results() -> None:
    respx.get("https://gamma-api.polymarket.com/public-search").mock(
        return_value=httpx.Response(
            200,
            json={
                "events": [
                    {
                        "id": 1,
                        "title": "Will BTC hit 150k?",
                        "markets": [],
                        "tags": [{"slug": "crypto"}],
                    }
                ]
            },
        )
    )
    respx.get("https://gamma-api.polymarket.com/events/keyset").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "id": 1,
                            "title": "Will BTC hit 150k?",
                            "markets": [
                                {
                                    "id": "m1",
                                    "question": "Will BTC hit 150k?",
                                    "clobTokenIds": '["yes", "no"]',
                                }
                            ],
                            "tags": [{"slug": "crypto"}],
                        }
                    ]
                },
            ),
            httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "id": 2,
                            "title": "Will ETH break ATH?",
                            "markets": [],
                            "tags": [{"slug": "crypto"}],
                        }
                    ],
                    "next_cursor": None,
                },
            ),
        ]
    )

    async with GammaClient("https://gamma-api.polymarket.com") as client:
        events = await client.discover_keywords(["bitcoin"], limit=10)

    assert [event.id for event in events] == ["1", "2"]
    assert events[0].keyword_hits == ["bitcoin"]
    assert events[0].markets[0].clob_token_ids == ["yes", "no"]
