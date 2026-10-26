# 9. PDP · Monitoring (Prometheus, Grafana) {#en-monitoring}

## In plain words

Monitoring answers "is the service healthy, and what does it cost?" with numbers that are collected all the time, not with log files read after the fact. The worker exposes a page of counters at `/metrics`; Prometheus reads that page every few seconds and stores the history; Grafana draws it; alert rules watch it. The whole stack runs on a laptop with one `docker compose up`.

![From an event in the worker to a number on the dashboard.](images/metrics.en.png)

## Theory in brief

- **Pull model.** Prometheus asks each service for its metrics on a schedule (here every 5 seconds). The service only has to serve a text page; it does not need to know where Prometheus is.
- **Metric types.** A *counter* only goes up (jobs processed, tokens sent); you look at its rate, never its raw value. A *gauge* can go up and down (queue length, memory). A *histogram* counts observations in buckets (job duration) so you can compute percentiles later.
- **Labels** split one metric into series: `jobs_processed_total{status="failed"}`. Useful, but every label value is a new series, so labels must have few values.
- **PromQL** is the query language: `rate(x[5m])` turns a counter into "per second over the last five minutes"; `histogram_quantile(0.95, …)` turns buckets into a p95. Binary operators pair series with identical labels, so ratios usually need `sum()` on both sides.
- **Alert rules** are PromQL expressions with a `for:` duration; they fire only after the condition has held long enough, which stops flapping. Prometheus decides *that* an alert fires; Alertmanager decides *who* is told.
- **Dashboards as code.** Grafana can load dashboards and data sources from JSON and YAML files at start-up, so the dashboard is versioned with the code and identical on every machine.

## How this project applies it

| Metric | Type | Question it answers |
| --- | --- | --- |
| `jobs_processed_total{status}` | counter | throughput, and the share of failed / skipped / ignored jobs |
| `job_duration_seconds` | histogram | p50 and p95 against the 600-second ack deadline |
| `llm_calls_total`, `llm_seconds_total` | counter | how often, and how long, the worker waits for Gemini |
| `llm_prompt_tokens_total`, `llm_response_tokens_total` | counter | cost per minute |
| `llm_cache_hits_total{policy}`, `llm_cache_misses_total{policy}` | counter | does the cache pay off, per eviction policy |
| `generated_test_files_total{result}` | counter | the quality KPI: how often generated tests pass |

Every known label value is exported at zero from start-up, because `rate()` cannot see the first increment of a series that did not exist before.

**The local demo** (`monitoring/docker-compose.yml`): the worker in dry-run mode with the demo repository mounted, Prometheus with the scrape config and alert rules, Grafana with the dashboard and data source provisioned from files. `python send_test_job.py --repeat 5` sends jobs; the hit-ratio panel climbs while token counters stay flat.

**Two alert rules** (`monitoring/alerts.yml`): more than 20 % of jobs failing over 15 minutes, and p95 duration above 5 minutes for 10 minutes (jobs close to the ack deadline get redelivered). The rules have unit tests: `promtool test rules alerts_test.yml` feeds synthetic series and checks which alerts fire.

**A bug that teaches the `sum()` rule.** The failure-rate alert originally divided `rate(jobs{status="failed"})` by `rate(jobs)` without `sum()`. PromQL paired the failed series only with itself, so the ratio was 1.0 after any single failure: the "more than 20 %" alert would fire on one failed job in a hundred. Measured locally: 1.0 shown while the true ratio was 0.13. The dashboard's pass-ratio panel had the mirror-image mistake and always showed "No data". Both were fixed with `sum()` on both sides, and the rule tests now catch this.

## Likely questions

**Q:** Why Prometheus and not the cloud's own monitoring?

**A:** The same `/metrics` endpoint works with Google's managed Prometheus on Cloud Run, so nothing in the code changes between the laptop and the cloud. The local stack is free and runs offline, which is what a demo and a test suite need.

**Q:** Why no queue-length metric?

**A:** The queue length is a property of Pub/Sub, and Cloud Monitoring already exports it (`num_undelivered_messages`). Measuring it again from the worker would be worse data.

**Q:** What would you alert on in production that you do not here?

**A:** A silent pipeline: no jobs processed for an hour while PRs were opened. That needs the GitHub side as a signal, which is out of scope for the demo.
