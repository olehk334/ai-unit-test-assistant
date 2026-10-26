# Topic 3 — Topological Sort & LRU / LFU Cache Internals

---

# PART A — SUMMARY-HINT (spoken answer)

## A1. Topological sort — definition and existence

A **topological order** of a directed graph is a linear ordering of its
vertices such that for every edge `u → v`, `u` appears before `v`.

- It exists **if and only if** the graph is a **DAG** (directed acyclic
  graph). A cycle makes ordering logically impossible: each vertex would have
  to precede itself.
- It is generally **not unique**. It is unique exactly when the DAG contains
  a Hamiltonian path — i.e. every consecutive pair is connected, leaving no
  freedom.
- Both standard algorithms run in **O(V + E)** time and **O(V)** extra space.

Read the edge direction as "must happen before": `models.py → service.py`
means models is a prerequisite of service.

## A2. Kahn's algorithm (BFS / in-degree)

```python
def kahn(nodes, edges):                 # edges: dependency -> [dependents]
    indegree = {n: 0 for n in nodes}
    for u in nodes:
        for v in edges[u]:
            indegree[v] += 1

    ready = deque(n for n in nodes if indegree[n] == 0)
    order = []
    while ready:
        u = ready.popleft()
        order.append(u)
        for v in edges[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                ready.append(v)

    if len(order) != len(nodes):
        cycle = [n for n in nodes if n not in set(order)]   # cycle members
    return order, cycle
```

**Why it works:** a vertex with in-degree 0 has no unmet prerequisites, so it
is safe to emit. Emitting it removes its edges, which may free others.

**Cycle detection is free:** if the loop ends before emitting every vertex,
the remaining vertices are exactly those trapped in (or downstream of) a
cycle — no extra bookkeeping needed.

**Useful variants:**

- Replace the queue with a **min-heap** → the lexicographically smallest
  valid order, `O(V log V + E)`.
- Process the queue **level by level** → each level is a set of tasks with no
  mutual dependencies, i.e. a **parallel execution schedule**; the number of
  levels is the length of the critical path.
- Break ties by the original input order → a **deterministic** result, which
  matters for reproducible builds and stable test output.

## A3. DFS-based algorithm

```python
WHITE, GRAY, BLACK = 0, 1, 2       # unvisited, in progress, finished

def dfs_topo(nodes, edges):
    colour, out = {n: WHITE for n in nodes}, []
    def visit(u):
        colour[u] = GRAY
        for v in edges[u]:
            if colour[v] == GRAY:  raise CycleError(u, v)   # back edge
            if colour[v] == WHITE: visit(v)
        colour[u] = BLACK
        out.append(u)              # post-order
    for n in nodes:
        if colour[n] == WHITE: visit(n)
    return out[::-1]               # reverse post-order = topological order
```

The insight: a vertex is appended only after **all** its descendants are
finished, so reversing the finish order puts every vertex before everything
it depends on. A **back edge** (an edge into a GRAY vertex) proves a cycle.

**Kahn vs DFS — how to choose:**

| | Kahn | DFS |
| --- | --- | --- |
| Style | Iterative — no recursion limit | Recursive (or explicit stack) |
| Cycle detection | Free (count check) | Back edge via 3-colour marking |
| Extra value | Level sets, parallel schedule, lexicographic control | Finish times, integrates with other DFS work (SCC) |
| Best when | You want determinism, level info, or safety on deep graphs | You are already doing DFS or need Tarjan's SCC |

## A4. Applications and neighbours

**Applications:** build systems (make, Bazel, Gradle), package/dependency
resolution, task schedulers (Airflow DAGs, CI pipelines), course
prerequisites, spreadsheet recalculation, compiler module-initialisation and
instruction scheduling, linker symbol resolution, database migration order,
dependency-injection container wiring, deadlock detection on a wait-for graph,
and — in this project — ordering changed source files so a module is analysed
before the modules that import it.

**Neighbouring algorithms worth naming:**

