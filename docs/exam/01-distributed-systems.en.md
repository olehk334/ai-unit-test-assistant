# Topic 1 — Distributed Systems & Cloud Architecture

---

# PART A — SUMMARY-HINT (spoken answer)

## A1. What a distributed system is, and why we accept the pain

A distributed system is a set of independent computers, connected by an
unreliable network, that cooperate to appear to the user as one coherent
system. Leslie Lamport's definition of the failure mode is the sharpest:
*"A distributed system is one in which the failure of a computer you didn't
even know existed can render your own computer unusable."*

We accept this complexity for four reasons only:

1. **Scale** — the workload no longer fits on one machine (CPU, RAM, disk,
   or network bandwidth).
2. **Availability** — one machine is a single point of failure; redundancy
   requires more than one.
3. **Latency/geography** — users are far away; you must put compute near
   them.
4. **Organisation** — Conway's Law: independent teams want independently
   deployable units.

If none of these applies, a monolith on one big machine is the correct
architecture. Say this out loud in an exam — it demonstrates judgement.

## A2. The constraints you cannot engineer away

**The 8 fallacies of distributed computing** (Deutsch/Gosling): the network
is reliable; latency is zero; bandwidth is infinite; the network is secure;
topology doesn't change; there is one administrator; transport cost is zero;
the network is homogeneous. Every one of these is false, and each false
assumption produces a specific class of outage.

**CAP theorem** (Brewer, proved by Gilbert & Lynch): during a **network
partition (P)** you must choose between **consistency (C — linearizability)**
and **availability (A — every non-failing node answers)**. Partitions are not
optional, so real systems are CP or AP *during a partition*.

**PACELC** is the more useful modern statement: *if* **P**artition, choose
**A** or **C**; **E**lse (normal operation), choose **L**atency or **C**onsistency.
This explains why DynamoDB and Cassandra offer tunable consistency: the
latency/consistency dial exists even when nothing is broken.

**Consistency models**, strongest to weakest:

| Model | Guarantee |
| --- | --- |
| Linearizable (strong) | Operations appear to happen instantly, in real-time order |
| Sequential | All nodes see the same order, not necessarily real time |
| Causal | Causally related operations are seen in order; concurrent ones may differ |
| Eventual | If writes stop, replicas converge — no timing guarantee |

**Session guarantees** are what users actually notice: read-your-writes,
monotonic reads (never go backwards in time), monotonic writes,
writes-follow-reads. "Eventual consistency + read-your-writes" is usually
enough for a UI; pure eventual consistency produces the classic bug of a
user posting a comment and not seeing it.

## A3. Microservices

**Definition.** An architectural style where an application is a suite of
small, independently deployable services, each owning its data, communicating
over the network, organised around business capabilities.

**The one criterion that matters:** split where **requirements conflict** —
different scaling profile, different availability requirement, different
release cadence, different team ownership, different technology need. Do not
split by noun ("UserService", "DataService") and do not split by technical
layer.

**Finding boundaries:** Domain-Driven Design *bounded contexts*; look for
places where the same word means different things ("Order" in Sales vs
Fulfilment). A good boundary has high cohesion inside and a thin, stable
contract outside.

**Communication:**

- **Synchronous** — REST/JSON (universal, human-debuggable), gRPC/protobuf
  (fast, typed, streaming, needs schema management), GraphQL (client-shaped
  queries, mostly at the edge). Cost: temporal coupling — the caller fails if
  the callee is down.
- **Asynchronous** — messages/events over a broker. Cost: eventual
  consistency, harder debugging. Benefit: temporal decoupling, natural
  buffering.

**Supporting patterns:** API Gateway (single entry, auth, rate limiting,
routing), Backend-for-Frontend (per-client gateway), Service Discovery
(DNS/Consul/K8s Services), Service Mesh (sidecar proxies — Envoy under
Istio/Linkerd — providing mTLS, retries, circuit breaking, traffic splitting
and telemetry *without* touching application code), Sidecar, Strangler Fig
(incremental migration off a monolith).

**Data — the hard part.** Database per service is the rule; a shared
database re-couples everything. Consequences:

