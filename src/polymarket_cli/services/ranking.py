from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import polars as pl
from pydantic import ValidationError

from polymarket_cli.config import Settings
from polymarket_cli.domain.models import RankingItem, RankingResult
from polymarket_cli.llm.base import RankingAdapter, extract_json_object
from polymarket_cli.llm.ollama import OllamaRankingAdapter
from polymarket_cli.llm.openrouter import OpenRouterRankingAdapter
from polymarket_cli.storage.csv_store import CSVStore
from polymarket_cli.storage.sqlite import SQLiteStore


logger = logging.getLogger(__name__)


def build_adapter(settings: Settings, provider: str) -> RankingAdapter:
    normalized = provider.lower()
    if normalized == "ollama":
        return OllamaRankingAdapter(
            settings.ollama_base_url,
            settings.ollama_model,
            timeout=float(settings.ollama_timeout),
        )
    if normalized == "openrouter":
        if not settings.openrouter_api_key:
            raise ValueError("POLYMARKET_OPENROUTER_API_KEY is required for OpenRouter")
        return OpenRouterRankingAdapter(
            settings.openrouter_base_url,
            settings.openrouter_api_key,
            settings.openrouter_model,
        )
    raise ValueError(f"Unsupported provider: {provider}")


class RankingService:
    def __init__(self, settings: Settings, csv_store: CSVStore, sqlite_store: SQLiteStore) -> None:
        self.settings = settings
        self.csv_store = csv_store
        self.sqlite_store = sqlite_store

    def _heuristic_rank(self, frame: pl.DataFrame) -> RankingResult:
        shortlist = []
        for row in frame.to_dicts()[:10]:
            volume = float(row.get("volume") or 0)
            liquidity = float(row.get("liquidity") or 0)
            is_live = bool(row.get("live"))
            score = min(100, int(volume / 1000) + int(liquidity / 100) + (15 if is_live else 0))
            shortlist.append(
                RankingItem(
                    event_id=str(row.get("event_id")),
                    title=str(row.get("title")),
                    score=score,
                    confidence=min(100, score),
                    action="monitor" if score < 55 else "paper_buy_yes",
                    thesis="Heuristic ranking based on liquidity, volume, and live status.",
                    risks=["Heuristic mode only", "LLM provider not used"],
                )
            )
        shortlist.sort(key=lambda item: item.score, reverse=True)
        return RankingResult(
            provider="heuristic",
            model="local-score",
            summary="Heuristic shortlist generated without external LLM.",
            shortlist=shortlist,
        )

    def _build_prompt(self, prompt_template: str, frame: pl.DataFrame) -> str:
        rows = frame.to_dicts()
        return (
            f"{prompt_template.strip()}\n\n"
            "CSV rows (JSON records):\n"
            f"{json.dumps(rows, indent=2)}"
        )

    def _coerce_ranking_item(self, payload: dict) -> dict:
        coerced = dict(payload)
        if "event_id" in coerced and coerced["event_id"] is not None:
            coerced["event_id"] = str(coerced["event_id"])
        if "title" in coerced and coerced["title"] is not None:
            coerced["title"] = str(coerced["title"])
        if "action" in coerced and coerced["action"] is not None:
            coerced["action"] = str(coerced["action"])
        if "thesis" in coerced and coerced["thesis"] is not None:
            coerced["thesis"] = str(coerced["thesis"])
        if "score" in coerced and coerced["score"] is not None:
            coerced["score"] = int(round(float(coerced["score"])))
        if "confidence" in coerced and coerced["confidence"] is not None:
            confidence = float(coerced["confidence"])
            if 0.0 <= confidence <= 1.0:
                confidence *= 100
            coerced["confidence"] = max(0, min(100, int(round(confidence))))
        risks = coerced.get("risks")
        if isinstance(risks, str):
            coerced["risks"] = [risks]
        return coerced

    async def rank_csv(
        self,
        *,
        label: str,
        csv_path: Path,
        prompt_path: Path,
        provider: str,
        dry_run: bool = False,
        max_rows: int | None = None,
    ) -> tuple[str, RankingResult, Path]:
        resolved_max_rows = max_rows if max_rows is not None else self.settings.ranking_max_rows
        frame = pl.read_csv(csv_path).head(max(1, resolved_max_rows))
        if dry_run or frame.is_empty():
            ranking = self._heuristic_rank(frame)
        else:
            prompt = self._build_prompt(prompt_path.read_text(encoding="utf-8"), frame)
            adapter = build_adapter(self.settings, provider)
            raw_response = await adapter.generate(prompt)
            try:
                payload = extract_json_object(raw_response)
                ranking = RankingResult(
                    provider=adapter.provider_name,
                    model=adapter.model,
                    summary=str(payload.get("summary", "")),
                    shortlist=[
                        RankingItem.model_validate(self._coerce_ranking_item(item))
                        for item in payload.get("shortlist", [])
                    ],
                    raw_response=raw_response,
                )
            except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning("Falling back to heuristic ranking after LLM parse failure: %s", exc)
                ranking = self._heuristic_rank(frame).model_copy(
                    update={
                        "summary": f"LLM response could not be parsed; fell back to heuristic ranking. {exc}",
                        "raw_response": raw_response,
                    }
                )

        run_id = uuid4().hex[:12]
        report_path = self.csv_store.write_ranking_report(label, ranking)
        self.sqlite_store.record_ranking_run(run_id, ranking)
        return run_id, ranking, report_path
