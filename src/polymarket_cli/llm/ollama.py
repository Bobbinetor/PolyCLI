from __future__ import annotations

import logging

import httpx

from polymarket_cli.llm.base import RankingAdapter


logger = logging.getLogger(__name__)


class OllamaRankingAdapter(RankingAdapter):
    provider_name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def generate(self, prompt: str) -> str:
        logger.info("Generating ranking with Ollama model %s", self.model)
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.post(
                    "/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Unable to connect to Ollama at {self.base_url}. Start Ollama and ensure the API is reachable."
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Ollama model {self.model} timed out after {self.timeout:.0f}s. Increase POLYMARKET_OLLAMA_TIMEOUT or use a smaller prompt."
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            detail = exc.response.text.strip()
            if status_code == 404:
                raise RuntimeError(
                    f"Ollama model {self.model} was not found. Pull it first or update POLYMARKET_OLLAMA_MODEL."
                ) from exc
            raise RuntimeError(
                f"Ollama request failed with status {status_code}: {detail or 'no response body'}"
            ) from exc
        return str(payload.get("response", "")).strip()
