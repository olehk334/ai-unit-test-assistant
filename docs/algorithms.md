# Algorithms: topological sort and LRU/LFU cache internals

Both algorithms are implemented from scratch inside the assistant (no
`graphlib`, no `functools.lru_cache`), each solving a problem the pipeline
actually has. PDP point 8.

## Topological sort — `ai_test_assistant/import_graph.py`

**Problem.** A PR often changes a module and the code that imports it. The
assistant processes changed files one at a time, and the order decides two
things. The report should list a module before the code that uses it. And a
module should be processed before tests exist for its importers: generated
tests are written under `tests/generated/`, which the related-test search
reads, so processing an importer first could feed its fresh tests into the
module's prompt as "related tests". The order does not change what a prompt
sees of the source code; every file is read from the PR head either way.

**Approach.** Build a directed graph over the *changed files only*: an edge
`A → B` means "B imports A" (dependency → dependent). Imports are extracted
with `ast` — plain `import x`, `from x import y`, and relative imports
resolved against the importing file's package. Then Kahn's algorithm:

1. Compute the in-degree (number of unprocessed dependencies) of every node.
2. Start with all zero-in-degree nodes.
3. Repeatedly emit a node and decrement the in-degree of its dependents;
   emit dependents when they reach zero.

The ready nodes sit in a min-heap keyed by original file position, so among
the files whose dependencies are done, the one listed first goes next and the
output is deterministic.

**Cycle handling.** If nodes remain unprocessed after the queue drains, they
form a cycle (`a imports b, b imports a`). Test generation must not stop for
a code smell, so the cycled files keep their original order and are listed in
the report (`import_cycle_files` in the JSON, a summary line in the
Markdown).

**Complexity.** O((V + E) log V) over changed files and the import edges
between them, plus the AST parse per file. Plain Kahn with a FIFO queue is
O(V + E); the heap costs the log factor and buys the original-order
tie-break. Kahn's was chosen over DFS-based sorting because cycle detection
falls out naturally (leftover nodes) instead of requiring recursion-stack
bookkeeping.

**Where it runs.** `pipeline.run_pr_assistant` orders changed files through
`order_files_by_imports` before processing.

## LRU cache — `ai_test_assistant/cache.py`

**Problem.** Re-running the assistant on a PR after a rebase re-sends
byte-identical prompts to Gemini. At temperature 0 the response is
deterministic, so the second call is pure waste.

**Internals.** The classic two-structure design:

- a `dict` maps key → node for O(1) lookup;
- a doubly linked list (with head/tail sentinel nodes) keeps usage order,
  most recent at the head.

`get` unlinks the node and re-links it after the head — two pointer swaps,
no scanning. `put` at capacity unlinks `tail.prev` (the least recently used
node) and drops it from the dict. Everything is O(1).

**Where it runs.** `LlmClient.generate` checks the cache before generating:
key = SHA-256 of (model, temperature, system instruction, prompt). The
analysis worker owns one process-lifetime cache (LRU by default,
`LLM_CACHE_POLICY=lfu` for LFU) and passes an `LlmClient` built with it into
`run_pr_assistant`, so cache entries survive across jobs — that is what makes "re-push the branch, watch tokens stay
flat" work. The CLI does not cache by default: a single run rarely repeats a
prompt, and adding a config knob for a near-zero win would be noise.

## LFU cache — `ai_test_assistant/cache.py`

**Internals.** Three structures:

- `dict` key → value;
- `dict` key → use count;
- `dict` use count → `OrderedDict` of keys at that count (insertion order =
  recency, oldest first), plus a `_min_frequency` pointer.

On use, a key moves from bucket *n* to bucket *n+1*. Eviction pops the
oldest key from the `_min_frequency` bucket — O(1), with LRU as the
tie-break inside a bucket.

**When LFU beats LRU.** LRU keeps *recent* keys; LFU keeps *popular* keys.
For a fleet-wide assistant where a few shared modules (`models.py`,
`utils.py`) appear in most PRs, LFU would protect those hot entries from
being flushed by a burst of one-off files. For a single repo's bursty PR
re-runs, LRU matches the access pattern better, which is why the worker uses
LRU by default. Set `LLM_CACHE_POLICY=lfu` to run the same jobs under LFU and
compare the two on the dashboard.

## Measuring the payoff

Both caches expose plain `hits` / `misses` integers. After each job the
analysis worker adds that job's share to the Prometheus counters
`llm_cache_hits_total` and `llm_cache_misses_total`, labelled with the
policy (`lru` or `lfu`). The Grafana dashboard shows one hit-ratio value per
policy, next to the token counters the cache is supposed to reduce.
