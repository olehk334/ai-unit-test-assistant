"""Gemini / Vertex AI client wrapper with a deterministic dry-run mode."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any

from .cache import LRUCache
from .config import AppConfig


# No header here: the pipeline prepends its own when writing the file.
_DRY_RUN_TEMPLATE = """import pytest


def test_generated_placeholder():
    assert True
"""


class LlmError(RuntimeError):
    """Raised when the LLM returns no usable response."""


@dataclass
class LlmUsageStats:
    """Cumulative LLM usage, kept as plain numbers so callers can export them
    to any metrics system without this package depending on one."""

    calls: int = 0
    total_seconds: float = 0.0
    prompt_tokens: int = 0
    response_tokens: int = 0


class LlmClient:
    """Thin wrapper around ``google-genai`` with Vertex AI configuration.

    When ``config.dry_run`` is True, no network call is made and a deterministic
    placeholder test file is returned. This keeps tests cheap and offline.

    ``response_cache`` (optional) short-circuits ``generate`` for prompts seen
    before. With temperature 0 the response is deterministic, so a repeat
    prompt — e.g. re-running a PR after a rebase that didn't touch the file —
    costs nothing. Pass a long-lived cache to share it across pipeline runs.
    """

    def __init__(self, config: AppConfig, response_cache: LRUCache | None = None):
        self._config = config
        self._client: Any | None = None
        self.response_cache = response_cache
        self.usage = LlmUsageStats()

    def _cache_key(self, system_instruction: str, prompt: str) -> str:
        material = "\x1f".join(
            (
                self._config.gemini_model,
                str(self._config.temperature),
                system_instruction,
                prompt,
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from google import genai  # type: ignore
        except ImportError as exc:  # pragma: no cover - import guarded at runtime
            raise LlmError(
                "google-genai is not installed; install the package or use --dry-run"
            ) from exc

        kwargs: dict[str, Any] = {}
        if self._config.google_cloud_project:
            kwargs["vertexai"] = True
            kwargs["project"] = self._config.google_cloud_project
            if self._config.google_cloud_location:
                kwargs["location"] = self._config.google_cloud_location
        self._client = genai.Client(**kwargs)
        return self._client

    async def generate(self, system_instruction: str, prompt: str) -> str:
        """Generate a response. In dry-run mode returns a fixed stub."""
        cache_key = None
        if self.response_cache is not None:
            cache_key = self._cache_key(system_instruction, prompt)
            cached = self.response_cache.get(cache_key)
            if cached is not None:
                return cached

        text = await self._generate_uncached(system_instruction, prompt)

        if self.response_cache is not None and cache_key is not None:
            self.response_cache.put(cache_key, text)
        return text

    async def _generate_uncached(self, system_instruction: str, prompt: str) -> str:
        if self._config.dry_run:
            self.usage.calls += 1
            return _DRY_RUN_TEMPLATE

        client = self._ensure_client()
        loop = asyncio.get_running_loop()

        def _call() -> Any:
            return client.models.generate_content(  # type: ignore[no-any-return]
                model=self._config.gemini_model,
                contents=prompt,
                config={
                    "system_instruction": system_instruction,
                    "temperature": self._config.temperature,
                },
            )

        started = time.monotonic()
        response = await loop.run_in_executor(None, _call)
        self.usage.calls += 1
        self.usage.total_seconds += time.monotonic() - started

        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            self.usage.prompt_tokens += getattr(usage_metadata, "prompt_token_count", 0) or 0
            self.usage.response_tokens += (
                getattr(usage_metadata, "candidates_token_count", 0) or 0
            )

        text = getattr(response, "text", None)
        if not text or not text.strip():
            raise LlmError("LLM returned an empty response")
        return text
