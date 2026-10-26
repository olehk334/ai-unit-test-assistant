# 10. PDP · Topological Sort and LRU / LFU Caches {#en-algorithms}

## In plain words

Two classic algorithms are implemented from scratch in this project, because each solves a problem the pipeline really has. A topological sort decides the order in which changed files are processed when they import each other. An LRU cache remembers recent LLM answers so a repeated prompt costs nothing; an LFU cache is the alternative policy, selectable with one setting, so the two can be compared on real jobs.

![Two algorithms implemented from scratch, each solving a real problem.](images/algorithms.en.png)

## Theory in brief

**Topological sort** orders the nodes of a directed graph so that every edge points forward. It exists only for graphs without cycles. **Kahn's algorithm**: count the incoming edges of every node; put the nodes with zero incoming edges in a queue; repeatedly take one, emit it, and decrease the count of its neighbours, adding those that reach zero. If the queue runs dry before all nodes are emitted, the leftovers are exactly the nodes in or behind a cycle: cycle detection comes free. With a plain queue the cost is O(V + E); with a min-heap instead of the queue you get a deterministic tie-break for O((V + E) log V).

**LRU (least recently used)** evicts the entry that has not been touched for the longest time. The classic O(1) design is a hash map from key to node plus a doubly linked list in usage order: a lookup moves its node to the front with two pointer swaps; eviction removes the tail.

**LFU (least frequently used)** evicts the entry used the fewest times, with LRU as the tie-break. The O(1) design keeps a map from key to value, a map from key to use count, and a map from use count to an ordered set of keys, plus a pointer to the smallest count; a use moves the key one bucket up.

**When which.** LRU wins when access has temporal locality: what was used recently will be used again (bursty re-runs of one branch). LFU wins when a few items are hot all the time and must survive bursts of one-off items (shared modules that appear in most PRs).

## How this project applies it

**Import order** (`import_graph.py`). The graph is built only over the changed files: an edge from `models.py` to `service.py` when `service` imports `models`. Imports are read with `ast`, including relative imports and the `from package import module` form. The ready nodes sit in a min-heap keyed by the file's original position, so among the files whose dependencies are done the one listed first goes next, and the output is reproducible. Files in a cycle keep their original order and are listed in the report; a cycle is a code smell in the analysed repository, not a reason to stop. What the order really changes: the report lists a module before the code that uses it, and a module is processed before any tests exist for its importers.

**Response cache** (`cache.py`, `llm_client.py`). The key is the SHA-256 of model, temperature, system instruction and prompt, so anything that could change the answer is in the key and nothing ever needs invalidating. The worker owns one 256-entry cache for the whole process, so entries survive across jobs. Both classes count hits and misses as plain integers; the worker turns them into Prometheus counters with a `policy` label. `LLM_CACHE_POLICY=lru` (default) or `lfu` picks the class at start-up; an unknown value stops the worker with a clear error.

**Measured.** Two identical jobs: the first made 3 LLM calls and 3 cache misses; the second made 0 calls and 3 hits, under both policies.

## Likely questions

**Q:** Why not Python's `graphlib` and `functools.lru_cache`?

**A:** They would do, and in a product I would use them. The PDP point is to show the internals: that cycle detection falls out of Kahn's algorithm, and why the linked list makes LRU O(1). The hand-written versions are small, tested, and used by the real pipeline.

**Q:** Is the cache thread-safe?

**A:** No, and it does not need to be: the worker handles one job at a time (Cloud Run concurrency 1 plus a lock). The limitation is documented rather than solved with a lock nobody needs.

**Q:** Why is the cache not used by the CLI?

**A:** A single CLI run rarely repeats a prompt. The cache earns its keep in the long-running worker, where a re-pushed branch sends the same prompts again.
