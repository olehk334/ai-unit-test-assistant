# Monitoring (Prometheus + Grafana)

PDP point 7. The analysis worker exposes Prometheus metrics at `/metrics`;
a docker-compose stack runs the full observability demo locally with zero
cloud dependencies.

## Metrics and why each type was chosen

| Metric | Type | Why this type |
| --- | --- | --- |
| `jobs_processed_total{status}` | counter | Monotonic event count; `rate()` gives throughput, the label splits outcomes (processed / failed / skipped / ignored). |
| `job_duration_seconds` | histogram | Durations need percentiles, not averages — a histogram's buckets let PromQL compute p50/p95 across restarts. |
| `llm_calls_total`, `llm_seconds_total` | counter | Cumulative LLM work; the ratio gives mean call latency. |
| `llm_prompt_tokens_total`, `llm_response_tokens_total` | counter | Tokens are the direct cost driver; `rate()` = spend per minute. |
| `llm_cache_hits_total{policy}`, `llm_cache_misses_total{policy}` | counter | Hit ratio proves the response cache pays for itself; the label (`lru` / `lfu`) tells the eviction policies apart. |
| `generated_test_files_total{result}` | counter | Headline quality KPI: how often generated tests pass. |

Every known label value (job status, test result, cache policy) is exported
at 0 from startup: `rate()` cannot see the first increment of a series that
did not exist before it.

Counter vs gauge rule of thumb used here: everything above only ever grows,
so counters + `rate()` are correct. Gauges (current value, may go down)
would suit queue depth — which is not a custom metric at all: Pub/Sub backlog
is already exported by Cloud Monitoring
(`pubsub.googleapis.com/subscription/num_undelivered_messages`); re-measuring
it in the worker would be worse data.

The receiver is intentionally not instrumented: it does one cheap thing, and
Cloud Run's built-in request metrics (count, latency, error rate) already
cover it. Custom metrics belong where custom logic is.

## Running the local demo

```bash
cd monitoring
docker compose up --build
```

Then generate traffic:

```bash
python send_test_job.py --repeat 5
```

- Worker: http://localhost:8080/metrics — raw metrics
- Prometheus: http://localhost:9090 — try `rate(jobs_processed_total[5m])`
- Grafana: http://localhost:3000 — "AI Test Assistant" dashboard is
  pre-provisioned (anonymous admin access, no login)

The worker runs in dry-run mode: real clone, real pipeline, real pytest —
stubbed LLM. Repeat runs of the same job demonstrate the cache: the hit
ratio panel climbs while token rates stay flat.

To try the LFU policy, set `LLM_CACHE_POLICY: "lfu"` in
`docker-compose.yml`, run `docker compose up --build` again and send the same
jobs; the hit-ratio panel then reports under the `lfu` label.

## Useful PromQL

```promql
# Throughput by outcome (jobs per minute)
rate(jobs_processed_total[5m]) * 60

# p95 job duration
histogram_quantile(0.95, rate(job_duration_seconds_bucket[15m]))

# Cache hit ratio (all-time, one series per policy)
llm_cache_hits_total / clamp_min(llm_cache_hits_total + llm_cache_misses_total, 1)

# Mean LLM call latency
rate(llm_seconds_total[15m]) / clamp_min(rate(llm_calls_total[15m]), 1e-9)
```

## Alerts

`monitoring/alerts.yml`, loaded by the local Prometheus (visible under
Alerts in its UI; wiring a notification channel needs Alertmanager, which is
out of scope):

- **HighJobFailureRate** — >20% of jobs failing over 15 min. First suspects:
  Gemini outage, bad deploy.
- **SlowAnalysisJobs** — p95 duration above 5 min for 10 min. Matters
  because the Pub/Sub ack deadline is 600 s: beyond it, redeliveries cause
  duplicate work.

The failure-rate alert and the dashboard's pass-ratio panel use `sum()` on
both sides of the division: dividing labelled series directly pairs only equal
label sets. The rules have unit tests in `monitoring/alerts_test.yml`; from the
repository root:

```bash
docker run --rm -v "$PWD/monitoring:/work" -w /work --entrypoint promtool prom/prometheus:v2.53.0 test rules alerts_test.yml
```

## Cloud path

The same `/metrics` endpoint works on Cloud Run with
[Managed Service for Prometheus](https://cloud.google.com/stackdriver/docs/managed-prometheus)
(sidecar collection), and the Grafana dashboard JSON imports unchanged
against it as a datasource. Nothing in the code changes between local and
cloud collection — that separation is the point.