- **Strongly connected components** (Tarjan or Kosaraju, both `O(V+E)`):
  when the graph *does* contain cycles, contract each SCC into one node. The
  **condensation** is always a DAG, so you can topologically sort that. This
  is the professional answer to "what if there is a cycle?" — don't fail,
  condense.
- **DP on a DAG:** relaxing edges in topological order gives shortest *and*
  longest paths in `O(V+E)` — impossible in general graphs. Longest path =
  **critical path** (CPM) = minimum possible completion time.
- **Coffman–Graham** scheduling for a bounded number of processors.

## A5. Caching — why eviction policy exists

A cache is a small fast store in front of a large slow one. Because it is
small, every insertion beyond capacity requires a decision: **which entry to
evict**. That decision is the eviction policy, and it determines the **hit
ratio** — the only metric that ultimately matters, because
`average latency ≈ hit_ratio × fast + (1 − hit_ratio) × slow`.

**Belady's optimal algorithm (OPT/MIN)** evicts the entry whose next use is
furthest in the future. It is provably optimal and impossible to implement
(it needs the future), so it serves as the benchmark: real policies are
measured as a percentage of OPT.

Two access patterns motivate the two main policies:

- **Temporal locality** — recently used items are likely to be used again →
  **LRU**.
- **Frequency skew** — a few items are popular over long periods → **LFU**.

## A6. LRU internals

**Requirement:** `get` and `put` both O(1), including eviction.

**Structure — hash map + doubly linked list:**

- `dict: key → node` gives O(1) lookup.
- A **doubly linked list** keeps recency order: most-recently-used just after
  `head`, least-recently-used just before `tail`.
- Two **sentinel nodes** (`head`, `tail`) remove all empty-list and
  end-of-list special cases — the list is never truly empty.

```
head ⇄ [MRU] ⇄ [ ] ⇄ [ ] ⇄ [LRU] ⇄ tail
```

**Operations:**

- `get(k)`: look up in the dict; on hit, **unlink** the node and **re-link**
  it after `head` (two pointer swaps); return the value.
- `put(k, v)`: if the key exists, update the value and move to front. If not
  and the cache is full, evict `tail.prev` — remove it from the list *and*
  from the dict — then insert the new node after `head`.

**Why doubly linked?** Removing a node from the middle in O(1) requires
knowing its predecessor. A singly linked list would need an O(n) scan.

**Why not an array or heap?** An array needs O(n) shifting; a heap makes
operations O(log n). The dict + list combination is the only structure that
gives O(1) for all three requirements.

**Language shortcuts:** Python's `collections.OrderedDict` provides
`move_to_end()` and `popitem(last=False)` — a C-implemented LRU;
`functools.lru_cache` uses a circular doubly linked list internally. Naming
them shows breadth, but an exam usually wants the hand-built version.

**Classic mistakes to avoid out loud:** forgetting that `get` must update
recency; forgetting to delete the evicted key from the dict (a memory leak);
letting an update of an existing key grow the size; and not handling
capacity 0.

## A7. LFU internals

**Naive:** a min-heap keyed by frequency → O(log n) per operation. Acceptable,
but the expected answer is the **O(1) design** (Shah, Mitra & Matani, 2010).

**Structure — three maps plus a pointer:**

- `values: key → value`
- `freqs: key → use count`
- `buckets: count → ordered set of keys with that count` (insertion order
  inside a bucket = recency order, oldest first)
- `min_freq`: the smallest non-empty bucket

**Operations:**

- `get(k)`: read the value, then move the key from `buckets[f]` to
  `buckets[f+1]`. If `buckets[f]` becomes empty **and** `f == min_freq`, then
  `min_freq += 1`.
- `put(k, v)` for a new key when full: evict the **oldest** key in
  `buckets[min_freq]` (`popitem(last=False)`), insert the new key with
  frequency 1 and set `min_freq = 1`.

**Why `min_freq` is always correct:** a new entry always enters at frequency
1, which resets the minimum; and a frequency only ever increases by one at a
time, so when the minimum bucket empties the new minimum is exactly the next
integer. No search is ever needed — that is what makes it O(1).

