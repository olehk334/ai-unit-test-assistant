# PDP Vision: AI Test Assistant Platform

This document maps the remaining PDP plan points onto two projects and lays
out the complete vision for evolving **this** project (AI Unit Test
Assistant) from a CLI MVP into a cloud-native, observable, algorithmically
optimized PR service.

## Point allocation

| PDP point | Project |
| --- | --- |
| 1. Video Stabilization (gyroscope + depth + algorithms) | **Project 2** — standalone CV repo |
| 6. Distributed Systems & Cloud Architecture | **This project** — Phase 2 |
| 7. Monitoring (Prometheus, Grafana) | **This project** — Phase 3 |
| 8. Topological sort & LRU/LFU cache internals | **This project** — Phase 4 |

Already covered by the existing MVP: CI/CD + coding agents, AI unit test
automation, LLM development basics, AI productivity (Tech 2, 3, 5, Soft 1).

---

# Project 1 vision: AI Test Assistant Platform

**One-line pitch:** what starts as a CLI that generates tests in CI becomes a
small event-driven cloud service that any repo in an organization can point a
webhook at — observable in Grafana, cheap thanks to response caching, and
correct thanks to dependency-ordered analysis.

## Phase 1 — MVP (done)

CLI + GitHub Actions. Detect changed files, generate/repair tests with
Gemini, suggest updates for existing tests, report as PR artifact.
Label-triggered apply-suggestions workflow.

## Phase 2 — Distributed Systems & Cloud Architecture (PDP 6)

### Target architecture

```text
GitHub PR webhook
      │
      ▼
[Webhook Receiver]  Cloud Run service (serverless, scales to zero)
  - verifies GitHub HMAC signature
  - publishes job message, returns 202 immediately
      │
      ▼
[Pub/Sub topic: pr-analysis-jobs]   (event-driven decoupling)
  - at-least-once delivery, retry policy
  - dead-letter topic after N failed deliveries
      │
      ▼
[Analysis Worker]  Cloud Run service (horizontal autoscaling)
  - clones repo at PR head, runs existing pipeline as a library
  - idempotency key = (repo, PR, head SHA) — duplicate deliveries no-op
      │
      ├──▶ [GCS bucket]  generated tests + reports (artifact store)
      └──▶ [GitHub Checks API]  posts result + report link back to the PR
```

### Theory checklist → where the project demonstrates it

| Theory topic | Demonstrated by |
| --- | --- |
| Microservices | Receiver / worker split; each independently deployable, communicating only through Pub/Sub |
| Event-driven systems | Pub/Sub topic between receiver and worker; webhook as the event source; DLQ for poison messages |
| Serverless design | Cloud Run scale-to-zero; stateless services; all state in GCS/Pub/Sub |
| Scalability patterns | Queue-based load leveling, horizontal worker scaling, idempotent consumers, retry with exponential backoff, dead-letter queue |
| Cloud platforms | GCP hands-on (Cloud Run, Pub/Sub, GCS, IAM, Artifact Registry); AWS/Azure covered in a written equivalence table (SQS/Lambda/S3, Service Bus/Functions/Blob) |

### Deliverables

- `services/webhook_receiver/` — FastAPI app, ~150 lines, Dockerfile
- `services/analysis_worker/` — wraps the existing `ai_test_assistant` package
- `infra/` — deployment scripts or Terraform for Cloud Run + Pub/Sub + GCS
- `docs/architecture.md` — diagram, message contract, failure-mode table
  (what happens when: LLM down, duplicate delivery, worker crash mid-job)
- `docs/cloud_equivalence.md` — GCP ↔ AWS ↔ Azure service mapping

## Phase 3 — Monitoring (PDP 7)

### What we instrument (real metrics, not toys)

| Metric | Type | Why it matters |
| --- | --- | --- |
| `llm_request_duration_seconds` | histogram | Gemini latency; p95 drives worker sizing |
| `llm_tokens_total{direction=in\|out}` | counter | direct cost driver |
| `jobs_processed_total{status=passed\|failed\|error}` | counter | pipeline health |
| `repair_attempts_total` | counter | LLM output quality trend |
| `generated_tests_pass_ratio` | gauge | headline quality KPI |
| `pubsub_queue_depth` | gauge | backlog → scaling signal |
| `cache_hits_total` / `cache_misses_total` | counter | Phase 4 payoff, measured |

### Stack

- `prometheus-client` in both services, `/metrics` endpoints
- Local: `docker-compose up` = receiver + worker + Prometheus + Grafana
  (fully reproducible demo without cloud)
