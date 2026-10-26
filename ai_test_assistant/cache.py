"""LRU and LFU caches implemented from scratch with O(1) operations.

Both track ``hits`` and ``misses`` as plain integers so callers (CLI, worker
metrics) can report cache effectiveness without this module depending on any
metrics library.

``LRUCache`` is used to cache LLM responses keyed by prompt hash: re-running
the assistant on an unchanged file (e.g. after a rebase) returns the cached
response instead of paying for another Gemini call.

``LFUCache`` is the alternative eviction policy (the worker switches with
LLM_CACHE_POLICY=lfu): it wins when a few keys are reused far more often than
the rest (hot shared modules), while LRU wins for bursty re-runs of recent
work. See docs/algorithms.md.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Hashable


class _LruNode:
    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key: Hashable, value: Any):
        self.key = key
        self.value = value
        self.prev: _LruNode | None = None
        self.next: _LruNode | None = None


class LRUCache:
    """Least-recently-used cache: dict for lookup, doubly linked list for order.

    The list runs from most recent (after ``_head``) to least recent (before
    ``_tail``). ``get`` and ``put`` are O(1): the dict finds the node, the
    linked list re-orders or evicts it without scanning.
    """

    policy = "lru"

    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("Cache capacity must be at least 1")
        self.capacity = capacity
        self.hits = 0
        self.misses = 0
        self._nodes: dict[Hashable, _LruNode] = {}
        self._head = _LruNode(None, None)  # sentinel: most recent side
        self._tail = _LruNode(None, None)  # sentinel: least recent side
        self._head.next = self._tail
        self._tail.prev = self._head

    def __len__(self) -> int:
        return len(self._nodes)

    def get(self, key: Hashable) -> Any | None:
        node = self._nodes.get(key)
        if node is None:
            self.misses += 1
            return None
        self.hits += 1
        self._unlink(node)
        self._link_after_head(node)
        return node.value

    def put(self, key: Hashable, value: Any) -> None:
        node = self._nodes.get(key)
        if node is not None:
            node.value = value
            self._unlink(node)
            self._link_after_head(node)
            return

        if len(self._nodes) >= self.capacity:
            least_recent = self._tail.prev
            assert least_recent is not None and least_recent is not self._head
            self._unlink(least_recent)
            del self._nodes[least_recent.key]

        node = _LruNode(key, value)
        self._nodes[key] = node
        self._link_after_head(node)

    def _unlink(self, node: _LruNode) -> None:
        assert node.prev is not None and node.next is not None
        node.prev.next = node.next
        node.next.prev = node.prev

    def _link_after_head(self, node: _LruNode) -> None:
        node.prev = self._head
        node.next = self._head.next
        assert self._head.next is not None
        self._head.next.prev = node
        self._head.next = node


class LFUCache:
    """Least-frequently-used cache with LRU tie-break inside each frequency.

    ``_keys_by_frequency`` maps a use-count to an ``OrderedDict`` of the keys
    currently at that count (insertion order = recency order, oldest first).
    ``_min_frequency`` always points at the lowest non-empty bucket, so
    eviction pops the oldest key of that bucket in O(1).
    """

    policy = "lfu"

    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("Cache capacity must be at least 1")
        self.capacity = capacity
        self.hits = 0
        self.misses = 0
        self._values: dict[Hashable, Any] = {}
        self._frequencies: dict[Hashable, int] = {}
        self._keys_by_frequency: dict[int, OrderedDict[Hashable, None]] = {}
        self._min_frequency = 0

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: Hashable) -> Any | None:
        if key not in self._values:
            self.misses += 1
            return None
        self.hits += 1
        self._increment_frequency(key)
        return self._values[key]

    def put(self, key: Hashable, value: Any) -> None:
        if key in self._values:
            self._values[key] = value
            self._increment_frequency(key)
            return

        if len(self._values) >= self.capacity:
            evict_bucket = self._keys_by_frequency[self._min_frequency]
            evicted_key, _ = evict_bucket.popitem(last=False)
            del self._values[evicted_key]
            del self._frequencies[evicted_key]

        self._values[key] = value
        self._frequencies[key] = 1
        self._keys_by_frequency.setdefault(1, OrderedDict())[key] = None
        self._min_frequency = 1

    def _increment_frequency(self, key: Hashable) -> None:
        frequency = self._frequencies[key]
        bucket = self._keys_by_frequency[frequency]
        del bucket[key]
        if not bucket:
            del self._keys_by_frequency[frequency]
            if self._min_frequency == frequency:
                self._min_frequency = frequency + 1

        self._frequencies[key] = frequency + 1
        self._keys_by_frequency.setdefault(frequency + 1, OrderedDict())[key] = None
