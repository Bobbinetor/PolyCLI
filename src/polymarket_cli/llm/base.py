from __future__ import annotations

import json
from abc import ABC, abstractmethod


class RankingAdapter(ABC):
    provider_name: str
    model: str

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError


def extract_json_object(raw_text: str) -> dict:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(raw_text[start : end + 1])
