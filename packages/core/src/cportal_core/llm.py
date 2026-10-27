"""Local LLM provider (ADR-008, Q-03): an Ollama server, JSON output constrained by a schema.

Only local models; `available()` lets callers fall back to rules when the server is absent or
the model is not pulled. Temperature 0, so the same text gives the same JSON.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from cportal_core.settings import get_settings


class LLMProvider(Protocol):
    model: str

    def available(self) -> bool: ...

    def json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class OllamaProvider:
    """Ollama's native chat API: `format` takes a JSON schema (grammar-constrained decoding)."""

    def __init__(
        self, base_url: str | None = None, model: str | None = None, timeout: float = 240
    ) -> None:
        settings = get_settings()
        self.root = (base_url or settings.llm_base_url).rstrip("/").removesuffix("/v1")
        self.model = model or settings.llm_model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            tags = httpx.get(f"{self.root}/api/tags", timeout=3).json()
        except (httpx.HTTPError, ValueError):
            return False
        return any(m.get("name") == self.model for m in tags.get("models", []))

    def json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.root}/api/chat",
            timeout=self.timeout,
            json={
                "model": self.model,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0, "num_ctx": 2048},
                # Reasoning models (Qwen3, DeepSeek-R1) answer directly: no hidden chain first.
                **({"think": False} if self.model.startswith(("qwen3", "deepseek")) else {}),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        out: dict[str, Any] = json.loads(content)
        return out