- Cloud: GCP Managed Service for Prometheus + Grafana against the same metrics
- Two dashboards: **Operations** (throughput, latency, queue depth, errors)
  and **Quality/Cost** (pass ratio, tokens/day, cache hit rate)
- Two alert rules: error-rate > 20% over 15 min; queue depth growing for 10 min

### Deliverables

- `monitoring/docker-compose.yml`, `monitoring/prometheus.yml`,
  `monitoring/grafana/dashboards/*.json`
- `docs/monitoring.md` — metric taxonomy (counter vs gauge vs histogram),
  PromQL queries used in dashboards, alerting rationale

## Phase 4 — Algorithms: topological sort + LRU/LFU (PDP 8)

Both are implemented **from scratch** (no `graphlib`, no `functools.lru_cache`)
inside the assistant, each solving a real problem it has today.

### Topological sort — dependency-ordered analysis

Problem it solves: when a PR changes `models.py` and `service.py` (which
imports `models`), analyzing them in arbitrary order produces suggestions
against stale context. Build the import graph of changed files, topo-sort
(Kahn's algorithm), analyze dependencies first; on cycle detection, fall back
to file order and record the cycle in the report.

- `ai_test_assistant/dep_graph.py` — import extraction (reuses the existing
  AST analyzer) + Kahn's algorithm with cycle reporting
- Unit tests: chain, diamond, cycle, disconnected components
- `docs/algorithms.md` section: Kahn vs DFS-based sort, complexity O(V+E)

### LRU / LFU cache — LLM response and analysis caching

Problem it solves: re-running the assistant on a PR after a rebase re-sends
identical prompts to Gemini. Cache keyed by SHA-256 of
(model, system_instruction, prompt): hit = zero cost, zero latency.

- `ai_test_assistant/cache.py`:
  - `LRUCache` — dict + hand-rolled doubly-linked list, O(1) get/put
  - `LFUCache` — frequency buckets of ordered nodes, O(1) get/put,
    LRU tie-break within a frequency bucket
- Wire into `LlmClient.generate()` behind a config flag; expose
  `cache_hits_total` / `cache_misses_total` to Prometheus (ties into Phase 3)
- Unit tests: capacity eviction, recency update on get, frequency promotion,
  tie-breaks; a micro-benchmark comparing hit/miss latency
- `docs/algorithms.md` section: LRU vs LFU internals, why O(1), when each
  eviction policy wins (LRU: bursty PR re-runs; LFU: hot shared modules)

## Suggested order & effort

| Phase | Effort | Depends on |
| --- | --- | --- |
| 4 — algorithms | ~1 week | nothing — pure Python inside existing package, do first for quick wins |
| 2 — cloud architecture | ~2–3 weeks | GCP project (already exists) |
| 3 — monitoring | ~1–2 weeks | Phase 2 services running (local docker-compose is enough) |

Phase 4 first is deliberate: it needs no infrastructure, and its cache
metrics become interesting content for the Phase 3 dashboards.

## Demo storyline (end state)

1. Open a PR against the calculator repo → webhook fires → job queued.
2. Grafana: queue depth ticks up, worker scales, LLM latency histogram fills.
3. PR gets its check + report; re-push the same branch → cache hits spike,
   token counter stays flat (screenshot the dashboard).
4. Show `dep_graph.py` deciding analysis order on a two-file PR.
5. Kill the worker mid-job → message redelivered → idempotency skips
   double-posting (failure-mode demo).

---

# Project 2 vision (brief): Video Stabilization (PDP 1)

Standalone repo: `video-stabilization`. Python + OpenCV + NumPy.

**Scope:** stabilize handheld/sports video using three complementary signals:

1. **Algorithmic baseline** — feature tracking (ORB/optical flow) →
   trajectory estimation → smoothing (moving average, then a 1D Kalman
   filter) → warp compensation.
2. **Gyroscope data** — ingest IMU logs (phone sensor CSV or GoPro GPMF),
   synchronize timestamps with frames, gyro-based rotation compensation and
   rolling-shutter correction; compare against the visual-only baseline.
3. **Depth data** — use depth maps (recorded LiDAR/ToF or monocular depth
   estimation) to separate foreground subject from background so parallax
   doesn't corrupt the motion model.

**Deliverables:** CLI (`stabilize input.mp4 --gyro imu.csv --mode
visual|gyro|hybrid`), side-by-side comparison renders, an evaluation metric
(inter-frame transform smoothness before/after), and docs covering the theory
of each stage. No cloud, no service — the depth of this project is the
algorithms themselves.

Kept separate because it shares no code, domain, or infrastructure with the
assistant; merging them would weaken the narrative of both.