**Tie-break by LRU** inside a bucket: among equally unpopular entries, evict
the one untouched longest.

**LFU's fatal flaw: ageing / cache pollution.** An item that was hot
yesterday keeps a huge count forever and can never be evicted, while genuinely
hot new items are thrown out at count 1. Fixes: periodically **halve all
counts** (exponential decay), use a **sliding window**, use a **probabilistic
counter with time-based decay** (Redis's approach), or use **W-TinyLFU**.

## A8. The policy landscape

| Policy | Idea | Strength | Weakness |
| --- | --- | --- | --- |
| **FIFO** | Evict oldest inserted | Trivial | Ignores usage; suffers Belady's anomaly |
| **Random** | Evict a random entry | O(1), no metadata | Mediocre hit ratio |
| **LRU** | Evict least recently used | Great for temporal locality; O(1) | A single full scan flushes the whole cache |
| **LFU** | Evict least frequently used | Great for stable popularity | Ageing problem; slow to adapt |
| **CLOCK / second chance** | Approximate LRU with one reference bit on a ring | Very cheap; used in OS page caches | Coarser than true LRU |
| **SLRU / 2Q** | Probation + protected segments | Scan-resistant | More tuning |
| **ARC** | Adaptive balance of recency and frequency with ghost lists | Self-tuning, excellent | Complex; was patent-encumbered |
| **W-TinyLFU** | Frequency sketch admission + small LRU window + SLRU main | Best-in-class hit ratios (Caffeine) | Most complex |

**Belady's anomaly:** for FIFO, *increasing* the cache size can *increase*
the miss count. It cannot happen for **stack algorithms** — LRU, LFU and OPT
— because their contents at size *n* are always a subset of their contents at
size *n+1* (the inclusion property). This is a favourite advanced question.

**Real systems:** CPU caches use set-associative pseudo-LRU; operating-system
page caches use CLOCK variants; **Redis** offers `allkeys-lru`,
`allkeys-lfu`, `volatile-ttl` and others, implementing *approximated* LRU by
sampling `maxmemory-samples` keys (default 5) rather than maintaining a
global list, and LFU as an 8-bit logarithmic counter with time decay;
**Caffeine** (Java) uses W-TinyLFU; **Memcached** uses segmented LRU; CDNs
often use frequency-based admission because storage is huge and objects are
large.

## A9. Caching patterns and hazards (beyond eviction)

**Read patterns:** *cache-aside* (application checks the cache, loads on
miss, populates — the most common, keeps the cache optional), *read-through*
(the cache library loads for you), *refresh-ahead* (proactive refresh before
expiry).
**Write patterns:** *write-through* (write both, consistent, slower),
*write-behind/back* (write cache now, store later — fast, risk of loss),
*write-around* (write the store, invalidate the cache — good when written
data is rarely read back).

**Hazards to name:**

- **Cache stampede / dogpile** — a hot key expires and a thousand requests
  hit the database at once. Fix: single-flight locking, probabilistic early
  expiry, or stale-while-revalidate.
- **Cache avalanche** — many keys expire simultaneously. Fix: TTL jitter.
- **Cache penetration** — repeated requests for a key that does not exist.
  Fix: negative caching or a Bloom filter.
- **Hot key** — one key saturates one node. Fix: replicate the key or add a
  client-side cache tier.
- **Stale data** — the hardest problem. Fix: short TTLs, event-driven
  invalidation, or versioned keys (`user:42:v7`) which sidestep deletion
  entirely.

**Distributed caching** adds **consistent hashing with virtual nodes** so
that adding a node moves only ~1/N of keys, and forces a decision about
whether the cache is authoritative (it should not be).

## A10. Rapid-fire Q&A

**Q: Prove a topological order exists iff the graph is a DAG.**
(⇐) In a finite DAG some vertex has in-degree 0 (otherwise follow edges
backwards forever and, being finite, you must revisit a vertex — a cycle).
Emit it, delete it, and the remainder is still a DAG; induct.
(⇒) If a cycle existed, its vertices would each have to precede the next and
therefore precede themselves — contradiction.

**Q: Kahn or DFS?** Kahn when you want cycle reporting, deterministic output,
level sets or no recursion depth risk; DFS when you already traverse depth-
first or need SCCs.

**Q: What if the dependency graph has a cycle?** Detect it, report the
members, and degrade gracefully — or condense the SCCs and sort the
condensation. Failing the whole job for a cycle is usually the wrong product
decision.

**Q: Why is LRU a hash map plus a doubly linked list?** The map gives O(1)
lookup, the list gives O(1) reordering and O(1) eviction from the tail, and
double links let you unlink a known node without scanning for its
predecessor.

**Q: How is LFU O(1)?** Frequency buckets of insertion-ordered keys plus a
`min_freq` pointer. Increments move a key to the adjacent bucket; eviction
pops the oldest key from the minimum bucket. Nothing is ever searched.

**Q: LRU or LFU for my workload?** LRU for bursty, recency-driven access
(re-runs, sessions, sliding working sets). LFU when a stable subset is
persistently popular and one-off traffic would otherwise flush the cache.
Modern default: a hybrid such as W-TinyLFU, or ARC.

**Q: What kills LRU?** A large sequential scan: it evicts the entire working
set with data that will never be reused. Scan-resistant policies (2Q, SLRU,
ARC, TinyLFU) exist for exactly this.

**Q: What is Belady's anomaly and which policies avoid it?** More cache can
mean more misses under FIFO. Stack algorithms (LRU, LFU, OPT) are immune by
the inclusion property.

**Q: How do you know your cache helps?** Measure hit ratio, and pair it with
the cost metric it is supposed to reduce. An unmeasured cache is a hypothesis.

---

# PART B — FULL REPORT

## B1. Graphs, formally but briefly

A directed graph `G = (V, E)` has vertices and ordered pairs of vertices. A
**path** follows edge directions; a **cycle** is a path from a vertex back to
itself. A **DAG** has no cycles. DAGs model every "must happen before"
relation — which is why the same algorithm appears in build tools, schedulers,
compilers and spreadsheets.

**Representation matters for complexity.** An adjacency list is
`O(V + E)` space and lets you iterate a vertex's neighbours in time
proportional to its degree — that is why both algorithms are `O(V + E)`. An
adjacency matrix is `O(V²)` space and would make the same algorithms `O(V²)`.
For sparse dependency graphs (real code, real tasks) adjacency lists are
always right.

**Vocabulary:** in-degree (edges arriving), out-degree (edges leaving),
source (in-degree 0), sink (out-degree 0), transitive reduction (the minimal
edge set preserving reachability — what build systems draw to avoid clutter).

## B2. Kahn's algorithm, worked

Take four files where `service` imports `models`, and `api` imports both:

```
models → service → api
   └───────────────↑
```

| Step | in-degrees | ready queue | emitted |
| --- | --- | --- | --- |
| init | models 0, service 1, api 2 | [models] | [] |
| 1 | service 0, api 1 | [service] | [models] |
| 2 | api 0 | [api] | [models, service] |
| 3 | — | [] | [models, service, api] |

Emitted 3 of 3 → no cycle.

Now add `models → api → models`:

| Step | in-degrees | ready | emitted |
| --- | --- | --- | --- |
| init | models 1, service 1, api 2 | [] | [] |

The queue starts empty; nothing is ever emitted; `len(order) = 0 ≠ 3`, so all
three are reported as cycle members. Note the subtlety: **vertices merely
*downstream* of a cycle are also never emitted**, so the "cycle set" is
really "everything blocked by a cycle." If you must report the exact cycle,
run Tarjan's SCC and take the components of size > 1 (or a self-loop).

**Determinism.** With a plain queue, the output depends on iteration order.
Sorting the ready set by the vertices' original input positions makes the
result reproducible — important when the output drives a build, a test run,
or a report a human will diff. This project does exactly that.

**Complexity proof sketch.** Computing in-degrees touches every edge once:
`O(V + E)`. In the main loop each vertex enters and leaves the queue exactly
once (`O(V)`), and each edge is relaxed exactly once when its source is
emitted (`O(E)`). Total `O(V + E)`; space `O(V)` for the degree map and
queue.

## B3. DFS-based sorting, and why three colours

Two colours (visited / unvisited) can detect that you have seen a vertex, but
not whether it is an *ancestor on the current path*. Only an edge into a
vertex that is still **in progress** (GRAY) is a back edge, and only a back
edge proves a cycle. An edge into a **finished** (BLACK) vertex is a
cross/forward edge and is perfectly legal in a DAG. Getting this distinction
right is the classic follow-up question.

**Recursion depth** is the practical hazard: a 10 000-file dependency chain
will exceed Python's default recursion limit. Either convert to an explicit
stack or use Kahn's algorithm — another reason this project chose Kahn.

## B4. Beyond a plain topological sort

**Parallel scheduling.** Emitting Kahn's ready set one *level* at a time
gives the maximum-parallelism schedule: every task in a level can run
concurrently, and the number of levels is the **critical path length** — the
theoretical minimum wall-clock time with unlimited workers. With a bounded
number of workers, **Coffman–Graham** produces a near-optimal schedule.

**Longest path / CPM.** Process vertices in topological order, relaxing
`dist[v] = max(dist[v], dist[u] + w(u,v))`. This is `O(V+E)` and is the basis
of project-management critical-path analysis and of the "estimated build
time" in modern build systems.

**Incremental rebuilds.** Real build systems do not re-sort from scratch:
they store the previous graph, apply the diff, and re-evaluate only the
affected subgraph. Bazel and similar tools additionally hash inputs so an
unchanged subtree is skipped entirely.

**Cycles in the wild.** Import cycles in Python often "work" at runtime but
break under some import orders; circular service dependencies in a
microservice architecture indicate a missing shared context. The engineering
answer is to *report* the cycle as a code-quality signal rather than to crash
the tool — a cycle in the analysed project is not an error in the analyser.

## B5. LRU implemented and dissected

The version implemented in this repository (`ai_test_assistant/cache.py`),
trimmed to essentials:

```python
class _LruNode:
    __slots__ = ("key", "value", "prev", "next")     # memory: no per-node dict

class LRUCache:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("Cache capacity must be at least 1")
        self.capacity = capacity
        self.hits = self.misses = 0
        self._nodes = {}
        self._head = _LruNode(None, None)     # sentinel: MRU side
        self._tail = _LruNode(None, None)     # sentinel: LRU side
        self._head.next, self._tail.prev = self._tail, self._head

    def get(self, key):
        node = self._nodes.get(key)
        if node is None:
            self.misses += 1
            return None
        self.hits += 1
        self._unlink(node)
        self._link_after_head(node)
        return node.value

    def put(self, key, value):
        node = self._nodes.get(key)
        if node is not None:                  # update, do not grow
            node.value = value
            self._unlink(node); self._link_after_head(node)
            return
        if len(self._nodes) >= self.capacity: # evict LRU
            victim = self._tail.prev
            self._unlink(victim)
            del self._nodes[victim.key]       # never forget the dict!
        node = _LruNode(key, value)
        self._nodes[key] = node
        self._link_after_head(node)
```

**Design points to defend:**

- **Sentinels.** `head` and `tail` are never removed, so `_unlink` and
  `_link_after_head` need no null checks — fewer branches, fewer bugs.
- **`__slots__`.** Removes each node's `__dict__`; with thousands of entries
  this is a large memory saving and a small speed win.
- **Counters as plain integers.** `hits`/`misses` are exposed as data, not
  pushed to a metrics library, so the cache has no dependency on Prometheus
  while still being observable. The *caller* decides how to export them.
- **Rejecting capacity < 1** at construction converts a silent
  misconfiguration (a cache that evicts everything immediately, quietly
  costing money) into a loud failure.

**Complexity:** `get`, `put`, evict — all `O(1)` amortised and worst case.
Space: `O(capacity)` with one dict entry and one node per key.

**Concurrency.** This implementation is not thread-safe: two concurrent
`put`s can corrupt the list. Options, in ascending order of sophistication:
a single mutex (simple, contended); **lock striping** (shard the cache by
`hash(key) % N`, each shard with its own lock — near-linear scaling);
lock-free designs; or Caffeine's approach of buffering access events in ring
buffers and replaying them asynchronously, so readers never block. In this
project jobs never overlap — Cloud Run gives each worker instance one request
at a time (**concurrency = 1**) and the worker holds a lock around each job —
so a lock inside the cache would be pure overhead. The limitation is
documented rather than ignored, which is the correct engineering posture.

## B6. LFU implemented and dissected

```python
class LFUCache:
    def __init__(self, capacity):
        self._values = {}                     # key -> value
        self._frequencies = {}                # key -> count
        self._keys_by_frequency = {}          # count -> OrderedDict of keys
        self._min_frequency = 0

    def get(self, key):
        if key not in self._values:
            self.misses += 1
            return None
        self.hits += 1
        self._increment_frequency(key)
        return self._values[key]

    def put(self, key, value):
        if key in self._values:
            self._values[key] = value
            self._increment_frequency(key)
            return
        if len(self._values) >= self.capacity:
            bucket = self._keys_by_frequency[self._min_frequency]
            evicted, _ = bucket.popitem(last=False)      # oldest at min freq
            del self._values[evicted]; del self._frequencies[evicted]
        self._values[key] = value
        self._frequencies[key] = 1
        self._keys_by_frequency.setdefault(1, OrderedDict())[key] = None
        self._min_frequency = 1                          # new key resets min

    def _increment_frequency(self, key):
        f = self._frequencies[key]
        bucket = self._keys_by_frequency[f]
        del bucket[key]
        if not bucket:
            del self._keys_by_frequency[f]
            if self._min_frequency == f:
                self._min_frequency = f + 1              # only ever +1
        self._frequencies[key] = f + 1
        self._keys_by_frequency.setdefault(f + 1, OrderedDict())[key] = None
```

**The two invariants that make it work:**

1. `_min_frequency` is always the smallest non-empty bucket. It is restored
   in exactly two places: set to 1 whenever a new key is inserted, and
   incremented by 1 when the current minimum bucket empties. No search.
2. Each bucket is an `OrderedDict`, so within one frequency the order is
   insertion/recency order and `popitem(last=False)` gives the LRU
   tie-break in `O(1)`.

**The ageing problem, concretely.** Suppose a key is fetched 10 000 times
during a launch, then never again. Its count stays at 10 000 forever, so it
occupies capacity permanently while today's hot keys, entering at count 1,
are evicted immediately. Mitigations:

- **Periodic halving** of all counts (cheap exponential decay).
- **Windowed counting** — only count accesses in the recent window.
- **Redis's approach** — an 8-bit *logarithmic* counter (so increments get
  rarer as the count grows, giving a large dynamic range in one byte) that
  **decays over time** (`lfu-decay-time`), combined with sampling rather
  than exact bookkeeping.