- **No distributed transactions.** Use the **Saga pattern**: a sequence of
  local transactions, each with a *compensating action*. Two flavours —
  **choreography** (services react to each other's events; decentralised, no
  single point of coordination, but the flow is implicit and hard to trace)
  and **orchestration** (a coordinator drives steps; explicit, testable,
  observable, but the coordinator is a component to own).
- **Dual-write problem.** Writing to your DB *and* publishing an event is
  not atomic. Solve with the **Transactional Outbox**: write the event into
  an `outbox` table in the same transaction, and a relay (poller or CDC tool
  such as Debezium) publishes it. **Change Data Capture** reads the DB log
  directly.
- **Queries spanning services:** API composition (fan-out and join at the
  gateway — simple, but N calls and partial failure) or **CQRS** (maintain a
  read model updated from events — fast reads, eventual consistency).
- **Event Sourcing** (optional, advanced): store the *events* as the source
  of truth, derive state by replay; snapshots keep replay cheap. Gives a
  perfect audit log and time travel; costs schema-evolution pain and query
  difficulty. It is orthogonal to CQRS although often paired.

**Anti-patterns to name:** the **distributed monolith** (services that must
be deployed together — all the cost of distribution, none of the benefit),
shared database, chatty synchronous chains (latency and failure multiply),
nano-services, and starting with microservices before the domain is
understood — *monolith-first* is the mainstream recommendation (Fowler).

## A4. Event-driven architecture

**Command vs Event.** A **command** is an instruction to a specific
recipient, expects to be handled, may be rejected ("CreateOrder"). An
**event** is an immutable statement of fact that already happened, addressed
to nobody in particular ("OrderCreated"). Events invert the dependency:
the producer does not know its consumers.

**Three styles of event** (Fowler):

1. **Event notification** — thin ("order 42 changed"), consumer calls back
   for detail. Low coupling, extra round trip.
2. **Event-carried state transfer** — fat event with the data; consumer needs
   no callback, but data is duplicated and can go stale.
3. **Event sourcing** — events *are* the state.

**Queue vs Topic.** A **queue** delivers each message to exactly one
consumer of a group (work distribution, competing consumers). A **topic /
pub-sub** delivers to every subscription (fan-out). Kafka merges both ideas:
a partitioned append-only log with consumer groups and independent offsets,
where messages are retained regardless of consumption.

**Delivery semantics — the classic question:**

- **At-most-once** — fire and forget; may lose messages.
- **At-least-once** — retry until acknowledged; **duplicates are
  guaranteed** ⇒ consumers must be **idempotent**. This is what almost all
  real systems use (SQS, Pub/Sub, Kafka defaults).
- **Exactly-once** — impossible in general end-to-end (Two Generals
  problem). What exists is **effectively-once**: at-least-once delivery plus
  deduplication/idempotency at the consumer, or transactional semantics
  inside one system (Kafka's exactly-once for consume→process→produce
  within Kafka).

**Idempotency techniques:** natural idempotency (setting a value); an
idempotency key + a dedup store with TTL; conditional writes / compare-and-set;
upsert on a unique business key; a completion marker checked before work
begins.

**Ordering.** Global ordering does not scale. Kafka guarantees order *within
a partition*; Pub/Sub only with an ordering key; SQS FIFO within a message
group. Design so that order is required only per entity (per order ID, per
user ID) and use that as the partition key.

**Operational must-haves:** **Dead Letter Queue** for poison messages after
N attempts; **retry with exponential backoff + jitter**; **backpressure**
(bounded queues, consumer-driven pull, load shedding) so a fast producer
cannot drown a slow consumer; **schema registry + versioning** (add optional
fields, never repurpose a field, tolerate unknown fields) since events are a
public contract; **replay** capability; monitoring of **consumer lag** — the
single most important health metric of an event pipeline.

## A5. Serverless

**Definition.** You deploy code or a container; the platform provisions,
scales (including to zero), patches, and bills per use. It is not "no
servers" — it is "not your servers."

- **FaaS** — function-per-event: AWS Lambda, Azure Functions, Cloud Run
  functions.
- **Serverless containers** — Cloud Run, AWS Fargate/App Runner, Azure
  Container Apps. Same operational model, standard container image, far less
  lock-in. **This is the sweet spot for most teams.**
