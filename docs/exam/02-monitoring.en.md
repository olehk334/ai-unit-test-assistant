# Topic 2 — Monitoring: Prometheus & Grafana

---

# PART A — SUMMARY-HINT (spoken answer)

## A1. Monitoring vs observability

**Monitoring** answers questions you prepared in advance ("is CPU above
80 %?"). **Observability** is the property of a system that lets you answer
questions you did *not* prepare for, from its external outputs. Monitoring
catches known unknowns; observability is how you debug unknown unknowns.

**Signals:** *metrics* (cheap, aggregated numbers over time — "how much,
how often"), *logs* (discrete events with detail — "what exactly happened"),
*traces* (the path of one request across services — "where did the time
go"), and increasingly *profiles* (which code consumed CPU/memory).
Prometheus owns the metrics pillar; Grafana visualises all of them.

**Cost/precision trade-off:** metrics are cheap and lossy (no per-request
detail); logs are precise and expensive; traces are precise but usually
sampled. A mature setup uses metrics to *detect*, traces to *localise*, and
logs to *explain*.

## A2. Prometheus — architecture and model

**Components:** the Prometheus server (scrape/retrieval → TSDB storage →
PromQL engine → HTTP API), **service discovery** (Kubernetes, EC2, GCE,
Consul, file-based), **exporters** (translate third-party systems into
Prometheus metrics), **client libraries** (instrument your own code),
**Pushgateway** (for short-lived batch jobs only), **Alertmanager**
(routing/dedup/silencing of alerts), and a UI — usually Grafana.

**Pull model.** Prometheus scrapes an HTTP `/metrics` endpoint on a schedule
(commonly every 15–30 s). Why pull is a good default:

- You get target health for free — the synthetic `up` metric is 1/0 per
  target, so "the service is gone" is itself a monitorable fact.
- Configuration is centralised; no application needs to know where the
  monitoring system lives.
- Easy to run by hand: `curl localhost:8080/metrics` shows exactly what the
  server will see.
- Natural rate limiting — a misbehaving app cannot flood the backend.

Pull is a bad fit for short-lived jobs (they die before being scraped —
hence Pushgateway) and for targets you cannot reach (behind NAT). Prometheus
also *pushes* outward via **remote write** for long-term storage.

**Data model.** A time series is identified by a metric name plus a set of
labels:

```
http_requests_total{method="POST", handler="/api", status="200"}  →  (timestamp, value)
```

A **sample** is a millisecond timestamp and a float64. Every unique label
combination is a **separate time series**. This gives the killer feature
(slice and dice by any dimension) and the killer risk (**cardinality
explosion**).

**Cardinality — say this before being asked.** Never put unbounded values in
labels: user IDs, email addresses, request IDs, full URLs with parameters,
timestamps. Series count multiplies: 10 methods × 50 endpoints ×
5 status codes = 2 500 series; add `user_id` and it becomes millions,
exhausting memory. Labels are for values from a *small, bounded* set.

## A3. The four metric types

| Type | Meaning | Query with | Example |
| --- | --- | --- | --- |
| **Counter** | Monotonically increases; resets to 0 on restart | `rate()`, `increase()` | `requests_total` |
| **Gauge** | Goes up and down | used directly, `avg_over_time`, `delta`, `predict_linear` | `queue_depth`, `memory_bytes` |
| **Histogram** | Cumulative buckets + `_sum` + `_count` | `histogram_quantile()` | `request_duration_seconds` |
| **Summary** | Client-computed quantiles + `_sum` + `_count` | read directly | legacy latency metrics |

**Histogram vs Summary — a guaranteed question.** A histogram exposes
`_bucket{le="0.1"}`, `le="0.5"`, `le="+Inf"`… Quantiles are computed at query
time, so histograms **can be aggregated across instances** (`sum by (le)`
then `histogram_quantile`). A summary computes quantiles inside the client;
they are cheap to read but **mathematically impossible to average across
instances** — you cannot combine the p99 of ten machines into a fleet p99.
Rule: **use histograms for anything you will aggregate**, which in practice
means latency; the price is choosing bucket boundaries in advance.

**Native histograms** (Prometheus 2.40+, matured with 3.0, still behind
`--enable-feature=native-histograms`) fix that: exponential buckets are
chosen automatically at high resolution and low storage cost, and they remain
aggregatable. This is the direction of travel.

Naming conventions: `_total` for counters, base units (seconds, bytes — not
milliseconds or megabytes), `snake_case`, and a namespace prefix
(`myapp_requests_total`).

## A4. PromQL

**Four expression types:** instant vector (one sample per series *now*),
range vector (a window of samples), scalar, and string.

```promql
http_requests_total{job="api"}          # instant vector selector
http_requests_total{job="api"}[5m]      # range vector — 5 minutes of samples
```

**The functions that matter:**

- `rate(counter[5m])` — per-second average rate over the window; **handles
  counter resets**; the default tool for counters and alerts.
- `irate(counter[5m])` — instantaneous rate from the last two samples; spiky
  graphs only, never alerts.
- `increase(counter[1h])` — total growth over the window (= `rate` × seconds);
  extrapolated, so it may return non-integers.
- `histogram_quantile(0.95, sum(rate(x_bucket[5m])) by (le))` — the p95 idiom.
- `predict_linear(disk_free[6h], 4*3600) < 0` — "will the disk be full in
  4 hours?"; the canonical predictive alert.
- `absent()` / `absent_over_time()` — alert when a series *disappears*.
- `*_over_time()` family (`avg`, `max`, `min`, `quantile`) — aggregate one
  series over time rather than across series.

**The golden rule: `rate()` before `sum()`.**
`sum(rate(x[5m]))` is correct; `rate(sum(x)[5m])` is wrong — summing raw
counters destroys the per-series reset detection, so a pod restart produces a
huge negative dip or bogus spike.

**Aggregation:** `sum`, `avg`, `min`, `max`, `count`, `topk`, `bottomk`,
`quantile`, `stddev` — each with `by (label,…)` (keep these) or
`without (label,…)` (drop these).

**Vector matching:** binary operations join series by label set;
`on(...)`/`ignoring(...)` control which labels are matched, and
`group_left`/`group_right` allow many-to-one joins (e.g. attaching a metadata
metric like `kube_pod_info` to a measurement).

**Window rule:** a `rate()` window must contain at least 2 samples, so make
it ≥ 4× the scrape interval (with 15 s scrapes, use `[1m]` or more; `[5m]` is
the safe common default).

**Recording rules** precompute expensive expressions on a schedule, stored as
new series. Naming convention `level:metric:operations`, e.g.
`job:http_requests:rate5m`. Use them for dashboard queries that are slow or
repeated.

## A5. Configuration, discovery, relabeling

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
rule_files: [ "alerts.yml" ]
scrape_configs:
  - job_name: analysis-worker
    static_configs:
      - targets: ["analysis-worker:8080"]
```

**Service discovery** replaces static targets in dynamic environments:
`kubernetes_sd_configs` (pods/services/endpoints/nodes), `ec2_sd`, `gce_sd`,
`azure_sd`, `consul_sd`, `file_sd` (a JSON file any script can write).

**Relabeling** — two hooks, frequently confused:

- `relabel_configs` runs **before** the scrape: choose which targets to
  scrape, rewrite target labels, drop targets.
- `metric_relabel_configs` runs **after** the scrape: drop or rewrite
  individual metrics — the main tool for **cutting cardinality** from a
  noisy exporter before it hits storage.

Actions: `keep`, `drop`, `replace`, `labelmap`, `labeldrop`, `labelkeep`,
`hashmod` (used to shard targets across several Prometheus servers).

## A6. Storage and scaling Prometheus

**Local TSDB:** incoming samples go to an in-memory **head block** and a
**write-ahead log** (crash safety); every 2 hours the head is flushed to a
persistent block (chunks + index); blocks are later compacted into bigger
ones; retention deletes old blocks by time or size. Compression is
excellent — roughly **1–2 bytes per sample**.

**A single Prometheus is deliberately not clustered.** It is one node, with
local storage, sized by cardinality and retention. To go beyond it:

- **HA:** run two identical servers scraping the same targets; Alertmanager
  clusters and deduplicates the resulting duplicate alerts.
- **Sharding:** split targets across servers with `hashmod` or by function.
- **Long-term & global view:** **Thanos** (sidecar ships blocks to object
  storage; Querier fans out; Compactor downsamples), **Mimir** or **Cortex**
  (horizontally scalable, multi-tenant, via remote write), or
  **VictoriaMetrics** (single binary, very efficient). Managed equivalents
  exist on all three clouds.
- **Remote write** is the standard push path into those systems.
  **Remote-Write 2.0** (Prometheus 3.0) adds metadata, exemplars, created
  timestamps and native histograms, and uses string interning to shrink
  payloads.

**Federation** (one Prometheus scraping aggregated series from another) is
for a small global view only — do not use it to copy everything.

## A7. Alerting

**Split of responsibilities:** *Prometheus* evaluates alerting rules and
decides an alert is firing; *Alertmanager* decides who hears about it and
how often.

```yaml
- alert: HighJobFailureRate
  expr: rate(jobs_processed_total{status="failed"}[15m])
        / clamp_min(rate(jobs_processed_total[15m]), 1e-9) > 0.2
  for: 15m
  labels:   { severity: warning }
  annotations:
    summary: "More than 20% of analysis jobs are failing"
```

Rule states: **inactive → pending** (condition true, waiting out `for`) →
**firing**. The `for` clause is what suppresses flapping.

**Alertmanager features:** *grouping* (one notification for 50 related
alerts, controlled by `group_by`, `group_wait`, `group_interval`,
`repeat_interval`), a *routing tree* with matchers to reach the right team,
*inhibition* (a firing critical suppresses its dependent warnings),
*silences* (time-boxed mutes during maintenance), and *receivers*
(PagerDuty, Slack, email, webhook).

**Alerting philosophy (Google SRE):**

- Alert on **symptoms**, not causes. "Users see errors" pages someone; "CPU
  is at 90 %" does not — high CPU with a healthy service is not an incident.
- Every page must be **urgent, actionable and require human judgement**.
  Anything else is a ticket or a dashboard.
- Alert fatigue is a real outage cause: a noisy pager trains people to
  ignore it.

**SLO-based alerting** is the modern practice. With a 99.9 % SLO the error
budget is 0.1 %. **Burn rate** = observed error rate ÷ budget rate. A
**multi-window, multi-burn-rate** policy pages only for genuinely urgent
burn and tickets the slow leaks:

| Burn rate | Long window | Short window | Action |
| --- | --- | --- | --- |
| 14.4× | 1 h | 5 m | Page (budget gone in ~2 days) |
| 6× | 6 h | 30 m | Page |
| 3× | 1 d | 2 h | Ticket |
| 1× | 3 d | 6 h | Ticket |

The short window prevents alerting on an incident that already ended.

## A8. What to measure — the three canonical methods

- **Four Golden Signals** (Google SRE): **latency, traffic, errors,
  saturation**. Universal starting point.
- **RED** (per service): **Rate, Errors, Duration**. What a service does.
- **USE** (per resource): **Utilisation, Saturation, Errors** for CPU,
  memory, disk, network. What a machine does.

Practical rule: RED for every service endpoint, USE for every resource, plus
a small number of **business metrics** (jobs processed, tests generated, cost
per job). Business metrics are what make the dashboard worth opening.

## A9. Grafana

**What it is:** a visualisation and alerting layer over many data sources
(Prometheus, Loki, Tempo, Mimir, SQL databases, CloudWatch, Azure Monitor,
Google Cloud Monitoring, Elasticsearch…). It stores no metrics itself.

**Core concepts:** *dashboards* made of *panels* (time series, stat, gauge,
bar, table, heatmap, logs, traces, geomap); *data sources*; *variables*
(query/custom/interval/datasource/ad-hoc) that make one dashboard serve every
service, with `repeat` to generate panels per value; *transformations*
(join, reduce, group by, rename, maths) applied client-side after the query;
*annotations* (deploy markers over the graphs — the fastest way to correlate
"it broke at 14:02" with "we deployed at 14:01"); *Explore* for ad-hoc
querying.

**Unified alerting** (Grafana 8+): Grafana-managed rules, contact points,
notification policies, silences and mute timings — an alternative to
Alertmanager when your data sources are heterogeneous.

**Provisioning / dashboards as code:** data sources, dashboards and alert
rules can be defined in YAML/JSON files mounted at startup, so the whole
observability setup is version-controlled and reproducible — exactly what
this project does under `monitoring/grafana/provisioning/`.
**Grafana 12** (May 2025) pushes this further with **Git Sync** (branches and
pull requests for dashboards from inside the UI), **dynamic dashboards**
(tabs, conditional logic), **Drilldown** apps (queryless point-and-click
exploration of metrics/logs/traces) and SQL expressions.

**The Grafana stack:** **Loki** (logs — indexes labels, not full text, so it
is cheap), **Tempo** (traces, queried with TraceQL), **Mimir** (long-term
scalable metrics), **Pyroscope** (continuous profiling), **Alloy** (the
OpenTelemetry-collector distribution that replaced Grafana Agent), **Beyla**
(eBPF auto-instrumentation), **k6** (load testing), **OnCall**.
**Exemplars** link a metric data point to a trace ID — the bridge from "p99
is bad" to "here is one slow request."

## A10. Rapid-fire Q&A

**Q: Why pull instead of push?** Target health for free (`up`), centralised
config, trivial local debugging, natural rate limiting. Push (remote write)
is still used for long-term storage and short-lived jobs.

**Q: Counter or gauge for "requests in flight"?** Gauge — it goes down.
Requests *served* is a counter.

**Q: Why not use summaries for latency?** Their quantiles are computed
per instance and cannot be aggregated; you can never compute a fleet-wide
p99. Histograms can.

**Q: `rate` vs `irate` vs `increase`?** `rate` = average per-second over the
window (alerts, dashboards); `irate` = last two samples only (volatile
graphs); `increase` = total over the window (human-readable counts).

**Q: What is cardinality and why does it kill Prometheus?** Each unique
label combination is a stored series held in memory in the head block;
unbounded label values (user IDs, request IDs) multiply series into millions
and OOM the server. Fix with `metric_relabel_configs` drops and by never
putting identifiers in labels.

**Q: How do you make Prometheus highly available?** Two identical servers
scraping the same targets, with clustered Alertmanager deduplicating alerts.
For long-term/global querying, add Thanos or Mimir — Prometheus itself does
not shard or replicate.

**Q: What is the Pushgateway for, and why is it discouraged?** For
service-level batch jobs that die before a scrape. It becomes a single point
of failure, retains metrics until explicitly deleted (stale data lives on),
and breaks per-target health. Use it only for its one intended case.

**Q: What do you alert on?** Symptoms visible to users, expressed as SLO
burn rate; plus a handful of "this is about to break" predictive alerts (disk
full in 4 h) and "the pipeline stopped" absence alerts.

**Q: How do you decide dashboard content?** Top row: the four golden signals
or RED for the service. Then business KPIs. Then resources (USE). Anything
you have never looked at during an incident should be deleted.

---

# PART B — FULL REPORT

## B1. Why the pull model shapes everything

The decision to scrape rather than receive determines Prometheus's whole
design. Because Prometheus initiates contact, it maintains an authoritative
**list of what should exist** — the service-discovery output. That list makes
possible the single most valuable metric in the system, `up`, which is
synthesised per target on every scrape. In a push architecture, "no data" is
ambiguous: the service might be healthy and idle, misconfigured, or dead. In
a pull architecture the difference is explicit.

The corollary is that Prometheus is a **monitoring system, not an event
store**. It samples state at intervals; it will never tell you about a spike
that lived entirely between two scrapes, and it is not a billing-grade
record. If you need every event, that is a log or a data pipeline. Say this
when asked "can we use Prometheus for X?" — the answer is no whenever exact
per-event accuracy is required.

Another consequence: **staleness handling**. If a series stops being
reported, Prometheus marks it stale after ~5 minutes rather than carrying the
last value forever, so graphs and alerts do not silently freeze on old data.

## B2. Instrumenting an application properly

Direct instrumentation with a client library, from this project's worker:

```python
from prometheus_client import Counter, Histogram, generate_latest

JOBS_PROCESSED = Counter(
    "jobs_processed_total", "Analysis jobs by outcome", ["status"]
)
JOB_DURATION = Histogram(
    "job_duration_seconds", "End-to-end job duration",
    buckets=(5, 15, 30, 60, 120, 300, 600),
)

@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

Design decisions visible here, each defensible in an exam:

1. **`status` is a label with a bounded set** (`processed`, `skipped`,
   `failed`, `ignored`) — four values, safe. A `repo` label would be
   unbounded and wrong.
2. **Buckets match the domain.** Default buckets top out around 10 seconds,
   which is useless for jobs that take minutes. Buckets were chosen around
   the SLO and the Pub/Sub 600 s acknowledgement deadline, so the histogram
   can actually answer "are we approaching redelivery?"
3. **Counters, not gauges, for events** — `rate()` then gives throughput and
   handles process restarts correctly.
4. **A counter for tokens** makes cost a first-class, graphable quantity.

**What not to instrument:** anything already provided by the platform.
Cloud Run exports request count, latency and error rate; Pub/Sub exports
`num_undelivered_messages` (backlog). Re-measuring backlog inside the worker
would be strictly worse data — the worker cannot see messages it has not
received. **Custom metrics belong where custom logic lives.**

## B3. PromQL as a language

PromQL is functional and set-oriented: every expression returns a *set* of
labelled series, and operations join those sets by label.

**Selector → range vector → function → aggregation** is the standard
pipeline:

```promql
sum by (status) (rate(jobs_processed_total[5m])) * 60
```

Read it inside-out: select the counter with 5 minutes of history; convert to
per-second rate per series (handling resets); sum those rates grouped by
`status`; convert to per-minute for humans.

**A cookbook worth memorising:**

```promql
# Throughput per minute, split by outcome
rate(jobs_processed_total[5m]) * 60

# Error ratio, guarded against divide-by-zero
rate(jobs_processed_total{status="failed"}[15m])
  / clamp_min(rate(jobs_processed_total[15m]), 1e-9)

# p95 latency across all instances (only possible with histograms)
histogram_quantile(0.95, sum by (le) (rate(job_duration_seconds_bucket[15m])))

# Mean latency (sum/count — cheaper and sometimes more honest than a quantile)
rate(job_duration_seconds_sum[15m]) / rate(job_duration_seconds_count[15m])

# Cache hit ratio (all-time)
llm_cache_hits_total / clamp_min(llm_cache_hits_total + llm_cache_misses_total, 1)

# Top 5 noisiest series — the cardinality investigation tool
topk(5, count by (__name__)({__name__=~".+"}))

# Alert when a pipeline goes silent
absent_over_time(jobs_processed_total[30m])

# Disk will be full within four hours
predict_linear(node_filesystem_avail_bytes[6h], 4*3600) < 0

# Attach metadata from an info metric (many-to-one join)
sum by (pod) (rate(http_requests_total[5m]))
  * on(pod) group_left(node) kube_pod_info
```

**Traps to name before the examiner does:**

- `rate()` on a gauge is meaningless — it assumes monotonicity.
- `sum()` before `rate()` breaks reset detection.
- A `rate()` window shorter than 4× the scrape interval yields gaps or
  noise.
- `histogram_quantile` on buckets that were never sized for your range
  returns garbage clamped to the highest bucket — always keep a sensible
  `+Inf` and enough resolution around your SLO threshold.
- Quantiles cannot be averaged. `avg(p99)` is not a p99 of anything.

## B4. Operating Prometheus at scale

**Sizing.** Memory is dominated by the number of active series in the head
block; a common rule of thumb is a few kB per series plus query workspace.
Disk is samples × ~1–2 bytes × retention. Both scale with **cardinality**,
which is therefore the number to watch and control.

**Controlling cardinality in practice:**

```yaml
metric_relabel_configs:
  # Drop a noisy metric family entirely
  - source_labels: [__name__]
    regex: "go_gc_duration_seconds.*"
    action: drop
  # Drop a high-cardinality label but keep the metric
  - regex: "request_id"
    action: labeldrop
```

Investigate with `topk(20, count by (__name__)({__name__=~".+"}))` and the
TSDB status page, which lists the highest-cardinality metric names and
labels.

**Choosing a long-term architecture:**

| Need | Solution |
| --- | --- |
| One team, 15 days of data | Plain Prometheus with a persistent volume |
| Survive a Prometheus outage | Two replicas + clustered Alertmanager |
| Years of history, global view | Thanos (object storage + downsampling) or Mimir |
| Multi-tenant platform | Mimir or Cortex |
| Minimal ops, high efficiency | VictoriaMetrics |
| Managed | Amazon Managed Prometheus / Google Managed Prometheus / Azure Monitor managed Prometheus |

**Prometheus 3.0** (November 2024) is the reference point for "what is
current": UTF-8 metric and label names by default, a native **OTLP receiver**
(`/api/v1/otlp/v1/metrics`) so OpenTelemetry SDKs can write directly,
Remote-Write 2.0, a rebuilt UI, and native histograms progressing toward
stable. The strategic message is convergence with OpenTelemetry: instrument
with OTel, store in Prometheus-compatible backends, query with PromQL.

## B5. Designing alerts that people trust

**Symptom vs cause, concretely.** A cause-based alert set for a web service
might page on high CPU, low disk, high GC time and pod restarts — four pages
for one incident, three of which may be harmless in isolation. A
symptom-based set pages on "error ratio above SLO burn" and "latency above
SLO", then lets the responder use dashboards to find which cause applies.
Causes belong in dashboards and tickets, not on the pager.

**The alert lifecycle to describe:**

1. Prometheus evaluates rules every `evaluation_interval`.
2. A matching expression puts the alert in **pending**.
3. After `for`, it becomes **firing** and is pushed to Alertmanager
   repeatedly (Prometheus re-sends; Alertmanager owns de-duplication).
4. Alertmanager groups by labels, waits `group_wait` to collect related
   alerts, applies inhibition and silences, and routes to a receiver.
5. When the expression stops matching, Prometheus sends a resolved
   notification.

**Runbooks.** Every alert annotation should link to a runbook that says what
the alert means, how to confirm it, how to mitigate, and how to escalate. An
alert without a runbook will be handled badly at 3 a.m. by whoever is on
call.

**This project's two rules and their justification:**

- `HighJobFailureRate` — > 20 % failures over 15 minutes. Symptom-level
  (users get no test suggestions), with a 15-minute `for` to ignore a single
  bad job.
- `SlowAnalysisJobs` — p95 job duration > 300 s for 10 minutes. Not vanity:
  the Pub/Sub acknowledgement deadline is 600 s, so crossing it causes
  redelivery and duplicated work. **This is the mark of a good alert — it is
  tied to a real system limit, not a round number.**

## B6. Dashboard design

A dashboard is a document with an audience and a purpose. State the purpose
first, then design.

**Layout that works:**

1. **Top row — the headline.** Four to six panels: request/job rate, error
   ratio, p95 latency, saturation. A responder must know "is it broken and
   how badly" within five seconds.
2. **Second row — business outcome.** For this project: generated-tests pass
   ratio, cache hit ratio, tokens per minute (cost).
3. **Lower rows — drill-down.** Per-dependency latency, queue depth,
   resource usage.
4. **Bottom — logs/links.** Exemplars and links to traces and runbooks.

**Craft rules:** consistent units and colours (red = bad everywhere);
thresholds drawn on the graph so "bad" is visible without knowing the SLO;
template variables instead of copies of a dashboard per environment;
annotations for deploys; and ruthless deletion — a 60-panel dashboard is a
dashboard nobody reads.

**Dashboards as code.** Provision JSON from git (this project) or use Grafana
12's Git Sync. Benefits: review, rollback, identical dashboards across
environments, and disaster recovery. Hand-built dashboards drift and die with
the person who made them.

## B7. Beyond metrics: the rest of observability

**Logs.** Structured (JSON) with a correlation/trace ID, levels used
meaningfully, and no secrets. In Loki, index only bounded labels
(`service`, `env`, `level`) and let the content be searched at query time —
Loki's cost model is the inverse of Elasticsearch's.

**Traces.** OpenTelemetry SDK propagates a trace context (W3C `traceparent`)
across service boundaries; each service records spans; a backend (Tempo,
Jaeger, X-Ray, Cloud Trace) reassembles the waterfall. Head sampling decides
at the start (cheap, may miss rare errors); tail sampling decides after
seeing the whole trace (keeps the interesting ones, needs more infrastructure).

**The three-signal workflow** to describe out loud: a metric alert fires →
the dashboard localises the failing service and time window → an exemplar
jumps to a representative trace → the trace shows which span is slow or
failing → logs for that trace ID explain why. Every hop should be one click;
building those links is most of the value of an observability platform.

**Instrumentation strategy today:** use OpenTelemetry for application
instrumentation (vendor-neutral, one API for metrics/traces/logs), export to
Prometheus-compatible storage, and keep Prometheus exporters for
infrastructure. This avoids re-instrumenting when you change backends.

## B8. How this project demonstrates the topic

**Local stack** (`monitoring/docker-compose.yml`) — three containers on one
network: the analysis worker (in dry-run mode: real clone, real pytest,
stubbed LLM), Prometheus scraping it every 5 s and evaluating alert rules,
and Grafana with a provisioned data source and dashboard. The entire
observability demo runs with `docker compose up --build` and needs no cloud
account and no credentials.

**The metric set and the reasoning behind each:**

| Metric | Type | Question it answers |
| --- | --- | --- |
| `jobs_processed_total{status}` | counter | Throughput and failure ratio |
| `job_duration_seconds` | histogram | p95 vs the 600 s ack deadline |
| `llm_calls_total`, `llm_seconds_total` | counter | How often and how long we wait on the model |
| `llm_prompt_tokens_total`, `llm_response_tokens_total` | counter | Cost per minute |
| `llm_cache_hits_total` / `_misses_total` | counter | Does the LRU cache actually pay off? |
| `generated_test_files_total{result}` | counter | Quality KPI: do generated tests pass? |

**A measured result worth quoting.** Four identical jobs were sent to the
local stack. The counters afterwards:

```
jobs_processed_total{status="processed"}  4
llm_calls_total                           3
llm_cache_hits_total                      9
llm_cache_misses_total                    3
generated_test_files_total{result="passed"} 8
```

Job 1 produced three cache misses (three real model calls); jobs 2–4 were
served entirely from the LRU cache — nine hits, zero additional calls. **The
optimisation from Topic 3 is not asserted, it is measured**, and the cache
hit ratio panel next to the token-rate panel makes the saving visible. That
pairing — an optimisation and the metric that proves it — is the strongest
possible answer to "why did you add monitoring?"

**Cloud path.** The same `/metrics` endpoint is scraped by Google Managed
Service for Prometheus on Cloud Run, and the same dashboard JSON imports
unchanged. Nothing in the application distinguishes local from cloud
collection — which is precisely the benefit of the pull model and an open
exposition format.

**An honest limitation to volunteer:** metrics live in process memory, so a
Cloud Run instance scaling to zero resets its counters. `rate()` handles
counter resets correctly, so throughput graphs stay right, but all-time
totals do not survive. The fix is remote write to a durable backend — worth
naming as future work rather than pretending it is solved.

## B9. Study plan and sources

**Days 1–2 — model and language.** The official Prometheus docs on data
model, metric types and querying basics. Then run Prometheus locally and
write twenty PromQL queries against real data; the language only becomes
intuitive by use.

**Days 3–4 — collection and storage.** Scrape configs, relabeling, service
discovery, TSDB internals, remote write. Instrument a small service of your
own with a client library — do not just deploy exporters.

**Day 5 — alerting.** The Google SRE Book chapters on monitoring and on
alerting (the "symptoms not causes" argument), then the SRE Workbook chapter
on SLO alerting for multi-window burn rates. Write three alerts for your own
service and justify each.

**Day 6 — Grafana.** Build one dashboard by hand, then export its JSON,
delete it, and reprovision it from the file. Learn variables and
transformations; they are what separate a template from a screenshot.

**Day 7 — the wider ecosystem.** Skim Thanos/Mimir architecture,
OpenTelemetry concepts, and Loki's label-based indexing. You need to be able
to say *when* each is needed, not to operate them.

**Primary sources:** prometheus.io documentation; grafana.com documentation;
*Site Reliability Engineering* and *The Site Reliability Workbook* (Google,
free online); Brendan Gregg's USE method; Tom Wilkie's RED method;
Prometheus 3.0 release notes for the current state.

**Sources consulted for the current-version facts in this document:**

- [Announcing Prometheus 3.0](https://prometheus.io/blog/2024/11/14/prometheus-3-0/)
- [Prometheus 3.0 release notes (GitHub)](https://github.com/prometheus/prometheus/releases/tag/v3.0.0)
- [Grafana 12 release: observability as code, dynamic dashboards, new alerting tools](https://grafana.com/blog/grafana-12-release-all-the-new-features/)
- [What's new in Grafana v12.0](https://grafana.com/docs/grafana/latest/whatsnew/whats-new-in-v12-0/)
