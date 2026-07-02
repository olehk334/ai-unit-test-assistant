"""Tests for LLM response caching inside LlmClient."""

from __future__ import annotations

from ai_test_assistant.cache import LRUCache
from ai_test_assistant.config import AppConfig
from ai_test_assistant.llm_client import LlmClient


def _dry_run_client(cache: LRUCache | None) -> LlmClient:
    config = AppConfig(dry_run=True)
    return LlmClient(config, response_cache=cache)


async def test_repeat_prompt_is_served_from_cache() -> None:
    cache = LRUCache(capacity=8)
    client = _dry_run_client(cache)

    first = await client.generate("system", "same prompt")
    second = await client.generate("system", "same prompt")

    assert first == second
    assert client.usage.calls == 1  # second call never reached generation
    assert cache.hits == 1
    assert cache.misses == 1


async def test_different_prompts_are_not_shared() -> None:
    cache = LRUCache(capacity=8)
    client = _dry_run_client(cache)

    await client.generate("system", "prompt one")
    await client.generate("system", "prompt two")

    assert client.usage.calls == 2
    assert cache.hits == 0


async def test_without_cache_every_call_generates() -> None:
    client = _dry_run_client(cache=None)

    await client.generate("system", "same prompt")
    await client.generate("system", "same prompt")

    assert client.usage.calls == 2