- **BaaS** — managed backends: DynamoDB, Firestore, S3, Cognito, Auth0.

**Rules you must obey:** stateless (any local disk is scratch); idempotent
(the platform will retry); fast startup; externalised state and config;
execution time and memory limits; concurrency is per instance (Lambda = 1
request per instance, Cloud Run can serve N per instance, which changes how
you think about connection pools and in-process caches).

**Cold starts** — the interview favourite. Causes: allocating a sandbox,
starting the runtime, loading dependencies, running init code, establishing
connections. Typical 100 ms–2 s, worse for JVM/.NET and VPC-attached
functions. Mitigations: provisioned concurrency / minimum instances, smaller
deployment artefacts, lazy imports, lightweight runtimes, connection reuse
across invocations, AWS Lambda SnapStart.

**Choose serverless when:** traffic is spiky or unpredictable, workloads are
event-driven glue, the team is small, time-to-market dominates, or usage is
low (scale-to-zero is free).
**Avoid it when:** sustained high throughput (a reserved VM is cheaper past
a break-even point), long-running or stateful jobs, hard low-latency SLAs
that cold starts would violate, heavy in-memory state, or when the platform
lock-in is unacceptable.

## A6. Scalability patterns (name them, one line each)

**Foundations:** vertical scaling (bigger machine — simple, has a ceiling)
vs **horizontal** (more machines — needs statelessness); **statelessness**
(put session state in Redis/JWT so any instance can serve any request);
**load balancing** (L4 transport vs L7 application; round-robin, least
connections, least response time, power-of-two-choices, consistent hashing
for cache affinity).

**Data scaling:** **replication** — single-leader (simple, read scaling,
replica lag), multi-leader (write availability, conflict resolution: LWW,
version vectors, CRDTs), leaderless/quorum (Dynamo-style, `R + W > N`, read
repair, hinted handoff). **Partitioning/sharding** — by hash (even spread,
no range scans), by range (range scans, hot spots), or directory-based;
**consistent hashing with virtual nodes** so adding a node moves ~1/N of
keys instead of everything. Watch for the **hot shard** (celebrity user)
problem.

**Caching:** CDN/edge → API cache → application cache → database cache. See
Topic 3 for internals and invalidation strategies.

**Traffic shaping:** **queue-based load levelling** (absorb bursts in a
queue, workers consume at their own rate); **competing consumers** (scale
workers horizontally on one queue); **rate limiting** (token bucket = allows
bursts; leaky bucket = smooths; sliding window); **autoscaling** (reactive on
CPU/RPS/queue depth, scheduled, or predictive) — always scale on the metric
that actually saturates, which for queue workers is **backlog**, not CPU.

**Resilience:** **timeouts** everywhere (with deadline propagation);
**retry with exponential backoff and full jitter** — plus a retry budget, or
you build a retry storm; **circuit breaker** (closed → open → half-open) to
stop hammering a dying dependency; **bulkhead** (separate connection/thread
pools per dependency so one saturation cannot sink everything); **graceful
degradation** (serve stale cache or a reduced feature set instead of an
error); **load shedding** (reject cheaply at the edge when overloaded);
**cell-based architecture** (replicate the whole stack into cells to bound
blast radius).

**Delivery safety:** health checks (liveness / readiness / startup), rolling,
blue-green and canary deploys, feature flags, chaos engineering.

**Measurement:** **SLI** (a measured number: p99 latency, success rate),
**SLO** (the target: 99.9 % of requests < 300 ms over 30 days), **SLA** (the
contract with penalties), **error budget** (1 − SLO; when it is spent, stop
shipping features and fix reliability).

## A7. Cloud platforms — the map