- **W-TinyLFU** — see below.

## B7. W-TinyLFU: the modern state of the art

Used by **Caffeine**, and the reason Java's default caching library beats
hand-rolled LRU by a wide margin.

Three parts:

1. **Frequency sketch** — a Count-Min Sketch with 4-bit counters estimates
   how often a key has been seen, using a few bytes per *cache slot* rather
   than storing counts per observed key. Counts are **halved periodically**,
   solving ageing by construction.
2. **Window cache (~1 %)** — a small LRU that absorbs bursts, so a brand-new
   hot key is not rejected before it can prove itself.
3. **Main cache (~99 %)** — a segmented LRU with probation and protected
   segments.

**Admission policy:** when the window evicts a candidate, its estimated
frequency is compared with that of the main cache's eviction victim; the
candidate is admitted only if it is estimated to be more valuable. This
"admission rather than eviction" idea is the key insight — it prevents a
one-off scan from displacing the working set at all, giving near-optimal hit
ratios with modest memory.

## B8. Choosing and measuring a cache

**Decision guide:**

| Situation | Policy |
| --- | --- |
| Sessions, recent work, re-runs (temporal locality) | LRU |
| A stable popular subset amid one-off noise | LFU (with ageing) or TinyLFU |
| Mixed/unknown, want self-tuning | ARC or W-TinyLFU |
| Kernel/page-cache scale, metadata must be tiny | CLOCK |
| Entries are equally valuable, simplicity wins | FIFO/Random |

