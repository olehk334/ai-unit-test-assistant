"""Tests for the hand-rolled LRU and LFU caches."""

from __future__ import annotations

import pytest

from ai_test_assistant.cache import LFUCache, LRUCache


class TestLRUCache:
    def test_returns_stored_value(self) -> None:
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        assert cache.get("a") == 1

    def test_miss_returns_none_and_counts(self) -> None:
        cache = LRUCache(capacity=2)
        assert cache.get("missing") is None
        assert cache.misses == 1
        assert cache.hits == 0

    def test_evicts_least_recently_used_at_capacity(self) -> None:
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_get_refreshes_recency(self) -> None:
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # "a" becomes most recent
        cache.put("c", 3)  # evicts "b", not "a"
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_put_updates_existing_value(self) -> None:
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        cache.put("a", 10)
        assert cache.get("a") == 10
        assert len(cache) == 1

    def test_rejects_zero_capacity(self) -> None:
        with pytest.raises(ValueError):
            LRUCache(capacity=0)


class TestLFUCache:
    def test_returns_stored_value(self) -> None:
        cache = LFUCache(capacity=2)
        cache.put("a", 1)
        assert cache.get("a") == 1

    def test_evicts_least_frequently_used(self) -> None:
        cache = LFUCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # a: freq 2, b: freq 1
        cache.put("c", 3)  # evicts "b"
        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3

    def test_lru_tie_break_within_same_frequency(self) -> None:
        cache = LFUCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        # Both at frequency 1; "a" is older, so it is evicted first.
        cache.put("c", 3)
        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_put_updates_value_and_counts_as_use(self) -> None:
        cache = LFUCache(capacity=2)
        cache.put("a", 1)
        cache.put("a", 10)  # a: freq 2
        cache.put("b", 2)
        cache.put("c", 3)  # evicts "b" (freq 1), keeps "a"
        assert cache.get("a") == 10
        assert cache.get("b") is None

    def test_hit_and_miss_counters(self) -> None:
        cache = LFUCache(capacity=2)
        cache.put("a", 1)
        cache.get("a")
        cache.get("nope")
        assert cache.hits == 1
        assert cache.misses == 1

    def test_rejects_zero_capacity(self) -> None:
        with pytest.raises(ValueError):
            LFUCache(capacity=0)
