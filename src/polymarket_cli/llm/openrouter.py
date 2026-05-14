from __future__ import annotations

import httpx

from polymarket_cli.llm.base import RankingAdapter


class OpenRouterRankingAdapter(RankingAdapter):
    provider_name = "openrouter"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def generate(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=120.0, headers=headers) as client:
            response = await client.post("/chat/completions", json=body)
            response.raise_for_status()
            payload = response.json()
        return payload["choices"][0]["message"]["content"].strip()