**Sizing.** Hit ratio versus capacity is a concave curve with a knee: doubling
a small cache helps a lot, doubling a large one barely moves. Find the knee by
replaying a real access trace against candidate sizes — and compare against
**Belady's OPT** on the same trace to know how much room for improvement the
*policy* has, rather than the size.

**Metrics to expose:** hit ratio, evictions per second, entry count, memory
usage, and — crucially — the downstream metric the cache is meant to
improve (backend QPS, latency, or cost). A cache with a 95 % hit ratio that
does not reduce cost is caching the wrong thing.

**When not to cache:** when the data must be strictly fresh; when the
computation is cheaper than the lookup; when the hit ratio would be near zero
(unique keys); or when invalidation complexity would exceed the benefit.
"Cache invalidation" is famously one of the two hard problems in computer
science, and the honest answer to many caching questions is "make the key
content-addressed so invalidation is unnecessary."

## B9. How this project uses both algorithms

Both were implemented from scratch (no `graphlib`, no `functools.lru_cache`)
and each solves a real problem in the pipeline — which is what makes them
defensible rather than academic.

### Topological sort — `ai_test_assistant/import_graph.py`

**Problem.** A pull request changes both `models.py` and `service.py`, and
`service` imports `models`. The assistant processes changed files one at a
time, so it needs an order that is reproducible and means something. The
report should list `models` before the code that uses it. And `models` should
be processed before tests exist for `service`: generated tests land under
`tests/generated/`, which the related-test search reads, so processing
`service` first could feed its fresh tests into the prompt for `models`.