| Capability | AWS | GCP | Azure |
| --- | --- | --- | --- |
| VMs | EC2 | Compute Engine | Virtual Machines |
| Managed Kubernetes | EKS | GKE | AKS |
| Serverless containers | Fargate / App Runner | **Cloud Run** | Container Apps |
| FaaS | Lambda | Cloud Run functions | Azure Functions |
| Object storage | S3 | Cloud Storage | Blob Storage |
| Queue | SQS | **Pub/Sub**, Cloud Tasks | Service Bus / Storage Queues |
| Pub-sub / fan-out | SNS | **Pub/Sub** | Service Bus Topics, Event Grid |
| Event streaming | Kinesis, MSK | Pub/Sub, Managed Kafka | Event Hubs |
| Event routing | EventBridge | Eventarc | Event Grid |
| Workflow orchestration | Step Functions | Workflows | Logic Apps, Durable Functions |
| Relational DB | RDS, Aurora | Cloud SQL, AlloyDB, Spanner | Azure SQL |
| NoSQL | DynamoDB | Firestore, Bigtable | Cosmos DB |
| Cache | ElastiCache | Memorystore | Azure Cache for Redis |
| Secrets | Secrets Manager | Secret Manager | Key Vault |
| Identity | IAM | Cloud IAM | Entra ID + RBAC |
| Observability | CloudWatch, X-Ray | Cloud Monitoring, Cloud Trace | Azure Monitor, App Insights |
| Managed Prometheus | Amazon Managed Prometheus | Google Managed Prometheus | Azure Monitor managed Prometheus |
| Container registry | ECR | Artifact Registry | ACR |
| CI/CD | CodePipeline/CodeBuild | Cloud Build | Azure DevOps |
| Keyless CI auth | IAM OIDC | Workload Identity Federation | Workload identity federation |
| Native IaC | CloudFormation, CDK | (Terraform is the norm) | ARM / Bicep |

**Positioning in one line each:** AWS — widest service catalogue, most
mature, most job postings, the safe default. GCP — strongest data/ML and
Kubernetes heritage, cleanest developer experience (Cloud Run is the best
serverless-container product). Azure — enterprise and Microsoft-estate
integration (AD/Entra, .NET, hybrid via Azure Arc).

**Multi-cloud:** usually a bad default — you pay for the lowest common
denominator and double the operational surface. Prefer *portability*
(containers, Terraform, OpenTelemetry, standard protocols) over active
multi-cloud. Watch **data gravity** and **egress costs**.

**Cross-cutting:** Infrastructure as Code (Terraform is the lingua franca;
Pulumi for real languages; CDK/Bicep cloud-native), the **12-factor app**,
least-privilege IAM with workload identity instead of long-lived keys, and
FinOps basics (right-sizing, autoscaling, committed-use discounts, spot
instances, lifecycle policies on storage).

## A8. Rapid-fire Q&A

**Q: Monolith or microservices for a new product?** Modular monolith first.
Split when you feel a specific pain: independent scaling, independent
deployment, or team contention.

**Q: What does CAP actually forbid?** Being simultaneously linearizable and
available *during a partition*. It says nothing about normal operation —
that's what PACELC adds.

**Q: Why is exactly-once delivery impossible?** The Two Generals problem: a
sender cannot distinguish "message lost" from "acknowledgement lost", so it
must either risk loss or risk duplication. Exactly-once *processing* is
achievable by combining at-least-once delivery with idempotency.

**Q: How do you keep data consistent across services?** Sagas with
compensations for the workflow, transactional outbox for reliable publishing,
idempotent consumers, and CQRS read models for queries. Accept eventual
consistency and make it visible in the UX.

**Q: Your queue backlog is growing. What do you do?** Confirm with the
consumer-lag metric; scale consumers horizontally; check for a poison message
blocking a partition; verify the DLQ policy; if the producer is the anomaly,
apply rate limiting or load shedding. Long term: autoscale on backlog, not
CPU.

**Q: When is serverless the wrong choice?** Sustained high load (cost
crossover), latency SLAs incompatible with cold starts, long-running or
stateful processes, and heavy vendor lock-in concerns.

**Q: How do you prevent retry storms?** Exponential backoff with full
jitter, a bounded retry budget, circuit breakers, and never retrying
non-idempotent operations without an idempotency key.

**Q: Consistent hashing — why?** With plain `hash(key) % N`, changing N
remaps nearly every key. Consistent hashing maps both nodes and keys onto a
ring so adding/removing a node moves only ~1/N of keys; virtual nodes even
out the distribution.

**Q: Sync or async between two services?** Sync if the caller needs the
result to answer its own request and the callee is fast and reliable. Async
if the work can complete later, the callee is slow or flaky, or you want the
two to scale and fail independently.

