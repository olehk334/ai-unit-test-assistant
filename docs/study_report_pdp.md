# Study & Exam Preparation Report

**Topics:** Distributed Systems & Cloud Architecture · Prometheus & Grafana · Topological Sort, LRU & LFU caches

**Sourcing note:** Core theory below is general engineering knowledge. Where current product facts matter, they were checked against the official [Prometheus documentation](https://prometheus.io/docs/introduction/overview/) and [Alertmanager docs](https://prometheus.io/docs/alerting/latest/alertmanager/), plus 2026 cloud comparison sources listed at the end. Cloud provider service names, quotas, and pricing change frequently — **always re-verify limits and prices against the provider's own docs before quoting them in an exam or design review.**

**A note on the examples:** Many examples reference `ai-unit-test-assistant` — the system built in this repository (Cloud Run + Pub/Sub + GCS + Vertex AI, with Prometheus metrics, Kahn's topological sort, and a hand-rolled LRU cache). Using a system you actually built is the strongest possible exam material: you can answer "have you used this in practice?" with specifics.

---

# English Version

## 1. Distributed Systems & Cloud Architecture

### 1.1 Exam Summary-Hint

#### What it is
A **distributed system** is a set of independent computers that appear to users as one coherent system. **Cloud architecture** is the practice of assembling such systems from managed building blocks (compute, storage, messaging, identity) rented from a provider.

#### Why it exists
Single machines hit three walls: **capacity** (one box can't hold the load), **availability** (one box is one failure away from downtime), and **geography** (users far away see high latency). Distribution solves all three — at the cost of new failure modes that don't exist in a monolith.

#### How it works (the one-sentence version)
Split work across machines, replicate state so no single loss is fatal, route requests with load balancers, decouple components with queues, and accept that the network will fail — so design every operation to be **retryable** and **idempotent**.

#### Main components
| Component | Role |
|---|---|
| Load balancer | Distributes requests; removes unhealthy instances |
| Service instances | Stateless compute, scaled horizontally |
| Message broker / queue | Decouples producers from consumers; absorbs bursts |
| Datastore(s) | Replicated and/or sharded persistent state |
| Cache | Reduces latency and load on the datastore |
| Service registry / discovery | Lets services find each other |
| Observability stack | Metrics, logs, traces — how you debug the above |

#### Main flow (a request's life)
```
Client → DNS → Load balancer → API gateway (authn/authz, rate limit)
      → Service A (sync call) → Service B
                             → publishes event → Broker → Consumer (async work)
      → Datastore (primary write → replicas)
      → Response
```

#### Important terminology (30-second version)
- **Latency** — time per operation. Quote **percentiles** (p50/p95/p99), never averages.
- **Availability** — fraction of time the system serves correctly ("three nines" = 99.9% ≈ 43 min downtime/month).
- **Consistency** — do all readers see the same data? **Strong** = always; **eventual** = eventually.
- **Partition tolerance** — the system keeps working when the network splits.
- **CAP theorem** — during a network **partition**, you must choose **consistency** or **availability**. Not a general "pick 2 of 3."
- **Replication** — same data on many nodes (availability, read scaling).
- **Sharding** — different data on different nodes (write/storage scaling).
- **Idempotency** — doing it twice equals doing it once. The foundation of safe retries.
- **Backpressure** — signalling upstream to slow down instead of collapsing.
- **Eventual consistency** — replicas converge if writes stop.

#### Common tools
Kubernetes, Envoy/NGINX, Kafka, RabbitMQ, GCP Pub/Sub, AWS SQS/SNS, Redis, PostgreSQL, Cassandra, DynamoDB, Terraform, Istio/Linkerd.

#### Strengths and weaknesses
| Strengths | Weaknesses |
|---|---|
| Horizontal scale, no single ceiling | Hard to reason about; partial failure everywhere |
| Fault isolation, no single point of failure | Debugging needs real observability investment |
| Independent deploys, team autonomy | Network is slow and unreliable vs. in-process calls |
| Geographic proximity to users | Distributed data consistency is genuinely difficult |
| Elastic cost | Operational and cognitive overhead |

#### Typical use cases
High-traffic web/mobile backends, streaming/event pipelines, multi-tenant SaaS, CI/CD and batch processing platforms, anything needing regional failover.

#### Common exam questions with short answers
| Question | Short answer |
|---|---|
| State CAP precisely. | When a partition (P) occurs, a system must sacrifice either consistency (C) or availability (A). Without a partition you can have both — so CAP is a statement about behavior *during* partitions. |
| CAP vs PACELC? | PACELC extends it: **if P** → choose A or C; **else (E)** → choose **L**atency or **C**onsistency. It captures the everyday tradeoff CAP ignores. |
| Why is exactly-once delivery "impossible"? | Two Generals: the sender can never be certain the ack was received. You get at-least-once delivery plus **idempotent processing**, which yields exactly-once *effects*. |
| Difference between replication and sharding? | Replication = copies of the *same* data (availability, read scale). Sharding = *different* data on each node (write/storage scale). Usually combined. |
| How do you make retries safe? | Idempotency keys, exponential backoff **with jitter**, bounded attempts, circuit breakers, and a dead-letter queue for poison messages. |
| What is a saga? | A long-running transaction split into local transactions, each with a compensating action. Used instead of 2PC across services. |

#### Common mistakes and misconceptions
1. **"CAP means pick 2 of 3."** No — P is not optional in a real network; you choose C or A during partitions.
2. **"Microservices are always better."** They trade code complexity for operational complexity. A modular monolith is the correct default for a small team.
3. **Reporting average latency.** Averages hide the tail that users actually feel.
4. **Retrying without idempotency** — turns a transient failure into duplicated side effects (double charges, double emails).
5. **Retrying without jitter** — synchronised retries produce a thundering herd that keeps the service down.
6. **"Eventual consistency = data can be wrong forever."** No — it converges once writes stop; the question is the convergence window.
7. **Sharing one database across microservices.** That's a distributed monolith: you get the operational cost with none of the independence.

#### The "perfect answer" to memorise
> A distributed system spreads work across independent machines to gain scale, availability, and geographic proximity. The price is partial failure: the network can drop, delay, duplicate, or reorder anything. The CAP theorem formalises the sharpest consequence — during a network partition you must choose consistency or availability — and PACELC adds that even without partitions you trade latency against consistency. So the practical discipline is: replicate for availability, shard for scale, put queues between components so bursts don't cascade, make every operation idempotent so retries are safe, and bound failure with timeouts, backoff-with-jitter, circuit breakers and dead-letter queues. Cloud platforms sell these primitives as managed services — for example, in my own project a GitHub webhook hits a Cloud Run receiver, which publishes to Pub/Sub; a private worker consumes with at-least-once delivery, deduplicates using an artifact marker in Cloud Storage as its idempotency key, and poison messages dead-letter after five attempts.

---

### 1.2 Full Study Report

#### 1.2.1 Core distributed systems concepts

##### The eight fallacies (why this is hard)
Peter Deutsch's fallacies of distributed computing — each one is a bug waiting to happen: the network is reliable; latency is zero; bandwidth is infinite; the network is secure; topology doesn't change; there is one administrator; transport cost is zero; the network is homogeneous. **Every one is false.** Most production incidents are one of these assumptions leaking into code.

##### Latency
Time to complete one operation. The critical discipline is *distribution thinking*:

| Metric | Meaning | Use |
|---|---|---|
| p50 (median) | Typical experience | Capacity planning |
| p95 / p99 | Tail — the unhappy users | SLOs, alerting |
| p99.9 | Rare but systemic | Large-scale systems |
| Average | **Misleading** | Avoid in user-facing SLOs |

Rough orders of magnitude worth memorising:

```
L1 cache reference               ~1 ns
Main memory reference            ~100 ns
SSD random read                  ~16 µs
Datacenter round trip            ~500 µs
Disk seek (HDD)                  ~2 ms
Packet CA → Netherlands → CA     ~150 ms
```

**Key insight:** a network call is ~10,000× more expensive than a memory access. Every microservice boundary you draw is a decision to pay that cost. **Tail latency amplification:** if one request fans out to 10 services each with p99 = 100 ms, the probability that *at least one* is slow approaches 1 — your p99 becomes their worst case. Mitigations: hedged requests, fan-out reduction, and tail-tolerant design.

##### Availability
```
Availability = uptime / (uptime + downtime)
```

| Nines | Availability | Downtime/year | Downtime/month |
|---|---|---|---|
| 2 | 99% | 3.65 days | 7.2 hours |
| 3 | 99.9% | 8.77 hours | 43.8 minutes |
| 4 | 99.99% | 52.6 minutes | 4.4 minutes |
| 5 | 99.999% | 5.26 minutes | 26 seconds |

**Serial dependencies multiply:** a service depending on three 99.9% components has a ceiling of 0.999³ ≈ **99.7%**. **Redundancy adds nines:** two independent 99% replicas give 1 − 0.01² = **99.99%** — *if* failures are truly independent (they rarely are: shared power, shared network, shared bad deploy).

##### Consistency models (strongest → weakest)
| Model | Guarantee | Cost |
|---|---|---|
| **Linearizable** (strong) | Every read sees the latest write; system behaves like one copy | Coordination on every op; latency; unavailable during partition |
| **Sequential** | All nodes see operations in the same order (not necessarily real-time) | Cheaper than linearizable |
| **Causal** | Causally related operations are seen in order; concurrent ops may differ | Good middle ground |
| **Read-your-writes** | You see your own writes | Session guarantee, cheap and very user-visible |
| **Monotonic reads** | You never see time go backwards | Session guarantee |
| **Eventual** | Replicas converge if writes stop | Cheapest, highest availability |

Practical note: **session guarantees** (read-your-writes + monotonic reads) deliver most of the *perceived* correctness of strong consistency at a fraction of the cost. This is why "sticky sessions to the primary after a write" is such a common pattern.

##### CAP and PACELC
**CAP (Brewer, proved by Gilbert & Lynch):** in the presence of a network **P**artition, a distributed system must choose between **C**onsistency (linearizability) and **A**vailability (every request gets a non-error response).

```
        Network partition happens
                  │
        ┌─────────┴──────────┐
     CP system            AP system
  Refuse writes on      Accept writes on
  the minority side     both sides
  → consistent          → available
  → unavailable         → divergent, needs reconciliation
  e.g. etcd, ZooKeeper, e.g. Cassandra, DynamoDB (tunable),
  HBase, Spanner*       Riak, DNS
```
\* Spanner is effectively CP but achieves very high availability by making partitions rare with a private global network plus TrueTime.

**PACELC (Abadi)** is the more useful daily model:
> **if (P)** then choose **A** or **C**; **else (E)** choose **L**atency or **C**onsistency.

Examples: DynamoDB = PA/EL (available and fast, eventually consistent by default, strong reads optional). Spanner = PC/EC (consistent, pays latency). Cassandra = PA/EL with tunable quorums.

**Quorum arithmetic** — the knob behind "tunable consistency":
```
N = replicas, W = write quorum, R = read quorum
If W + R > N  →  read and write sets overlap  →  strong-ish consistency
Common: N=3, W=2, R=2  →  2+2 > 3 ✓
Fast reads:  N=3, W=3, R=1   (slow writes, fast reads)
Fast writes: N=3, W=1, R=3   (fast writes, slow reads)
```

##### Replication
| Strategy | How | Pros | Cons |
|---|---|---|---|
| **Single-leader** | All writes to leader; replicated to followers | Simple; no write conflicts | Leader is a bottleneck & failover point |
| **Multi-leader** | Multiple accept writes; replicate to each other | Multi-region write locality | **Write conflicts** need resolution (LWW, CRDTs, app logic) |
| **Leaderless** (Dynamo-style) | Client writes to N, waits for W acks | No failover step; highly available | Needs read-repair, anti-entropy, quorum tuning |

**Synchronous vs asynchronous replication** is the durability/latency dial: sync = no data loss on failover but a slow replica stalls writes; async = fast, but failover can lose the un-replicated tail. Common compromise: **semi-synchronous** — one sync replica, rest async.

**Replication lag** causes the classic bugs: user posts a comment, reads from a lagging replica, comment "disappears." Fix with read-your-writes routing.

##### Sharding (partitioning)
| Scheme | How | Pros | Cons |
|---|---|---|---|
| **Range** | Key ranges per shard (A–M, N–Z) | Efficient range scans | **Hotspots** (e.g. time-ordered keys hit the newest shard) |
| **Hash** | `hash(key) % N` | Even distribution | Range queries need scatter-gather; resharding moves everything |
| **Consistent hashing** | Keys and nodes on a ring; virtual nodes | Adding a node moves only ~1/N of keys | More complex; needs vnodes for balance |
| **Directory / lookup** | Explicit shard map service | Maximum flexibility, easy rebalancing | Lookup service is a dependency and SPOF |

**Hot key / celebrity problem:** one key (a viral post, a huge tenant) exceeds one shard's capacity. Mitigations: key salting/split counters, dedicated shards for whales, caching in front.

##### Load balancing
| Layer | Operates on | Examples | Notes |
|---|---|---|---|
| **L4** | TCP/UDP | AWS NLB, IPVS | Fast, protocol-agnostic, no HTTP awareness |
| **L7** | HTTP/gRPC | Envoy, NGINX, AWS ALB | Path/header routing, retries, TLS termination |
| **Client-side** | In-process | gRPC-LB, Ribbon | No extra hop; client needs registry data |
| **Service mesh (sidecar)** | Per-pod proxy | Istio, Linkerd | mTLS, retries, telemetry without app changes |

Algorithms: round-robin, weighted RR, **least connections**, **least request** (better for uneven request costs), consistent hash (cache affinity, sticky sessions), EWMA/latency-aware. **Health checks** matter more than the algorithm: *passive* (eject on errors) plus *active* (probe endpoint) with a slow-start period to avoid hammering a cold instance.

##### Fault tolerance
Design assumption: **everything fails, all the time.** Toolkit:
- **Timeouts** — the most under-used tool. No timeout = a hung dependency exhausts your thread/connection pool and takes you down with it. Set them from p99 measurements, not by feel.
- **Retries** — only for *transient* faults, only on *idempotent* operations, always bounded, always with jitter.
- **Circuit breaker** — closed → (failures exceed threshold) → open (fail fast, don't hammer) → after cooldown → half-open (trial requests) → closed.
- **Bulkheads** — isolated resource pools per dependency so one slow downstream can't consume every thread.
- **Graceful degradation** — serve stale cache, hide a non-critical widget, queue the write for later.
- **Redundancy** — N+1 instances, multi-AZ, multi-region.

**Backoff with jitter** (do not skip the jitter):
```python
delay = min(cap, base * 2 ** attempt)
delay = random.uniform(0, delay)      # "full jitter" — decorrelates clients
```
Without jitter, every client retries at the same instant and the recovering service is knocked down again — a **retry storm**. Guard the whole system with a **retry budget** (e.g. retries ≤ 10% of requests).

##### Idempotency
**Definition:** `f(f(x)) == f(x)`. Applying an operation N times has the same effect as applying it once.

| Naturally idempotent | Not idempotent |
|---|---|
| `PUT /users/42 {...}` (full replace) | `POST /orders` (creates a new order each time) |
| `DELETE /users/42` | `balance += 100` |
| `SET key value` | `INCR counter` |

**Implementation patterns:**
1. **Idempotency key** — client sends a unique key; server stores `key → result` and replays the stored result on repeat (how Stripe's API works).
2. **Natural key / dedup marker** — derive a deterministic ID from the payload; check existence before acting. *This is what the assistant does: the marker is the GCS object `repo/PR/head_sha/reports/ai-test-report.json` — if it exists, the job is acknowledged without reprocessing.*
3. **Conditional writes** — compare-and-set, `If-Match` ETags, optimistic versioning.
4. **Dedup table with TTL** — store processed message IDs for a bounded window.

**Exactly-once, honestly:** exactly-once *delivery* is impossible over an unreliable network (Two Generals problem). What is achievable is **at-least-once delivery + idempotent processing = exactly-once effects**. Kafka's "exactly-once semantics" is precisely this: idempotent producers plus transactional read-process-write within Kafka — it does not extend to arbitrary external side effects.

##### Backpressure
When a producer is faster than a consumer, something must give. Options, best to worst:
1. **Blocking / pull-based flow control** — consumer requests what it can handle (Kafka pull, Reactive Streams `request(n)`, TCP windows).
2. **Bounded buffer + reject** — queue with a cap; return 429/503 when full (**load shedding**).
3. **Rate limiting** — token bucket / leaky bucket at the entry point.
4. **Unbounded queue** — ⚠️ **the trap**: latency grows without bound, memory exhausts, and the system fails in the worst possible way (slowly, then all at once). "Queues don't fix throughput mismatches — they only smooth bursts."

##### Message queues and brokers
| Model | Semantics | Examples |
|---|---|---|
| **Point-to-point queue** | Each message to exactly one consumer; competing consumers | SQS, RabbitMQ queue |
| **Pub/Sub topic** | Each message to *every* subscriber | SNS, GCP Pub/Sub, Redis pub/sub |
| **Log / stream** | Ordered, replayable, offset-based; consumers track position | Kafka, Kinesis, Pulsar |

**Queue vs log** is the distinction people miss: a queue *deletes* on ack; a log *retains* for a retention window, so new consumers can replay history and multiple consumer groups read independently. Choose a log when you need replay, event sourcing, or multiple independent readers.

##### Distributed transactions
| Approach | How | Pros | Cons |
|---|---|---|---|
| **2PC** | Coordinator: prepare → commit | Real ACID across nodes | **Blocking** if coordinator dies; poor availability; rarely used across services |
| **Saga** | Chain of local txns + compensating actions | Available, scalable, no locks | No isolation (intermediate states visible); compensations are hard to write |
| **Outbox** | Write business row + event row in **one** local txn; relay publishes | Atomic DB-write + publish, no 2PC | Needs a relay/CDC; at-least-once → needs idempotent consumers |
| **TCC** | Try / Confirm / Cancel with reservations | Better isolation than saga | Invasive API design |

**Sagas** come in two flavours: **choreography** (each service reacts to events — no coordinator, but the flow is implicit and hard to trace) and **orchestration** (a central orchestrator drives steps — explicit and debuggable, but the orchestrator is a component to own). Prefer orchestration once a flow exceeds ~3 steps.

**Dual-write problem:** writing to a DB *and* publishing to a broker without a shared transaction. If the process dies between them, state and events diverge — permanently. The **transactional outbox** is the standard fix.

#### 1.2.2 Microservices architecture

##### Service boundaries
The hardest and most consequential decision. Guidance:
- **Domain-Driven Design bounded contexts** — a service owns a model whose terms mean one thing ("Order" in Sales ≠ "Order" in Shipping).
- **Team ownership (Conway's Law)** — your architecture will mirror your communication structure; design boundaries you can actually staff.
- **Rate of change** — code that changes together belongs together.
- **Data ownership** — one service is the source of truth for each entity.

**Smells of wrong boundaries:** every feature requires changing 3 services; services share a database; chatty synchronous chains (A→B→C→D); a "distributed monolith" that must be deployed in lockstep.

**Modern consensus:** start with a **modular monolith**, extract services when a *specific* pressure appears (independent scaling need, team autonomy at scale, isolation of a risky component). Extracting too early is the most common expensive mistake.

##### API gateway
Single entry point handling cross-cutting concerns: TLS termination, authentication/authorization, rate limiting, request routing, response aggregation, protocol translation (REST↔gRPC), and API versioning.

```
                     ┌──────────────┐
Mobile ──┐           │              │──► Orders service
Web    ──┼──────────►│ API Gateway  │──► Users service
Partner ─┘           │  authn/rate  │──► Catalog service
                     └──────────────┘
```
**Risks:** it can become a monolithic bottleneck and a deployment chokepoint. Keep business logic out of it. **BFF (Backend For Frontend)** is a common refinement: one gateway per client type so mobile and web can evolve independently.

##### Service discovery
| Pattern | How |
|---|---|
| **Client-side** | Client queries a registry (Consul, Eureka) and load-balances itself |
| **Server-side** | Client hits a stable LB/DNS name; the platform resolves instances |
| **Platform-native** | Kubernetes Services + DNS, or the cloud's own routing (Cloud Run URLs) |

Registration is either **self-registration** (service calls the registry) or **third-party** (the platform registers it — Kubernetes' model). Health checks must drive deregistration, otherwise you route to corpses.

##### Synchronous vs asynchronous communication
| | Synchronous (REST/gRPC) | Asynchronous (events/queues) |
|---|---|---|
| **Coupling** | Temporal — callee must be up *now* | Decoupled — broker buffers |
| **Latency** | Immediate result | Eventually processed |
| **Failure** | Propagates up the chain | Absorbed by queue, retried |
| **Complexity** | Simple to trace | Harder to debug; needs correlation IDs |
| **Use when** | You need the answer to respond | Fire-and-forget, fan-out, long work |

**Rule of thumb:** synchronous for *queries* the user is waiting on; asynchronous for *commands* and side effects. Each synchronous hop multiplies failure probability and adds latency — a 5-deep sync chain is a design smell.

##### Database per service
Each service owns its schema; others access it **only** through its API. This buys independent deployment, schema evolution, and technology choice — at the cost of losing joins and cross-service ACID.

Consequences you must handle:
- **No joins across services** → API composition, or **CQRS** with a read model built from events.
- **Data duplication is normal** — Orders may cache the customer's name. Accept it; refresh via events.
- **Reporting** → publish to a warehouse (BigQuery/Redshift/Snowflake); never query services' internal DBs.

##### Observability for microservices
The three pillars, plus what actually matters:
- **Metrics** — cheap, aggregated, alertable. RED (Rate, Errors, Duration) per service; USE (Utilization, Saturation, Errors) per resource.
- **Logs** — structured JSON, with a **correlation/trace ID** on every line. Unstructured logs across 20 services are unusable.
- **Traces** — the request's path across services with per-span timing. The only practical way to answer "why was *this* request slow?"

**Non-negotiable:** propagate a trace context (W3C `traceparent`) through every hop, including through queues. OpenTelemetry is now the vendor-neutral standard for all three signals.

##### Deployment and scaling
| Strategy | Description | Risk |
|---|---|---|
| **Rolling** | Replace instances gradually | Two versions coexist — needs compatible APIs/schemas |
| **Blue-green** | Full parallel environment, flip traffic | Fast rollback; 2× cost during the flip |
| **Canary** | 1% → 10% → 100%, watching metrics | Best risk control; needs good telemetry and automation |
| **Feature flags** | Deploy dark, enable per-cohort | Decouples deploy from release; flag debt accumulates |

**Scaling:** horizontal (add instances — requires stateless services) beats vertical (bigger machine — simple but capped). Autoscale on the signal that reflects work: CPU for compute-bound, **queue depth** for worker pools, RPS/concurrency for web tiers. **Database migrations must be backwards-compatible** — expand/contract: add column → deploy code writing both → backfill → switch reads → drop old column, across multiple releases.

#### 1.2.3 Event-driven systems

##### Roles
```
┌──────────┐   publish   ┌────────────────┐  deliver  ┌───────────┐
│ Producer │────────────►│     Broker     │──────────►│ Consumer  │
└──────────┘             │ topics/queues  │           └───────────┘
                         │  retention     │                 │ ack/nack
                         │  partitions    │◄────────────────┘
                         └────────────────┘
                                 │ after N failed attempts
                                 ▼
                         ┌────────────────┐
                         │ Dead-letter Q  │
                         └────────────────┘
```
- **Producer** — publishes an event (a fact: `OrderPlaced`), never knows who consumes it.
- **Broker** — stores, routes, and tracks delivery. The system's shock absorber.
- **Consumer** — subscribes and processes; acknowledges to advance.
- **Topic** — named channel, usually multi-subscriber.
- **Queue** — work distribution among competing consumers.
- **Subscription** — a consumer group's cursor/state over a topic.

**Push vs pull** is a real architectural choice: **pull** (Kafka, SQS) gives the consumer natural flow control; **push** (GCP Pub/Sub push, webhooks) is simpler to operate — the consumer is just an HTTP endpoint — but the broker must handle flow control and the consumer must respond fast. *The assistant uses push: the worker is a plain Cloud Run HTTP service, and HTTP status codes are the queue protocol — 200 = ack, 500 = retry then dead-letter.*

##### Event types (frequently confused)
| Type | Contains | Consumer needs |
|---|---|---|
| **Event notification** | "Order 42 changed" | Must call back for details |
| **Event-carried state transfer** | Full order payload | Self-sufficient; enables replicas but couples to schema |
| **Event sourcing** | The event log **is** the source of truth; state = replay | Powerful audit/replay; high complexity, schema evolution pain |

Also distinguish **events** ("something happened", past tense, no expectation) from **commands** ("do this", imperative, expects an outcome). Mixing them in one topic makes ownership ambiguous.

##### Ordering
Total ordering across a distributed topic is expensive and usually unnecessary. What real systems provide:
- **Per-partition/per-key ordering** — Kafka guarantees order within a partition; route by key (`order_id`) so one entity's events stay ordered.
- **GCP Pub/Sub** offers optional **ordering keys**, at a throughput cost.
- **No global order** — accept it and design for it: version numbers/timestamps in payloads so consumers can detect and discard stale updates.

**Consequence of parallelism:** more consumers = more concurrency = weaker ordering. Ordering and throughput are directly opposed.

##### Delivery guarantees
| Guarantee | Meaning | Cost |
|---|---|---|
| **At-most-once** | Ack before processing; may lose messages | Fast, lossy — only for disposable telemetry |
| **At-least-once** | Ack after processing; may duplicate | **The practical default** — requires idempotent consumers |
| **Exactly-once** | No loss, no duplicates | Only within a closed system (Kafka transactions); across external effects, achieved via at-least-once + idempotency |

##### Dead-letter queues
After N failed delivery attempts, the broker moves the message to a DLQ instead of retrying forever.

**Why essential:** one **poison message** (malformed, or hitting a permanent bug) would otherwise block or endlessly consume retry capacity. **Operating a DLQ:** alert on non-zero depth (it means human attention is needed), keep failure metadata, provide a replay path after fixing the bug, and inspect before purging.

**Key design distinction:** *permanent* errors (malformed payload — will never succeed) should be **acknowledged immediately**, not retried. Only *transient* errors deserve retries. *The assistant does exactly this: an undecodable Pub/Sub envelope returns 200 (ack, don't retry), while a failed clone or LLM outage returns 500 (retry → DLQ after 5 attempts).*

##### Event schema evolution
Events are a public contract with an unbounded set of consumers. Rules: additive changes only (new optional fields), never remove or repurpose a field, version the schema (`OrderPlaced.v2`), use a **schema registry** (Avro/Protobuf) to enforce compatibility at publish time, and have consumers **ignore unknown fields**.

#### 1.2.4 Serverless

##### What it means
You deploy **code or containers**; the platform handles provisioning, scaling (including to zero), patching, and availability. You pay per use rather than per hour of reserved capacity. "Serverless" ≠ "no servers" — it means *not your servers*.

##### FaaS vs managed services vs serverless containers
| Model | Unit | Examples | Best for |
|---|---|---|---|
| **FaaS** | A function, event-triggered | Lambda, Cloud Functions, Azure Functions | Glue code, event handlers, short tasks |
| **Serverless containers** | A container image, HTTP/event-driven | Cloud Run, AWS Fargate, Container Apps | Normal web services; no runtime lock-in |
| **Managed backing services** | A capability | S3, DynamoDB, Pub/Sub, BigQuery, Aurora Serverless | Storage/messaging/analytics without ops |

##### Cold starts
The latency when a request arrives with no warm instance: provision sandbox → load runtime → initialise your code → handle the request.

| Factor | Effect |
|---|---|
| Runtime | Interpreted (Python/JS) fast; JVM/.NET slower (though AOT/native images close the gap) |
| Package size | Bigger deployment = slower load |
| Init code | Heavy imports/connections at module scope cost every cold start |
| VPC attachment | Historically a large penalty; much improved on modern platforms |
| Memory allocated | More memory usually means more CPU → faster init |

**Mitigations:** provisioned concurrency / minimum instances (costs money, defeats scale-to-zero), lazy initialisation, trimmed dependencies, and — most importantly — **deciding whether it matters**: for an async worker behind a queue, a 2-second cold start is irrelevant.

##### Scaling and pricing
Scaling is per-request/per-event and near-instant, bounded by account concurrency limits. **The classic failure mode:** the function scales to 1,000 concurrent instances and each opens a database connection — the database dies. Fixes: connection pooling proxies (RDS Proxy), reserved concurrency caps, or queue-buffered workers.

**Pricing** = invocations × duration × memory (plus network/egress). Serverless is dramatically cheaper for spiky/low-duty-cycle workloads and *more* expensive than reserved capacity for sustained high load. There is a real crossover point — compute it rather than assuming.

##### Limitations (know these for the exam)
- Execution time caps (minutes-scale; varies by platform — check current docs).
- Payload and memory ceilings.
- No persistent local state — external store required.
- Vendor lock-in via event formats and IAM (mitigate with containers + hexagonal architecture).
- Debugging is harder: no SSH, ephemeral instances — observability must be built in.
- Long-lived connections (WebSockets) need platform-specific support.

#### 1.2.5 Cloud platform comparison — AWS vs GCP vs Azure

| Capability | AWS | GCP | Azure |
|---|---|---|---|
| **VMs** | EC2 | Compute Engine | Virtual Machines |
| **Managed Kubernetes** | EKS | GKE | AKS |
| **Serverless containers** | Fargate / App Runner | **Cloud Run** | Container Apps |
| **FaaS** | Lambda | Cloud Functions | Azure Functions |
| **PaaS** | Elastic Beanstalk | App Engine | App Service |
| **Object storage** | S3 | Cloud Storage | Blob Storage |
| **Relational** | RDS / Aurora | Cloud SQL / **Spanner** | SQL Database |
| **NoSQL** | DynamoDB | Firestore / Bigtable | **Cosmos DB** |
| **Data warehouse** | Redshift | **BigQuery** | Synapse / Fabric |
| **Queue** | SQS | Pub/Sub | Service Bus / Storage Queues |
| **Pub/Sub** | SNS | Pub/Sub | Event Grid |
| **Streaming** | Kinesis / MSK | Pub/Sub + Dataflow | Event Hubs |
| **Monitoring** | CloudWatch | Cloud Monitoring (+ Managed Prometheus) | Azure Monitor |
| **Tracing** | X-Ray | Cloud Trace | Application Insights |
| **Identity** | IAM | Cloud IAM | Entra ID + Azure RBAC |
| **Secrets** | Secrets Manager | Secret Manager | Key Vault |
| **IaC (native)** | CloudFormation / CDK | Deployment Manager / Config Controller | ARM / Bicep |
| **LLM platform** | Bedrock | Vertex AI | Azure OpenAI |

**IAM model differences (a favourite exam question):**
- **AWS** — policies (JSON) attached to users/roles/resources; explicit deny always wins; assume-role for cross-account.
- **GCP** — a **resource hierarchy** (Organization → Folder → Project → Resource) with **inherited** role bindings; principals are users/groups/service accounts; policy = binding of role → members.
- **Azure** — **management groups → subscriptions → resource groups → resources**, with RBAC role assignments plus **Azure Policy** for governance; identity lives in Entra ID (formerly Azure AD).

**Character of each platform:**
| | Strengths | Weaknesses | Choose when |
|---|---|---|---|
| **AWS** | Widest service catalogue and instance variety; deepest ecosystem; most third-party integrations | Complexity; console/UX; pricing opacity | You want maximum optionality and hiring pool |
| **GCP** | Best-in-class data/analytics (BigQuery), strong Kubernetes heritage, clean networking, simple pricing; Cloud Run is the nicest serverless-container UX | Smaller catalogue; enterprise sales/support historically weaker | Data/ML-heavy work, container-native teams |
| **Azure** | Deep Microsoft/enterprise integration (AD, Office, .NET), strong hybrid story (Arc), enterprise agreements | Some service quality unevenness; portal complexity | Microsoft-shop enterprises, hybrid/on-prem |

**Multi-cloud caution:** portability is expensive and usually theoretical. Use managed services deeply; achieve portability where it matters via containers and by isolating provider SDKs behind your own interfaces (hexagonal architecture) — not by using only the lowest common denominator.

#### 1.2.6 Worked example — the architecture in this repository

```
GitHub PR event
      │ HTTPS + HMAC-SHA256 signature
      ▼
┌─────────────────────┐   Cloud Run, public, scale-to-zero
│  webhook-receiver   │   verify signature → filter event → publish → 202
└──────────┬──────────┘
           │ publish
           ▼
┌─────────────────────────────────────────┐
│ Pub/Sub topic: pr-analysis-jobs         │
│  push subscription, ack deadline 600s   │
│  5 delivery attempts → dead-letter topic│
└──────────┬──────────────────────────────┘
           │ push (OIDC-authenticated)
           ▼
┌─────────────────────┐  Cloud Run, private, concurrency=1
│  analysis-worker    │  idempotency check → clone → analyse → LLM → pytest
└───┬─────────────┬───┘
    │             │
    ▼             ▼
 GCS bucket   GitHub commit status
 (artifacts)  (best-effort)
```

Which concept each piece demonstrates:

| Concept | Where it appears |
|---|---|
| Microservice boundary by *conflicting requirements* | Receiver must answer within GitHub's ~10 s webhook timeout and is public; worker runs for minutes and is private |
| Queue-based load levelling | Burst of PRs queues instead of overloading workers |
| At-least-once + idempotent consumer | GCS report object as the dedup marker; duplicates are acked and skipped |
| Retry vs permanent failure | 500 → retry; malformed message → 200 (ack, never retryable) |
| Dead-letter queue | 5 attempts → `pr-analysis-jobs-dead-letter` + an inspection subscription |
| Serverless scale-to-zero | Both services cost nothing while idle |
| Horizontal scaling | concurrency=1; scale by instances because the job shells out to git/pytest |
| Least privilege | Worker is private; only a dedicated service account has `run.invoker` |
| Defence in depth | HMAC signature verification is the *only* gate on a public endpoint |

#### 1.2.7 Failure modes and debugging

| Failure mode | Symptom | Diagnosis | Fix |
|---|---|---|---|
| **Cascading failure** | One slow service → everything times out | Traces show one common slow span | Timeouts, circuit breakers, bulkheads |
| **Retry storm** | Load spikes after a blip; service can't recover | Request rate ≫ normal during recovery | Backoff **with jitter**, retry budgets, load shedding |
| **Thundering herd** | Spike at cache expiry or on restart | Periodic synchronised spikes | Staggered TTLs, request coalescing, warm caches |
| **Unbounded queue growth** | Latency climbs steadily; OOM | Queue depth metric only goes up | Backpressure, autoscale on depth, shed load |
| **Split brain** | Two leaders, divergent writes | Conflicting versions post-partition | Quorum-based election, fencing tokens |
| **Replication lag** | "My write disappeared" | Lag metric high; reads hitting followers | Read-your-writes routing; monitor lag |
| **Hot shard** | One node saturated, rest idle | Per-shard metrics wildly uneven | Better key, salting, dedicated shard |
| **Poison message** | Consumer crashloop on one message | Same message ID repeatedly | DLQ + max delivery attempts |
| **Clock skew** | Ordering/TTL anomalies | Timestamps disagree across nodes | NTP; use logical clocks, don't trust wall time for ordering |
| **Zombie/duplicate work** | Duplicate side effects | Job ran twice after "timeout" | Idempotency + fencing tokens |

**Debugging method:**
1. **Metrics first** — *what* and *when* (RED/USE dashboards narrow it to a service).
2. **Traces second** — *where* in the request path.
3. **Logs last** — *why*, filtered by trace ID.
4. Correlate with **change events** — most incidents follow a deploy, config change, or traffic shift.
5. Check **dependencies and saturation** — connection pools, thread pools, disk, quotas.

#### 1.2.8 Security, performance, scalability, reliability

**Security:** defence in depth; least privilege (per-service identities, no shared god-credentials); **zero trust** (authenticate service-to-service — mTLS or signed tokens — not "it's inside the VPC so it's fine"); encrypt in transit (TLS) and at rest; secrets in a manager with rotation, never in env vars in source control; validate *all* input at trust boundaries (the assistant verifies HMAC signatures before parsing anything); audit logging.

**Performance:** cache at every sensible layer (client → CDN → gateway → app → DB); batch to amortise round trips; use async I/O for I/O-bound work; keep payloads small; place compute near data.

**Scalability:** stateless services; shard the state; **asynchronous processing for anything the user isn't waiting on**; autoscale on the right signal; test with realistic load, including failure injection.

**Reliability:** define **SLIs/SLOs** (latency, availability, correctness) and use an **error budget** to arbitrate between shipping and stabilising; practise chaos engineering; run game days; automate rollback; write blameless postmortems.

#### 1.2.9 Glossary (distributed systems)

| Term | Definition |
|---|---|
| **ACID** | Atomicity, Consistency, Isolation, Durability — traditional DB transaction guarantees |
| **BASE** | Basically Available, Soft state, Eventual consistency — the AP counterpart |
| **Bulkhead** | Isolated resource pool preventing one dependency from consuming everything |
| **CAP** | Consistency, Availability, Partition tolerance — pick C or A during a partition |
| **CDC** | Change Data Capture — streaming DB changes as events |
| **Circuit breaker** | Fail-fast wrapper that stops calling a failing dependency |
| **CQRS** | Command Query Responsibility Segregation — separate write and read models |
| **CRDT** | Conflict-free Replicated Data Type — merges concurrent updates deterministically |
| **DLQ** | Dead-letter queue — parking lot for undeliverable messages |
| **Fencing token** | Monotonic token preventing a stale leader/lock holder from acting |
| **Idempotency** | Repeating an operation has no additional effect |
| **Leader election** | Consensus on which node coordinates (Raft, Paxos, ZAB) |
| **Outbox pattern** | Atomically write state + event, relay publishes later |
| **PACELC** | If Partition: A or C; Else: Latency or Consistency |
| **Quorum** | Majority (W + R > N) ensuring read/write overlap |
| **Saga** | Distributed transaction as local steps with compensations |
| **Sharding** | Splitting data across nodes by key |
| **SLI/SLO/SLA** | Indicator (measurement) / Objective (internal target) / Agreement (contractual) |
| **Split brain** | Two nodes both believe they are leader |
| **Thundering herd** | Many clients acting simultaneously, overwhelming a resource |
| **Two Generals** | Proof that guaranteed agreement over a lossy channel is impossible |

#### 1.2.10 Advanced questions with answers

**Q: Your service calls three others synchronously. How do you keep p99 acceptable?**
A: First, question the design — three sync hops on the critical path is a smell; consider async or data denormalisation. Then: aggressive timeouts derived from measured p99s (not defaults), parallel rather than sequential calls where possible, circuit breakers to fail fast, caching for slow-changing data, and hedged requests for tail-tolerance. Quantitatively: sequential p99s add up, while parallel calls take the max — so parallelising is often the single biggest win.

**Q: How would you migrate a monolith to microservices?**
A: **Strangler fig.** Put a facade/gateway in front of the monolith. Extract one bounded context at a time, starting with something loosely coupled and valuable (e.g. a component with a distinct scaling profile). Route that traffic to the new service through the facade, run both in parallel with comparison/shadow traffic, then cut over and delete the old code. Data is the hard part: split the schema last, using CDC or the outbox pattern to keep the two in sync during transition. Never attempt a big-bang rewrite.

**Q: Kafka or a traditional queue (SQS/RabbitMQ)?**
A: Kafka when you need an ordered, replayable **log**: event sourcing, multiple independent consumer groups reading the same stream, high sustained throughput, or replay after a bug. A traditional queue when you need **work distribution** with per-message ack/retry/DLQ semantics, simple ops, and no replay requirement. Kafka's operational burden is far higher (though managed offerings reduce it); SQS/Pub/Sub are effectively zero-ops.

**Q: How do you handle a schema change consumed by 20 downstream services?**
A: Backwards-compatible, additive-only changes; publish the new version alongside the old (`v1` and `v2` topics or a version field) during a migration window; enforce compatibility with a schema registry at publish time; require consumers to ignore unknown fields; track consumer versions and only retire `v1` when telemetry shows nobody reads it. Communicate a deprecation timeline — this is an organisational problem as much as a technical one.

**Q: When is serverless the wrong choice?**
A: Sustained high-throughput workloads (reserved capacity is cheaper), latency-critical paths that can't absorb cold starts, long-running or stateful processes, workloads needing specialised hardware or kernel tuning, and cases where the platform's execution/payload limits genuinely bind. Also: when your team's operational maturity means the observability gap will hurt more than the ops savings help.

**Q: Explain the difference between "at-least-once delivery" and "exactly-once processing" in one minute.**
A: Delivery is what the broker promises about handing you a message; processing is about the *effects* in your system. Since the network can lose acks, a broker can only guarantee at-least-once without loss. You convert that into exactly-once *effects* by making the consumer idempotent — dedup by message ID, use a natural key, or use conditional writes. Anyone selling "exactly-once delivery" is either operating inside a closed transactional system or is being imprecise.

#### 1.2.11 Recommended learning path (distributed systems)

1. **Foundations** — *Designing Data-Intensive Applications* (Kleppmann), chapters 1–9. The single highest-value book in this field.
2. **Practice** — build a small event-driven system end-to-end with a real broker (as in this repo). Force yourself to handle duplicate delivery and a DLQ.
3. **Patterns** — microservices.io (Chris Richardson) for the pattern catalogue; *Release It!* (Nygard) for stability patterns.
4. **Papers** — Dynamo, Google File System, MapReduce, Spanner, Raft ("In Search of an Understandable Consensus Algorithm").
5. **Cloud** — pick one provider and go deep (associate-level architect certification is a reasonable syllabus); learn the other two only by mapping services.
6. **Operations** — Google's *SRE Book* (free online) for SLO/error-budget thinking.
7. **Deliberate failure** — inject faults into your own system: kill a worker mid-job, send a poison message, partition a network with `tc`/toxiproxy.

---

## 2. Monitoring Tools: Prometheus and Grafana

### 2.1 Exam Summary-Hint

#### What it is
**Prometheus** is an open-source monitoring system and time-series database that **pulls (scrapes)** metrics from HTTP endpoints, stores them locally, evaluates rules over them, and fires alerts. **Grafana** is a visualization and dashboarding platform that queries Prometheus (and many other sources) and renders panels, plus its own alerting.

#### Why they exist
You cannot operate a distributed system you cannot see. Prometheus provides *numbers over time* (cheap, aggregatable, alertable); Grafana turns them into something a human can interpret at 3 a.m.

#### How it works
Applications expose a plain-text `/metrics` endpoint. Prometheus discovers targets (static config or service discovery), scrapes them on an interval, stores samples in its local TSDB, evaluates **recording rules** (precompute) and **alerting rules** (conditions), and pushes firing alerts to **Alertmanager**, which deduplicates, groups, silences, and routes notifications. Grafana queries Prometheus with **PromQL** to draw dashboards.

#### Main components
```
┌──────────────┐  scrape   ┌────────────────────┐  alerts  ┌──────────────┐
│ App /metrics │◄──────────│    Prometheus      │─────────►│ Alertmanager │
│  Exporters   │  (pull)   │  TSDB + rules      │          │ dedupe/route │
└──────────────┘           └─────────┬──────────┘          └──────┬───────┘
┌──────────────┐  push              │ PromQL                      │
│ Pushgateway  │──────────►         ▼                             ▼
│ (batch jobs) │           ┌────────────────────┐        Slack / Email /
└──────────────┘           │      Grafana       │        PagerDuty
                           │ dashboards/panels  │
                           └────────────────────┘
```

#### Main flow
`instrument → expose → discover → scrape → store → query (PromQL) → visualise (Grafana) → alert (rules → Alertmanager → notification)`

#### Important terminology
- **Time series** — a stream of samples identified by a metric name + label set.
- **Label** — key/value dimension (`status="500"`). Labels define series identity.
- **Cardinality** — number of distinct series. **The #1 operational risk.**
- **Scrape interval** — how often Prometheus polls (commonly 15–60 s).
- **Metric types** — Counter (only up), Gauge (up/down), Histogram (bucketed), Summary (client-side quantiles).
- **PromQL** — the query language.
- **Exporter** — a sidecar/agent translating a third-party system's stats into Prometheus format (node_exporter, blackbox_exporter, postgres_exporter).
- **Alertmanager** — separate binary handling dedup, grouping, silencing, inhibition, routing.
- **Recording rule** — precomputed query saved as a new series (for expensive dashboard queries).

#### Metric types — when to use which
| Type | Use for | Example |
|---|---|---|
| **Counter** | Monotonically increasing events | `http_requests_total` |
| **Gauge** | Values that go up and down | `queue_depth`, `memory_bytes` |
| **Histogram** | Distributions; percentiles computed **server-side** | `http_request_duration_seconds` |
| **Summary** | Percentiles computed **client-side** | Legacy; **cannot be aggregated across instances** |

**Rule:** use Histogram for latency (aggregatable), not Summary.

#### Strengths and weaknesses
| Prometheus strengths | Prometheus weaknesses |
|---|---|
| Simple, self-contained, no external deps | **Not** long-term storage by default (needs Thanos/Mimir/Cortex) |
| Powerful dimensional data model + PromQL | Single-node by design; scaling needs federation/sharding |
| Pull model: easy to detect a dead target | Pull is awkward for short-lived jobs (hence Pushgateway) |
| Huge exporter ecosystem; the de-facto standard | High cardinality will destroy it |
| Alerting built in | Not for logs, traces, or event-level data |

#### Typical use cases
Infrastructure and service monitoring, SLO tracking and error budgets, autoscaling signals, capacity planning, cost/usage tracking (as in this repo: LLM tokens and cache hit ratio).

#### Common exam questions with short answers
| Question | Short answer |
|---|---|
| Why pull instead of push? | Prometheus controls the sampling rate, target liveness is trivially detectable (`up` metric), and targets need no monitoring configuration. Push suits short-lived jobs — hence Pushgateway as the exception. |
| Counter vs Gauge? | Counter only increases (use `rate()`); Gauge can go both ways (use directly). |
| Why `rate()` on counters? | The absolute value is meaningless and resets on restart. `rate()` computes per-second increase and handles resets automatically. |
| Histogram vs Summary? | Histogram sends bucket counts, so quantiles can be computed **across** instances at query time. Summary computes quantiles in the client and cannot be aggregated. |
| What is cardinality and why care? | The number of unique label combinations. Each is a separate time series in RAM/disk; unbounded labels (user IDs, request IDs) cause a **cardinality explosion** that OOMs Prometheus. |
| Does Grafana store data? | No — it stores dashboards and its own alert config; the metric data stays in the datasource. |
| What does Alertmanager add? | Deduplication, grouping, silencing, inhibition, and routing to receivers — none of which belongs in Prometheus itself. |

#### Common mistakes
1. **Cardinality explosion** — putting user IDs, emails, UUIDs, or full URLs in labels. This kills Prometheus faster than anything else.
2. **Averaging percentiles** — `avg(p99)` is mathematically meaningless; aggregate the *histogram buckets* and compute the quantile after.
3. Using **Summary** for latency then discovering you can't aggregate across replicas.
4. Alerting on **causes rather than symptoms** — alert on "users see errors", not "CPU is 90%".
5. Forgetting the **`_total` suffix convention** on counters and **base units** (seconds, bytes — not ms or MB).
6. Treating Prometheus as durable long-term storage without Thanos/Mimir.
7. Alert fatigue — every alert should be actionable and urgent; the rest are dashboards.

#### The "perfect answer" to memorise
> Prometheus is a pull-based metrics system: services expose a `/metrics` endpoint in a simple text format, Prometheus discovers targets and scrapes them on a fixed interval into a local time-series database where each series is identified by a metric name plus a set of labels. You query it with PromQL — `rate()` over counters for throughput, `histogram_quantile()` over histogram buckets for latency percentiles — and you define alerting rules that fire into Alertmanager, which deduplicates, groups, silences, and routes notifications. Grafana sits on top purely as a query and visualization layer; it stores dashboards, not data. The main operational risk is cardinality: every unique label combination is a separate series, so you never put unbounded values like user IDs in labels. In my own project the worker exposes counters for jobs by outcome, LLM calls and tokens, and cache hits, plus a histogram for job duration — so the Grafana dashboard shows both operational health and the direct cost effect of the LLM response cache.

---

### 2.2 Full Study Report

#### 2.2.1 Observability: metrics, logs, traces

**Monitoring** answers *known* questions ("is CPU high?"). **Observability** is the ability to answer *new* questions about your system without shipping new code. The three signals:

| Signal | What it is | Cost | Cardinality tolerance | Best for |
|---|---|---|---|---|
| **Metrics** | Numeric measurements over time, aggregated | Very low, constant per series | **Low** — labels must be bounded | Alerting, trends, dashboards, SLOs |
| **Logs** | Discrete timestamped events, usually text/JSON | High (volume) | High | Debugging specifics, audit trails |
| **Traces** | Causally linked spans across services | Medium (usually sampled) | High | Latency attribution across services |

They are complementary, and the standard workflow uses all three in order: a **metric** alerts you that error rate rose; a **trace** shows which service and which span; **logs** filtered by that trace ID tell you why.

**OpenTelemetry (OTel)** is now the vendor-neutral standard covering all three: one instrumentation API/SDK, one wire protocol (OTLP), pluggable backends. Modern advice: instrument with OTel, export metrics to Prometheus, traces to Tempo/Jaeger, logs to Loki/Elastic.

**Profiles** are increasingly called the fourth signal (continuous CPU/memory profiling — Pyroscope/Parca).

#### 2.2.2 Prometheus architecture in depth

Per the [official overview](https://prometheus.io/docs/introduction/overview/), Prometheus scrapes metrics from instrumented jobs (directly or via a pushgateway for short-lived jobs), stores all scraped samples locally, and runs rules over this data to aggregate/record new series or generate alerts. Prometheus servers operate **independently, relying only on local storage** — a deliberate design choice for reliability: your monitoring keeps working when the rest of the infrastructure is broken.

##### The data model
```
metric_name{label1="value1", label2="value2"}  @timestamp  value

http_requests_total{method="POST", handler="/api", status="200"}  1717000000  12345
```
- A **time series** is uniquely identified by the metric name plus **the full set of labels**. Change any label value → different series.
- Samples are `(float64 value, int64 millisecond timestamp)`.
- **Naming conventions:** `<namespace>_<subsystem>_<name>_<unit>`, base units (seconds, bytes, ratios 0–1), `_total` for counters, `_seconds` for durations.

##### Scraping and service discovery
Prometheus polls each target's HTTP endpoint (default `/metrics`) on `scrape_interval`. Every scrape automatically produces:
- `up{job="...", instance="..."}` — 1 if the scrape succeeded, 0 otherwise. **The most important metric you get for free** — this is how a pull system detects dead targets.
- `scrape_duration_seconds`, `scrape_samples_scraped`, and related meta-metrics.

**Service discovery** mechanisms: `static_configs`, `kubernetes_sd`, `ec2_sd`, `gce_sd`, `consul_sd`, `dns_sd`, `file_sd`. **Relabeling** (`relabel_configs` before the scrape, `metric_relabel_configs` after) is the powerful/confusing part — it filters targets, rewrites labels, and **drops high-cardinality metrics before they are stored**. Learning relabeling is what separates casual users from operators.

A minimal config (from this repository):
```yaml
global:
  scrape_interval: 5s
  evaluation_interval: 15s
rule_files:
  - /etc/prometheus/alerts.yml
scrape_configs:
  - job_name: analysis-worker
    static_configs:
      - targets: ["analysis-worker:8080"]
```

##### The TSDB (storage)
- Samples are appended to an in-memory **head block** with a **write-ahead log** (WAL) for crash recovery.
- Every ~2 hours the head is flushed to an immutable on-disk **block** (chunks + index + tombstones).
- Older blocks are **compacted** into larger ones; blocks past the retention window are deleted.
- Compression is excellent — roughly **1–2 bytes per sample** thanks to delta-of-delta timestamp encoding and XOR value encoding (from the Facebook Gorilla paper).

**Capacity rule of thumb:**
```
disk ≈ retention_seconds × ingested_samples_per_second × bytes_per_sample(~2)
```
Memory is dominated by the **number of active series**, not the sample rate — which is exactly why cardinality is the thing to control.

**Long-term/HA options:** Prometheus is intentionally single-node and local-storage. For long retention, global query views, and HA, add **Thanos**, **Grafana Mimir**, or **Cortex** via `remote_write` or sidecars. **Remote write** also enables managed backends (Grafana Cloud, GCP Managed Service for Prometheus, Amazon Managed Prometheus).

##### Labels and cardinality (the operational make-or-break)
```
Total series = Π (distinct values per label) × number of metrics
```
Concrete disaster: a `user_id` label with 100,000 users × 5 endpoints × 4 status codes = **2,000,000 series** from a single metric.

| ✅ Good labels (bounded) | ❌ Dangerous labels (unbounded) |
|---|---|
| `status="500"`, `method="POST"` | `user_id`, `email`, `session_id` |
| `region="us-central1"` | `request_id`, `trace_id` |
| `queue="jobs"`, `result="passed"` | Full URL path with IDs, raw SQL, timestamps |

**Rule:** if you can't enumerate the possible values in advance, it is not a label — it belongs in a log or a trace. Guard with `metric_relabel_configs` drops and by alerting on your own series count (`prometheus_tsdb_head_series`).

##### PromQL
Four expression types: **instant vector** (one sample per series at a timestamp), **range vector** (a window of samples, e.g. `[5m]`), **scalar**, **string**.

Essential functions:
```promql
# Throughput: per-second rate over 5 minutes (handles counter resets)
rate(http_requests_total[5m])

# irate: instantaneous rate from the last two points — spiky graphs only, never alerts
irate(http_requests_total[1m])

# increase: total growth in a window (= rate × window)
increase(http_requests_total[1h])

# Error ratio, aggregated across instances
sum(rate(http_requests_total{status=~"5.."}[5m]))
  / sum(rate(http_requests_total[5m]))

# p95 latency from histogram buckets — note: rate() inside, by (le) required
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# Aggregation with grouping
sum by (service) (rate(errors_total[5m]))
topk(5, sum by (endpoint) (rate(http_requests_total[5m])))

# Predictive: will the disk fill within 4 hours?
predict_linear(node_filesystem_free_bytes[6h], 4*3600) < 0

# Joins: attach metadata from an info-style metric
sum by (version) (rate(requests_total[5m]) * on(instance) group_left(version) build_info)
```

**Frequent PromQL mistakes:**
| Mistake | Why wrong | Correct |
|---|---|---|
| `histogram_quantile(0.95, rate(x_bucket[5m]))` without `by (le)` when aggregating | Buckets from different instances aren't combined | `histogram_quantile(0.95, sum(rate(x_bucket[5m])) by (le))` |
| `avg(rate(...))` for an overall error ratio | Averages ratios of unequal denominators | `sum(...) / sum(...)` |
| `rate()` on a gauge | `rate` assumes monotonicity | Use `deriv()` or the raw gauge |
| Range shorter than 2× scrape interval | Too few points; empty results | Range ≥ 4× scrape interval is a safe rule |
| `irate()` in alerts | Extremely noisy | Use `rate()` |

##### Recording and alerting rules
**Recording rules** precompute expensive expressions on a schedule:
```yaml
groups:
  - name: slo
    interval: 30s
    rules:
      - record: job:http_error_ratio:rate5m
        expr: sum by (job) (rate(http_requests_total{status=~"5.."}[5m]))
              / sum by (job) (rate(http_requests_total[5m]))
```
Convention: `level:metric:operation`. Use them for anything a dashboard re-queries constantly.

**Alerting rules** (this repository's, verbatim in spirit):
```yaml
groups:
  - name: ai-test-assistant
    rules:
      - alert: HighJobFailureRate
        expr: rate(jobs_processed_total{status="failed"}[15m])
              / clamp_min(rate(jobs_processed_total[15m]), 1e-9) > 0.2
        for: 15m
        labels: {severity: warning}
        annotations:
          summary: "More than 20% of analysis jobs are failing"

      - alert: SlowAnalysisJobs
        expr: histogram_quantile(0.95, rate(job_duration_seconds_bucket[15m])) > 300
        for: 10m
        labels: {severity: warning}
        annotations:
          summary: "p95 job duration above 5 minutes"
```
`for:` is essential — it requires the condition to hold continuously before firing, which eliminates flapping. `clamp_min` avoids division by zero when there is no traffic.

##### Alertmanager
A **separate binary** (deliberately — routing policy is not the monitoring engine's job). Per the [official docs](https://prometheus.io/docs/alerting/latest/alertmanager/), it handles alerts sent by clients such as the Prometheus server, taking care of deduplicating, grouping, and routing them to the correct receiver integration such as email, PagerDuty, or OpsGenie. It also silences and inhibits alerts.

| Feature | Purpose |
|---|---|
| **Grouping** | One notification for 50 instances of the same alert, not 50 pages |
| **Deduplication** | HA Prometheus pairs send the same alert twice; you get one |
| **Inhibition** | Suppress "service down" alerts when the parent "cluster down" alert is firing |
| **Silencing** | Mute during planned maintenance |
| **Routing tree** | severity/team/time-based → correct receiver |

```yaml
route:
  group_by: [alertname, cluster]
  group_wait: 30s          # collect more alerts before the first notification
  group_interval: 5m       # wait before notifying about new alerts in an existing group
  repeat_interval: 4h      # re-notify for still-firing alerts
  receiver: team-default
  routes:
    - matchers: [severity="critical"]
      receiver: pagerduty
```

##### Pushgateway — and when *not* to use it
For **short-lived batch jobs** that exit before any scrape can happen. Push the final value, Prometheus scrapes the gateway. **Do not** use it as a general push proxy: it becomes a single point of failure, it breaks the `up` liveness semantics, and stale values persist until explicitly deleted. For most "I can't be scraped" situations, the right answer is a sidecar exporter or remote-write.

#### 2.2.3 Grafana in depth

##### Core concepts
| Concept | Meaning |
|---|---|
| **Data source** | A backend Grafana queries: Prometheus, Loki, Tempo, Elasticsearch, PostgreSQL, CloudWatch, … |
| **Dashboard** | A JSON document containing panels, variables, and layout |
| **Panel** | One visualization bound to one or more queries |
| **Variable** | Template parameter (`$service`) creating reusable, filterable dashboards |
| **Annotation** | Event marker on a graph (deploys, incidents) — invaluable for correlation |
| **Alert rule** | Grafana's own (unified) alerting, independent of Prometheus rules |
| **Provisioning** | Dashboards/datasources defined as files in git rather than clicked in the UI |

##### Panel types and when to use them
| Panel | Use for |
|---|---|
| **Time series** | Nearly everything trending over time |
| **Stat** | One current number (hit ratio, error budget remaining) |
| **Gauge** | A value against a threshold |
| **Bar gauge** | Comparing a small set of categories |
| **Table** | Top-N lists, per-instance detail |
| **Heatmap** | Latency distribution over time (histogram buckets shine here) |
| **Logs** | Loki output, ideally linked from a metric panel |
| **State timeline** | Up/down status over time |

##### Grafana alerting vs Prometheus alerting
| | Prometheus rules + Alertmanager | Grafana unified alerting |
|---|---|---|
| Evaluation | In Prometheus | In Grafana |
| Multi-datasource | No | **Yes** (can alert across Prometheus + SQL) |
| Config as code | YAML files, git-native | Provisioning files or UI |
| Survives Grafana outage | **Yes** | No |
| Best for | Core infrastructure alerts | Business/cross-source alerts, teams already living in Grafana |

**Recommendation:** keep critical infrastructure alerting in Prometheus/Alertmanager (fewer moving parts on the critical path); use Grafana alerting for cross-datasource and business-level conditions.

##### Provisioning (dashboards as code)
This repository provisions both datasource and dashboard from files, which is the practice to adopt:
```yaml
# grafana/provisioning/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    uid: prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```
Why it matters: dashboards clicked together in a UI are undocumented, unreviewable, and lost when the volume dies. Dashboards in git are diffable, code-reviewed, and reproducible.

#### 2.2.4 How they work together — end to end

```
1. App code:      CACHE_HITS.inc()  /  JOB_DURATION.observe(1.7)
                            │
2. Client library aggregates in memory, renders text on /metrics:
                            │   llm_cache_hits_total 9
                            ▼
3. Prometheus scrapes every 5–60 s ──► TSDB (head → blocks)
                            │
        ┌───────────────────┴────────────────────┐
4a. Rules evaluate every 15 s              4b. Grafana queries PromQL
        │ condition true for `for:` duration      │ every dashboard refresh
        ▼                                         ▼
5.  Alertmanager: dedupe → group →           6. Panels render;
    inhibit → route → notify                    annotations mark deploys
```

**A concrete, exam-ready example from this repository.** The worker instruments:
```python
JOBS_PROCESSED = Counter("jobs_processed_total", "Analysis jobs by outcome", ["status"])
JOB_DURATION   = Histogram("job_duration_seconds", "End-to-end job duration",
                           buckets=(5, 15, 30, 60, 120, 300, 600))
LLM_CALLS      = Counter("llm_calls_total", "LLM generate calls (cache misses)")
LLM_PROMPT_TOKENS   = Counter("llm_prompt_tokens_total", "Prompt tokens sent")
CACHE_HITS     = Counter("llm_cache_hits_total", "LLM response cache hits")
CACHE_MISSES   = Counter("llm_cache_misses_total", "LLM response cache misses")
GENERATED_FILES = Counter("generated_test_files_total", "By pytest outcome", ["result"])
```
Dashboard queries built on them:
```promql
# Throughput by outcome (per minute)
rate(jobs_processed_total[5m]) * 60

# p50 / p95 job duration
histogram_quantile(0.50, rate(job_duration_seconds_bucket[15m]))
histogram_quantile(0.95, rate(job_duration_seconds_bucket[15m]))

# Cache hit ratio — proves the LRU cache is paying for itself
llm_cache_hits_total / clamp_min(llm_cache_hits_total + llm_cache_misses_total, 1)

# Quality KPI: share of generated test files that passed
generated_test_files_total{result="passed"} / clamp_min(sum(generated_test_files_total), 1)

# Cost driver: tokens per minute
rate(llm_prompt_tokens_total[5m]) * 60
```
**Measured result in that system:** four identical jobs produced `llm_calls_total = 3` with `llm_cache_hits_total = 9` and `llm_cache_misses_total = 3` — i.e. a 75% hit ratio, with the token counters staying flat after the first job. That is the entire point of instrumenting a cache: the optimisation is *demonstrated*, not assumed.

**Two deliberate non-decisions worth quoting in an exam:**
1. **Queue depth is not a custom metric** — Pub/Sub already exports `num_undelivered_messages` to Cloud Monitoring; re-measuring it in the app would be strictly worse data.
2. **The webhook receiver is not instrumented** — it does one cheap thing, and Cloud Run's built-in request count/latency/error metrics already cover it. *Custom metrics belong where custom logic is.*

#### 2.2.5 What to measure: RED, USE, and the Four Golden Signals

| Method | Applies to | Measures |
|---|---|---|
| **RED** | Request-driven **services** | **R**ate, **E**rrors, **D**uration |
| **USE** | **Resources** (CPU, disk, pool) | **U**tilization, **S**aturation, **E**rrors |
| **Four Golden Signals** (Google SRE) | Services | Latency, Traffic, Errors, Saturation |

**SLI/SLO in PromQL** — the pattern to memorise:
```promql
# SLI: fraction of successful requests
sum(rate(http_requests_total{status!~"5.."}[30d]))
  / sum(rate(http_requests_total[30d]))

# Error budget burn rate (1 = burning exactly at budget)
(1 - sli) / (1 - slo_target)
```
Alert on **multi-window, multi-burn-rate** conditions (e.g. fast burn: 14.4× over 1 h; slow burn: 6× over 6 h) rather than on raw thresholds — this is the SRE-book approach and a strong thing to mention.

#### 2.2.6 Failure modes and debugging (monitoring stack)

| Symptom | Likely cause | Fix |
|---|---|---|
| Prometheus OOM / restarts | Cardinality explosion | Find offenders: `topk(10, count by (__name__)({__name__=~".+"}))`; drop labels via `metric_relabel_configs` |
| Gaps in graphs | Scrapes timing out, target restarts | Check `up`, `scrape_duration_seconds` vs `scrape_timeout` |
| Alert never fires | Bad expression, or `for:` too long | Test the expression in the Prometheus UI; check the Alerts tab state (inactive/pending/firing) |
| Alert fires but no notification | Alertmanager routing/silence | Check Alertmanager UI, routing tree, active silences |
| Counters reset to zero | Process restart | Normal — `rate()` handles it; never alert on raw counter value |
| Dashboard slow | Expensive query, long range, high cardinality | Recording rules; narrow ranges; reduce series |
| Duplicate alerts | HA Prometheus pair | Alertmanager dedup handles it — verify identical label sets |
| Metrics missing after deploy | Endpoint renamed / port changed | Check target list in Prometheus → Status → Targets |

**A real one from this project, worth telling:** the deployed service exposed `/healthz` and Google's front end returned 404 for it — `/healthz` is a **reserved path** on Google's infrastructure. Renaming to `/health` fixed it. The lesson: *health/metrics endpoint paths interact with the platform in front of them* — always verify from outside, not just locally.

#### 2.2.7 Best practices

1. **Instrument the RED signals first** for every service; add domain metrics second.
2. **Base units and conventions:** seconds, bytes, ratios; `_total` suffix on counters.
3. **Bounded labels only.** If you cannot enumerate the values, don't make it a label.
4. **Histogram over Summary** for latency (aggregation across instances).
5. **Alert on symptoms** users feel, with `for:` durations; every alert must be actionable and have a runbook link in its annotations.
6. **Dashboards as code**, provisioned from git.
7. **Recording rules** for anything queried repeatedly.
8. **Monitor the monitoring**: `up`, `prometheus_tsdb_head_series`, WAL size, rule evaluation duration.
9. **Retention plan** — decide days locally vs remote-write to long-term storage before you need it.
10. **Correlate signals** — put trace IDs in logs, exemplars in histograms (Prometheus supports exemplars linking a metric bucket to a trace ID — an excellent thing to mention in an exam).

#### 2.2.8 Comparison with alternatives

| Tool | Model | Strengths | Weaknesses |
|---|---|---|---|
| **Prometheus** | Pull, dimensional, local TSDB | Standard, free, powerful PromQL, huge ecosystem | Single-node, no long-term storage, cardinality-fragile |
| **VictoriaMetrics** | Prometheus-compatible | Faster, lower memory, better cardinality tolerance, clustering | Smaller community; some PromQL dialect differences (MetricsQL) |
| **Thanos / Mimir / Cortex** | Prometheus + object storage | Long retention, global query, HA dedup | Substantial extra operational complexity |
| **InfluxDB** | Push, TSDB | Good for high-frequency/IoT; SQL-ish (Flux/InfluxQL) | Smaller monitoring ecosystem; licence history |
| **Datadog / New Relic** | SaaS agent-based | All-in-one, low ops, great UX | **Cost at scale** (often the largest observability line item); lock-in |
| **Cloud-native (CloudWatch / Cloud Monitoring / Azure Monitor)** | Managed, push | Zero setup for platform metrics, deep IAM integration | Weaker query languages; per-metric pricing; provider-scoped |
| **OpenTelemetry** | Instrumentation standard | Vendor-neutral, all three signals | It's a standard/collector, not a backend |
| **Loki** | Log aggregation, label-indexed | Prometheus-like model, cheap (indexes labels not content) | Not for full-text search at scale |
| **Tempo / Jaeger** | Tracing backends | Trace storage/query | Needs instrumentation + sampling strategy |

**The modern default stack:** OpenTelemetry for instrumentation → Prometheus (or Mimir/VictoriaMetrics) for metrics, Loki for logs, Tempo for traces → Grafana as the single pane of glass. This repository implements the metrics half of exactly that.

#### 2.2.9 Glossary (monitoring)

| Term | Definition |
|---|---|
| **Alertmanager** | Separate service handling dedup, grouping, silencing, inhibition, routing |
| **Cardinality** | Count of unique time series (label-value combinations) |
| **Counter** | Monotonically increasing metric; query with `rate()` |
| **Exemplar** | A trace ID attached to a metric sample, linking metrics to traces |
| **Exporter** | Adapter exposing a third-party system's metrics in Prometheus format |
| **Gauge** | Metric that can rise and fall |
| **Histogram** | Bucketed distribution; enables server-side quantiles |
| **Instance / Job** | Target labels: a single scraped process / a group of like processes |
| **PromQL** | Prometheus Query Language |
| **Pushgateway** | Intermediary for short-lived batch jobs to push final metrics |
| **Recording rule** | Precomputed query stored as a new series |
| **Relabeling** | Rewriting/filtering labels and targets during or after scraping |
| **Remote write** | Streaming samples to an external long-term store |
| **Scrape** | One HTTP fetch of a target's `/metrics` |
| **Series** | A unique metric-name + label-set stream of samples |
| **SLI / SLO / Error budget** | Measured indicator / target / allowed unreliability |
| **Summary** | Client-side quantiles; not aggregatable |
| **`up`** | Auto-generated metric: 1 if the last scrape succeeded |
| **WAL** | Write-ahead log protecting the in-memory head block |

#### 2.2.10 Advanced questions with answers

**Q: How do you find and fix a cardinality explosion?**
A: Identify it with `prometheus_tsdb_head_series` (trend), `topk(10, count by (__name__)({__name__=~".+"}))` (which metric), and `count(count by (label)(metric))` (which label). Fix at three levels: (1) stop emitting it in the app — the real fix; (2) drop it at ingestion with `metric_relabel_configs` `action: drop` or `labeldrop`; (3) reduce retention or shard Prometheus while you clean up. Prevent recurrence with a series-count alert and code review rules about label values.

**Q: How do you compute p99 across 50 instances correctly?**
A: `histogram_quantile(0.99, sum(rate(latency_seconds_bucket[5m])) by (le))`. The order matters: `rate()` first (per-series, handles resets), then `sum ... by (le)` to merge instances while preserving the bucket boundary label, then `histogram_quantile`. You cannot average per-instance p99s — quantiles are not linear. Also note the result's accuracy is bounded by bucket granularity, so choose buckets around your SLO thresholds.

**Q: Prometheus is a single point of failure. How do you make monitoring HA?**
A: Run two identical Prometheus servers scraping the same targets; both send to a clustered Alertmanager, which deduplicates identical alerts — so alerting is HA with no coordination between the Prometheus instances. For query HA and long retention, add Thanos (sidecar + querier + object storage) or Mimir, which also deduplicate at query time. Note the design philosophy: each Prometheus stays independent and local-storage-based so that monitoring survives the failure of everything else.

**Q: When would you *not* use Prometheus?**
A: When you need per-event fidelity (billing, audit — use logs/a database), very high-cardinality analysis (use tracing or a columnar store), long retention as the primary requirement without extra components, or when your team has no capacity to operate it and a SaaS is genuinely cheaper in total cost. Also: Prometheus is not a good fit for irregular short-lived jobs unless you accept Pushgateway's caveats.

**Q: What's the difference between `rate`, `irate`, and `increase`?**
A: `rate(v[5m])` = average per-second increase over the window, using all samples, extrapolated at the edges, reset-aware — use this for alerts and most graphs. `irate(v[5m])` = instantaneous rate from only the **last two** samples — very responsive, very noisy, only for high-resolution graphs, never for alerts. `increase(v[5m])` = total increase over the window, which is exactly `rate × window_seconds` — use for "how many events in the last hour".

#### 2.2.11 Recommended learning path (monitoring)

1. Run Prometheus + Grafana locally with docker-compose against an app you wrote (as in `monitoring/` here). Instrument one counter and one histogram yourself.
2. Learn the four metric types and the naming conventions cold.
3. Spend real time on PromQL: `rate`, `sum by`, `histogram_quantile`, `clamp_min`, offsets, joins. Use the Prometheus expression browser interactively.
4. Write three alerts with `for:` clauses; break the app on purpose and watch them fire.
5. Read the Prometheus docs on relabeling and storage; learn `metric_relabel_configs`.
6. Read Google's SRE book chapters on SLOs, error budgets, and alerting on burn rate.
7. Extend to logs and traces (Loki + Tempo, or OpenTelemetry end-to-end).
8. Only then explore Thanos/Mimir for scale.

---

## 3. Topological Sort, LRU Cache, LFU Cache

### 3.1 Exam Summary-Hint

#### Topological sort — what and why
An ordering of a **directed acyclic graph's (DAG)** vertices such that for every edge `u → v`, `u` appears before `v`. It exists **if and only if** the graph has no cycle. It solves every "do these in dependency order" problem: build systems, package managers, task schedulers, course prerequisites, spreadsheet recalculation, data pipeline (DAG) execution.

#### Two algorithms
| | **Kahn's (BFS-style)** | **DFS-based** |
|---|---|---|
| Idea | Repeatedly emit vertices with in-degree 0 | DFS; push vertex on **post-order**; reverse at the end |
| Data | In-degree array + queue | Recursion/explicit stack + colour marks |
| Cycle detection | **Free**: if emitted count < V, the rest form a cycle | Back edge to a **GRAY** (in-progress) vertex |
| Output order | Natural (dependencies first) | Reversed post-order |
| Complexity | **O(V+E)** time, O(V) space | **O(V+E)** time, O(V) space (+ recursion depth) |
| Best when | You want cycle reporting and iterative code | You already have a DFS; recursion is natural |

#### Kahn's in five lines
1. Compute in-degree of every vertex.
2. Enqueue all vertices with in-degree 0.
3. Pop `u`, append to result, and for each edge `u → v` decrement `in_degree[v]`; enqueue `v` if it hits 0.
4. Repeat until the queue is empty.
5. If `len(result) < V` → **cycle**; the missing vertices are (part of) it.

#### Caches — what and why
A cache stores a subset of data in fast storage to reduce latency and load on a slow source. Capacity is finite, so an **eviction policy** decides who leaves. LRU and LFU are the two classic answers.

| | **LRU** | **LFU** |
|---|---|---|
| Evicts | Least **recently** used | Least **frequently** used |
| Bets on | **Temporal locality** — recent = soon again | **Popularity** — frequent = important |
| Structure | Hash map + **doubly linked list** | Hash map + freq map + **buckets of ordered keys** + `min_freq` |
| Complexity | O(1) get/put | O(1) get/put (with the bucket design) |
| Weakness | A large scan flushes everything ("cache pollution") | **Cache pollution by history**: an old once-popular key never leaves; slow to adapt |
| Use when | Access is bursty/recency-driven (most workloads) | A stable hot set dominates; long-lived caches |

#### LRU internals in one breath
A hash map gives O(1) lookup of a **node**; a doubly linked list with head/tail **sentinel** nodes maintains usage order — most recent right after head, least recent right before tail. `get` unlinks the node and relinks it after head (a few pointer writes, no scan). `put` at capacity unlinks `tail.prev` and deletes its key from the map. Everything is O(1) because the map removes the need to search the list and the doubly-linked structure allows O(1) removal from the middle.

#### LFU internals in one breath
Three structures: `key → value`, `key → frequency`, and `frequency → ordered set of keys at that frequency` (insertion-ordered, so oldest is first), plus a `min_freq` pointer. On access, move the key from bucket *f* to bucket *f+1*; if bucket *f* becomes empty and `f == min_freq`, increment `min_freq`. On eviction, remove the **oldest** key from the `min_freq` bucket — that is LFU with **LRU tie-breaking**. All O(1) because frequencies only ever move up by exactly one.

#### Common exam questions with short answers
| Question | Short answer |
|---|---|
| Why a **doubly** linked list for LRU? | To unlink a node in O(1) you need its predecessor. A singly linked list would require an O(n) scan to find it. |
| Why sentinel head/tail nodes? | They eliminate null/edge-case branches when inserting or removing at the ends — shorter, less bug-prone code. |
| Why is a Python `OrderedDict` (or Java `LinkedHashMap`) enough? | Both *are* hash map + doubly linked list internally, with `move_to_end`/access-order — exactly the LRU structure. |
| How does LFU stay O(1) on eviction? | `min_freq` points at the lowest non-empty bucket; eviction pops that bucket's oldest key in O(1). It stays correct because a frequency only increases by 1 at a time. |
| What breaks LFU in practice? | Stale popularity: a key that was hot yesterday keeps a huge count forever. Real systems add **ageing/decay** (or use W-TinyLFU) so counts decay over time. |
| How to detect a cycle with topological sort? | Kahn's: emitted count < V. DFS: an edge to a vertex currently on the recursion stack (GRAY). |
| Is a topological order unique? | Only when the DAG has a Hamiltonian path (a total order); otherwise many valid orders exist. Break ties deterministically if reproducibility matters. |

#### Common mistakes
1. Using a singly linked list for LRU, then discovering removal is O(n).
2. Forgetting that **`put` on an existing key counts as a use** (must refresh recency/frequency).
3. LFU: forgetting to update `min_freq` when a bucket empties → wrong evictions.
4. LFU without tie-breaking → non-deterministic and usually worse behaviour.
5. Topological sort: not handling the cycle case at all (silently producing a partial order).
6. Assuming a unique topological order.
7. Ignoring thread safety — the textbook implementations are **not** thread-safe.

#### The "perfect answer" to memorise
> Topological sort orders a DAG so every dependency precedes its dependents. I use **Kahn's algorithm**: compute in-degrees, start from the zero-in-degree vertices, and each time I emit one I decrement its neighbours' in-degrees, emitting them when they reach zero. It's O(V+E) and detects cycles for free — if fewer vertices are emitted than exist, the remainder form a cycle. I chose it over DFS precisely because cycle reporting falls out naturally and the code is iterative. For caches: LRU is a hash map plus a doubly linked list with sentinels — the map finds the node in O(1) and the list reorders or evicts in O(1) without scanning. LFU adds a frequency map and buckets of keys per frequency with a `min_freq` pointer, giving O(1) eviction with LRU tie-breaking inside each bucket. LRU bets on recency, LFU on popularity; LRU is the better default for bursty workloads, which is why my LLM response cache uses LRU, while LFU would win if a few shared keys dominated across many tenants.

---

### 3.2 Full Study Report

#### 3.2.1 Topological sort

##### The problem it solves
Given tasks with "X must happen before Y" constraints, produce a valid execution order — or prove none exists.

Real instances: `make`/Bazel build graphs; `npm`/`pip`/`apt` dependency resolution; Airflow/Dagster DAG execution; university course prerequisites; spreadsheet formula recalculation; Terraform resource graphs; Java class initialisation; symbol/link ordering in compilers; **and, in this repository, ordering changed Python files so that an imported module is analysed before the module that imports it.**

##### DAGs
A **DAG** is a directed graph with no directed cycle.

```
Valid DAG (topological order exists)      Not a DAG (no valid order)
    A ──► B ──► D                             A ──► B
    │           ▲                             ▲     │
    └───► C ────┘                             └─────┘
Orders: A,B,C,D is invalid (B before C is fine,
        but D needs both) → A,B,C,D ✓ / A,C,B,D ✓
```
**Theorem:** a directed graph has a topological ordering **iff** it is acyclic. Intuition for the forward direction: in any cycle `v1 → v2 → … → v1`, each vertex would have to precede itself.

##### Kahn's algorithm (BFS-style), step by step

```python
from collections import deque

def kahn_topological_sort(vertices, edges):
    """edges: list of (u, v) meaning u must come before v."""
    adjacency = {v: [] for v in vertices}
    in_degree = {v: 0 for v in vertices}
    for u, v in edges:
        adjacency[u].append(v)
        in_degree[v] += 1

    ready = deque(v for v in vertices if in_degree[v] == 0)
    order = []

    while ready:
        u = ready.popleft()
        order.append(u)
        for v in adjacency[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                ready.append(v)

    if len(order) < len(vertices):
        cycle_members = [v for v in vertices if v not in set(order)]
        raise ValueError(f"cycle detected involving: {cycle_members}")
    return order
```

**Trace** on `A→B`, `A→C`, `B→D`, `C→D`:

| Step | Queue | Emitted | In-degrees after |
|---|---|---|---|
| init | [A] | [] | A:0 B:1 C:1 D:2 |
| pop A | [B, C] | [A] | B:0 C:0 D:2 |
| pop B | [C] | [A,B] | C:0 D:1 |
| pop C | [D] | [A,B,C] | D:0 |
| pop D | [] | [A,B,C,D] | — |

Result `A, B, C, D`. (`A, C, B, D` is equally valid — order among ready vertices is a free choice.)

**Determinism:** replace the FIFO queue with a **min-heap** (or sort ready vertices by a stable key) to get a reproducible, canonical order. *This repository sorts ready vertices by the original file order, so the assistant's output never changes between runs on the same input — important because the result feeds LLM prompts that are cached by hash.*

##### DFS-based topological sort

```python
WHITE, GRAY, BLACK = 0, 1, 2   # unvisited, in progress, finished

def dfs_topological_sort(vertices, adjacency):
    color = {v: WHITE for v in vertices}
    postorder = []

    def visit(u):
        color[u] = GRAY
        for v in adjacency[u]:
            if color[v] == GRAY:
                raise ValueError(f"cycle detected at edge {u} -> {v}")
            if color[v] == WHITE:
                visit(v)
        color[u] = BLACK
        postorder.append(u)        # append AFTER all descendants

    for v in vertices:
        if color[v] == WHITE:
            visit(v)

    return postorder[::-1]         # reverse post-order = topological order
```

**Why reverse post-order works:** a vertex is appended only after every vertex reachable from it is already appended. So in the post-order list every vertex appears *after* its dependents; reversing puts it *before* them.

**The three-colour scheme is the key detail:** WHITE = unvisited, GRAY = on the current recursion stack, BLACK = fully processed. An edge to a **GRAY** vertex is a **back edge** = cycle. An edge to a BLACK vertex is fine (already finished, just a cross/forward edge).

##### Complexity

| Algorithm | Time | Space | Notes |
|---|---|---|---|
| Kahn's | **O(V + E)** | O(V) for in-degrees + queue | Iterative; no stack-depth limit |
| DFS (recursive) | **O(V + E)** | O(V) colours + O(V) recursion depth | Risk of stack overflow on deep graphs (~1000 in Python by default) |
| DFS (iterative) | O(V + E) | O(V) | Safer for very deep graphs, more code |

Building the adjacency structure is itself O(V + E), so the bound is tight and optimal — every vertex and edge must be examined at least once.

##### Cycle detection in depth
| Method | How | Extra benefit |
|---|---|---|
| **Kahn's count** | `len(order) < V` → the leftover vertices contain all cycles | Simple; identifies the *set* involved, not the exact cycle path |
| **DFS colours** | Edge to a GRAY vertex | The recursion stack **is** the cycle path — better error messages |
| **Union-Find** | For *undirected* cycle detection | Not applicable to directed cycles |
| **Tarjan's SCC** | Strongly connected components of size > 1 (or a self-loop) are cycles | Best when you need *all* cycles enumerated, still O(V+E) |

**Reporting a readable cycle** (a nice detail to mention): with DFS, when you find a back edge `u → v` where `v` is GRAY, the cycle is the segment of the current recursion stack from `v` to `u`, plus the edge back to `v`.

##### Edge cases (exam favourites)
| Case | Correct behaviour |
|---|---|
| Empty graph | Return `[]` |
| Single vertex, no edges | Return `[v]` |
| No edges at all | Any permutation is valid |
| Disconnected components | Handled naturally — Kahn's starts from all in-degree-0 vertices; DFS loops over all vertices |
| **Self-loop** `v → v` | A cycle. Kahn's: `in_degree[v] ≥ 1` forever, never enqueued. DFS: `v` is GRAY when the edge is examined |
| Duplicate edges | Inflate in-degree → **hangs the algorithm**. Deduplicate, or the count never reaches zero |
| Vertex referenced only as a target | Must still be in the vertex set, or in-degree bookkeeping breaks |

**The duplicate-edge trap is real:** naïvely doing `in_degree[v] += 1` for each parsed edge, when the same edge is discovered twice (e.g. a module imported on two lines), permanently prevents `v` from reaching in-degree 0 — the vertex silently vanishes from the output and looks like a phantom "cycle". *This repository guards against it by checking membership in the dependents set before incrementing.*

##### Practical example — the version in this codebase
The assistant orders changed files so a dependency is analysed before its dependents:

```
PR changes: service.py (imports models), models.py, unrelated.py

Build graph over changed files only:
    models.py ──► service.py        unrelated.py  (isolated)

In-degrees: models=0, service=1, unrelated=0
Ready (original file order): [models.py, unrelated.py]
Emit models.py → service.py drops to 0 → ready
Emit unrelated.py, emit service.py
Result: models.py, unrelated.py, service.py
```

Two deliberate design choices worth explaining:
1. **The graph covers only the changed files.** External imports (stdlib, third-party, unchanged modules) are irrelevant to processing order, so they never become vertices. This keeps the graph tiny — usually under ten vertices.
2. **A cycle does not abort the run.** Cyclic files keep their original order and are reported in the output (`import_cycle_files`). An import cycle is a code smell in the *analysed* project; refusing to generate tests because of it would be the wrong product decision.

##### Related algorithms worth knowing
- **Longest path in a DAG** — solvable in O(V+E) by relaxing edges in topological order (NP-hard in general graphs). This is the basis of **critical path** analysis in project scheduling.
- **Shortest path in a DAG** — same technique, works even with negative weights (unlike Dijkstra).
- **Counting paths / DP on DAGs** — dynamic programming in topological order is a standard pattern.
- **Parallel scheduling** — vertices at the same "level" (all dependencies satisfied) can run concurrently; the number of Kahn's iterations equals the critical path length.

#### 3.2.2 Cache fundamentals

##### Why caches exist
```
Registers   <1 ns          ← smallest, fastest
L1/L2/L3    1–40 ns
RAM         ~100 ns
SSD         ~16 µs         (≈160× RAM)
Network     ~500 µs – 150 ms
Disk/Remote DB / LLM API: milliseconds to seconds
```
A cache trades **memory for latency** (and for load on the origin, and often for money — as with LLM API calls). It is worthwhile when access is **skewed**: a small fraction of keys serves a large fraction of requests (Zipf-like distributions, which are extremely common in practice).

**Key metric:**
```
hit_ratio = hits / (hits + misses)
average_latency = hit_ratio × hit_cost + (1 − hit_ratio) × miss_cost
```
Note the asymmetry: going from a 50% to a 75% hit ratio **halves** the number of expensive origin calls. Small hit-ratio improvements matter a lot when the miss is very expensive (a 2-second LLM call, a cross-region query).

##### Eviction policies
| Policy | Rule | Pros | Cons |
|---|---|---|---|
| **FIFO** | Oldest inserted leaves | Trivial | Ignores usage entirely |
| **LRU** | Least recently used leaves | Great for temporal locality; simple O(1) | Flushed by a single large scan |
| **LFU** | Least frequently used leaves | Protects a genuinely hot set | Stale history; slow adaptation; more memory |
| **MRU** | Most recently used leaves | Good for looping scans over a large file | Rare |
| **Random** | Random victim | O(1), no metadata, surprisingly decent | No workload awareness |
| **CLOCK / Second-chance** | Approximated LRU with a reference bit | Cheap, low overhead — used in OS page caches | Approximate |
| **ARC** | Adapts between recency and frequency | Self-tuning, strong hit ratios | Patented history; more complex |
| **2Q / LIRS** | Separate probationary and protected queues | Scan-resistant | More complex |
| **TinyLFU / W-TinyLFU** | Frequency sketch admits only worthy entries | **Best-in-class hit ratios**; scan-resistant; small memory | More complex; used by Caffeine |
| **TTL-based** | Expire by age | Freshness guarantees | Not a capacity policy by itself |

**Bélády's optimal algorithm (OPT/MIN)** evicts the entry that will be used furthest in the future. It is unimplementable (requires the future) but is the theoretical upper bound used to benchmark real policies.

**Also know these cache concepts:** cache-aside (lazy loading), read-through, write-through, write-behind (write-back), **cache stampede/thundering herd** on expiry (fix with request coalescing, probabilistic early expiry, or a lock), and **negative caching** (caching "not found" to protect the origin).

#### 3.2.3 LRU cache internals

##### The two structures and why each is necessary
| Requirement | Structure that provides it |
|---|---|
| O(1) lookup by key | **Hash map** `key → node` |
| O(1) removal of an arbitrary node | **Doubly** linked list (needs `prev` to unlink) |
| O(1) identification of the eviction victim | Tail of the list |
| O(1) marking "just used" | Move node to the head |

Neither structure alone suffices: a hash map has no order; a list has no O(1) lookup. Together they give O(1) for everything.

##### The layout
```
       ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
head ──│ SENTIN │◄─►│  K:C   │◄─►│  K:B   │◄─►│  K:A   │◄─►│ SENTIN │── tail
       └────────┘   └────────┘   └────────┘   └────────┘   └────────┘
                    most recent               least recent
                                              ▲ evict from here

hash map: { "A": node_A, "B": node_B, "C": node_C }
```
**Sentinels** (dummy head/tail nodes) mean every real node always has both a `prev` and a `next` — removing all the "is this the first/last node?" branches. This is a small trick with an outsized effect on code correctness.

##### Operations

```python
class Node:
    __slots__ = ("key", "value", "prev", "next")

class LRUCache:
    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self.hits = self.misses = 0
        self._nodes = {}                       # key -> Node
        self._head = Node(); self._tail = Node()   # sentinels
        self._head.next = self._tail
        self._tail.prev = self._head

    def get(self, key):
        node = self._nodes.get(key)
        if node is None:
            self.misses += 1
            return None
        self.hits += 1
        self._unlink(node)
        self._link_after_head(node)            # refresh recency
        return node.value

    def put(self, key, value):
        node = self._nodes.get(key)
        if node is not None:                   # update counts as a use
            node.value = value
            self._unlink(node)
            self._link_after_head(node)
            return
        if len(self._nodes) >= self.capacity:  # evict LRU
            victim = self._tail.prev
            self._unlink(victim)
            del self._nodes[victim.key]
        node = Node(key, value)
        self._nodes[key] = node
        self._link_after_head(node)

    def _unlink(self, node):                   # O(1) — needs prev, hence doubly
        node.prev.next = node.next
        node.next.prev = node.prev

    def _link_after_head(self, node):
        node.prev = self._head
        node.next = self._head.next
        self._head.next.prev = node
        self._head.next = node
```

##### Worked trace (capacity = 2)
| Operation | State (MRU → LRU) | Result |
|---|---|---|
| `put(A,1)` | A | — |
| `put(B,2)` | B, A | — |
| `get(A)` | **A, B** | 1 (A refreshed) |
| `put(C,3)` | C, A | evicts **B** (not A, because `get(A)` refreshed it) |
| `get(B)` | C, A | `None` — miss |

That fourth row is the single most-tested behaviour in interviews: **`get` must reorder**, otherwise you've built FIFO.

##### Complexity and edge cases
- **Time:** O(1) amortised for `get` and `put` (hash map average case).
- **Space:** O(capacity) — each entry costs the key, value, and two pointers.

| Edge case | Correct behaviour |
|---|---|
| `capacity = 0` or negative | Reject in the constructor (or make every `get` a miss) — but be explicit |
| `put` of an existing key | Update value **and** refresh recency; size unchanged |
| `get` of a missing key | Return a sentinel/`None`, count a miss, do not mutate order |
| Capacity 1 | Every new key evicts the previous one |
| Storing `None` as a value | `get` returning `None` becomes ambiguous — use a distinct sentinel object |

##### Real-world notes
- **Python** `functools.lru_cache` is a function decorator built on this structure; `collections.OrderedDict` with `move_to_end()` **is** hash map + doubly linked list and is the idiomatic short implementation.
- **Java** `LinkedHashMap(capacity, loadFactor, accessOrder=true)` with `removeEldestEntry()` overridden is a five-line LRU.
- **Redis** does **not** implement exact LRU: it samples `maxmemory-samples` (default 5) random keys and evicts the best candidate — approximated LRU that avoids per-key list maintenance at scale. It also offers `allkeys-lfu` (approximated LFU with counter decay). *Great exam point: at scale, exact policies are often abandoned for sampled approximations, because the metadata bookkeeping costs more than the hit-ratio gain.*
- **Thread safety:** none of the above is thread-safe. Options: a mutex around the whole cache (simple, contended), sharded/striped locks (typical), or a concurrent design like Caffeine's (buffered reads replayed asynchronously into the policy structures).

#### 3.2.4 LFU cache internals

##### The naïve approach and why it fails
Store a count per key and scan for the minimum on eviction: O(n) per eviction. A heap improves it to O(log n) but updating an arbitrary key's priority is still O(log n). The **O(1) design** (Ketan Shah, Anirban Mitra, Dhruv Matani, 2010) uses bucketing.

##### The three structures + one pointer
```
values:     {key → value}
frequencies:{key → use count}
buckets:    {count → OrderedDict of keys at that count}   # insertion order = recency
min_freq:   the lowest non-empty count
```

```
min_freq = 1
                       ▼
buckets:  freq 1 → [ D , E ]        ← D is oldest here → evict D first
          freq 2 → [ B ]
          freq 5 → [ A , C ]
                     ▲ oldest within this bucket

Eviction: take the OLDEST key from bucket[min_freq]  →  O(1)
```

##### The critical insight for O(1)
A frequency only ever increases **by exactly one** at a time. So:
- moving a key from bucket *f* to bucket *f+1* is O(1) (both buckets are directly addressable);
- when bucket `min_freq` becomes empty because its last key was promoted, the new minimum can only be `min_freq + 1` — no search required;
- on insertion, the new key has frequency 1, so `min_freq` resets to 1 — again no search.

That is the whole trick, and it is exactly what an examiner will ask you to justify.

##### Implementation

```python
from collections import OrderedDict

class LFUCache:
    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self.hits = self.misses = 0
        self._values = {}                 # key -> value
        self._frequencies = {}            # key -> use count
        self._keys_by_frequency = {}      # count -> OrderedDict[key, None]
        self._min_frequency = 0

    def get(self, key):
        if key not in self._values:
            self.misses += 1
            return None
        self.hits += 1
        self._increment_frequency(key)
        return self._values[key]

    def put(self, key, value):
        if key in self._values:           # update counts as a use
            self._values[key] = value
            self._increment_frequency(key)
            return
        if len(self._values) >= self.capacity:
            bucket = self._keys_by_frequency[self._min_frequency]
            evicted, _ = bucket.popitem(last=False)   # oldest in bucket = LRU tie-break
            del self._values[evicted]
            del self._frequencies[evicted]
        self._values[key] = value
        self._frequencies[key] = 1
        self._keys_by_frequency.setdefault(1, OrderedDict())[key] = None
        self._min_frequency = 1           # a brand-new key is always the minimum

    def _increment_frequency(self, key):
        f = self._frequencies[key]
        bucket = self._keys_by_frequency[f]
        del bucket[key]
        if not bucket:
            del self._keys_by_frequency[f]
            if self._min_frequency == f:
                self._min_frequency = f + 1     # only possible new minimum
        self._frequencies[key] = f + 1
        self._keys_by_frequency.setdefault(f + 1, OrderedDict())[key] = None
```

##### Worked trace (capacity = 2)
| Operation | values | frequencies | buckets | min_freq | Result |
|---|---|---|---|---|---|
| `put(A,1)` | A | A:1 | 1→[A] | 1 | — |
| `put(B,2)` | A,B | A:1 B:1 | 1→[A,B] | 1 | — |
| `get(A)` | A,B | A:2 B:1 | 1→[B], 2→[A] | 1 | 1 |
| `put(C,3)` | A,C | A:2 C:1 | 1→[C], 2→[A] | 1 | evicts **B** (freq 1) |
| `get(B)` | A,C | — | — | 1 | `None` |

Tie-break demonstration: had `get(A)` not happened, A and B would both sit at frequency 1 and **A** (older in the bucket) would be evicted — LFU falling back to LRU.

##### Complexity and edge cases
- **Time:** O(1) for `get`, `put`, and eviction.
- **Space:** O(capacity), with a constant factor roughly 2–3× LRU's due to the extra maps.

| Edge case | Correct behaviour |
|---|---|
| All keys at the same frequency | Degenerates to LRU (thanks to the ordered bucket) |
| `put` on existing key | Update value **and** increment frequency |
| Bucket becomes empty | Delete it; bump `min_freq` **only if** it was the minimum |
| New insert after eviction | `min_freq` must reset to 1 — forgetting this is *the* classic LFU bug |
| Frequency overflow | Irrelevant in Python (bignum); matters with fixed-width counters — cap or decay |

##### The stale-popularity problem and its fixes
A key hammered a million times last week keeps its count forever and can never be evicted, even if it is now dead. Remedies used in practice:
- **Ageing/decay** — periodically halve all counts, or decay by elapsed time (Redis's LFU uses a logarithmic counter with a decay period).
- **Windowed counting** — count only within a sliding window.
- **TinyLFU / W-TinyLFU** — a probabilistic frequency sketch (Count-Min Sketch) with periodic reset, plus a small LRU admission window. It decides *whether a candidate deserves admission at all*, which is why **Caffeine** (the Java cache) achieves near-optimal hit ratios with modest memory. This is the state of the art and an excellent thing to name-drop.

#### 3.2.5 LRU vs LFU — direct comparison

| Dimension | LRU | LFU |
|---|---|---|
| Eviction basis | Recency | Frequency (+ recency tie-break) |
| Structures | Map + doubly linked list | Map + freq map + buckets + `min_freq` |
| Memory overhead | Lower (2 pointers/entry) | Higher (extra maps) |
| Implementation complexity | Low | Moderate |
| Adapts to changing workload | **Fast** | **Slow** (history sticks) |
| Resistant to scan pollution | **No** — a big sweep evicts the hot set | **Yes** — one-off keys never accumulate frequency |
| Handles cyclic access > capacity | Worst case (evicts exactly what's needed next) | Better |
| Typical hit ratio | Good | Often better *for stable hot sets* |

**Choosing:**
- **LRU** — bursty, recency-driven access; short-lived caches; changing working sets; when simplicity matters. *This is most workloads, which is why LRU is the default nearly everywhere.*
- **LFU** — a stable, genuinely skewed popularity distribution; long-lived caches; expensive misses; e.g. CDN edge caches, shared multi-tenant caches.
- **Modern answer:** neither, in isolation — **W-TinyLFU** (Caffeine) or **ARC** adapt automatically and beat both in most benchmarks. Say this if asked "which would you use in production?"

##### The decision made in this repository — a defensible case study
The assistant caches LLM responses keyed by `SHA-256(model, temperature, system_instruction, prompt)`. It uses **LRU**, and implements LFU as a tested-but-unwired alternative. The reasoning, which generalises well:
- The access pattern is **bursty**: a developer re-pushes the same branch several times within an hour → the same prompts recur → strong temporal locality → LRU.
- LFU would win in a different deployment: one worker serving many repositories where a few shared modules appear in most PRs; there, popularity would beat recency.
- Wiring LFU in without a workload where it wins would be **speculative complexity** — so it is implemented, tested, documented, and deliberately not used.
- Because both expose `hits`/`misses` counters that feed Prometheus, the choice is **measurable** rather than assumed. Measured result: four identical jobs → 3 LLM calls, 9 cache hits, 3 misses (75% hit ratio) — with token counters flat after the first job.

**A genuinely instructive bug from that system:** the cache initially never hit across jobs. Cause — prompts embedded the absolute path of a temporary clone directory, which differs per job, so byte-identical work produced different SHA-256 keys. **Lesson: a cache key must be built from *normalised* inputs; any incidental variability in the input silently reduces the hit ratio to zero, and nothing crashes to tell you.** A regression test now pins prompt stability across clone locations.

#### 3.2.6 Glossary (algorithms)

| Term | Definition |
|---|---|
| **Back edge** | DFS edge to a vertex currently on the recursion stack — proves a cycle |
| **Bélády's OPT** | Theoretically optimal eviction (evict what's used furthest in future); unimplementable benchmark |
| **Cache-aside** | App checks cache, loads from origin on miss, populates cache |
| **Cardinality (of a cache)** | Number of distinct keys; drives sizing |
| **DAG** | Directed acyclic graph |
| **Eviction policy** | Rule choosing which entry to remove when full |
| **In-degree** | Number of incoming edges to a vertex |
| **Kahn's algorithm** | BFS-style topological sort using in-degrees |
| **LFU** | Least Frequently Used eviction |
| **LRU** | Least Recently Used eviction |
| **min_freq** | Pointer to the lowest non-empty frequency bucket in an O(1) LFU |
| **Post-order** | DFS order where a vertex is emitted after all its descendants |
| **Scan resistance** | A policy's ability to survive a large one-off sweep of keys |
| **Sentinel node** | Dummy head/tail node removing edge-case branches |
| **SCC** | Strongly connected component; size > 1 implies a cycle |
| **Temporal locality** | Recently used data is likely to be used again soon |
| **Thundering herd (cache)** | Many clients simultaneously missing and hitting the origin |
| **TinyLFU / W-TinyLFU** | Sketch-based admission policy; state-of-the-art hit ratios |
| **Topological order** | Vertex order where every edge points forward |

#### 3.2.7 Advanced questions with answers

**Q: Design an LRU cache with a TTL as well.**
A: Keep the map + doubly linked list, and store an expiry timestamp on each node. On `get`, if the node is expired, unlink it, delete it, and report a miss (**lazy expiration**). Optionally add a second structure — a min-heap by expiry or a timing wheel — plus a background sweeper for **active expiration**, so memory is reclaimed even for keys nobody reads again. The subtlety: lazy-only expiration means dead entries occupy capacity and can evict live ones, so a sweeper matters when TTLs are short relative to the access rate.

**Q: How would you make an LRU cache thread-safe with good concurrency?**
A: The simple answer is one mutex — correct but heavily contended, because *reads mutate the list*. Better: **striped/sharded locks** — shard by `hash(key) % N` with an independent cache per shard, giving N-way concurrency and independent eviction. Best-in-class (Caffeine's approach): keep the hash map lock-free (`ConcurrentHashMap`), record reads into per-thread **ring buffers**, and replay them into the policy structures asynchronously under a single lock — so reads never block, at the cost of the eviction order being slightly approximate.

**Q: Your LFU cache serves a workload whose popularity shifts weekly. What breaks and how do you fix it?**
A: Stale counts break it: last week's hot keys keep enormous frequencies and become effectively unevictable, so the cache stops adapting and the hit ratio decays. Fixes, in increasing sophistication: (1) periodic global decay — halve all counts every N operations or T seconds; (2) windowed frequency counting; (3) switch to **W-TinyLFU**, whose Count-Min Sketch is periodically halved and whose admission window handles newly-hot keys. Also add a metric for hit ratio over time so the decay is visibly working.

**Q: Give a case where topological sort alone is insufficient for scheduling.**
A: When tasks have durations and limited workers. Topological order gives a *valid* sequence but not an *optimal* schedule. For that you compute the **critical path** (longest path in the DAG, itself computed in topological order) and use list scheduling with resource constraints — optimal multi-processor scheduling is NP-hard in general. Also insufficient when edges are conditional (only some branches execute) or when the graph changes at runtime, which is why workflow engines re-plan dynamically.

**Q: How do you topologically sort a graph too large for memory?**
A: Use external-memory/distributed approaches: (1) an external-memory Kahn's variant — keep in-degrees in a key-value store, process the zero-in-degree frontier level by level, streaming edges from disk; (2) a Pregel/vertex-centric formulation (Giraph, Spark GraphX) where each superstep peels the current frontier — the number of supersteps equals the longest path; (3) partition the graph, sort within partitions, then merge along cross-partition edges. The frontier-based formulation is the important insight: Kahn's algorithm is naturally level-synchronous and therefore parallelisable.

**Q: Why do real systems (Redis) use *approximated* LRU instead of the exact O(1) structure?**
A: The exact structure requires per-key pointer bookkeeping and mutating a shared list on *every read* — which costs memory (two pointers per key across millions of keys) and becomes a concurrency bottleneck. Redis instead samples a handful of random keys and evicts the best candidate; with a sample of 5–10 the result is very close to true LRU at a fraction of the cost. It is a classic engineering trade: give up exactness that users cannot perceive to gain memory and throughput they can.

#### 3.2.8 Recommended learning path (algorithms)

1. **Implement both topological sorts from scratch** — Kahn's and DFS — including cycle *reporting*, not just detection.
2. Solve the classics: LeetCode 207/210 (Course Schedule I/II), 269 (Alien Dictionary), 146 (LRU Cache), 460 (LFU Cache). Write them without looking.
3. Read CLRS chapter 22 (elementary graph algorithms) for the DFS/edge-classification foundations.
4. **Instrument a real cache** — add hit/miss counters to something you use daily and graph the hit ratio. Intuition arrives with the graph.
5. Study a production implementation: read the [Caffeine](https://github.com/ben-manes/caffeine) design notes on W-TinyLFU; read Redis's `evict.c` for approximated LRU/LFU.
6. Benchmark policies against a real trace (LRU vs LFU vs random) — the results are frequently counter-intuitive and make the tradeoffs concrete.
7. Extend to distributed caching: consistent hashing, cache stampede protection, invalidation strategies.

---

# Russian Version

> Это не дословный перевод, а техническая адаптация: формулировки, примеры и акценты
> подобраны под русскоязычную инженерную терминологию и под устный ответ на экзамене.

## 1. Распределённые системы и облачная архитектура

### 1.1 Краткий конспект для экзамена

#### Что это
**Распределённая система** — набор независимых машин, который для пользователя выглядит как одна согласованная система. **Облачная архитектура** — сборка такой системы из управляемых блоков (вычисления, хранилище, очереди, идентификация), арендуемых у провайдера.

#### Зачем это нужно
Одна машина упирается в три стены: **ёмкость** (не тянет нагрузку), **доступность** (один отказ = простой) и **география** (далёкие пользователи получают высокую задержку). Распределение решает все три — ценой новых видов отказов, которых в монолите не существует.

#### Как это работает (одним предложением)
Разделить работу между машинами, реплицировать состояние, распределять запросы балансировщиком, развязать компоненты очередями и исходить из того, что сеть **будет** отказывать — поэтому каждая операция должна быть **повторяемой** и **идемпотентной**.

#### Основные компоненты
| Компонент | Роль |
|---|---|
| Балансировщик | Распределяет запросы, выводит нездоровые инстансы |
| Инстансы сервисов | Stateless-вычисления, масштабируются горизонтально |
| Брокер / очередь | Развязывает продюсера и консьюмера, гасит всплески |
| Хранилища | Реплицированное и/или шардированное состояние |
| Кеш | Снижает задержку и нагрузку на источник |
| Service discovery | Позволяет сервисам находить друг друга |
| Наблюдаемость | Метрики, логи, трейсы — то, чем всё это отлаживают |

#### Основной поток
```
Клиент → DNS → Балансировщик → API Gateway (аутентификация, лимиты)
      → Сервис A (синхронный вызов) → Сервис B
                                    → публикует событие → Брокер → Консьюмер
      → Хранилище (запись в лидер → реплики)
      → Ответ
```

#### Терминология за 30 секунд
- **Задержка (latency)** — время операции. Называть **перцентили** (p50/p95/p99), никогда среднее.
- **Доступность** — доля времени корректной работы («три девятки» = 99.9% ≈ 43 мин простоя в месяц).
- **Согласованность** — видят ли все читатели одни и те же данные. **Строгая** — всегда; **итоговая** — со временем.
- **Устойчивость к разделению** — система работает при разрыве сети.
- **Теорема CAP** — во время **разделения сети** нужно выбрать согласованность **или** доступность. Это *не* «выбери 2 из 3».
- **Репликация** — одни и те же данные на нескольких узлах.
- **Шардирование** — разные данные на разных узлах.
- **Идемпотентность** — повтор операции не меняет результат. Основа безопасных ретраев.
- **Backpressure (обратное давление)** — сигнал «замедлись» вверх по потоку вместо обвала.
- **Итоговая согласованность** — реплики сходятся, если записи прекратились.

#### Инструменты
Kubernetes, Envoy/NGINX, Kafka, RabbitMQ, GCP Pub/Sub, AWS SQS/SNS, Redis, PostgreSQL, Cassandra, DynamoDB, Terraform, Istio.

#### Сильные и слабые стороны
| Плюсы | Минусы |
|---|---|
| Горизонтальное масштабирование без потолка | Тяжело рассуждать: частичные отказы повсюду |
| Изоляция отказов | Отладка требует реальных вложений в наблюдаемость |
| Независимые деплои, автономия команд | Сеть медленная и ненадёжная в сравнении с вызовом в процессе |
| Близость к пользователю географически | Согласованность распределённых данных объективно сложна |
| Эластичная стоимость | Операционные и когнитивные накладные расходы |

#### Типичные вопросы и короткие ответы
| Вопрос | Ответ |
|---|---|
| Сформулируйте CAP точно. | При возникновении разделения сети (P) система жертвует либо согласованностью (C), либо доступностью (A). Без разделения доступны обе — CAP описывает поведение **во время** разделения. |
| CAP и PACELC? | PACELC расширяет: **если P** → A или C; **иначе (E)** → **L**atency или **C**onsistency. Описывает повседневный компромисс, который CAP игнорирует. |
| Почему exactly-once доставка невозможна? | Задача двух генералов: отправитель никогда не уверен, что подтверждение дошло. Получают at-least-once + **идемпотентную обработку**, что даёт exactly-once по **эффекту**. |
| Репликация vs шардирование? | Репликация — копии **одних и тех же** данных (доступность, чтение). Шардирование — **разные** данные на узлах (запись, объём). Обычно применяются вместе. |
| Как сделать ретраи безопасными? | Ключи идемпотентности, экспоненциальная задержка **с джиттером**, ограниченное число попыток, circuit breaker, DLQ для «ядовитых» сообщений. |
| Что такое сага? | Длинная транзакция как цепочка локальных транзакций с компенсирующими действиями. Замена 2PC между сервисами. |

#### Типичные ошибки
1. «CAP — выбери 2 из 3». Нет: P в реальной сети не опционально, выбор — между C и A во время разделения.
2. «Микросервисы всегда лучше». Это обмен сложности кода на сложность эксплуатации. Для небольшой команды правильный дефолт — модульный монолит.
3. Средняя задержка вместо перцентилей — среднее прячет хвост, который и чувствует пользователь.
4. Ретраи без идемпотентности → дубли эффектов (двойные списания, двойные письма).
5. Ретраи без джиттера → «шторм ретраев» добивает восстанавливающийся сервис.
6. «Итоговая согласованность = данные могут быть вечно неверны». Нет: они сходятся; вопрос в окне сходимости.
7. Общая БД у нескольких микросервисов — это распределённый монолит: все издержки без независимости.

#### «Идеальный ответ» для заучивания
> Распределённая система распределяет работу по независимым машинам ради масштаба, доступности и близости к пользователю. Плата — частичные отказы: сеть может потерять, задержать, продублировать или переупорядочить что угодно. Теорема CAP формализует главное следствие: во время разделения сети выбираем согласованность или доступность, а PACELC добавляет, что и без разделения мы торгуем задержку против согласованности. Отсюда практическая дисциплина: реплицировать ради доступности, шардировать ради масштаба, ставить очереди между компонентами, чтобы всплески не каскадировали, делать операции идемпотентными ради безопасных ретраев и ограничивать отказы таймаутами, backoff с джиттером, circuit breaker и dead-letter очередями. Облака продают эти примитивы как управляемые сервисы: в моём проекте вебхук GitHub приходит в приёмник на Cloud Run, тот публикует в Pub/Sub; приватный воркер потребляет с гарантией at-least-once, дедуплицирует по маркеру-артефакту в Cloud Storage как ключу идемпотентности, а «ядовитые» сообщения после пяти попыток уходят в dead-letter.

---

### 1.2 Полный учебный отчёт

#### 1.2.1 Базовые понятия

##### Восемь заблуждений распределённых вычислений
Заблуждения Питера Дойча — каждое является будущим багом: сеть надёжна; задержка нулевая; полоса бесконечна; сеть безопасна; топология не меняется; администратор один; стоимость передачи нулевая; сеть однородна. **Все восемь ложны.** Большинство инцидентов — это одно из этих допущений, просочившееся в код.

##### Задержка
Мыслить нужно **распределением**, а не средним:

| Метрика | Смысл | Где применять |
|---|---|---|
| p50 (медиана) | Типичный опыт | Планирование ёмкости |
| p95 / p99 | Хвост — недовольные пользователи | SLO, алерты |
| p99.9 | Редкое, но системное | Крупные системы |
| Среднее | **Вводит в заблуждение** | Не использовать в пользовательских SLO |

Порядки величин, которые стоит помнить:
```
Обращение к L1-кешу        ~1 нс
Обращение к RAM            ~100 нс
Случайное чтение SSD       ~16 мкс
Round-trip внутри ДЦ       ~500 мкс
Seek на HDD                ~2 мс
Пакет Калифорния↔Европа    ~150 мс
```
**Вывод:** сетевой вызов примерно в 10 000 раз дороже обращения к памяти. Каждая граница микросервиса — это осознанное согласие платить эту цену.

**Усиление хвоста:** если запрос разветвляется на 10 сервисов с p99 = 100 мс каждый, вероятность, что *хотя бы один* окажется медленным, близка к единице — ваш p99 становится их худшим случаем. Лечится hedged-запросами и сокращением fan-out.

##### Доступность
| Девятки | Доступность | Простой в год | В месяц |
|---|---|---|---|
| 2 | 99% | 3.65 дня | 7.2 часа |
| 3 | 99.9% | 8.77 часа | 43.8 мин |
| 4 | 99.99% | 52.6 мин | 4.4 мин |
| 5 | 99.999% | 5.26 мин | 26 сек |

**Последовательные зависимости перемножаются:** сервис поверх трёх компонентов по 99.9% имеет потолок 0.999³ ≈ **99.7%**. **Избыточность добавляет девятки:** две независимые реплики по 99% дают 99.99% — *если* отказы действительно независимы (а они редко таковы: общее питание, общая сеть, общий плохой деплой).

##### Модели согласованности
| Модель | Гарантия | Цена |
|---|---|---|
| **Линеаризуемость** | Чтение всегда видит последнюю запись; система ведёт себя как одна копия | Координация на каждой операции, недоступность при разделении |
| **Последовательная** | Все узлы видят операции в одном порядке | Дешевле линеаризуемости |
| **Причинная** | Причинно связанные операции упорядочены | Хороший компромисс |
| **Read-your-writes** | Пользователь видит собственные записи | Сессионная гарантия, дёшево, заметно пользователю |
| **Монотонные чтения** | Время не идёт назад | Сессионная гарантия |
| **Итоговая** | Реплики сходятся | Максимальная доступность |

Практика: **сессионные гарантии** дают бо́льшую часть *воспринимаемой* корректности за долю стоимости строгой согласованности. Отсюда популярность «после записи читаем с лидера».

##### CAP и PACELC
```
        Произошло разделение сети
                  │
        ┌─────────┴──────────┐
      CP-система          AP-система
   Отказ в записи на    Принимает записи
   меньшей стороне      с обеих сторон
   → согласована        → доступна
   → недоступна         → расходится, нужна реконсиляция
   etcd, ZooKeeper,     Cassandra, DynamoDB,
   HBase, Spanner*      Riak, DNS
```
\* Spanner фактически CP, но добивается очень высокой доступности, делая разделения редкими (частная глобальная сеть + TrueTime).

**PACELC (Абади)** — более полезная в быту модель: *если (P) — выбирай A или C; иначе (E) — выбирай L (задержку) или C*. DynamoDB = PA/EL, Spanner = PC/EC, Cassandra = PA/EL с настраиваемыми кворумами.

**Арифметика кворумов:**
```
N — число реплик, W — кворум записи, R — кворум чтения
Если W + R > N — множества пересекаются → строгая согласованность
Классика: N=3, W=2, R=2
Быстрое чтение:  N=3, W=3, R=1
Быстрая запись:  N=3, W=1, R=3
```

##### Репликация
| Стратегия | Как | Плюсы | Минусы |
|---|---|---|---|
| **Один лидер** | Все записи в лидер, реплицируются на фолловеров | Просто, нет конфликтов записи | Лидер — узкое место и точка отказа |
| **Мульти-лидер** | Несколько узлов принимают записи | Локальность записи по регионам | **Конфликты записи** (LWW, CRDT, логика приложения) |
| **Без лидера** (Dynamo) | Клиент пишет в N, ждёт W подтверждений | Нет процедуры failover, высокая доступность | Нужны read-repair, anti-entropy, настройка кворумов |

**Синхронная vs асинхронная репликация** — регулятор «надёжность/задержка»: синхронная не теряет данные при failover, но медленная реплика тормозит записи; асинхронная быстра, но при failover теряется нереплицированный хвост. Компромисс — полусинхронная (одна синхронная реплика).

**Лаг репликации** порождает классический баг: пользователь написал комментарий, прочитал с отстающей реплики — комментарий «исчез». Лечится маршрутизацией read-your-writes.

##### Шардирование
| Схема | Как | Плюсы | Минусы |
|---|---|---|---|
| **Диапазонная** | Диапазоны ключей на шард | Эффективные range-запросы | **Горячие точки** (например, ключи по времени бьют в последний шард) |
| **Хеш** | `hash(key) % N` | Равномерность | Range-запросы требуют scatter-gather; решардинг двигает всё |
| **Консистентное хеширование** | Кольцо + виртуальные узлы | Добавление узла двигает ~1/N ключей | Сложнее, нужны vnodes |
| **Каталог** | Явная карта шардов | Максимальная гибкость | Сервис-каталог — зависимость и точка отказа |

**Проблема «горячего ключа»** (вирусный пост, огромный арендатор): решается солью в ключе, разделёнными счётчиками, выделенными шардами, кешем перед хранилищем.

##### Балансировка нагрузки
| Уровень | Работает с | Примеры |
|---|---|---|
| **L4** | TCP/UDP | AWS NLB, IPVS — быстро, без понимания HTTP |
| **L7** | HTTP/gRPC | Envoy, NGINX, ALB — маршрутизация по путям, ретраи, TLS |
| **Клиентская** | В процессе | gRPC-LB — нет лишнего хопа |
| **Service mesh** | Sidecar-прокси | Istio, Linkerd — mTLS, ретраи, телеметрия без правок приложения |

Алгоритмы: round-robin, взвешенный RR, **least connections**, **least request**, консистентный хеш, EWMA. **Health-check важнее алгоритма**: пассивные (исключение по ошибкам) + активные (проба) + slow start для «холодного» инстанса.

##### Отказоустойчивость
Исходное допущение: **отказывает всё и постоянно.**
- **Таймауты** — самый недооценённый инструмент. Без таймаута зависшая зависимость исчерпает пул потоков/соединений и утянет вас за собой. Ставить по измеренному p99, а не «на глаз».
- **Ретраи** — только для *временных* сбоев, только для *идемпотентных* операций, всегда ограниченные, всегда с джиттером.
- **Circuit breaker** — закрыт → (превышен порог ошибок) → открыт (быстрый отказ) → полуоткрыт (пробные запросы) → закрыт.
- **Переборки (bulkhead)** — изолированные пулы ресурсов на каждую зависимость.
- **Плавная деградация** — отдать устаревший кеш, скрыть некритичный блок, отложить запись.

```python
delay = min(cap, base * 2 ** attempt)
delay = random.uniform(0, delay)      # «полный джиттер» — расцепляет клиентов
```
Без джиттера все клиенты повторяют одновременно и снова роняют сервис. Дополнительно вводят **бюджет ретраев** (не более ~10% от запросов).

##### Идемпотентность
`f(f(x)) == f(x)`. Способы реализации:
1. **Ключ идемпотентности** — клиент присылает уникальный ключ, сервер хранит `ключ → результат` и повторно отдаёт сохранённый (модель Stripe).
2. **Естественный ключ / маркер** — детерминированный ID из содержимого; проверка существования до действия. *Именно так работает ассистент: маркер — объект GCS `repo/PR/head_sha/reports/ai-test-report.json`.*
3. **Условные записи** — CAS, ETag `If-Match`, оптимистичное версионирование.
4. **Таблица дедупликации с TTL**.

**Честно об exactly-once:** exactly-once *доставка* невозможна поверх ненадёжной сети. Достижимо: **at-least-once доставка + идемпотентная обработка = exactly-once по эффекту**. «Exactly-once semantics» в Kafka — именно это, и только внутри Kafka; на произвольные внешние эффекты оно не распространяется.

##### Backpressure
От лучшего к худшему: (1) pull-модель и управление потоком со стороны консьюмера (Kafka, Reactive Streams, окна TCP); (2) ограниченный буфер + отказ 429/503 (**сброс нагрузки**); (3) rate limiting на входе (token bucket); (4) **неограниченная очередь** — ⚠️ ловушка: задержка растёт неограниченно, память кончается, система умирает «медленно, а потом сразу». Очереди сглаживают всплески, но **не чинят несоответствие пропускной способности**.

##### Очереди и брокеры
| Модель | Семантика | Примеры |
|---|---|---|
| **Очередь point-to-point** | Сообщение — ровно одному консьюмеру | SQS, очередь RabbitMQ |
| **Pub/Sub топик** | Сообщение — **каждому** подписчику | SNS, GCP Pub/Sub |
| **Лог / поток** | Упорядоченный, воспроизводимый, по смещениям | Kafka, Kinesis, Pulsar |

**Очередь vs лог** — различие, которое часто упускают: очередь *удаляет* после подтверждения, лог *хранит* в течение окна ретенции, поэтому новые консьюмеры могут перечитать историю, а группы читают независимо. Лог нужен для реплея, event sourcing и нескольких независимых читателей.

##### Распределённые транзакции
| Подход | Суть | Плюсы | Минусы |
|---|---|---|---|
| **2PC** | Координатор: prepare → commit | Настоящий ACID между узлами | **Блокирующий** при смерти координатора; плохая доступность |
| **Сага** | Цепочка локальных транзакций + компенсации | Доступно, масштабируемо, без блокировок | Нет изоляции; компенсации трудно писать |
| **Outbox** | Бизнес-строка + строка события в **одной** локальной транзакции; релей публикует | Атомарность записи и публикации без 2PC | Нужен релей/CDC; at-least-once → идемпотентные консьюмеры |
| **TCC** | Try / Confirm / Cancel с резервированием | Лучше изоляция, чем у саги | Инвазивно для API |

Саги бывают **хореографией** (каждый сервис реагирует на события — нет координатора, но поток неявный) и **оркестрацией** (центральный оркестратор — явно и отлаживаемо). Начиная с ~3 шагов предпочтительна оркестрация.

**Проблема двойной записи:** запись в БД и публикация в брокер без общей транзакции. Падение между ними разводит состояние и события навсегда. Стандартное решение — **транзакционный outbox**.

#### 1.2.2 Микросервисы

##### Границы сервисов
Самое сложное и дорогое решение. Ориентиры: **ограниченные контексты DDD** (в разных контекстах «Заказ» — это разные модели), **владение командой** (закон Конвея), **скорость изменений** (что меняется вместе — живёт вместе), **владение данными** (у каждой сущности один источник истины).

**Признаки неверных границ:** любая фича требует правок в трёх сервисах; сервисы делят одну БД; длинные синхронные цепочки A→B→C→D; «распределённый монолит», деплоящийся только целиком.

**Современный консенсус:** начинать с **модульного монолита** и выделять сервис, когда появилось *конкретное* давление (независимое масштабирование, автономия команд, изоляция рискованного компонента). Преждевременное выделение — самая дорогая типовая ошибка.

##### API Gateway
Единая точка входа: TLS, аутентификация/авторизация, лимиты, маршрутизация, агрегация ответов, трансляция протоколов, версионирование API. **Риск** — превратиться в монолитное узкое место; бизнес-логику туда не класть. Развитие идеи — **BFF** (свой шлюз под каждый тип клиента).

##### Service discovery
Клиентская (Consul, Eureka), серверная (стабильное DNS-имя/LB) или платформенная (Kubernetes Services, URL Cloud Run). Регистрация — самостоятельная или сторонняя (модель Kubernetes). Health-check обязан управлять дерегистрацией, иначе трафик идёт на «трупы».

##### Синхронно vs асинхронно
| | Синхронно (REST/gRPC) | Асинхронно (события) |
|---|---|---|
| Связность | Временна́я: адресат должен быть жив **сейчас** | Развязано, брокер буферизует |
| Отказ | Распространяется по цепочке | Поглощается очередью, ретраится |
| Сложность | Легко трассировать | Труднее отлаживать, нужны correlation ID |
| Когда | Нужен ответ для отдачи пользователю | Fire-and-forget, fan-out, долгая работа |

**Правило:** синхронно — для *запросов*, которых ждёт пользователь; асинхронно — для *команд* и побочных эффектов. Пять синхронных хопов подряд — запах архитектуры.

##### База данных на сервис
Каждый сервис владеет своей схемой, остальные ходят только через API. Следствия: **нет join между сервисами** (композиция в API или CQRS с проекцией из событий); **дублирование данных нормально** (обновляется событиями); **отчётность** — в отдельное хранилище (BigQuery/Redshift), никогда не запросами во внутренние БД сервисов.

##### Наблюдаемость и деплой
Метрики (RED на сервис, USE на ресурс), структурированные логи с **trace ID**, распределённые трейсы. Обязательно: прокидывать контекст трассировки (`traceparent`) через **все** хопы, включая очереди; OpenTelemetry — нейтральный стандарт.

Стратегии выката: rolling (две версии сосуществуют — нужна совместимость), blue-green (быстрый откат, двойная стоимость), **canary** (1% → 10% → 100% под контролем метрик), feature flags (деплой отделён от релиза). **Миграции БД — только обратносовместимые** (expand/contract: добавить колонку → писать в обе → бэкофилл → переключить чтение → удалить старую).

#### 1.2.3 Событийно-ориентированные системы

```
┌──────────┐ публикация ┌────────────────┐ доставка ┌───────────┐
│ Продюсер │───────────►│     Брокер     │─────────►│ Консьюмер │
└──────────┘            │ топики/очереди │          └─────┬─────┘
                        │ ретенция       │◄───────────────┘ ack/nack
                        └───────┬────────┘
                                │ после N неудачных попыток
                                ▼
                        ┌────────────────┐
                        │  Dead-letter   │
                        └────────────────┘
```

**Push vs pull** — реальный архитектурный выбор: **pull** (Kafka, SQS) даёт консьюмеру естественное управление потоком; **push** (GCP Pub/Sub push, вебхуки) проще в эксплуатации — консьюмер это просто HTTP-эндпоинт. *Ассистент использует push: воркер — обычный HTTP-сервис Cloud Run, а HTTP-коды и есть протокол очереди: 200 = подтвердить, 500 = повторить и затем в DLQ.*

**Типы событий:** *уведомление* («заказ 42 изменился» — нужен обратный вызов за деталями), *перенос состояния* (полная нагрузка внутри — самодостаточно, но привязывает к схеме), *event sourcing* (лог событий **и есть** источник истины). Отличайте **события** (факт в прошедшем времени) от **команд** (императив, ожидает результата) — смешивать их в одном топике вредно.

**Упорядочивание.** Глобальный порядок дорог и обычно не нужен. Реальные системы дают порядок **в пределах партиции/ключа** (Kafka — по партициям; Pub/Sub — опциональные ordering keys ценой пропускной способности). Больше консьюмеров = больше параллелизма = слабее порядок; это прямой конфликт.

**Гарантии доставки:** *at-most-once* (подтверждение до обработки, возможна потеря), **at-least-once** (подтверждение после обработки, возможны дубли — **практический дефолт**), *exactly-once* (только внутри замкнутой транзакционной системы).

**Dead-letter queue.** После N неудачных попыток сообщение уходит в отдельный топик. **Зачем:** одно «ядовитое» сообщение иначе блокирует очередь или бесконечно жжёт мощность ретраев. **Эксплуатация:** алерт на ненулевую глубину, сохранение метаданных отказа, путь для реплея после починки, разбор перед очисткой.

**Ключевое различие:** *постоянные* ошибки (некорректный формат — успех невозможен никогда) надо **сразу подтверждать**, а не ретраить; ретраи заслуживают только *временные* сбои. *Ассистент делает ровно так: недекодируемый конверт → 200 (подтвердить), неудачный clone или сбой LLM → 500 (ретраи → DLQ после 5 попыток).*

**Эволюция схем событий:** только аддитивные изменения, поля не удалять и не перепрофилировать, версионировать (`OrderPlaced.v2`), использовать schema registry (Avro/Protobuf), консьюмерам — игнорировать неизвестные поля.

#### 1.2.4 Serverless

**Что это:** вы деплоите код или контейнер, платформа берёт на себя провижининг, масштабирование (в том числе до нуля), патчинг и доступность; оплата по факту использования. «Serverless» ≠ «нет серверов», а «не ваши серверы».

| Модель | Единица | Примеры | Когда |
|---|---|---|---|
| **FaaS** | Функция по событию | Lambda, Cloud Functions | Клей, обработчики событий, короткие задачи |
| **Serverless-контейнеры** | Образ контейнера | **Cloud Run**, Fargate, Container Apps | Обычные веб-сервисы без привязки к рантайму |
| **Управляемые сервисы** | Возможность | S3, DynamoDB, Pub/Sub, BigQuery | Хранилище/очереди/аналитика без эксплуатации |

**Холодные старты:** провижининг песочницы → загрузка рантайма → инициализация кода → обработка. Влияют: рантайм (Python/JS быстро, JVM/.NET медленнее), размер пакета, тяжёлый код на уровне модуля, подключение к VPC, объём памяти (больше памяти → больше CPU). **Смягчение:** минимальные инстансы (стоит денег и убивает scale-to-zero), ленивая инициализация, урезание зависимостей и главное — **решить, важно ли это вообще**: для асинхронного воркера за очередью 2 секунды холодного старта не значат ничего.

**Классический провал масштабирования:** функция разворачивается в 1000 инстансов, каждый открывает соединение к БД — БД умирает. Лечится пулом-прокси, лимитом конкурентности или буферизацией через очередь.

**Ограничения:** потолок времени выполнения, лимиты payload/памяти, отсутствие локального состояния, привязка к вендору через форматы событий и IAM, сложная отладка (нет SSH), долгоживущие соединения требуют отдельной поддержки.

#### 1.2.5 Сравнение AWS / GCP / Azure

| Возможность | AWS | GCP | Azure |
|---|---|---|---|
| Виртуальные машины | EC2 | Compute Engine | Virtual Machines |
| Kubernetes | EKS | GKE | AKS |
| Serverless-контейнеры | Fargate / App Runner | **Cloud Run** | Container Apps |
| FaaS | Lambda | Cloud Functions | Azure Functions |
| Объектное хранилище | S3 | Cloud Storage | Blob Storage |
| Реляционная БД | RDS / Aurora | Cloud SQL / **Spanner** | SQL Database |
| NoSQL | DynamoDB | Firestore / Bigtable | **Cosmos DB** |
| Хранилище данных | Redshift | **BigQuery** | Synapse / Fabric |
| Очередь | SQS | Pub/Sub | Service Bus |
| Pub/Sub | SNS | Pub/Sub | Event Grid |
| Стриминг | Kinesis / MSK | Pub/Sub + Dataflow | Event Hubs |
| Мониторинг | CloudWatch | Cloud Monitoring | Azure Monitor |
| Трассировка | X-Ray | Cloud Trace | Application Insights |
| Идентификация | IAM | Cloud IAM | Entra ID + RBAC |
| Секреты | Secrets Manager | Secret Manager | Key Vault |
| LLM-платформа | Bedrock | Vertex AI | Azure OpenAI |

**Различия моделей IAM (частый вопрос):**
- **AWS** — JSON-политики на пользователей/роли/ресурсы; явный deny всегда побеждает; assume-role между аккаунтами.
- **GCP** — **иерархия ресурсов** (Организация → Папка → Проект → Ресурс) с **наследованием** привязок ролей; принципалы — пользователи, группы, сервисные аккаунты.
- **Azure** — management groups → подписки → группы ресурсов → ресурсы; назначения ролей RBAC + Azure Policy для governance; идентичность в Entra ID.

**Характер платформ:** AWS — самый широкий каталог и экосистема, но сложность и непрозрачность цен. GCP — лучшая аналитика (BigQuery), сильное наследие Kubernetes, простые цены, самый удобный serverless-контейнерный UX (Cloud Run). Azure — глубокая интеграция с экосистемой Microsoft, сильный гибридный сценарий, корпоративные соглашения.

**Про мультиклауд:** переносимость дорога и обычно теоретична. Разумно использовать управляемые сервисы глубоко, а переносимость обеспечивать контейнерами и изоляцией SDK провайдера за собственными интерфейсами (гексагональная архитектура), а не использованием «наименьшего общего знаменателя».

#### 1.2.6 Разбор архитектуры этого репозитория

```
Событие PR в GitHub
      │ HTTPS + подпись HMAC-SHA256
      ▼
┌─────────────────────┐  Cloud Run, публичный, scale-to-zero
│  webhook-receiver   │  проверил подпись → отфильтровал → опубликовал → 202
└──────────┬──────────┘
           ▼
┌─────────────────────────────────────────┐
│ Pub/Sub: pr-analysis-jobs               │
│ push-подписка, ack deadline 600 с       │
│ 5 попыток → dead-letter топик           │
└──────────┬──────────────────────────────┘
           │ push с OIDC-аутентификацией
           ▼
┌─────────────────────┐  Cloud Run, приватный, concurrency=1
│  analysis-worker    │  идемпотентность → clone → анализ → LLM → pytest
└───┬─────────────┬───┘
    ▼             ▼
 GCS-бакет   commit status в GitHub
```

| Концепция | Где проявляется |
|---|---|
| Граница по **конфликту требований** | Приёмник публичный и обязан ответить за ~10 с; воркер приватный и работает минутами |
| Выравнивание нагрузки очередью | Всплеск PR встаёт в очередь, а не роняет воркеры |
| At-least-once + идемпотентный консьюмер | Объект отчёта в GCS как маркер дедупликации |
| Ретраи vs постоянные ошибки | 500 → повтор; некорректное сообщение → 200 |
| DLQ | 5 попыток → `pr-analysis-jobs-dead-letter` + подписка для разбора |
| Scale-to-zero | Оба сервиса ничего не стоят в простое |
| Горизонтальное масштабирование | concurrency=1, масштаб инстансами (внутри git и pytest) |
| Наименьшие привилегии | Воркер приватный, `run.invoker` только у выделенного сервисного аккаунта |
| Эшелонированная защита | Проверка HMAC — единственный барьер публичного эндпоинта |

#### 1.2.7 Режимы отказа и отладка

| Отказ | Симптом | Диагностика | Лечение |
|---|---|---|---|
| **Каскадный отказ** | Один медленный сервис — таймауты везде | Трейсы показывают общий медленный span | Таймауты, circuit breaker, переборки |
| **Шторм ретраев** | Нагрузка растёт после сбоя, сервис не встаёт | Частота запросов ≫ нормы при восстановлении | Backoff **с джиттером**, бюджет ретраев, сброс нагрузки |
| **Thundering herd** | Всплеск при истечении кеша | Периодические синхронные пики | Разброс TTL, объединение запросов |
| **Рост очереди** | Задержка растёт, затем OOM | Глубина очереди только вверх | Backpressure, автоскейл по глубине |
| **Split brain** | Два лидера, расходящиеся записи | Конфликтующие версии после разделения | Кворумные выборы, fencing-токены |
| **Лаг репликации** | «Моя запись исчезла» | Высокий лаг, чтение с фолловера | Маршрутизация read-your-writes |
| **Горячий шард** | Один узел загружен, остальные простаивают | Метрики по шардам резко неравномерны | Другой ключ, соль, выделенный шард |
| **Ядовитое сообщение** | Консьюмер в crashloop | Один и тот же message ID | DLQ + лимит попыток |
| **Расхождение часов** | Аномалии порядка и TTL | Метки времени расходятся | NTP, логические часы вместо wall-clock |

**Метод отладки:** метрики (*что* и *когда*) → трейсы (*где* в пути запроса) → логи по trace ID (*почему*) → корреляция с изменениями (деплой, конфиг, сдвиг трафика) → проверка насыщения (пулы, диск, квоты).

#### 1.2.8 Безопасность, производительность, масштабируемость, надёжность

**Безопасность:** эшелонированная защита; наименьшие привилегии (идентичность на сервис, никаких общих «богов»); **zero trust** — аутентификация между сервисами (mTLS или подписанные токены), а не «внутри VPC всё своё»; шифрование в транзите и покое; секреты в менеджере с ротацией; валидация **всего** входа на границе доверия (ассистент проверяет HMAC до любого разбора); аудит-логи.

**Производительность:** кеш на каждом разумном уровне (клиент → CDN → шлюз → приложение → БД); батчинг ради амортизации round-trip; асинхронный I/O; малые payload; вычисления рядом с данными.

**Масштабируемость:** stateless-сервисы; шардирование состояния; **асинхронная обработка всего, чего не ждёт пользователь**; автоскейл по правильному сигналу; нагрузочное тестирование с инъекцией отказов.

**Надёжность:** **SLI/SLO** и **бюджет ошибок** как арбитр между «выкатывать» и «стабилизировать»; chaos engineering; game days; автоматический откат; безвинные постмортемы.

#### 1.2.9 Продвинутые вопросы

**В: Сервис синхронно вызывает три других. Как удержать p99?**
О: Сначала усомниться в дизайне — три синхронных хопа на критическом пути это запах. Затем: агрессивные таймауты по измеренному p99, **параллельные** вызовы вместо последовательных (последовательные p99 складываются, параллельные дают максимум), circuit breaker, кеширование медленно меняющихся данных, hedged-запросы против хвоста.

**В: Как мигрировать монолит в микросервисы?**
О: Паттерн **strangler fig**: поставить фасад перед монолитом, выносить по одному ограниченному контексту (начиная с слабо связанного и ценного), переводить трафик через фасад, некоторое время работать параллельно с shadow-трафиком, затем удалять старый код. Данные — в последнюю очередь, синхронизация через CDC/outbox на время перехода. Big-bang переписывание не делать никогда.

**В: Kafka или обычная очередь?**
О: Kafka — когда нужен упорядоченный воспроизводимый **лог**: event sourcing, несколько независимых групп консьюмеров, высокая устойчивая пропускная способность, реплей после бага. Обычная очередь — когда нужно **распределение работы** с ack/retry/DLQ на сообщение, простая эксплуатация и реплей не требуется. Операционная нагрузка Kafka существенно выше.

**В: Когда serverless — неправильный выбор?**
О: Устойчиво высокая нагрузка (зарезервированные мощности дешевле), критичная к задержке синхронная обработка без запаса на холодный старт, долгоживущие или stateful процессы, потребность в специальном железе, а также случаи, когда лимиты платформы действительно связывают руки.

#### 1.2.10 План изучения

1. **Фундамент** — Клеппман, «Высоконагруженные приложения» (DDIA), главы 1–9.
2. **Практика** — собрать небольшую событийную систему с реальным брокером, обязательно обработав дубликаты доставки и DLQ.
3. **Паттерны** — microservices.io (Ричардсон), «Release It!» (Найгард).
4. **Статьи** — Dynamo, GFS, MapReduce, Spanner, Raft.
5. **Облако** — выбрать одного провайдера и уйти вглубь (программа associate-архитектора как учебный план), остальные учить через карту соответствий.
6. **Эксплуатация** — SRE-книга Google (бесплатно онлайн): SLO и бюджеты ошибок.
7. **Намеренные отказы** — убить воркер посреди задания, послать ядовитое сообщение, разорвать сеть через `tc`/toxiproxy.

---

## 2. Инструменты мониторинга: Prometheus и Grafana

### 2.1 Краткий конспект для экзамена

#### Что это
**Prometheus** — система мониторинга и БД временных рядов, которая **сама забирает (pull/scrape)** метрики с HTTP-эндпоинтов, хранит их локально, вычисляет правила и отправляет алерты. **Grafana** — платформа визуализации, которая запрашивает Prometheus (и десятки других источников) и рисует панели, плюс имеет собственный алертинг.

#### Зачем
Нельзя эксплуатировать распределённую систему, которую не видно. Prometheus даёт *числа во времени* (дёшево, агрегируемо, алертоспособно), Grafana превращает их в то, что человек поймёт в три часа ночи.

#### Как работает
Приложение отдаёт текстовый `/metrics`. Prometheus обнаруживает цели (статически или через service discovery), опрашивает их по интервалу, кладёт сэмплы в локальную TSDB, вычисляет **recording rules** (предрасчёт) и **alerting rules** (условия) и шлёт сработавшие алерты в **Alertmanager**, который дедуплицирует, группирует, подавляет и маршрутизирует уведомления. Grafana запрашивает Prometheus на **PromQL**.

```
┌──────────────┐  scrape  ┌────────────────────┐ алерты ┌──────────────┐
│ App /metrics │◄─────────│    Prometheus      │───────►│ Alertmanager │
│  Экспортеры  │  (pull)  │  TSDB + правила    │        │ дедуп/роутинг│
└──────────────┘          └─────────┬──────────┘        └──────┬───────┘
                                    │ PromQL                   ▼
                                    ▼                   Slack / Email /
                          ┌────────────────────┐        PagerDuty
                          │      Grafana       │
                          └────────────────────┘
```

#### Терминология
- **Временной ряд** — поток сэмплов, идентифицируемый именем метрики + набором меток.
- **Метка (label)** — измерение `status="500"`. Метки определяют идентичность ряда.
- **Кардинальность** — число уникальных рядов. **Главный операционный риск.**
- **Типы метрик** — Counter (только вверх), Gauge (вверх/вниз), Histogram (по корзинам), Summary (квантили на клиенте).
- **Экспортер** — адаптер, отдающий метрики стороннего софта в формате Prometheus.
- **Recording rule** — предрассчитанный запрос, сохранённый как новый ряд.

| Тип | Для чего | Пример |
|---|---|---|
| **Counter** | Монотонно растущие события | `http_requests_total` |
| **Gauge** | Значения вверх и вниз | `queue_depth` |
| **Histogram** | Распределения, перцентили **на сервере** | `http_request_duration_seconds` |
| **Summary** | Квантили **на клиенте** | Устарело: **не агрегируется между инстансами** |

#### Сильные и слабые стороны
| Плюсы | Минусы |
|---|---|
| Просто, самодостаточно, без внешних зависимостей | **Не** долговременное хранилище (нужны Thanos/Mimir/Cortex) |
| Мощная модель меток + PromQL | Одноузловой по замыслу |
| Pull: мёртвая цель обнаруживается тривиально (`up`) | Pull неудобен для короткоживущих задач (отсюда Pushgateway) |
| Огромная экосистема экспортеров | Высокая кардинальность его убивает |

#### Типичные вопросы
| Вопрос | Ответ |
|---|---|
| Почему pull, а не push? | Prometheus контролирует частоту опроса, живость цели определяется тривиально (метрика `up`), целям не нужна конфигурация мониторинга. |
| Counter vs Gauge? | Counter только растёт (нужен `rate()`), Gauge меняется в обе стороны. |
| Зачем `rate()` на счётчиках? | Абсолютное значение бессмысленно и сбрасывается при рестарте; `rate()` даёт прирост в секунду и корректно обрабатывает сбросы. |
| Histogram vs Summary? | Histogram шлёт счётчики корзин, поэтому квантили считаются **по всем** инстансам во время запроса. Summary считает квантили в клиенте и не агрегируется. |
| Хранит ли Grafana данные? | Нет — только дашборды и собственную конфигурацию алертов. |
| Что добавляет Alertmanager? | Дедупликацию, группировку, подавление (inhibition), сайленсы и маршрутизацию. |

#### Типичные ошибки
1. **Взрыв кардинальности** — user ID, email, UUID, полные URL в метках. Убивает Prometheus быстрее всего остального.
2. **Усреднение перцентилей** — `avg(p99)` математически бессмысленно; агрегировать нужно **корзины гистограммы**, а квантиль считать после.
3. Summary для латентности, а затем открытие, что её нельзя агрегировать по репликам.
4. Алерты на **причины вместо симптомов** — алертить надо на «пользователи видят ошибки», а не «CPU 90%».
5. Забытые соглашения: суффикс `_total`, базовые единицы (секунды, байты).
6. Отношение к Prometheus как к долговременному хранилищу без Thanos/Mimir.

#### «Идеальный ответ»
> Prometheus — система метрик по модели pull: сервисы отдают `/metrics` в простом текстовом формате, Prometheus обнаруживает цели и опрашивает их с фиксированным интервалом в локальную БД временных рядов, где каждый ряд определяется именем метрики и набором меток. Запрашивают его на PromQL: `rate()` по счётчикам для пропускной способности, `histogram_quantile()` по корзинам гистограммы для перцентилей задержки. Правила алертинга отправляют сработки в Alertmanager, который дедуплицирует, группирует, подавляет и маршрутизирует уведомления. Grafana сверху — только слой запросов и визуализации: она хранит дашборды, а не данные. Главный операционный риск — кардинальность: каждое уникальное сочетание меток это отдельный ряд, поэтому в метки нельзя класть неограниченные значения вроде user ID. В моём проекте воркер экспортирует счётчики заданий по исходам, вызовов и токенов LLM, попаданий кеша и гистограмму длительности — поэтому дашборд показывает и здоровье, и прямой экономический эффект кеша ответов LLM.

---

### 2.2 Полный учебный отчёт

#### 2.2.1 Наблюдаемость: метрики, логи, трейсы

**Мониторинг** отвечает на *заранее известные* вопросы, **наблюдаемость** — способность отвечать на *новые* вопросы без выкладки нового кода.

| Сигнал | Что это | Стоимость | Терпимость к кардинальности | Для чего |
|---|---|---|---|---|
| **Метрики** | Числа во времени, агрегированные | Очень низкая | **Низкая** | Алерты, тренды, SLO |
| **Логи** | Дискретные события с меткой времени | Высокая (объём) | Высокая | Отладка деталей, аудит |
| **Трейсы** | Причинно связанные span'ы между сервисами | Средняя (сэмплирование) | Высокая | Атрибуция задержки |

Рабочий процесс использует все три по порядку: **метрика** сообщает, что выросли ошибки; **трейс** показывает, в каком сервисе и span'е; **логи** по этому trace ID объясняют почему.

**OpenTelemetry** — нейтральный стандарт для всех трёх сигналов: единый API/SDK, единый протокол OTLP, сменные бэкенды. Современный совет: инструментировать через OTel, метрики отдавать в Prometheus, трейсы в Tempo/Jaeger, логи в Loki.

#### 2.2.2 Архитектура Prometheus подробно

Согласно [официальной документации](https://prometheus.io/docs/introduction/overview/), Prometheus собирает метрики с инструментированных задач напрямую (или через pushgateway для короткоживущих), хранит все сэмплы локально и выполняет правила для агрегации новых рядов и генерации алертов. Серверы Prometheus **работают независимо и полагаются только на локальное хранилище** — сознательное решение ради надёжности: мониторинг продолжает работать, когда сломана вся остальная инфраструктура.

##### Модель данных
```
имя_метрики{метка1="знач1", метка2="знач2"}  @метка_времени  значение

http_requests_total{method="POST", handler="/api", status="200"}  1717000000  12345
```
Ряд уникально определяется именем **и полным набором меток**: изменение любого значения метки создаёт другой ряд. Соглашения: `<namespace>_<subsystem>_<name>_<unit>`, базовые единицы (секунды, байты), `_total` для счётчиков.

##### Сбор и service discovery
Каждый scrape автоматически даёт `up{job=..., instance=...}` — 1 при успехе, 0 при неудаче. **Самая важная бесплатная метрика**: именно так pull-система обнаруживает мёртвые цели. Механизмы обнаружения: `static_configs`, `kubernetes_sd`, `ec2_sd`, `gce_sd`, `consul_sd`, `dns_sd`, `file_sd`. **Relabeling** (`relabel_configs` до сбора, `metric_relabel_configs` после) фильтрует цели, переписывает метки и **отбрасывает высококардинальные метрики до записи** — владение relabeling отличает оператора от пользователя.

##### TSDB
- Сэмплы дописываются в in-memory **head-блок** с **WAL** для восстановления после падения.
- Каждые ~2 часа head сбрасывается в неизменяемый блок на диске, старые блоки **компактируются**, вышедшие за ретенцию — удаляются.
- Сжатие очень плотное: примерно **1–2 байта на сэмпл** (delta-of-delta для времени, XOR для значений — из статьи Facebook Gorilla).

```
диск ≈ ретенция_в_секундах × сэмплов_в_секунду × ~2 байта
```
Память определяется **числом активных рядов**, а не частотой сэмплов — поэтому контролировать нужно именно кардинальность. Для долгого хранения, глобальных запросов и HA добавляют **Thanos**, **Mimir** или **Cortex** через `remote_write`.

##### Кардинальность
```
Всего рядов = Π (число значений каждой метки) × число метрик
```
Пример катастрофы: метка `user_id` со 100 000 пользователей × 5 эндпоинтов × 4 статуса = **2 000 000 рядов** из одной метрики.

| ✅ Хорошие метки (ограниченные) | ❌ Опасные (неограниченные) |
|---|---|
| `status="500"`, `method="POST"` | `user_id`, `email`, `session_id` |
| `region="us-central1"` | `request_id`, `trace_id` |
| `result="passed"` | URL с идентификаторами, сырой SQL |

**Правило:** если множество значений нельзя перечислить заранее — это не метка, это лог или трейс.

##### PromQL
```promql
# Пропускная способность: прирост в секунду за 5 минут (учитывает сбросы счётчика)
rate(http_requests_total[5m])

# Доля ошибок, агрегированная по инстансам
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

# p95 из корзин гистограммы — rate внутри, by (le) обязательно
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# Агрегация с группировкой и топ-N
sum by (service) (rate(errors_total[5m]))
topk(5, sum by (endpoint) (rate(http_requests_total[5m])))

# Прогноз: заполнится ли диск за 4 часа
predict_linear(node_filesystem_free_bytes[6h], 4*3600) < 0
```

| Ошибка | Почему неверно | Правильно |
|---|---|---|
| `histogram_quantile` без `by (le)` при агрегации | Корзины разных инстансов не объединяются | `sum(rate(...)) by (le)` внутри |
| `avg(rate(...))` для общей доли ошибок | Усредняет отношения с разными знаменателями | `sum(...) / sum(...)` |
| `rate()` по gauge | `rate` предполагает монотонность | `deriv()` или само значение |
| `irate()` в алертах | Крайне шумно | `rate()` |

##### Правила и Alertmanager
**Recording rules** предрассчитывают дорогие выражения (соглашение об именовании `level:metric:operation`). **Alerting rules** — из этого репозитория:
```yaml
- alert: HighJobFailureRate
  expr: rate(jobs_processed_total{status="failed"}[15m])
        / clamp_min(rate(jobs_processed_total[15m]), 1e-9) > 0.2
  for: 15m
```
`for:` обязателен — требует непрерывного выполнения условия и убирает «дребезг». `clamp_min` защищает от деления на ноль при отсутствии трафика.

**Alertmanager** — отдельный бинарник (маршрутизация уведомлений не дело движка мониторинга). По [документации](https://prometheus.io/docs/alerting/latest/alertmanager/) он занимается дедупликацией, группировкой и маршрутизацией алертов в нужный приёмник (email, PagerDuty, OpsGenie), а также сайленсами и подавлением.

| Функция | Зачем |
|---|---|
| **Группировка** | Одно уведомление на 50 инстансов вместо 50 звонков |
| **Дедупликация** | HA-пара Prometheus шлёт алерт дважды — доходит один |
| **Inhibition** | Подавить «сервис упал», когда горит «упал кластер» |
| **Silence** | Заглушить на время планового обслуживания |
| **Дерево маршрутов** | По severity/команде/времени в нужный приёмник |

**Pushgateway** — только для **короткоживущих batch-задач**. Не использовать как общий push-прокси: он становится точкой отказа, ломает семантику `up` и хранит устаревшие значения до явного удаления.

#### 2.2.3 Grafana

| Понятие | Смысл |
|---|---|
| **Источник данных** | Бэкенд для запросов: Prometheus, Loki, Tempo, SQL, CloudWatch |
| **Дашборд** | JSON-документ с панелями, переменными и раскладкой |
| **Панель** | Одна визуализация с одним или несколькими запросами |
| **Переменная** | Шаблонный параметр (`$service`) для переиспользуемых дашбордов |
| **Аннотация** | Отметка события на графике (деплой, инцидент) — бесценно для корреляции |
| **Provisioning** | Дашборды и источники как файлы в git, а не клики в UI |

**Типы панелей:** time series (почти всё во времени), stat (одно текущее число), gauge (значение против порога), table (топ-N), **heatmap** (распределение задержек — идеально для корзин гистограммы), logs, state timeline.

**Алертинг Grafana vs Prometheus:** правила Prometheus + Alertmanager вычисляются в Prometheus, живут в git, **переживают падение Grafana** — держите там критичные инфраструктурные алерты. Grafana-алертинг умеет работать **между источниками данных** (метрики + SQL) — используйте для бизнес-условий.

**Provisioning** обязателен: дашборды, накликанные в UI, недокументированы, нерецензируемы и теряются вместе с томом; дашборды в git — diff'аются, проходят ревью и воспроизводятся.

#### 2.2.4 Как они работают вместе — пример из репозитория

```
1. Код:      CACHE_HITS.inc() / JOB_DURATION.observe(1.7)
2. Библиотека агрегирует в памяти, отдаёт текст на /metrics
3. Prometheus опрашивает раз в 5–60 с ──► TSDB
4a. Правила раз в 15 с → Alertmanager     4b. Grafana запрашивает PromQL
5. Дедуп → группировка → маршрут → уведомление / отрисовка панелей
```

Инструментирование воркера:
```python
JOBS_PROCESSED = Counter("jobs_processed_total", "Задания по исходам", ["status"])
JOB_DURATION   = Histogram("job_duration_seconds", "Длительность задания",
                           buckets=(5, 15, 30, 60, 120, 300, 600))
LLM_CALLS      = Counter("llm_calls_total", "Вызовы LLM (промахи кеша)")
CACHE_HITS     = Counter("llm_cache_hits_total", "Попадания в кеш ответов LLM")
GENERATED_FILES = Counter("generated_test_files_total", "По исходу pytest", ["result"])
```
Запросы дашборда:
```promql
rate(jobs_processed_total[5m]) * 60                                  # заданий в минуту
histogram_quantile(0.95, rate(job_duration_seconds_bucket[15m]))     # p95 длительности
llm_cache_hits_total / clamp_min(llm_cache_hits_total + llm_cache_misses_total, 1)
generated_test_files_total{result="passed"} / clamp_min(sum(generated_test_files_total), 1)
```
**Измеренный результат:** четыре одинаковых задания дали `llm_calls_total = 3` при 9 попаданиях и 3 промахах кеша — 75% хитрейта, счётчики токенов после первого задания остались плоскими. В этом и смысл инструментирования кеша: оптимизация **доказана**, а не постулирована.

**Два осознанных «не-решения», которые стоит уметь объяснить:**
1. **Глубину очереди не измеряем сами** — Pub/Sub уже экспортирует `num_undelivered_messages`; собственный замер был бы строго хуже.
2. **Приёмник не инструментирован** — он делает одну дешёвую вещь, а Cloud Run из коробки даёт счётчики запросов, задержку и ошибки. *Кастомные метрики нужны там, где кастомная логика.*

#### 2.2.5 Что измерять: RED, USE и четыре золотых сигнала

| Метод | Применяется к | Измеряет |
|---|---|---|
| **RED** | Сервисам, обрабатывающим запросы | Rate, Errors, Duration |
| **USE** | Ресурсам (CPU, диск, пул) | Utilization, Saturation, Errors |
| **Четыре золотых сигнала** | Сервисам | Задержка, трафик, ошибки, насыщение |

```promql
# SLI: доля успешных запросов
sum(rate(http_requests_total{status!~"5.."}[30d])) / sum(rate(http_requests_total[30d]))
# Скорость сжигания бюджета ошибок (1 = ровно по бюджету)
(1 - sli) / (1 - slo_target)
```
Алертить следует на **многооконные условия по скорости сжигания** (быстрое: 14.4× за 1 ч; медленное: 6× за 6 ч), а не на сырые пороги — это подход SRE-книги.

#### 2.2.6 Режимы отказа и отладка

| Симптом | Причина | Лечение |
|---|---|---|
| Prometheus в OOM | Взрыв кардинальности | `topk(10, count by (__name__)({__name__=~".+"}))`, дропы в `metric_relabel_configs` |
| Разрывы на графиках | Таймауты сбора, рестарты цели | Проверить `up`, `scrape_duration_seconds` против `scrape_timeout` |
| Алерт не срабатывает | Неверное выражение или слишком долгий `for:` | Проверить выражение в UI, состояние на вкладке Alerts |
| Алерт горит, уведомления нет | Маршрутизация или сайленс | UI Alertmanager, дерево маршрутов, активные сайленсы |
| Счётчики обнулились | Рестарт процесса | Норма — `rate()` это учитывает |
| Дашборд медленный | Дорогой запрос, длинный диапазон | Recording rules, уже диапазон |

**Реальный случай из этого проекта:** развёрнутый сервис отдавал `/healthz`, а фронтенд Google возвращал 404 — `/healthz` является **зарезервированным путём** в инфраструктуре Google. Переименование в `/health` решило проблему. Урок: *пути health/metrics взаимодействуют с платформой перед вами* — проверять надо снаружи, а не только локально.

#### 2.2.7 Лучшие практики

1. Сначала сигналы **RED** для каждого сервиса, доменные метрики — вторым шагом.
2. Базовые единицы и соглашения: секунды, байты, доли; `_total` для счётчиков.
3. **Только ограниченные метки.**
4. **Histogram вместо Summary** для задержек.
5. Алертить на **симптомы**, с `for:`, каждый алерт — с ссылкой на runbook в аннотации.
6. **Дашборды как код** из git.
7. **Recording rules** для часто повторяемых запросов.
8. **Мониторить сам мониторинг:** `up`, `prometheus_tsdb_head_series`, размер WAL, длительность вычисления правил.
9. Заранее решить вопрос ретенции и долговременного хранилища.
10. **Связывать сигналы** — trace ID в логах, экземпляры (exemplars) в гистограммах.

#### 2.2.8 Сравнение с альтернативами

| Инструмент | Модель | Плюсы | Минусы |
|---|---|---|---|
| **Prometheus** | Pull, метки, локальная TSDB | Стандарт, бесплатен, PromQL, экосистема | Одноузловой, нет долгого хранения, хрупок к кардинальности |
| **VictoriaMetrics** | Совместим с Prometheus | Быстрее, меньше памяти, лучше держит кардинальность, кластеризация | Меньше сообщество, диалект MetricsQL |
| **Thanos / Mimir / Cortex** | Prometheus + объектное хранилище | Долгая ретенция, глобальные запросы, HA | Существенная операционная сложность |
| **Datadog / New Relic** | SaaS на агентах | Всё в одном, минимум эксплуатации | **Стоимость на масштабе**, вендорлок |
| **CloudWatch / Cloud Monitoring / Azure Monitor** | Управляемые, push | Нулевая настройка для метрик платформы | Слабее язык запросов, оплата за метрику |
| **OpenTelemetry** | Стандарт инструментирования | Нейтрален, все три сигнала | Это не бэкенд |
| **Loki / Tempo** | Логи / трейсы | Модель как у Prometheus, дёшево | Loki не для полнотекстового поиска |

**Современный дефолтный стек:** OpenTelemetry → Prometheus (метрики) + Loki (логи) + Tempo (трейсы) → Grafana как единое окно. Этот репозиторий реализует метрическую половину.

#### 2.2.9 Продвинутые вопросы

**В: Как найти и устранить взрыв кардинальности?**
О: Обнаружить: `prometheus_tsdb_head_series` (тренд), `topk(10, count by (__name__)({__name__=~".+"}))` (какая метрика), `count(count by (label)(metric))` (какая метка). Устранять на трёх уровнях: перестать эмитить в приложении (настоящее решение); дропнуть при приёме через `metric_relabel_configs`; временно снизить ретенцию или шардировать. Профилактика — алерт на число рядов и правила ревью для значений меток.

**В: Как правильно посчитать p99 по 50 инстансам?**
О: `histogram_quantile(0.99, sum(rate(latency_seconds_bucket[5m])) by (le))`. Порядок важен: сначала `rate()` по каждому ряду (учитывает сбросы), затем `sum ... by (le)` для объединения инстансов с сохранением границ корзин, затем квантиль. Усреднять p99 по инстансам нельзя — квантили не линейны. Точность ограничена гранулярностью корзин, поэтому корзины выбирают вокруг порогов SLO.

**В: Prometheus — единая точка отказа. Как сделать HA?**
О: Два одинаковых сервера опрашивают одни и те же цели и шлют в кластер Alertmanager, который дедуплицирует — алертинг становится HA без координации между ними. Для HA запросов и долгого хранения добавляют Thanos или Mimir с дедупликацией на этапе запроса. Философия при этом сохраняется: каждый Prometheus независим и работает на локальном хранилище, чтобы мониторинг пережил отказ всего остального.

**В: Разница между `rate`, `irate` и `increase`?**
О: `rate` — средний прирост в секунду по всем точкам окна, с учётом сбросов, для алертов и большинства графиков. `irate` — мгновенная скорость по **двум последним** точкам: отзывчиво, шумно, только для графиков высокого разрешения, никогда для алертов. `increase` — суммарный прирост за окно, то есть `rate × длительность_окна`.

#### 2.2.10 План изучения

1. Поднять Prometheus + Grafana локально через docker-compose против собственного приложения; самому добавить один счётчик и одну гистограмму.
2. Выучить четыре типа метрик и соглашения об именовании.
3. Серьёзно поработать с PromQL в интерактивном браузере выражений.
4. Написать три алерта с `for:`, намеренно сломать приложение и посмотреть, как они срабатывают.
5. Прочитать документацию по relabeling и хранилищу.
6. Прочитать главы SRE-книги про SLO, бюджеты ошибок и алертинг по скорости сжигания.
7. Расширить на логи и трейсы (Loki + Tempo или OpenTelemetry).
8. Только затем — Thanos/Mimir для масштаба.

---

## 3. Топологическая сортировка, LRU Cache, LFU Cache

### 3.1 Краткий конспект для экзамена

#### Топологическая сортировка
Упорядочивание вершин **направленного ациклического графа (DAG)** так, что для каждого ребра `u → v` вершина `u` идёт раньше `v`. Существует **тогда и только тогда**, когда в графе нет цикла. Решает любую задачу «выполнить в порядке зависимостей»: сборка, менеджеры пакетов, планировщики задач, предварительные курсы, пересчёт формул, выполнение DAG в пайплайнах.

| | **Алгоритм Кана (BFS)** | **На основе DFS** |
|---|---|---|
| Идея | Выдавать вершины с нулевой входящей степенью | DFS, добавление в **пост-порядке**, разворот в конце |
| Структуры | Массив входящих степеней + очередь | Стек/рекурсия + цветовые метки |
| Обнаружение цикла | **Бесплатно**: выдано < V вершин | Обратное ребро в **СЕРУЮ** вершину |
| Сложность | **O(V+E)** время, O(V) память | **O(V+E)** время, O(V) память + глубина рекурсии |
| Когда | Нужны отчёт о цикле и итеративный код | Уже есть DFS, рекурсия естественна |

**Алгоритм Кана в пять строк:** посчитать входящие степени → в очередь все нулевые → извлечь `u`, добавить в результат, уменьшить степени соседей, добавляя достигших нуля → повторять → если выдано меньше V вершин, остаток образует **цикл**.

#### Кеши
| | **LRU** | **LFU** |
|---|---|---|
| Вытесняет | Самый давно **используемый** | Самый **редко** используемый |
| Ставка на | **Временну́ю локальность** | **Популярность** |
| Структуры | Хеш-таблица + **двусвязный список** | Хеш-таблица + карта частот + **корзины** + `min_freq` |
| Сложность | O(1) get/put | O(1) get/put |
| Слабость | Один большой скан вымывает кеш | **Устаревшая популярность**: старый горячий ключ не уходит никогда |
| Когда | Всплесковый доступ по свежести (большинство нагрузок) | Стабильное «горячее ядро», долгоживущие кеши |

**LRU одним дыханием:** хеш-таблица даёт O(1) поиск **узла**, двусвязный список с фиктивными узлами-часовыми хранит порядок использования — самый свежий сразу за головой, самый старый перед хвостом. `get` выдёргивает узел и вставляет за голову (несколько записей указателей, без сканирования). `put` при переполнении удаляет `tail.prev`. Всё O(1), потому что таблица избавляет от поиска по списку, а двусвязность позволяет удалять из середины за O(1).

**LFU одним дыханием:** три структуры — `ключ → значение`, `ключ → частота`, `частота → упорядоченное множество ключей` — плюс указатель `min_freq`. При обращении ключ переезжает из корзины *f* в *f+1*; если корзина опустела и `f == min_freq`, минимум увеличивается на единицу. Вытесняется **самый старый** ключ из корзины `min_freq` — то есть LFU с **разрешением ничьих по LRU**. Всё O(1), потому что частота растёт строго по одному.

#### Типичные вопросы
| Вопрос | Ответ |
|---|---|
| Почему список **двусвязный**? | Чтобы удалить узел за O(1), нужен доступ к предыдущему; в односвязном пришлось бы искать за O(n). |
| Зачем фиктивные head/tail? | Они убирают проверки на «первый/последний» при вставке и удалении — код короче и надёжнее. |
| Почему `OrderedDict` / `LinkedHashMap` достаточно? | Внутри это и есть хеш-таблица + двусвязный список с порядком доступа. |
| Как LFU держит O(1) при вытеснении? | `min_freq` указывает на низшую непустую корзину; из неё за O(1) достаётся самый старый ключ. Корректно, потому что частота растёт ровно на 1. |
| Что ломает LFU на практике? | Устаревшая популярность: вчерашний горячий ключ навсегда сохраняет огромный счётчик. Лечится старением/затуханием счётчиков или W-TinyLFU. |
| Уникален ли топологический порядок? | Только если в DAG есть гамильтонов путь; иначе валидных порядков много. |

#### Типичные ошибки
1. Односвязный список в LRU — и обнаружение, что удаление стало O(n).
2. Забыть, что **`put` существующего ключа — это использование** (нужно обновить свежесть/частоту).
3. LFU: не обновить `min_freq` при опустошении корзины → неверные вытеснения.
4. LFU без разрешения ничьих → недетерминированное и обычно худшее поведение.
5. Топологическая сортировка без обработки цикла — молча выдаётся частичный порядок.
6. Игнорирование потокобезопасности: учебные реализации **не** потокобезопасны.

#### «Идеальный ответ»
> Топологическая сортировка упорядочивает DAG так, что каждая зависимость идёт раньше зависящих. Я использую **алгоритм Кана**: считаю входящие степени, начинаю с вершин с нулевой степенью, и каждый раз при выдаче вершины уменьшаю степени соседей, выдавая их при достижении нуля. Это O(V+E) и бесплатно обнаруживает циклы — если выдано меньше вершин, чем есть, остаток образует цикл. Я выбрал его вместо DFS именно потому, что отчёт о цикле получается естественно, а код итеративный. Для кешей: LRU это хеш-таблица плюс двусвязный список с часовыми — таблица находит узел за O(1), список переупорядочивает или вытесняет за O(1) без сканирования. LFU добавляет карту частот и корзины ключей по частотам с указателем `min_freq`, что даёт O(1) вытеснение с разрешением ничьих по LRU. LRU ставит на свежесть, LFU на популярность; LRU — лучший дефолт для всплесковых нагрузок, поэтому мой кеш ответов LLM использует LRU, а LFU выиграл бы, если бы несколько общих ключей доминировали у многих арендаторов.

---

### 3.2 Полный учебный отчёт

#### 3.2.1 Топологическая сортировка

##### Задача и DAG
Дан набор задач с ограничениями «X раньше Y» — построить корректный порядок выполнения или доказать, что его нет.

```
Корректный DAG                      Не DAG (порядка не существует)
    A ──► B ──► D                        A ──► B
    │           ▲                        ▲     │
    └───► C ────┘                        └─────┘
Порядки: A,B,C,D или A,C,B,D
```
**Теорема:** топологический порядок существует **тогда и только тогда**, когда граф ацикличен. Интуиция: в цикле каждая вершина должна была бы предшествовать самой себе.

##### Алгоритм Кана

```python
from collections import deque

def kahn_topological_sort(vertices, edges):
    """edges: список пар (u, v) — u должна идти раньше v."""
    adjacency = {v: [] for v in vertices}
    in_degree = {v: 0 for v in vertices}
    for u, v in edges:
        adjacency[u].append(v)
        in_degree[v] += 1

    ready = deque(v for v in vertices if in_degree[v] == 0)
    order = []
    while ready:
        u = ready.popleft()
        order.append(u)
        for v in adjacency[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                ready.append(v)

    if len(order) < len(vertices):
        raise ValueError("обнаружен цикл")
    return order
```

Трассировка для `A→B`, `A→C`, `B→D`, `C→D`:

| Шаг | Очередь | Выдано | Степени после |
|---|---|---|---|
| старт | [A] | [] | A:0 B:1 C:1 D:2 |
| извлечь A | [B, C] | [A] | B:0 C:0 D:2 |
| извлечь B | [C] | [A,B] | C:0 D:1 |
| извлечь C | [D] | [A,B,C] | D:0 |
| извлечь D | [] | [A,B,C,D] | — |

**Детерминизм:** заменив FIFO-очередь на кучу-минимум (или сортируя готовые вершины по устойчивому ключу), получаем воспроизводимый канонический порядок. *В этом репозитории готовые вершины сортируются по исходному порядку файлов, поэтому результат не меняется между запусками — это важно, так как он попадает в промпты LLM, кешируемые по хешу.*

##### Вариант на DFS

```python
WHITE, GRAY, BLACK = 0, 1, 2   # не посещена, в обработке, завершена

def dfs_topological_sort(vertices, adjacency):
    color = {v: WHITE for v in vertices}
    postorder = []

    def visit(u):
        color[u] = GRAY
        for v in adjacency[u]:
            if color[v] == GRAY:
                raise ValueError(f"цикл на ребре {u} -> {v}")
            if color[v] == WHITE:
                visit(v)
        color[u] = BLACK
        postorder.append(u)          # добавляем ПОСЛЕ всех потомков

    for v in vertices:
        if color[v] == WHITE:
            visit(v)
    return postorder[::-1]           # обратный пост-порядок
```
**Почему работает:** вершина добавляется только после всех достижимых из неё, поэтому в пост-порядке она стоит **после** своих зависимых; разворот ставит её **перед** ними. **Три цвета — ключевая деталь:** ребро в СЕРУЮ вершину — обратное ребро, то есть цикл; ребро в ЧЁРНУЮ безопасно.

##### Сложность и обнаружение циклов
| Алгоритм | Время | Память | Замечание |
|---|---|---|---|
| Кана | **O(V + E)** | O(V) | Итеративный, без ограничения глубины |
| DFS (рекурсивный) | **O(V + E)** | O(V) + глубина рекурсии | Риск переполнения стека на глубоких графах |

| Метод обнаружения | Как | Бонус |
|---|---|---|
| Счётчик Кана | Выдано < V | Даёт **множество** участников, не сам путь |
| Цвета DFS | Ребро в СЕРУЮ | Стек рекурсии **и есть** путь цикла — лучшие сообщения об ошибке |
| Tarjan (SCC) | Компонента размера > 1 | Перечисление **всех** циклов, тоже O(V+E) |

##### Краевые случаи
| Случай | Правильное поведение |
|---|---|
| Пустой граф | Вернуть `[]` |
| Нет рёбер | Любая перестановка валидна |
| Несвязные компоненты | Обрабатываются естественно |
| **Петля** `v → v` | Цикл: степень никогда не станет нулевой; в DFS вершина СЕРАЯ |
| **Дублирующиеся рёбра** | Завышают входящую степень → **алгоритм зависает**. Нужна дедупликация |
| Вершина только как цель | Должна быть в множестве вершин |

**Ловушка дублирующихся рёбер реальна:** наивное `in_degree[v] += 1` при повторном обнаружении того же ребра (например, модуль импортирован в двух строках) навсегда мешает вершине достичь нуля — она молча исчезает из результата и выглядит как фантомный «цикл». *Реализация в этом репозитории проверяет принадлежность множеству зависимых перед инкрементом.*

##### Пример из этого проекта
```
PR меняет: service.py (импортирует models), models.py, unrelated.py

Граф строится только по изменённым файлам:
    models.py ──► service.py        unrelated.py (изолирован)

Степени: models=0, service=1, unrelated=0
Готовы (в исходном порядке): [models.py, unrelated.py]
Результат: models.py, unrelated.py, service.py
```
Два осознанных решения: **граф охватывает только изменённые файлы** (внешние импорты не влияют на порядок обработки, граф остаётся крошечным), и **цикл не прерывает работу** — циклические файлы сохраняют исходный порядок и попадают в отчёт, потому что цикл импортов это запах кода в *анализируемом* проекте, а не повод отказаться генерировать тесты.

##### Смежные алгоритмы
**Самый длинный путь в DAG** решается за O(V+E) релаксацией рёбер в топологическом порядке (в общем графе NP-трудно) — это основа анализа **критического пути**. **Кратчайший путь в DAG** тем же приёмом работает даже с отрицательными весами. **Параллельное планирование:** вершины одного «уровня» выполняются одновременно, число итераций Кана равно длине критического пути.

#### 3.2.2 Основы кеширования

```
Регистры    <1 нс
L1/L2/L3    1–40 нс
RAM         ~100 нс
SSD         ~16 мкс
Сеть        ~500 мкс – 150 мс
Удалённая БД / вызов LLM: миллисекунды–секунды
```
Кеш меняет **память на задержку** (а также на нагрузку источника и часто на деньги — как в случае вызовов LLM). Он оправдан при **перекошенном** распределении обращений (Zipf), что на практике встречается почти всегда.

```
hit_ratio = попадания / (попадания + промахи)
средняя_задержка = hit_ratio × стоимость_попадания + (1 − hit_ratio) × стоимость_промаха
```
Асимметрия важна: рост хитрейта с 50% до 75% **вдвое** сокращает число дорогих обращений к источнику.

| Политика | Правило | Плюсы | Минусы |
|---|---|---|---|
| **FIFO** | Уходит вставленный раньше всех | Тривиально | Игнорирует использование |
| **LRU** | Уходит давно не используемый | Отлично при временной локальности, O(1) | Вымывается одним большим сканом |
| **LFU** | Уходит редко используемый | Защищает горячее ядро | Устаревшая история, медленная адаптация |
| **Random** | Случайная жертва | O(1), без метаданных | Не учитывает нагрузку |
| **CLOCK** | Приближение LRU по биту обращения | Дёшево, применяется в ОС | Приближённо |
| **ARC** | Адаптируется между свежестью и частотой | Самонастройка | Сложнее, патентная история |
| **TinyLFU / W-TinyLFU** | Вероятностный счётчик допускает только достойных | **Лучшие хитрейты**, устойчив к сканам | Сложнее; применяется в Caffeine |

**Оптимальный алгоритм Белади (OPT)** вытесняет то, что понадобится позже всего в будущем: нереализуем, но служит теоретической верхней границей для сравнения политик.

#### 3.2.3 Внутреннее устройство LRU

| Требование | Структура |
|---|---|
| O(1) поиск по ключу | **Хеш-таблица** `ключ → узел` |
| O(1) удаление произвольного узла | **Двусвязный** список (нужен `prev`) |
| O(1) выбор жертвы | Хвост списка |
| O(1) отметка «только что использован» | Перенос в голову |

```
       ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
head ──│ ЧАСОВОЙ│◄─►│  K:C   │◄─►│  K:B   │◄─►│  K:A   │◄─►│ ЧАСОВОЙ│── tail
       └────────┘   └────────┘   └────────┘   └────────┘   └────────┘
                    самый свежий              самый старый
                                              ▲ отсюда вытесняем
```
**Часовые** (фиктивные узлы) гарантируют, что у каждого реального узла всегда есть `prev` и `next` — исчезают все проверки «а это первый/последний?».

```python
def get(self, key):
    node = self._nodes.get(key)
    if node is None:
        self.misses += 1
        return None
    self.hits += 1
    self._unlink(node)
    self._link_after_head(node)        # обновляем свежесть
    return node.value

def put(self, key, value):
    node = self._nodes.get(key)
    if node is not None:               # обновление считается использованием
        node.value = value
        self._unlink(node); self._link_after_head(node)
        return
    if len(self._nodes) >= self.capacity:
        victim = self._tail.prev       # самый давний
        self._unlink(victim)
        del self._nodes[victim.key]
    node = Node(key, value)
    self._nodes[key] = node
    self._link_after_head(node)

def _unlink(self, node):               # O(1) — нужен prev, отсюда двусвязность
    node.prev.next = node.next
    node.next.prev = node.prev
```

Трассировка (ёмкость 2):

| Операция | Состояние (свежий → старый) | Результат |
|---|---|---|
| `put(A,1)` | A | — |
| `put(B,2)` | B, A | — |
| `get(A)` | **A, B** | 1 (A обновлён) |
| `put(C,3)` | C, A | вытесняет **B** |
| `get(B)` | C, A | `None` |

Четвёртая строка — самое проверяемое на собеседованиях поведение: **`get` обязан переупорядочивать**, иначе получился FIFO.

**Практика:** в Python `collections.OrderedDict` с `move_to_end()` **и есть** хеш-таблица + двусвязный список; в Java `LinkedHashMap(cap, lf, accessOrder=true)` с переопределённым `removeEldestEntry()` — LRU в пять строк. **Redis не реализует точный LRU**: он сэмплирует несколько случайных ключей (`maxmemory-samples`, по умолчанию 5) и вытесняет лучшего кандидата — приближение, позволяющее не вести список на каждый ключ. *Отличный тезис для экзамена: на масштабе точные политики заменяют сэмплированными приближениями, потому что учёт метаданных дороже выигрыша в хитрейте.*

**Потокобезопасность:** учебные реализации небезопасны. Варианты — общий мьютекс (просто, но высокая конкуренция), полосатые/шардированные блокировки (типовое решение), либо подход Caffeine: неблокирующая хеш-таблица плюс буферы чтений, асинхронно проигрываемые в структуры политики.

#### 3.2.4 Внутреннее устройство LFU

Наивный вариант со сканированием минимума — O(n) на вытеснение; куча даёт O(log n). **Схема за O(1)** (Shah, Mitra, Matani, 2010) использует корзины.

```
min_freq = 1
                       ▼
корзины:  частота 1 → [ D , E ]     ← D самый старый здесь → вытесняется первым
          частота 2 → [ B ]
          частота 5 → [ A , C ]
```

**Ключевая идея для O(1):** частота растёт **строго на единицу**. Поэтому переезд из корзины *f* в *f+1* — O(1); если корзина `min_freq` опустела из-за повышения последнего ключа, новый минимум может быть только `min_freq + 1`; при вставке новый ключ имеет частоту 1, значит `min_freq` сбрасывается в 1. Поиск не нужен нигде.

```python
def _increment_frequency(self, key):
    f = self._frequencies[key]
    bucket = self._keys_by_frequency[f]
    del bucket[key]
    if not bucket:
        del self._keys_by_frequency[f]
        if self._min_frequency == f:
            self._min_frequency = f + 1     # единственно возможный новый минимум
    self._frequencies[key] = f + 1
    self._keys_by_frequency.setdefault(f + 1, OrderedDict())[key] = None

def put(self, key, value):
    if key in self._values:
        self._values[key] = value
        self._increment_frequency(key)
        return
    if len(self._values) >= self.capacity:
        bucket = self._keys_by_frequency[self._min_frequency]
        evicted, _ = bucket.popitem(last=False)   # самый старый = ничья по LRU
        del self._values[evicted]; del self._frequencies[evicted]
    self._values[key] = value
    self._frequencies[key] = 1
    self._keys_by_frequency.setdefault(1, OrderedDict())[key] = None
    self._min_frequency = 1                       # новый ключ всегда минимум
```

Трассировка (ёмкость 2):

| Операция | Значения | Частоты | Корзины | min_freq | Результат |
|---|---|---|---|---|---|
| `put(A,1)` | A | A:1 | 1→[A] | 1 | — |
| `put(B,2)` | A,B | A:1 B:1 | 1→[A,B] | 1 | — |
| `get(A)` | A,B | A:2 B:1 | 1→[B], 2→[A] | 1 | 1 |
| `put(C,3)` | A,C | A:2 C:1 | 1→[C], 2→[A] | 1 | вытесняет **B** |

Если бы `get(A)` не было, A и B стояли бы на частоте 1 и вытеснился бы **A** как более старый — LFU вырождается в LRU.

**Краевые случаи:** все ключи с одинаковой частотой → поведение LRU; `put` существующего ключа обновляет значение **и** частоту; при опустошении корзины `min_freq` увеличивается **только если** она была минимальной; после вытеснения и вставки `min_freq` обязан сброситься в 1 — забыть это *классический* баг LFU.

**Проблема устаревшей популярности:** ключ, использованный миллион раз на прошлой неделе, навсегда сохраняет счётчик и не вытесняется, даже если он мёртв. Средства: **старение/затухание** (периодически делить счётчики пополам; Redis использует логарифмический счётчик с периодом затухания), **оконный подсчёт**, **TinyLFU / W-TinyLFU** — вероятностный счётчик (Count-Min Sketch) с периодическим сбросом плюс небольшое LRU-окно допуска. Именно так **Caffeine** достигает почти оптимальных хитрейтов при умеренной памяти.

#### 3.2.5 LRU против LFU

| Критерий | LRU | LFU |
|---|---|---|
| Основание вытеснения | Свежесть | Частота (+ ничья по свежести) |
| Структуры | Таблица + двусвязный список | Таблица + частоты + корзины + `min_freq` |
| Накладные расходы памяти | Ниже | Выше |
| Сложность реализации | Низкая | Средняя |
| Адаптация к смене нагрузки | **Быстрая** | **Медленная** |
| Устойчивость к сканам | **Нет** | **Да** |
| Типичный хитрейт | Хороший | Часто выше *при стабильном ядре* |

**Выбор:** LRU — всплесковый доступ по свежести, короткоживущие кеши, меняющееся рабочее множество, приоритет простоты (это большинство нагрузок). LFU — стабильно перекошенная популярность, долгоживущие кеши, дорогие промахи (CDN, общие многоарендные кеши). **Современный ответ:** ни то, ни другое в чистом виде — **W-TinyLFU** (Caffeine) или **ARC** адаптируются сами и превосходят обе политики в большинстве бенчмарков.

##### Разбор решения в этом репозитории
Ассистент кеширует ответы LLM по ключу `SHA-256(модель, температура, системная инструкция, промпт)` и использует **LRU**, имея LFU как протестированную, но не подключённую альтернативу. Обоснование, которое хорошо обобщается: доступ **всплесковый** (разработчик несколько раз за час пушит одну ветку → повторяются те же промпты → сильная временная локальность → LRU); LFU выиграл бы при одном воркере на много репозиториев, где несколько общих модулей встречаются в большинстве PR; подключать LFU без нагрузки, где он выигрывает, было бы **спекулятивным усложнением**. Оба кеша отдают счётчики `hits`/`misses` в Prometheus, поэтому выбор **измерим**: четыре одинаковых задания дали 3 вызова LLM, 9 попаданий и 3 промаха (75% хитрейта).

**Поучительный баг оттуда же:** изначально кеш не срабатывал между заданиями. Причина — в промпты попадал абсолютный путь временного каталога клона, который у каждого задания свой, поэтому байт-идентичная работа давала разные ключи SHA-256. **Урок: ключ кеша строится только из *нормализованных* входных данных; любая случайная изменчивость входа молча обнуляет хитрейт, и при этом ничего не падает.** Теперь стабильность промптов зафиксирована регрессионным тестом.

#### 3.2.6 Продвинутые вопросы

**В: Спроектируйте LRU-кеш с поддержкой TTL.**
О: Сохраняем таблицу + двусвязный список, добавляем в узел метку истечения. В `get` просроченный узел удаляется и засчитывается промах (**ленивое истечение**). Дополнительно — минимальная куча по времени истечения или timing wheel плюс фоновый сборщик (**активное истечение**), чтобы память освобождалась и для ключей, которые больше никто не читает. Тонкость: при только ленивом истечении мёртвые записи занимают ёмкость и вытесняют живые.

**В: Как сделать LRU потокобезопасным с хорошей конкурентностью?**
О: Простой ответ — один мьютекс; корректно, но конкуренция высока, поскольку **чтения мутируют список**. Лучше — **шардирование блокировок** по `hash(key) % N` с независимым кешем в каждом шарде. Лучшее в классе (подход Caffeine): неблокирующая хеш-таблица, чтения записываются в кольцевые буферы по потокам и асинхронно проигрываются в структуры политики под одной блокировкой — чтения не блокируются ценой слегка приближённого порядка вытеснения.

**В: Нагрузка LFU меняет популярность еженедельно. Что сломается?**
О: Устаревшие счётчики: прошлонедельные горячие ключи станут практически невытесняемыми, кеш перестанет адаптироваться, хитрейт деградирует. Лечение по возрастанию сложности: периодическое глобальное затухание (делить счётчики пополам каждые N операций); оконный подсчёт; переход на **W-TinyLFU**. Обязательно добавить метрику хитрейта во времени, чтобы затухание было видно.

**В: Когда топологической сортировки недостаточно для планирования?**
О: Когда у задач есть длительности и ограниченное число исполнителей. Топологический порядок даёт *корректную* последовательность, но не *оптимальное* расписание — для этого считают **критический путь** (самый длинный путь в DAG, вычисляемый в топологическом порядке) и применяют list scheduling; оптимальное многопроцессорное планирование в общем случае NP-трудно. Также недостаточно при условных рёбрах и графах, меняющихся во время выполнения.

**В: Почему Redis использует *приближённый* LRU?**
О: Точная структура требует хранения указателей на каждый ключ и мутации общего списка **при каждом чтении** — это память (два указателя на миллионы ключей) и узкое место конкурентности. Redis вместо этого сэмплирует несколько случайных ключей и вытесняет лучшего кандидата; при выборке 5–10 результат очень близок к настоящему LRU за долю стоимости. Классический инженерный размен: отказ от незаметной пользователю точности ради заметных памяти и пропускной способности.

#### 3.2.7 План изучения

1. **Реализовать обе топологические сортировки с нуля**, включая *отчёт* о цикле, а не только его обнаружение.
2. Решить классику: LeetCode 207/210 (Course Schedule), 269 (Alien Dictionary), 146 (LRU), 460 (LFU) — без подсказок.
3. Прочитать главу 22 CLRS (элементарные алгоритмы на графах) ради классификации рёбер в DFS.
4. **Инструментировать реальный кеш** — добавить счётчики попаданий и промахов и построить график хитрейта.
5. Изучить продакшен-реализацию: заметки о дизайне [Caffeine](https://github.com/ben-manes/caffeine) про W-TinyLFU, `evict.c` в Redis.
6. Сравнить политики на реальной трассе (LRU vs LFU vs random) — результаты часто контринтуитивны.
7. Перейти к распределённому кешированию: консистентное хеширование, защита от stampede, стратегии инвалидации.

---

# Final Materials / Итоговые материалы

## Final comparison table / Итоговая сравнительная таблица

| Dimension | Distributed Systems | Prometheus / Grafana | Topological Sort | LRU | LFU |
|---|---|---|---|---|---|
| **Core problem** | Scale, availability, geography | See what the system is doing | Dependency ordering | Limited fast memory | Limited fast memory |
| **Key insight** | The network fails; design for partial failure | Metrics are cheap and aggregatable; labels define identity | Order exists iff acyclic | Recency predicts reuse | Frequency predicts value |
| **Main structure** | Services + queues + replicated stores | TSDB + label sets + PromQL | In-degree array + queue (Kahn) | Hash map + doubly linked list | Maps + frequency buckets + `min_freq` |
| **Complexity** | — | O(1) per sample ingest; query varies | O(V + E) | O(1) get/put | O(1) get/put |
| **Main failure mode** | Cascading failure, retry storm | Cardinality explosion | Undetected cycle / duplicate edges | Scan pollution | Stale popularity |
| **Standard fix** | Timeouts, backoff+jitter, idempotency, DLQ | Bounded labels, relabel drops | Count check / colour marks | Switch to LFU/ARC/W-TinyLFU | Frequency decay, W-TinyLFU |
| **Killer question** | State CAP precisely | Why `rate()` on counters? | Why does Kahn detect cycles free? | Why *doubly* linked? | Why is eviction O(1)? |
| **In this repo** | Cloud Run + Pub/Sub + DLQ + GCS idempotency | Worker `/metrics`, dashboards as code | `import_graph.py` | `cache.py` (wired) | `cache.py` (implemented, unwired) |

## Consolidated glossary / Сводный глоссарий

| Term / Термин | EN | RU |
|---|---|---|
| **Availability** | Fraction of time the system serves correctly | Доля времени корректной работы |
| **Backpressure** | Signalling upstream to slow down | Сигнал «замедлись» вверх по потоку |
| **CAP** | During a partition: choose C or A | При разделении: выбор C или A |
| **Cardinality** | Number of unique time series | Число уникальных временных рядов |
| **Circuit breaker** | Fail-fast wrapper around a failing dependency | Быстрый отказ при сбоящей зависимости |
| **DAG** | Directed acyclic graph | Направленный ациклический граф |
| **DLQ** | Dead-letter queue for undeliverable messages | Очередь недоставленных сообщений |
| **Eventual consistency** | Replicas converge once writes stop | Реплики сходятся после прекращения записей |
| **Exporter** | Adapter exposing third-party metrics | Адаптер метрик стороннего софта |
| **Histogram** | Bucketed distribution; server-side quantiles | Распределение по корзинам, квантили на сервере |
| **Idempotency** | Repeating an operation changes nothing further | Повтор операции ничего не меняет |
| **Kahn's algorithm** | BFS-style topological sort via in-degrees | Топологическая сортировка по входящим степеням |
| **LRU / LFU** | Least Recently / Frequently Used eviction | Вытеснение по давности / по частоте |
| **PACELC** | If P: A or C; Else: Latency or Consistency | Если P: A или C; иначе: задержка или согласованность |
| **PromQL** | Prometheus Query Language | Язык запросов Prometheus |
| **Quorum** | W + R > N ensures overlap | W + R > N гарантирует пересечение |
| **Saga** | Local transactions + compensations | Локальные транзакции + компенсации |
| **Sentinel node** | Dummy node removing edge cases | Фиктивный узел, убирающий краевые случаи |
| **Sharding** | Different data on different nodes | Разные данные на разных узлах |
| **SLI / SLO** | Measured indicator / target | Измеряемый индикатор / целевое значение |
| **Thundering herd** | Simultaneous client stampede | Одновременный наплыв клиентов |
| **W-TinyLFU** | Sketch-based admission policy | Политика допуска на вероятностном счётчике |

## Likely examiner questions with strong answers / Вероятные вопросы экзаменатора

**1. "Explain CAP and why 'pick 2 of 3' is wrong."**
Partition tolerance is not optional in any system communicating over a real network — packets will be lost. So the genuine choice appears only *during* a partition: keep answering with possibly-stale data (AP), or refuse to answer to preserve correctness (CP). PACELC completes the picture: even with no partition, you trade latency against consistency on every replicated read.

**2. "Your consumer processed a message twice. Whose bug is it?"**
Nobody's — at-least-once delivery is the contract, and duplicates are guaranteed by physics, not by a defect. The bug is that the consumer isn't idempotent. Fix it with a dedup key: a natural key derived from content, an idempotency key from the producer, or a conditional write. In my system the dedup marker is the artifact object in Cloud Storage keyed by repo/PR/commit SHA.

**3. "Why does Prometheus pull instead of push?"**
Three reasons. Prometheus controls the sampling rate, so a misbehaving target can't flood it. Target liveness is detectable for free — the auto-generated `up` metric is 0 when a scrape fails, whereas with push you can't distinguish "healthy but quiet" from "dead". And targets need no monitoring configuration at all. The exception is short-lived batch jobs that exit before any scrape, which is exactly what Pushgateway exists for.

**4. "How do you compute p99 latency across many instances?"**
`histogram_quantile(0.99, sum(rate(latency_seconds_bucket[5m])) by (le))`. `rate()` first to handle counter resets per series, then sum the buckets across instances while keeping the `le` label, then compute the quantile. You cannot average per-instance p99s — quantiles aren't linear. That's also why you use a Histogram rather than a Summary: Summary computes quantiles client-side and they can't be aggregated at all.

**5. "Why is Kahn's algorithm O(V+E), and how does it detect cycles?"**
Each vertex enters and leaves the queue exactly once, and each edge is relaxed exactly once when its source is emitted — so the work is linear in vertices plus edges. Cycle detection is free: a vertex inside a cycle always has at least one unprocessed predecessor, so its in-degree never reaches zero and it never enters the queue. If the emitted count is less than the vertex count, the remainder contains every cycle.

**6. "Walk me through why LRU is O(1)."**
Two structures cover complementary weaknesses. The hash map gives O(1) lookup but has no order. The doubly linked list gives O(1) insertion and removal at any position but no lookup. Combined: the map hands you the node directly, so you never scan the list; the list's `prev` pointer lets you unlink that node in two pointer writes; the tail sentinel's predecessor is always the eviction victim. Sentinel head and tail nodes remove every boundary check.

**7. "You have 30 seconds: sell me event-driven architecture, then argue against it."**
For: it decouples producers from consumers in time, so a burst queues instead of cascading; components fail and restart without losing work; new consumers can be added without touching the producer. Against: you lose the straight-line call stack, so debugging requires distributed tracing and correlation IDs; you inherit duplicate delivery and must make every consumer idempotent; ordering guarantees weaken as you parallelise; and eventual consistency becomes visible to users. It's the right choice when work is asynchronous by nature, and the wrong one when a user is waiting for the answer.

**8. "What did you actually build, and what did you learn?"**
An AI unit-test assistant: a GitHub webhook hits a public Cloud Run receiver that verifies an HMAC signature and publishes to Pub/Sub; a private Cloud Run worker consumes push deliveries, clones the PR, orders changed files with Kahn's algorithm so imported modules are analysed first, calls Gemini through an LRU response cache, runs pytest with a repair loop, and uploads artifacts to Cloud Storage — which doubles as the idempotency marker. Prometheus metrics feed a provisioned Grafana dashboard. Two lessons stand out. First, a cache key must be built from normalised inputs: mine silently never hit because absolute clone paths leaked into the prompts, and nothing crashed to tell me — only the metric did. Second, dead-lettering isn't theoretical: a malformed environment variable broke every clone, and watching messages retry five times and land in the DLQ was the best possible proof the failure path worked.

## 7-day study plan / План на 7 дней

| Day | Focus | Do (practical) | Read / Review | Self-test |
|---|---|---|---|---|
| **1** | Distributed fundamentals | Draw your system's architecture from memory; mark every network hop and what happens if it fails | Latency numbers, availability math, CAP/PACELC, consistency models | Recite CAP precisely; compute availability of 3 chained 99.9% services |
| **2** | Reliability patterns | Add a timeout, retry-with-jitter and circuit breaker to a real client; force a failure and watch it | Retries, idempotency, backpressure, queues vs logs, delivery guarantees | Explain why exactly-once delivery is impossible in 60 seconds |
| **3** | Microservices & events | Trace one request end-to-end across your services; write the message contract for one event | Boundaries, gateway, discovery, sync vs async, DLQ, schema evolution | Argue both for and against extracting a service from a monolith |
| **4** | Serverless & cloud comparison | Deploy one container to Cloud Run (or Lambda); measure the cold start yourself | FaaS vs containers, cold starts, pricing, the AWS/GCP/Azure mapping table | Reproduce the service-mapping table from memory; name each IAM model |
| **5** | Prometheus | Instrument one counter + one histogram; write 5 PromQL queries; break the app and watch an alert fire | Metric types, cardinality, `rate` vs `irate` vs `increase`, Alertmanager roles | Write the p99-across-instances query with no notes |
| **6** | Grafana + algorithms (topo sort) | Build a 4-panel dashboard, provisioned from a file; implement Kahn's + DFS sort from scratch | Panels, variables, provisioning; DAGs, cycle detection, complexity | Explain why reverse post-order works; handle the duplicate-edge trap |
| **7** | Caches + full rehearsal | Implement LRU and LFU from memory; add hit/miss counters and graph the ratio | LRU/LFU internals, comparison, W-TinyLFU, Redis approximation | Deliver all three "perfect answers" out loud, timed; answer the 8 examiner questions above |

**Method notes:** (1) Practice **out loud** — the gap between "I understand this" and "I can explain this" is exactly what an oral exam measures. (2) Rebuild the diagrams from a blank page; recognition is not recall. (3) For every topic, prepare one concrete story from your own project — examiners consistently reward specifics over textbook phrasing. (4) On day 7, deliberately answer a question you *can't* fully answer and practise saying "that depends on the implementation — in Prometheus it works like X, and I'd verify Y in the docs." Calibrated uncertainty scores better than confident error.

---

## Sources

- [Prometheus — Overview](https://prometheus.io/docs/introduction/overview/) — architecture, scraping model, local storage design
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) — deduplication, grouping, routing
- [Prometheus — Alerting overview](https://prometheus.io/docs/alerting/latest/overview/)
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/) — scrape configs, relabeling
- [AWS vs Azure vs GCP Service Mapping (2026)](https://cloudjobs.io/insights/articles/aws-vs-azure-vs-gcp-comparison-2026) — service equivalence
- [Comparing AWS, Azure, and GCP (DigitalOcean, 2026)](https://www.digitalocean.com/resources/articles/comparing-aws-azure-gcp) — platform strengths
- [Caffeine cache design notes](https://github.com/ben-manes/caffeine) — W-TinyLFU admission policy

Core theory (CAP/PACELC, consistency models, replication, sagas, cache internals, graph algorithms) is standard engineering knowledge, drawn from the canonical literature listed in the learning paths — principally Kleppmann's *Designing Data-Intensive Applications*, Google's *SRE Book*, CLRS, and the original O(1) LFU paper (Shah, Mitra, Matani, 2010). **Cloud service names, quotas, limits, and pricing change frequently — verify against provider documentation before relying on them.**