What the order does **not** do: change what a prompt sees of the source code.
Every file is read from the PR head either way, so "it avoids testing against
a stale dependency" would be a wrong answer.

**Solution.** Build an import graph **over the changed files only** (external
and unchanged modules are irrelevant to ordering), then run Kahn's algorithm:

```python
order = order_files_by_imports(changed_files, repo_root)
for changed_file in order.ordered_files:   # dependencies first
    ...
if order.cycle_files:                      # reported, not fatal
    ...
```

Design decisions worth quoting in an exam:

- **Imports are extracted with `ast`**, not regular expressions — including
  relative imports (`from .operations import add`) resolved against the
  importing module's package, and the `from package import module` form which
  must create an edge to `package.module`, not merely to `package`. (That
  last case was a real bug found in review and fixed with a regression test.)
- **Ties break by original file order**, so the pipeline is reproducible:
  the ready files sit in a min-heap keyed by original position (the min-heap
  variant from B2), `O((V + E) log V)`. The first version re-sorted the whole
  ready list on every step, which is `O(V² log V)`; harmless at PR size, but
  the documented complexity was wrong until the heap replaced it.
- **Cycles degrade gracefully**: the affected files keep their original order
  and are listed in the JSON and Markdown reports as
  `import_cycle_files`. A cycle in the analysed repository is a code smell in
  *that* repository, not a reason for the tool to fail.