---

# PART B — FULL REPORT

## B1. The physics: what actually breaks

Every distributed-systems pattern is a response to one of four physical
realities.

**1. The network is a partial-failure device.** A local function call has two
outcomes (return or throw). A network call has three: success, failure, and
**timeout** — where you do not know whether the other side did the work.
That third outcome is the origin of idempotency, retries, sagas, and
reconciliation jobs. When you see a pattern, ask "which partial failure does
this handle?"

**2. Latency has a floor.** Light in fibre travels ~200 km/ms; a round trip
New York–London is ~70 ms minimum. No amount of engineering fixes it — only
moving the data (CDN, edge, regional replicas) or removing the round trip
(batching, caching, async).

**3. Clocks disagree.** Wall clocks drift and jump (NTP corrections, leap
seconds); you cannot order events across machines with timestamps. Hence
logical clocks (Lamport timestamps, vector clocks), and Google Spanner's
TrueTime, which uses GPS/atomic clocks to bound the uncertainty and waits it
out — buying real linearizability with hardware.

**4. Consensus is expensive.** Agreeing on a value among unreliable nodes
requires a protocol (Paxos, Raft, Zab) that costs round trips and a majority
quorum. FLP impossibility: no deterministic consensus protocol can guarantee
termination in an asynchronous system with even one faulty process; practical
protocols use timeouts/randomness to sidestep it. **Practical consequence:
never invent consensus. Use it via etcd, ZooKeeper, Consul, Spanner, or a
managed service, and design to need it rarely.**

## B2. Microservices in depth

### Decomposition

The failure mode of microservices is almost always **wrong boundaries**. A
boundary is wrong if a typical feature requires changing three services and
deploying them together.

Practical techniques:

- **Bounded contexts (DDD).** Model the language. If "Customer" means
  something different to Billing and to Support, that is a seam.
- **Event storming.** Put domain events on a wall in time order; clusters of
  events around the same data are candidate services.
- **The two-pizza / cognitive-load test.** A service should be owned and
  fully understood by one small team.
- **Change coupling analysis.** Mine the git history: files that always
  change together belong together.

Start with a **modular monolith** — enforced module boundaries in one
deployable. You get the domain clarity without the network. Extract a module
into a service when it needs its own scaling, availability, cadence, or
owner. This is the Strangler Fig approach when migrating a legacy system:
put a facade in front, redirect one capability at a time, delete the old
code path when traffic reaches zero.

### Contracts and versioning

The network boundary is a **published contract**. Rules:

- Backwards-compatible evolution only: add optional fields; never change the
  meaning or type of an existing field; never remove without a deprecation
  window.