- **Known limits, stated honestly:** dynamic imports (`importlib`,
  `__import__`) are invisible to static analysis, and only edges *between
  changed files* are built.

### LRU cache — `ai_test_assistant/cache.py` + `llm_client.py`

**Problem.** Re-running the assistant on a pull request after a rebase sends
byte-identical prompts to Gemini. At `temperature = 0` the response is
deterministic, so the second call is pure waste of money and latency.

**Solution.** A content-addressed cache in front of the model call:

```python
def _cache_key(self, system_instruction: str, prompt: str) -> str:
    material = "\x1f".join((self._config.gemini_model,
                            str(self._config.temperature),
                            system_instruction, prompt))
    return hashlib.sha256(material.encode()).hexdigest()
```

- **Everything that changes the answer is in the key** — model, temperature,
  system instruction, prompt. Change any of them and you get a different
  entry, so **explicit invalidation is never needed**. This is the
  content-addressed trick from B8.
- **Hashing, not raw prompts, as keys** keeps memory bounded and lookups
  cheap.
- **The cache is injected, not built in.** The CLI passes none (a single run
  rarely repeats a prompt); the long-running worker owns one 256-entry cache
  for the whole process (`LRUCache` by default, `LFUCache` with
  `LLM_CACHE_POLICY=lfu`), so it spans jobs — which is what makes "push the
  branch again, pay nothing" work.
- **Correctness precondition:** caching is only sound because
  `temperature = 0`. At non-zero temperature you would be replacing a
  distribution of answers with one sample. Naming this precondition is the
  difference between "I added a cache" and "I understood the cache."

**A real bug worth telling.** The cache never hit across jobs at first. The
cause: prompts embedded **absolute paths of the temporary clone directory**,
which differ on every job, so every key was unique. The fix was to include
only the module path and file name in prompts, with a regression test
(`test_prompt_stability.py`) asserting that two clones of the same code
produce identical prompts. **General lesson: a cache key must be built from
*normalised* input; any incidental variability silently destroys the hit
rate — silently, because a cache that never hits still returns correct
results.**

**Measured effect** (four identical jobs against the local monitoring stack):
job 1 produced 3 misses and 3 real model calls; jobs 2–4 produced 9 hits and
**zero** additional calls. Exported as `llm_cache_hits_total` and
`llm_cache_misses_total` (labelled with the policy) and displayed next to the
token-rate panel in Grafana — the optimisation is measured, not assumed.

### LFU — the switchable alternative

`LFUCache` is fully implemented with `O(1)` operations and unit tests, and
the worker runs with it when `LLM_CACHE_POLICY=lfu` is set; an unknown value
stops the worker at startup with a clear error. **LRU stays the default
because it matches the actual access pattern** (bursty re-runs of the same
branch — temporal locality). LFU would win in a different deployment: one
worker serving many repositories, where a few shared modules appear in most
pull requests. Because the cache counters carry a `policy` label, the same
jobs can be run under each policy and compared on the hit-ratio panel, so
the choice between them is measured rather than argued.

## B10. Study plan and sources

**Day 1 — graphs.** Implement both topological sorts from an empty file. Then
implement cycle *reporting* (not just detection) with Tarjan's SCC. Solve:
LeetCode 207/210 (Course Schedule I & II), 269 (Alien Dictionary), 310
(Minimum Height Trees), 1136 (Parallel Courses — the level-based variant).

**Day 2 — DAG dynamic programming.** Longest path, counting paths, and
critical-path scheduling. Read how one real build system schedules work.

**Day 3 — LRU.** Implement from scratch with sentinels (LeetCode 146), then
re-implement using `OrderedDict` and compare. Add hit/miss counters and a
micro-benchmark.

**Day 4 — LFU.** Implement the `O(1)` version (LeetCode 460). Then implement
count halving and measure hit ratio on a synthetic Zipf-distributed trace
against LRU.

**Day 5 — real systems.** Read the Redis eviction documentation
(`maxmemory-policy`, sampling, the LFU counter) and the Caffeine
design/W-TinyLFU write-up. Write one paragraph on when each policy wins.

**References:** *Introduction to Algorithms* (CLRS) ch. 22 for DFS,
topological sort and SCC; Kahn (1962) for the original algorithm; Shah,
Mitra & Matani, *An O(1) algorithm for implementing the LFU cache eviction
scheme* (2010); Einziger, Friedman & Manes, *TinyLFU: A Highly Efficient
Cache Admission Policy* (2015); Megiddo & Modha, *ARC* (2003); Belady (1966)
for the optimal algorithm and the anomaly; the Redis and Caffeine
documentation for production behaviour.