- Consumers must **tolerate unknown fields** (Postel's law, "tolerant
  reader").
- Use **consumer-driven contract tests** (Pact) so a provider learns at
  build time that it broke a consumer.
- Version explicitly when you must break: `/v2/...` or a versioned event
  type, and run both for a migration window.

### Service mesh: what it buys and costs

A mesh puts a proxy (Envoy) beside every service instance. The control plane
(Istio, Linkerd) configures them. You get, without touching application code:
mTLS everywhere, automatic retries/timeouts/circuit breaking, traffic
splitting for canaries, and uniform L7 metrics/traces. You pay: an extra
network hop of latency, memory per sidecar, and a genuinely complex control
plane. **Rule of thumb:** below ~10 services, libraries and an API gateway
are simpler; a mesh earns its keep when uniform policy across many
heterogeneous services becomes the problem. (Ambient/sidecar-less modes
reduce the per-pod cost.)

### Data patterns worked through

**Saga, orchestration flavour** — order fulfilment:

```
Orchestrator: ReserveInventory → ChargePayment → ScheduleShipping
If ChargePayment fails → compensate: ReleaseInventory
If ScheduleShipping fails → compensate: RefundPayment, ReleaseInventory
```

Key insights: compensations are *business* operations (a refund, not a
rollback — the charge really happened); every step must be idempotent
because every step will be retried; the saga state must be persisted, or a
crashed orchestrator forgets in-flight workflows. Managed implementations:
AWS Step Functions, Azure Durable Functions, GCP Workflows, Temporal.

**Transactional outbox** — the fix for the dual-write problem:

```sql
BEGIN;
  INSERT INTO orders (...) VALUES (...);
  INSERT INTO outbox (aggregate_id, type, payload) VALUES (...);
COMMIT;
-- a relay polls outbox (or CDC tails the WAL) and publishes, then marks sent
```

Because both writes are in one local transaction, you can never have an
order without its event or an event without its order. Delivery is
at-least-once (the relay may crash after publishing, before marking) — so
consumers still need idempotency.

**CQRS.** Separate the write model (normalised, validated, transactional)
from one or more read models (denormalised, shaped per query, possibly in a
different store — Elasticsearch for search, Redis for hot lookups). Read
models are updated from events, so they are eventually consistent. Use it
when read and write loads differ radically or when queries would otherwise
force a bad write model. Do not use it by default — it doubles the moving
parts.

## B3. Event-driven architecture in depth

### Broker comparison

| | Kafka | RabbitMQ | SQS | Google Pub/Sub |
| --- | --- | --- | --- | --- |
| Model | Partitioned log | Broker with exchanges/queues | Managed queue | Managed pub-sub |
| Retention | Time/size based, replayable | Until acked | Up to 14 days | 7 days (configurable) |
| Ordering | Per partition | Per queue | FIFO queues only | With ordering key |
| Throughput | Very high | Moderate | High | Very high |
| Best for | Streaming, replay, event sourcing, analytics | Complex routing, RPC-ish workflows | Simple decoupling on AWS | Simple decoupling / fan-out on GCP |

The mental model that matters: **Kafka is a log** (consumers track an offset,
data stays, many independent consumer groups, replay is natural), while
**classic queues are mailboxes** (a message is consumed and gone). Choose a
log when you need replay, multiple independent consumers, or ordered streams;
choose a queue when you need simple work distribution.

### Push vs pull subscriptions

**Pull** — the consumer asks for messages: natural backpressure, consumer
controls its rate, needs a long-running process.
**Push** — the broker POSTs to an HTTP endpoint: works beautifully with
scale-to-zero serverless (no idle consumer to pay for), the platform handles
retries via HTTP status codes, but flow control is the broker's job and your
endpoint must be publicly addressable and authenticated.

This project uses **push** for exactly that reason — the worker is a Cloud
Run service that scales to zero, and Pub/Sub authenticates with an OIDC
token.

### Designing an idempotent consumer

```
on_message(msg):
    key = idempotency_key(msg)            # e.g. repo/PR/commit-SHA
    if store.contains(key):               # already done
        ack(); return
    result = do_work(msg)                 # must be safe to repeat
    store.put(key, result)                # commit marker AFTER work
    ack()
```

Two subtleties: (1) writing the marker **after** the work means a crash in
between causes a safe retry, whereas writing it first risks losing work
entirely; (2) the marker store needs a TTL matched to the maximum possible
redelivery window, or it grows forever.

In this repository the marker is the report object in GCS, and the key is
`repo/PR/head_sha` — a natural business key that needs no extra store.

### Failure taxonomy for an event pipeline

| Failure | Correct response |
| --- | --- |
| Transient (network blip, 503 from a dependency) | Retry with backoff |
| Poison message (malformed, will never succeed) | Acknowledge and route to DLQ/quarantine — never retry forever |
| Slow consumer | Scale out; if impossible, apply backpressure/shed load |
| Duplicate delivery | Idempotent consumer absorbs it |
| Consumer bug shipped | Stop consumers, fix, replay from offset/DLQ |
| Broker unavailable | Producer buffers locally or fails fast; outbox makes this recoverable |

## B4. Serverless in depth

**The billing model drives the architecture.** You pay per invocation and per
GB-second of execution. Therefore: idle costs nothing (great for spiky
work), long waits are pure waste (never sleep or poll inside a function —
use a queue or a workflow engine), and memory size also sets CPU share, so
*increasing* memory often reduces total cost by finishing faster.

**Concurrency models differ and it matters.** Lambda serves one request per
instance — in-process caching is nearly useless, and connection pools are
per-instance, so a spike creates a connection storm on your database
(mitigate with RDS Proxy / PgBouncer). Cloud Run serves many requests per
instance — in-process caches and pools work as usual, but your code must be
thread-safe. Deliberately setting Cloud Run concurrency to 1 (as this
project does) trades efficiency for a dead-simple mental model when work is
CPU-heavy and shells out to subprocesses.

**Cold start anatomy:** sandbox allocation → runtime boot → dependency load
→ your init code → first request. Only the last two are yours to optimise:
trim dependencies, import lazily, defer client construction, keep the image
small. Platform levers: minimum instances / provisioned concurrency (you pay
to keep warmth), and SnapStart on Lambda (snapshot after init, restore in
milliseconds).

**Serverless is not only compute.** The full pattern is compute + managed
queue + managed storage + managed identity. The moment you add a self-managed
VM to the diagram, you have re-acquired all the patching and scaling work you
were trying to avoid.

## B5. Scalability and resilience: mechanics

### Autoscaling on the right signal

Scaling on CPU is a habit, not a principle. For a queue worker, CPU may be
low while the backlog explodes (the bottleneck is an external API). Scale on
what saturates:

| Workload | Scale on |
| --- | --- |
| Web/API | Requests per second, or concurrency |
| Queue worker | Backlog size / consumer lag / oldest-message age |
| Batch | Wall-clock deadline (schedule-based) |
| CPU-bound compute | CPU utilisation (here it is genuinely right) |

Always set a **maximum**: unbounded autoscaling turns a traffic spike into a
bill, or hammers a downstream database into collapse.

### Retry mathematics

Naive retries amplify load exactly when the system is weakest: if every
client retries 3 times, a struggling service sees 4× traffic — the
**retry storm** that converts a brownout into an outage. Correct recipe:

```
delay = random(0, min(cap, base * 2 ** attempt))     # full jitter
```

Full jitter (AWS's recommendation) spreads retries out; without jitter,
clients synchronise into thundering herds. Add a **retry budget** (e.g.
retries may not exceed 10 % of requests) and a **circuit breaker** so a
failing dependency is not retried at all for a cooling-off period.

### Circuit breaker states

- **Closed** — traffic flows; count failures in a rolling window.
- **Open** — threshold exceeded; fail fast immediately (no call at all),
  which protects both you (threads not blocked) and the dependency (no load).
- **Half-open** — after a cooldown, allow a few probe requests; success
  closes it, failure re-opens it with a longer timer.

Combine with a **fallback**: cached data, a default value, or a degraded
feature. "Serve stale but useful" beats "return 500" for most read paths.

### Bulkheads

Named after ship compartments: give each dependency its own resource pool.
Without one, a slow third-party API consumes all threads/connections and
takes down endpoints that never touch that API. With one, only the calls to
that API queue and fail.

## B6. Cloud architecture practice

### Well-Architected pillars (all three clouds converged on the same list)

Operational excellence, security, reliability, performance efficiency, cost
optimisation, sustainability. Useful as a review checklist for any design
question: for each pillar, name one thing your design does.

### Security defaults you should always state

- **Least privilege IAM**, scoped per workload; one identity per service.
- **No long-lived keys.** Use workload identity federation (GitHub Actions →
  cloud, without a stored JSON key) and short-lived tokens. A leaked static
  key is the most common cloud breach.
- **Secrets in a secret manager**, not env vars in a repo, not in images.
- **Private by default**: only the component that must be public is public.
  In this project the receiver is public (GitHub must reach it) but is
  protected by HMAC signature verification, while the worker is private and
  callable only by the Pub/Sub service account.
- **Encryption** in transit (TLS everywhere, mTLS inside the mesh) and at
  rest (default on all three clouds; customer-managed keys when required).
- **Audit logging** on and shipped off-account.

### Infrastructure as Code

Terraform is the default answer: multi-cloud, huge provider ecosystem,
declarative with a state file and a plan/apply workflow. Know the pitfalls:
state must be remote and locked; drift happens when humans click in the
console; secrets can end up in state; module versioning matters. Alternatives:
Pulumi (real programming languages), CDK (TypeScript/Python → CloudFormation),
Bicep (Azure), Crossplane (Kubernetes-native control planes).

A shell script of `gcloud` commands — like `infra/deploy.sh` in this
repository — is legitimate for a demo (readable, zero dependencies,
idempotent through existence checks) but has no state, no drift detection,
and no clean destroy. Being able to articulate that trade-off is the point.

### Cost

Compute dominates until it doesn't: watch **egress** (cross-region and
internet traffic is billed and often surprises), **NAT gateway** charges,
idle managed services, over-provisioned databases, and log/metric retention.
Levers: right-sizing, autoscaling, scale-to-zero, committed-use/savings
plans, spot/preemptible for interruptible work, storage lifecycle policies,
and tagging everything so cost is attributable.

## B7. How this project demonstrates the topic

The AI Unit Test Assistant is a genuine, if small, distributed system —
useful as a concrete anchor for every abstract point above.

```
GitHub PR event
   │  HTTPS webhook, HMAC-SHA256 signed
   ▼
webhook-receiver        Cloud Run, public, scale-to-zero
   │  verifies signature → filters events → publishes → 202 Accepted
   ▼
Pub/Sub topic pr-analysis-jobs
   │  push subscription, OIDC auth, ack deadline 600 s,
   │  5 delivery attempts → dead-letter topic
   ▼
analysis-worker         Cloud Run, private, concurrency = 1
   │  idempotency check → clone → analyse → generate → pytest
   ├──▶ Cloud Storage (artefacts: reports, generated tests)
   └──▶ GitHub commit status (best-effort)
```

| Concept from Part A | Where it lives here |
| --- | --- |
| Microservice boundary by conflicting requirements | Receiver must answer within GitHub's 10 s webhook timeout and is public; worker runs for minutes and is private |
| Event-driven decoupling | Pub/Sub between them; the receiver returns 202 without waiting |
| Queue-based load levelling | A burst of PRs queues instead of overloading workers |
| At-least-once + idempotent consumer | Duplicate delivery is skipped by checking for the report object at `repo/PR/head_sha` in GCS |
| Retry & DLQ | 5 attempts, then `pr-analysis-jobs-dead-letter`; verified live by inspecting a dead-lettered job |
| Poison-message handling | Malformed payloads are acknowledged (HTTP 200) instead of retried forever |
| Serverless design | Both services scale to zero; all state in Pub/Sub and GCS; the in-process LRU cache is an optimisation, not state |
| Horizontal scaling | `concurrency = 1`, so load is handled by more instances, not more threads |
| Least privilege | Worker is `--no-allow-unauthenticated`; a dedicated service account holds only `roles/run.invoker` |
| Defence for a public endpoint | HMAC signature check rejects unsigned requests with 401 |
| Best-effort side effects | A GitHub API failure logs a warning; the job still succeeds because artefacts are already durable |

Two lessons learned during the real deployment are worth telling in an exam,
because they show operational experience:

1. **A malformed environment variable poisoned every clone**, which caused
   5 retries and a dead-letter — an unplanned but perfect demonstration that
   the retry/DLQ policy worked exactly as designed.
2. **Failure reasons were invisible**, because the explanation was only in
   the HTTP response body, which Pub/Sub discards. Fix: log server-side.
   *Anything a distributed system does not log, it did not do — as far as
   the operator is concerned.*

## B8. Study plan and sources

**Week 1 — foundations.** Fallacies, CAP/PACELC, consistency models,
replication and partitioning. *Designing Data-Intensive Applications*
(Kleppmann) chapters 5–9 is the single best source in the field.

**Week 2 — services and events.** microservices.io pattern catalogue
(Richardson) — read the pattern pages for API Gateway, Saga, Outbox, CQRS.
Fowler's articles on microservices trade-offs and event-driven styles.

**Week 3 — cloud and serverless.** Pick one cloud and build the same small
system twice (once with containers, once serverless). The Well-Architected
Framework of your chosen cloud, read as a checklist.

**Week 4 — reliability.** Google SRE Book chapters on SLOs, cascading
failures and overload; AWS Builders' Library articles on timeouts, retries
and backoff (short and outstanding).

**Practice questions to answer in writing:** design a URL shortener; design
a rate limiter; design a notification service; design a CI system that runs
untrusted code. For each, state the SLO first, then the failure modes, then
the architecture — that order impresses examiners.
