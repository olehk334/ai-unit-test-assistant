# How This Project Works — Architecture Explained

**Project:** AI Unit Test Assistant (`ai-unit-test-assistant`)
**Purpose of this document:** explain what we built, which techniques we used, *why* we chose each one, and what concrete improvement each brought. Everything here describes the code as it actually exists in this repository, with measured numbers from real runs — not aspirations.

**Companion documents:**
- [study_report_pdp.md](study_report_pdp.md) — the general theory (distributed systems, Prometheus/Grafana, algorithms)
- [pdp_features_guide_ru.md](pdp_features_guide_ru.md) — Russian deep-dive on the PDP features
- [architecture.md](architecture.md) · [monitoring.md](monitoring.md) · [algorithms.md](algorithms.md) — focused reference docs

---

# English Version

## 1. What the project is, in one page

A developer opens a pull request. Somewhere in it, a public function changed or a new one appeared. The assistant notices, reads the diff, works out which functions actually changed, asks Gemini to write pytest tests for them, **runs those tests**, repairs them if they fail, and hands the developer a reviewable artifact — plus a suggested update for any hand-written test file the change broke.

Three rules constrain everything:

| Rule | Why it matters |
|---|---|
| Never modify production code | The tool is an assistant, not an author. A test generator that edits your source is a liability. |
| Never overwrite existing tests automatically | Hand-written tests encode human intent. They are overwritten only when a human clicks a label. |
| Never auto-commit | Everything lands as a reviewable artifact or a labelled bot commit. The human stays in control. |

The project runs in **two modes from one codebase**:

```
MODE 1 — CLI / GitHub Actions          MODE 2 — Cloud service
developer runs a command,              GitHub webhook fires,
or a workflow runs it in CI            two Cloud Run services process it asynchronously
        │                                       │
        └───────────────┬───────────────────────┘
                        ▼
          the same `ai_test_assistant` package
                (one pipeline, one set of tests)
```

That single-implementation property is the most important structural decision in the project: the cloud services are thin HTTP wrappers around the same library the CLI calls. There is no duplicated business logic to drift apart.

## 2. Repository map

```
ai_test_assistant/          the library — 15 modules, ~1,700 lines
├── cli.py                  Typer CLI: 3 commands
├── config.py               settings from CLI > env > .env > YAML > defaults
├── models.py               shared dataclasses
├── git_utils.py            which files changed, and which lines
├── source_analyzer.py      AST parsing → public functions/methods
├── import_graph.py         ⭐ topological sort of changed files
├── test_finder.py          find related existing tests
├── llm_client.py           Vertex AI/Gemini + ⭐ response cache + usage stats
├── cache.py                ⭐ LRU and LFU implemented from scratch
├── prompts.py              all prompt text in one place
├── test_generator.py       generate / update / repair + validation
├── pytest_runner.py        run pytest in a subprocess
├── report.py               Markdown + JSON reports
└── pipeline.py             the orchestrator

services/                   ⭐ the cloud deployment
├── webhook_receiver/       public Cloud Run service (100 lines)
└── analysis_worker/        private Cloud Run service (335 lines)

monitoring/                 ⭐ Prometheus + Grafana stack (docker-compose)
infra/                      deploy.sh + Cloud Build configs
tests/                      77 tests (unit + service)
docs/                       this and other documentation
```

⭐ = added during the PDP work; everything else is the original MVP.

## 3. The core pipeline — what existed before the PDP additions

This is the part that does the actual job. It is deliberately **linear**: input → transform → output, with no framework, no plugin system, no DAG executor.

```
1. get_changed_python_files()    git diff → which .py files changed, and which lines
2. order_files_by_imports()      ⭐ dependency order (added later — §4)
3. analyze_source_file()         AST → public functions, classes, methods
4. select_test_targets()         which of them intersect the changed lines
5. find_related_tests()          which existing test files touch those targets
6. generate_tests()              Gemini → a pytest module
7. validate + write              parse-check, then write to tests/generated/
8. run_pytest()                  actually execute it
9. repair loop                   on failure, feed pytest output back to Gemini (≤2×)
10. update_existing_tests()      suggest rewrites of related hand-written tests
11. write reports                Markdown + JSON
```

### 3.1 Change detection — `git_utils.py`

We run `git diff --unified=0 <base>...HEAD` and parse the hunk headers to get **exact changed line numbers**, not just filenames.

**Why line numbers matter:** a PR that adds one function to a 500-line module should produce tests for *that function*, not for all twenty. Line-level precision is what keeps token cost and review burden proportional to the change.

**The filtering rule** (`is_production_python_file`) excludes test files, `*_generated.py`, and configured paths. This is a small function with a large safety role: it is the reason the assistant can never target its own output and enter a feedback loop.

**Graceful degradation:** if the diff can't be parsed, the changed-line set comes back empty and the analyzer selects *all* public targets. Degraded, but never broken.

### 3.2 Source analysis — `source_analyzer.py`

Pure `ast` parsing — no regex, no heuristics on source text.

- Walks the module body, collects public functions (name doesn't start with `_`) and public classes with their public methods.
- Reconstructs a readable signature for each (including defaults, `*args`, keyword-only args, annotations, return types).
- Extracts each target's source with `ast.get_source_segment`.
- `select_test_targets()` keeps only targets whose line range **intersects** the changed lines.

**Why AST and not regex:** decorators, multi-line signatures, nested definitions, and `async def` all break naive text matching. The AST is the language's own understanding of the file, and it is in the standard library — zero dependency cost.

### 3.3 Finding related tests — `test_finder.py`

Two complementary heuristics:
1. **Name/path conventions** — `tests/test_<stem>.py`, mirrored layout `tests/<pkg>/test_<stem>.py`, and `tests/<stem>_test.py`.
2. **Content scan** — read test files and look for the module path or target names.

The content scan uses **word-boundary regex** so a function named `add` doesn't match the word `address`. That was a real bug we fixed: substring matching pulled unrelated test files into the prompt, wasting tokens and adding noise.

**Why heuristics rather than call-graph analysis:** the goal is to give the LLM useful context, not to be provably complete. A false positive costs a few tokens; a full static call graph would cost weeks of work and still miss dynamic dispatch. This is documented as a limitation rather than hidden.

### 3.4 The LLM boundary — `llm_client.py` + `prompts.py`

**One module talks to Gemini.** Everything else is provider-agnostic. If we swapped Vertex AI for Bedrock, exactly one file changes.

Design choices:
- **`temperature = 0.0`** — we want reproducible test scaffolds, not creative variation. This also makes response caching *correct* (see §5).
- **All prompt text lives in `prompts.py`** — three system instructions (generate / repair / update) and three builders returning `(system_instruction, user_prompt)`. Prompts are reviewable in code review, not buried in f-strings across the codebase.
- **Lazy SDK import** — `google-genai` is imported inside the function, so unit tests run without the cloud SDK installed.
- **`dry_run` mode** — returns a fixed placeholder and makes **zero** network calls. This is what makes the entire test suite and the local monitoring demo free and offline.

### 3.5 Validation — `test_generator.py`

LLM output is untrusted input. Every response passes through:

```
raw response
  → clean_llm_python_response()   strip ```python fences, stray backticks, whitespace
  → validate_python_test_code()   must be non-empty
                                  must parse with ast.parse()
                                  must contain a test_ function or Test class
                                  must not contain a shell shebang
  → write to disk
```

**Why this matters:** without validation, a chatty model reply ("Sure! Here are your tests:") gets written to a `.py` file and breaks the developer's test run. With it, a bad response produces a clean per-file error in the report and the pipeline moves on to the next file.

### 3.6 Execution and repair — `pytest_runner.py` + the loop in `pipeline.py`

Generated tests are **executed**, not just written. `subprocess.run([sys.executable, "-m", "pytest", "-q", ...])` with a timeout, capturing stdout/stderr, never raising on test failure.

If tests fail, the pipeline sends the source, the current test code, and the **pytest output** back to Gemini with the repair prompt, up to `repair_attempts` (default 2) times.

**Why the repair loop is the highest-value feature:** the difference between "the AI wrote some tests" and "the AI wrote tests that pass" is enormous in practice. Most first-attempt failures are trivial — a wrong import path, an assertion on an exact float, a misremembered error message — and exactly the kind of thing a model fixes immediately when shown the traceback.

**Safety:** the only thing ever executed is Python that passed AST validation, run through pytest, in a subprocess with a timeout. We never execute shell commands from LLM output.

### 3.7 Outputs — `report.py` + the file-writing rules

| Output | Path | Header |
|---|---|---|
| Generated tests | `tests/generated/test_<path>_generated.py` | "generated by AI Unit Test Assistant — review before committing" |
| Suggested updates | `reports/suggested-tests/<original path>` | "suggested update — review before replacing the original" |
| Human report | `reports/ai-test-report.md` | — |
| Machine report | `reports/ai-test-report.json` | — |

The generated filename derives from the **repo-relative path** (`calculator/pricing.py` → `test_calculator_pricing_generated.py`) so two modules with the same stem in different packages can't collide — a bug we found and fixed during the audit.

**Error isolation:** every file is processed in its own try/except. One file failing — bad syntax, LLM error, validation failure — produces an `error` entry in the report and the rest continue. A five-file PR never loses four files' work because of one.

---

## 4. Addition 1 — Topological sort (`import_graph.py`)

### The problem in our project

A PR changes both `models.py` and `service.py`, where `service.py` imports `models`. Processing order came from `git diff`, which is effectively arbitrary. If `service.py` is processed first, its tests are generated against a module whose dependency the pipeline hasn't looked at yet — and the order changes between runs, making output non-reproducible.

### What we built

`order_files_by_imports()` — Kahn's algorithm over the changed files:

1. Parse each changed file's imports with `ast` (plain `import x`, `from x import y`, and relative imports resolved against the file's package).
2. Build a graph **restricted to the changed files** — an edge `A → B` means "B imports A".
3. Kahn's: emit zero-in-degree vertices, decrement neighbours, repeat.
4. Ties are broken by **original file order**, so output is deterministic.
5. If vertices remain, they form a cycle: keep their original order and record them in `import_cycle_files`.

### Why these specific choices

| Choice | Reason |
|---|---|
| **Kahn's, not DFS** | Cycle detection is free (emitted count < vertex count) and the code is iterative — no recursion-depth concerns. |
| **Only changed files in the graph** | External imports (stdlib, third-party, unchanged modules) don't affect *processing order*. Restricting the graph keeps it tiny — usually under ten vertices — and makes the code simple. |
| **Cycles don't abort the run** | An import cycle is a code smell in the *analysed* project. Refusing to generate tests because of it would be the wrong product decision. We degrade to original order and report it. |
| **Deterministic tie-breaking** | Output feeds LLM prompts that are cached by hash. Non-deterministic order would silently reduce the cache hit rate. |

### Improvement it brings

- **Correct context ordering** — dependencies are analysed before dependents.
- **Reproducibility** — the same PR produces the same processing order every time.
- **A free diagnostic** — import cycles now surface in the report (`import_cycle_files` in JSON, a summary line in Markdown) as a side effect.
- **Cost:** ~120 lines, no dependencies, O(V+E) — unmeasurable next to a multi-second LLM call.

### A bug worth knowing about

Naively doing `in_degree[v] += 1` for every parsed edge breaks when the same edge is discovered twice (a module imported on two lines): the in-degree never reaches zero, the vertex silently vanishes from the output, and it looks like a phantom cycle. We guard by checking set membership before incrementing.

---

## 5. Addition 2 — LRU / LFU caches (`cache.py`)

### The problem in our project

At `temperature = 0`, Gemini's response to an identical prompt is deterministic. Yet the same prompt gets sent repeatedly:
- a developer rebases and re-pushes a branch → same files, same prompts;
- Pub/Sub redelivers a message (at-least-once) → the job runs again;
- two PRs touch the same unchanged module.

Every repeat costs money and multi-second latency for a response we could have predicted exactly.

### What we built

**Both policies from scratch**, no `functools.lru_cache`, no library:

**`LRUCache`** — hash map + doubly linked list with head/tail sentinels. `get` unlinks and relinks the node after the head; `put` at capacity unlinks `tail.prev`. Both O(1), no scanning.

**`LFUCache`** — `key→value`, `key→frequency`, `frequency→OrderedDict of keys`, plus a `min_freq` pointer. Access moves a key from bucket *f* to *f+1*; eviction pops the oldest key from the `min_freq` bucket — LFU with LRU tie-breaking. All O(1), because a frequency only ever increases by exactly one.

**Wiring** — `LlmClient.generate()` checks the cache first, keyed by:
```python
SHA-256(model, temperature, system_instruction, prompt)
```
The cache is **injected from outside**: the CLI passes none (a single run rarely repeats a prompt), while the worker owns one process-lifetime `LRUCache(capacity=256)` shared across jobs.

### Why LRU is wired and LFU is not

Our access pattern is **bursty**: a developer re-pushes the same branch several times within an hour. That is textbook temporal locality → LRU.

LFU would win in a different deployment: one worker serving many repositories where a few shared modules (`models.py`, `utils.py`) appear in most PRs — there, popularity beats recency. We don't have that workload, so wiring LFU in would be **speculative complexity**. It is implemented, tested, documented, and deliberately unused. That is a defensible engineering position, not an oversight.

### Improvement it brings — measured

Two identical jobs run back-to-back through the worker:

| Run | LLM calls | Cache hits | Cache misses |
|---|---|---|---|
| Job 1 | 3 | 0 | 3 |
| Job 2 | **0** | **3** | 0 |

Four identical jobs in the local monitoring stack:
```
jobs_processed_total{status="processed"} 4
llm_calls_total                          3      ← not 12
llm_cache_hits_total                     9
llm_cache_misses_total                   3      ← 75% hit ratio
```

**In plain terms:** re-running an unchanged PR costs zero tokens and zero LLM latency.

### The bug that taught us the most

The cache initially **never hit across jobs** — hits stayed at 0 no matter how many identical jobs ran. Cause: the prompts embedded the **absolute path of the temporary clone directory**, which is different for every job. Byte-identical work produced different SHA-256 keys.

Nothing crashed. Nothing logged an error. The only symptom was a metric that stayed at zero.

**Fix:** prompts now identify files by module path and file name only — clone paths never appear. A regression test (`test_prompt_stability.py`) asserts that two different clone locations produce byte-identical prompts.

**The general lesson:** *a cache key must be built from normalised inputs. Any incidental variability in the input silently reduces the hit ratio to zero, and nothing tells you except a metric you thought to add.*

---

## 6. Addition 3 — Event-driven cloud architecture (`services/`, `infra/`)

### The problem in our project

The CLI/GitHub-Actions mode works, but it has structural limits: every repository must install the tool and configure credentials itself, the analysis runs inside the CI job's time budget, and there's no shared cache or central visibility across repositories.

A service model fixes that: one deployment, many repositories, work absorbed asynchronously.

### What we built

```
GitHub PR event (opened / synchronize / reopened)
      │  HTTPS + HMAC-SHA256 signature
      ▼
┌──────────────────────┐  Cloud Run · public · scale-to-zero
│  webhook-receiver    │  verify signature → filter event → publish job → 202
│  (100 lines)         │
└──────────┬───────────┘
           │ publish
           ▼
┌───────────────────────────────────────────────┐
│ Pub/Sub topic: pr-analysis-jobs               │
│  push subscription · ack deadline 600 s       │
│  5 delivery attempts → pr-analysis-jobs-dead-letter
└──────────┬────────────────────────────────────┘
           │ push, OIDC-authenticated
           ▼
┌──────────────────────┐  Cloud Run · private · concurrency = 1
│  analysis-worker     │  idempotency check → clone → pipeline → upload
│  (335 lines)         │
└───┬──────────────┬───┘
    ▼              ▼
 GCS bucket    GitHub commit status
 (artifacts)   (best-effort)
```

### Why each decision

**Why two services and not one?** They have *opposite* requirements. The receiver is public and must answer within GitHub's ~10-second webhook timeout. The worker runs for minutes (clone + LLM + pytest) and must not be publicly reachable. That conflict is the correct place to draw a service boundary — not "one service per noun".

**Why a queue between them?** Queue-based load levelling. A burst of ten PRs queues up instead of overwhelming the workers. The receiver's job finishes in milliseconds regardless of how long the analysis takes.

**Why push subscription rather than pull?** The worker stays a plain HTTP service — the same programming model as the receiver, no subscriber loop to run and supervise. The elegant consequence: **HTTP status codes become the queue protocol.**

| Worker response | Pub/Sub behaviour | When we use it |
|---|---|---|
| **200** | Acknowledge — done | Job succeeded, or was skipped as duplicate, or the message is permanently malformed |
| **500** | Retry, then dead-letter after 5 attempts | Transient failure: clone failed, LLM outage, unexpected error |

That distinction is important and easy to get wrong: **a malformed message returns 200**, not 500. Retrying a message that can never be parsed would loop forever and consume retry capacity. Only *transient* failures deserve retries.

**Why concurrency = 1 on the worker?** The pipeline shells out to `git` and `pytest`. One job per container keeps the mental model simple — no shared-state races, no interleaved subprocess output. Scaling happens by adding *instances*, which is what Cloud Run does automatically.

**How idempotency works.** Pub/Sub guarantees at-least-once delivery, so duplicates are certain, not hypothetical. Our dedup key is:
```
repo_full_name / pr_number / head_sha
```
which is also the GCS artifact prefix. Before doing any work, the worker checks whether `<prefix>/reports/ai-test-report.json` exists. If it does, the job is acknowledged without reprocessing. The marker is written **only on success**, so a job that crashed halfway is correctly replayed.

**Security posture:**
- The receiver is the only public surface, and HMAC-SHA256 signature verification is its gate — unsigned or wrongly-signed requests get 401 *before* the body is parsed.
- The worker is private (`--no-allow-unauthenticated`); only a dedicated service account holds `roles/run.invoker`.
- The GitHub token, when present, is injected into clone URLs but **never** appears in error messages — we deliberately re-raise git failures without `exc.cmd`, which would contain the token.

### Improvement it brings

| Before (CLI/Actions only) | After (service) |
|---|---|
| Each repo installs and configures the tool | One deployment serves many repos |
| Analysis runs inside the CI time budget | Asynchronous; CI is not blocked |
| Cache lives for one process run | Process-lifetime cache shared across jobs and repos |
| A crash loses the work | Message redelivered; job replayed |
| No central visibility | One metrics endpoint, one dashboard |
| Cost = CI minutes | Cost ≈ $0 idle (scale-to-zero) + Gemini calls |

### Verified in production

We deployed it and ran the drills:

| Check | Result |
|---|---|
| Unsigned webhook → receiver | **401** |
| Wrong signature → receiver | **401** |
| Signed webhook → receiver | **202** with a real Pub/Sub `message_id` |
| Pub/Sub → private worker (OIDC) | **200**, delivered |
| Worker → GCS | `ai-test-report.json` + `.md` uploaded |
| **Duplicate delivery** | `jobs_processed_total{processed}=1, {skipped}=1` — idempotency held |
| **Poison job** (broken env var) | retried 5×, landed in `pr-analysis-jobs-dead-letter`, pulled and inspected |

---

## 7. Addition 4 — Monitoring with Prometheus and Grafana (`monitoring/`)

### The problem in our project

Once the work moved behind a queue, the CLI's printed output stopped being the source of truth. Questions we could no longer answer by watching a terminal: Is it keeping up? How long do jobs take? **Is the cache actually saving anything?** What is this costing in tokens? Are generated tests any good?

### What we measure and why

| Metric | Type | The question it answers |
|---|---|---|
| `jobs_processed_total{status}` | Counter | Throughput and failure rate (`processed`/`failed`/`skipped`/`ignored`) |
| `job_duration_seconds` | Histogram | p95 duration — are we approaching the 600 s ack deadline? |
| `llm_calls_total` | Counter | How many calls actually reached Gemini |
| `llm_seconds_total` | Counter | Time spent waiting on the LLM (÷ calls = mean latency) |
| `llm_prompt_tokens_total` / `llm_response_tokens_total` | Counter | **Direct cost driver** |
| `llm_cache_hits_total` / `llm_cache_misses_total` | Counter | **Does the cache pay for itself?** |
| `generated_test_files_total{result}` | Counter | Quality KPI: what share of generated tests pass |

**Type choices:** everything monotonic is a Counter queried with `rate()`. Duration is a **Histogram**, not a Summary, because histogram buckets aggregate correctly across instances — `histogram_quantile(0.95, ...)` over many workers is meaningful; averaged per-instance quantiles are not.

**Two deliberate non-decisions** worth explaining:
1. **Queue depth is not our metric.** Pub/Sub already exports `num_undelivered_messages` to Cloud Monitoring. Re-measuring it in the app would produce strictly worse data.
2. **The receiver is not instrumented.** It does one cheap thing, and Cloud Run's built-in request count / latency / error metrics already cover it. *Custom metrics belong where custom logic is.*

### The local stack

`monitoring/docker-compose.yml` runs three containers: the **real worker image** (built from the same Dockerfile as production, with `DRY_RUN=true`), **Prometheus** scraping it every 5 seconds, and **Grafana** with the datasource and dashboard provisioned from files in git.

**Why this matters:** the observability demo needs no cloud, no credentials, and costs nothing — real clone, real pipeline, real pytest, stubbed LLM. Anyone can reproduce it with one command.

**Dashboards as code.** Both the datasource and the dashboard JSON live in `monitoring/grafana/`. Dashboards clicked together in a UI are undocumented, unreviewable, and lost when the volume dies. Ours are diffable and reproducible.

**Alerts** (`monitoring/alerts.yml`) — two rules, both about consequences rather than aesthetics:
- `HighJobFailureRate` — >20% of jobs failing over 15 minutes.
- `SlowAnalysisJobs` — p95 duration above 5 minutes for 10 minutes, because the Pub/Sub ack deadline is 600 s and crossing it causes redelivery and duplicated work.

Both use `for:` so a momentary blip doesn't page anyone, and `clamp_min` to avoid dividing by zero when there is no traffic.

### Improvement it brings

- **The cache optimisation is proven, not assumed** — the 75% hit ratio is a number on a dashboard.
- **Cost is visible** — token counters make Gemini spend a graph rather than a monthly surprise.
- **Quality is tracked** — `generated_test_files_total{result="passed"}` is the headline KPI of whether the tool is actually working.
- **Debugging got faster** — when the deployed worker started failing, `jobs_processed_total{status="failed"}` and the logs identified the cause in minutes.

---

## 8. Decisions we deliberately did *not* make

Restraint is a design contribution. Each of these was considered and rejected with a reason:

| Not built | Why |
|---|---|
| Multi-agent architecture | The task is a linear pipeline. Agents would add coordination complexity and non-determinism for zero benefit. |
| Plugin system / DAG executor | Ten steps in a fixed order. A `for` loop is the correct executor. |
| Database | Reports are files; artifacts are objects in a bucket. A database would add operational burden and back up nothing we need to query. |
| LFU wired into the pipeline | No workload where it beats LRU. Implemented and tested as the documented alternative. |
| Custom queue-depth metric | The platform already exports it better. |
| Instrumenting the receiver | Cloud Run's built-in metrics already cover it. |
| Auto-applying suggestions by default | Overwriting hand-written tests without review violates the project's core rule. It happens only on an explicit label. |
| Generated tests auto-committed by the label workflow | New files are a bigger decision than editing an existing one. The label applies *suggested updates* only; generated tests stay artifacts. |
| Exact-once delivery machinery | Impossible over an unreliable network. At-least-once + idempotent consumer gives exactly-once *effects*. |

## 9. Real incidents and what they taught

These all happened during development and verification. Each is a better lesson than any textbook example.

| Incident | Root cause | Lesson |
|---|---|---|
| **Cache never hit across jobs** | Absolute clone paths leaked into prompts → different hash per job | Cache keys must be built from **normalised** inputs; silent failure is only visible via metrics |
| **Every cloud job failed** | A malformed `GITHUB_TOKEN` env var (a comma split it into a bogus second variable) broke even public clones | Config errors look like code errors. Also: it gave us a genuine dead-letter demonstration |
| **Failures invisible in logs** | The error text went only into the HTTP response body, which Pub/Sub discards | If a caller discards your response, the response is not a log. Write to stderr |
| **`/healthz` returned 404 in cloud** | `/healthz` is a **reserved path** on Google's front end | Health and metrics paths interact with the platform in front of you — verify from outside |
| **Bot commit contained a service-account key** | `git add -A` after the GCP auth action, which writes `gha-creds-*.json` into the workspace | Never `git add -A` in a workflow that authenticates. Key was revoked, workflow now deletes creds and stages only source paths |
| **Generated filenames could collide** | Name derived from the file stem only | Derive artifact names from the repo-relative path |
| **`add` matched `address`** | Substring search in the related-test scan | Use word boundaries when matching identifiers |

## 10. Measured results

| Measurement | Value |
|---|---|
| Test suite | **77 passing** |
| Library size | 15 modules, ~1,700 lines |
| Services | 435 lines total (100 receiver + 335 worker) |
| Real Gemini run (2 changed files) | 2 test modules generated, **both passed pytest on first attempt** — no repair needed |
| Generated coverage example | `pricing.py` → 15 test methods covering normal, boundary, and error cases for `apply_discount` and `apply_tax` |
| Suggested update quality | Correctly tightened the `divide` assertion to the new error message **and** matched the existing file's non-parametrized style |
| Cache effect (4 identical jobs) | 3 LLM calls instead of 12; 75% hit ratio |
| Job duration (dry-run, local) | ~1.07 s average |
| Cloud idempotency drill | `processed=1, skipped=1` on duplicate delivery |
| Cloud DLQ drill | 5 retries → message in dead-letter topic, pulled and inspected |
| Idle cloud cost | ≈ $0 (both services scale to zero) |

## 11. How to run and verify each part

```bash
# 1. Everything, offline, no credentials, no cost
python -m pytest -q                      # 77 tests

# 2. Single-file generation against real Gemini
ai-test-assistant generate-tests --source calculator/pricing.py

# 3. Full PR analysis
ai-test-assistant run-pr-assistant --base-ref main

# 4. Same, but without touching Gemini
ai-test-assistant run-pr-assistant --base-ref main --dry-run

# 5. Apply suggested test updates (guarded: test files only)
ai-test-assistant apply-suggestions

# 6. Monitoring stack: worker + Prometheus + Grafana
cd monitoring && docker compose up --build
python send_test_job.py --repeat 5
#   worker      http://localhost:8080/metrics
#   Prometheus  http://localhost:9090
#   Grafana     http://localhost:3000  (dashboard pre-provisioned)

# 7. Cloud deployment (creates billable resources)
bash infra/deploy.sh
```

## 12. Current state and honest limitations

**Working and verified:** the library and all 77 tests; CLI in real and dry-run mode; GitHub Actions workflows; the label-triggered apply flow; the local Prometheus/Grafana stack; and the full cloud pipeline including idempotency and dead-letter drills.

**Known limitations:**
- Python and pytest only.
- Related-test detection is heuristic — it can miss or over-include.
- Generated tests **require human review**: they can encode a bug as expected behaviour, over-mock, or assert tautologies.
- Coverage measurement is out of scope.
- The response cache is per-process — a worker restart loses it, and multiple instances don't share it. A shared cache would need Redis.
- `CacheDeltaCounter` assumes `concurrency = 1`; concurrent jobs would need a lock.
- The cloud worker needs a valid `GITHUB_TOKEN` to clone private repositories.

---

# Русская версия

## 1. Что это за проект — одна страница

Разработчик открывает pull request. Где-то внутри изменилась публичная функция или появилась новая. Ассистент это замечает, читает диф, определяет, какие именно функции изменились, просит Gemini написать для них pytest-тесты, **запускает эти тесты**, чинит их при падении и отдаёт разработчику артефакт для ревью — плюс предложенное обновление для тех рукописных тестов, которые изменение сломало.

Всё подчинено трём правилам:

| Правило | Почему важно |
|---|---|
| Никогда не менять продакшен-код | Инструмент — ассистент, а не автор. Генератор тестов, правящий исходники, это риск. |
| Никогда не перезаписывать существующие тесты автоматически | Рукописные тесты кодируют человеческое намерение. Их перезаписывают только по явному действию человека. |
| Никогда не коммитить автоматически | Всё попадает в артефакт для ревью или в помеченный бот-коммит. Контроль остаётся у человека. |

Проект работает в **двух режимах из одной кодовой базы**:

```
РЕЖИМ 1 — CLI / GitHub Actions        РЕЖИМ 2 — облачный сервис
разработчик запускает команду,        приходит вебхук GitHub,
или это делает workflow в CI          два сервиса Cloud Run обрабатывают асинхронно
        │                                       │
        └───────────────┬───────────────────────┘
                        ▼
              один и тот же пакет `ai_test_assistant`
                (один пайплайн, один набор тестов)
```

Это самое важное структурное решение проекта: облачные сервисы — тонкие HTTP-обёртки вокруг той же библиотеки, которую вызывает CLI. Дублирующейся бизнес-логики, способной разойтись, попросту нет.

## 2. Карта репозитория

```
ai_test_assistant/          библиотека — 15 модулей, ~1700 строк
├── cli.py                  CLI на Typer: 3 команды
├── config.py               настройки: CLI > env > .env > YAML > умолчания
├── models.py               общие датаклассы
├── git_utils.py            какие файлы и строки изменились
├── source_analyzer.py      разбор AST → публичные функции и методы
├── import_graph.py         ⭐ топологическая сортировка изменённых файлов
├── test_finder.py          поиск связанных существующих тестов
├── llm_client.py           Vertex AI/Gemini + ⭐ кеш ответов + статистика
├── cache.py                ⭐ LRU и LFU, написанные с нуля
├── prompts.py              весь текст промптов в одном месте
├── test_generator.py       генерация / обновление / починка + валидация
├── pytest_runner.py        запуск pytest в подпроцессе
├── report.py               отчёты Markdown + JSON
└── pipeline.py             оркестратор

services/                   ⭐ облачное развёртывание
├── webhook_receiver/       публичный сервис Cloud Run (100 строк)
└── analysis_worker/        приватный сервис Cloud Run (335 строк)

monitoring/                 ⭐ стек Prometheus + Grafana (docker-compose)
infra/                      deploy.sh + конфиги Cloud Build
tests/                      77 тестов (юнит + сервисные)
docs/                       документация
```

⭐ — добавлено в рамках PDP; остальное — исходный MVP.

## 3. Базовый пайплайн — то, что было до PDP-доработок

Сознательно **линейный**: вход → преобразование → выход. Без фреймворка, без плагинов, без DAG-исполнителя.

```
1. get_changed_python_files()    git diff → какие .py и какие строки изменились
2. order_files_by_imports()      ⭐ порядок зависимостей (добавлено позже — §4)
3. analyze_source_file()         AST → публичные функции, классы, методы
4. select_test_targets()         какие из них пересекают изменённые строки
5. find_related_tests()          какие существующие тесты затрагивают эти цели
6. generate_tests()              Gemini → модуль pytest
7. валидация + запись            проверка разбором, затем запись в tests/generated/
8. run_pytest()                  реальный запуск
9. цикл починки                  при падении вывод pytest уходит обратно в Gemini (≤2×)
10. update_existing_tests()      предложение переписать связанные рукописные тесты
11. запись отчётов               Markdown + JSON
```

### 3.1 Обнаружение изменений — `git_utils.py`

Выполняем `git diff --unified=0 <base>...HEAD` и разбираем заголовки ханков, получая **точные номера изменённых строк**, а не только имена файлов.

**Зачем нужны строки:** PR, добавивший одну функцию в модуль на 500 строк, должен породить тесты для *этой функции*, а не для всех двадцати. Точность до строки удерживает и стоимость токенов, и объём ревью пропорциональными размеру изменения.

**Правило фильтрации** (`is_production_python_file`) исключает тестовые файлы, `*_generated.py` и пути из конфигурации. Маленькая функция с большой ролью в безопасности: именно она не даёт ассистенту нацелиться на собственный вывод и уйти в петлю обратной связи.

**Плавная деградация:** если диф разобрать не удалось, множество изменённых строк оказывается пустым, и анализатор выбирает *все* публичные цели. Хуже, но не сломано.

### 3.2 Анализ исходников — `source_analyzer.py`

Чистый разбор через `ast` — никаких регулярных выражений по тексту.

- Обходит тело модуля, собирает публичные функции (имя не начинается с `_`) и публичные классы с их публичными методами.
- Восстанавливает читаемую сигнатуру (значения по умолчанию, `*args`, keyword-only, аннотации, тип возврата).
- Извлекает исходный код цели через `ast.get_source_segment`.
- `select_test_targets()` оставляет только цели, чей диапазон строк **пересекается** с изменёнными.

**Почему AST, а не регулярки:** декораторы, многострочные сигнатуры, вложенные определения и `async def` ломают наивный текстовый поиск. AST — это понимание файла самим языком, и оно есть в стандартной библиотеке, то есть бесплатно по зависимостям.

### 3.3 Поиск связанных тестов — `test_finder.py`

Две дополняющие эвристики: **соглашения об именах и путях** (`tests/test_<stem>.py`, зеркальная раскладка, `tests/<stem>_test.py`) и **сканирование содержимого** тестовых файлов на упоминание модуля или имён целей.

Сканирование использует **регулярку с границами слова**, чтобы функция `add` не совпадала со словом `address`. Это был реальный баг: подстрочный поиск затягивал в промпт посторонние тестовые файлы, тратя токены и добавляя шум.

**Почему эвристики, а не анализ графа вызовов:** цель — дать LLM полезный контекст, а не быть доказуемо полными. Ложное срабатывание стоит нескольких токенов; полноценный статический граф вызовов стоил бы недель и всё равно не покрыл бы динамическую диспетчеризацию. Это записано как ограничение, а не спрятано.

### 3.4 Граница с LLM — `llm_client.py` + `prompts.py`

**С Gemini разговаривает ровно один модуль.** Всё остальное не знает о провайдере. При замене Vertex AI на Bedrock меняется ровно один файл.

- **`temperature = 0.0`** — нужны воспроизводимые заготовки тестов, а не творческая вариативность. Это же делает кеширование ответов **корректным** (§5).
- **Весь текст промптов в `prompts.py`** — три системные инструкции (генерация / починка / обновление) и три построителя, возвращающие `(системная_инструкция, пользовательский_промпт)`. Промпты проходят код-ревью, а не рассыпаны по f-строкам.
- **Ленивый импорт SDK** — `google-genai` импортируется внутри функции, поэтому юнит-тесты работают без облачного SDK.
- **Режим `dry_run`** — возвращает фиксированную заглушку и делает **ноль** сетевых вызовов. Именно поэтому весь набор тестов и локальное демо мониторинга бесплатны и работают офлайн.

### 3.5 Валидация — `test_generator.py`

Вывод LLM — недоверенный вход. Каждый ответ проходит:

```
сырой ответ
  → clean_llm_python_response()   срезать ```python-ограждения, обратные кавычки, пробелы
  → validate_python_test_code()   не пустой
                                  разбирается через ast.parse()
                                  содержит функцию test_ или класс Test
                                  не содержит shell-шебанг
  → запись на диск
```

**Зачем:** без валидации болтливый ответ модели («Конечно! Вот ваши тесты:») запишется в `.py` и сломает прогон тестов у разработчика. С валидацией плохой ответ даёт аккуратную ошибку по файлу в отчёте, а пайплайн идёт дальше.

### 3.6 Выполнение и починка — `pytest_runner.py` + цикл в `pipeline.py`

Сгенерированные тесты **выполняются**, а не просто записываются: `subprocess.run([sys.executable, "-m", "pytest", "-q", ...])` с таймаутом, с захватом stdout/stderr, без исключения при падении тестов.

При падении пайплайн отправляет в Gemini исходник, текущий код тестов и **вывод pytest** с промптом починки, до `repair_attempts` (по умолчанию 2) раз.

**Почему цикл починки — самая ценная функция:** разница между «ИИ написал какие-то тесты» и «ИИ написал проходящие тесты» на практике огромна. Большинство падений с первой попытки тривиальны — неверный путь импорта, сравнение float на точное равенство, неточно вспомненный текст ошибки — и модель исправляет их сразу, увидев трейсбек.

**Безопасность:** выполняется только Python, прошедший валидацию AST, и только через pytest в подпроцессе с таймаутом. Shell-команды из вывода LLM не выполняются никогда.

### 3.7 Результаты — `report.py` и правила записи файлов

| Артефакт | Путь | Шапка |
|---|---|---|
| Сгенерированные тесты | `tests/generated/test_<путь>_generated.py` | «сгенерировано ассистентом — проверьте перед коммитом» |
| Предложенные обновления | `reports/suggested-tests/<исходный путь>` | «предложение — проверьте перед заменой оригинала» |
| Отчёт для человека | `reports/ai-test-report.md` | — |
| Отчёт для машины | `reports/ai-test-report.json` | — |

Имя сгенерированного файла выводится из **пути относительно репозитория** (`calculator/pricing.py` → `test_calculator_pricing_generated.py`), поэтому два модуля с одинаковым именем в разных пакетах не конфликтуют — этот баг нашли и починили при аудите.

**Изоляция ошибок:** каждый файл обрабатывается в своём try/except. Падение одного — плохой синтаксис, ошибка LLM, провал валидации — даёт запись `error` в отчёте, остальные продолжают обрабатываться. PR из пяти файлов не теряет работу по четырём из-за одного.

---

## 4. Доработка 1 — топологическая сортировка (`import_graph.py`)

### Проблема в нашем проекте

PR меняет и `models.py`, и `service.py`, причём `service.py` импортирует `models`. Порядок обработки брался из `git diff`, то есть был фактически произвольным. Если первым обрабатывается `service.py`, тесты для него генерируются, когда его зависимость пайплайном ещё не рассмотрена — и порядок меняется между запусками, делая вывод невоспроизводимым.

### Что сделали

`order_files_by_imports()` — алгоритм Кана по изменённым файлам:

1. Разбор импортов каждого файла через `ast` (`import x`, `from x import y` и относительные импорты, разрешаемые относительно пакета файла).
2. Построение графа **только по изменённым файлам**: ребро `A → B` означает «B импортирует A».
3. Алгоритм Кана: выдавать вершины с нулевой входящей степенью, уменьшать степени соседей, повторять.
4. Ничьи разрешаются по **исходному порядку файлов** — результат детерминирован.
5. Если вершины остались, они образуют цикл: сохраняем их исходный порядок и записываем в `import_cycle_files`.

### Почему именно так

| Решение | Причина |
|---|---|
| **Кан, а не DFS** | Обнаружение цикла бесплатно (выдано < числа вершин), код итеративный — нет вопросов о глубине рекурсии. |
| **В графе только изменённые файлы** | Внешние импорты не влияют на *порядок обработки*. Ограничение графа делает его крошечным (обычно меньше десяти вершин) и упрощает код. |
| **Цикл не прерывает работу** | Цикл импортов — запах кода в *анализируемом* проекте. Отказ генерировать тесты из-за него был бы неверным продуктовым решением. Деградируем до исходного порядка и сообщаем. |
| **Детерминированное разрешение ничьих** | Результат попадает в промпты LLM, кешируемые по хешу. Недетерминированный порядок молча снижал бы хитрейт. |

### Что это даёт

- **Корректный порядок контекста** — зависимости анализируются раньше зависящих.
- **Воспроизводимость** — один и тот же PR всегда даёт один и тот же порядок обработки.
- **Бесплатная диагностика** — циклы импортов теперь видны в отчёте как побочный эффект.
- **Цена:** ~120 строк, без зависимостей, O(V+E) — неизмеримо мало на фоне многосекундного вызова LLM.

### Баг, о котором стоит знать

Наивное `in_degree[v] += 1` на каждое разобранное ребро ломается, когда одно и то же ребро обнаруживается дважды (модуль импортирован в двух строках): степень никогда не достигает нуля, вершина молча исчезает из результата и выглядит как фантомный цикл. Защищаемся проверкой принадлежности множеству перед инкрементом.

---

## 5. Доработка 2 — кеши LRU / LFU (`cache.py`)

### Проблема в нашем проекте

При `temperature = 0` ответ Gemini на одинаковый промпт детерминирован. При этом одинаковые промпты отправляются постоянно: разработчик делает rebase и пушит заново → те же файлы, те же промпты; Pub/Sub переотправляет сообщение (at-least-once) → задание выполняется снова; два PR затрагивают один неизменившийся модуль.

Каждый повтор стоит денег и нескольких секунд ожидания ради ответа, который мы могли бы предсказать точно.

### Что сделали

**Обе политики с нуля**, без `functools.lru_cache` и без библиотек:

**`LRUCache`** — хеш-таблица + двусвязный список с фиктивными узлами-часовыми. `get` выдёргивает узел и вставляет за головой; `put` при переполнении удаляет `tail.prev`. Обе операции O(1), без сканирования.

**`LFUCache`** — `ключ→значение`, `ключ→частота`, `частота→OrderedDict ключей` и указатель `min_freq`. Обращение переносит ключ из корзины *f* в *f+1*; вытесняется самый старый ключ из корзины `min_freq` — LFU с разрешением ничьих по LRU. Всё O(1), потому что частота растёт строго на единицу.

**Подключение** — `LlmClient.generate()` сначала проверяет кеш по ключу:
```python
SHA-256(модель, температура, системная_инструкция, промпт)
```
Кеш **внедряется извне**: CLI не передаёт его (в одном запуске промпты почти не повторяются), а воркер владеет одним `LRUCache(capacity=256)` на весь процесс, общим для всех заданий.

### Почему LRU подключён, а LFU нет

Наш паттерн доступа **всплесковый**: разработчик несколько раз за час пушит одну ветку. Это учебниковая временная локальность → LRU.

LFU выиграл бы при другом развёртывании: один воркер на много репозиториев, где несколько общих модулей (`models.py`, `utils.py`) встречаются в большинстве PR — там популярность важнее свежести. Такой нагрузки у нас нет, поэтому подключение LFU было бы **спекулятивным усложнением**. Он реализован, покрыт тестами, задокументирован и сознательно не используется. Это защитимая инженерная позиция, а не недоработка.

### Что это даёт — измерено

Два одинаковых задания подряд через воркер:

| Запуск | Вызовы LLM | Попадания | Промахи |
|---|---|---|---|
| Задание 1 | 3 | 0 | 3 |
| Задание 2 | **0** | **3** | 0 |

Четыре одинаковых задания в локальном стеке мониторинга:
```
jobs_processed_total{status="processed"} 4
llm_calls_total                          3      ← а не 12
llm_cache_hits_total                     9
llm_cache_misses_total                   3      ← хитрейт 75%
```

**Простыми словами:** повторный прогон неизменившегося PR стоит ноль токенов и ноль секунд ожидания LLM.

### Баг, который научил большему всего

Изначально кеш **никогда не срабатывал между заданиями** — попадания оставались нулевыми при любом числе одинаковых заданий. Причина: в промпты попадал **абсолютный путь временного каталога клона**, разный у каждого задания. Байт-идентичная работа давала разные ключи SHA-256.

Ничего не падало. Ничего не логировалось как ошибка. Единственным симптомом была метрика, застрявшая на нуле.

**Исправление:** промпты идентифицируют файлы только модульным путём и именем файла — пути клона не появляются нигде. Регрессионный тест (`test_prompt_stability.py`) проверяет, что два разных каталога клона дают байт-идентичные промпты.

**Общий урок:** *ключ кеша должен строиться из нормализованных входных данных. Любая случайная изменчивость входа молча обнуляет хитрейт, и об этом не сообщит ничего, кроме метрики, которую вы догадались добавить.*

---

## 6. Доработка 3 — событийная облачная архитектура (`services/`, `infra/`)

### Проблема в нашем проекте

Режим CLI/GitHub Actions работает, но структурно ограничен: каждый репозиторий должен сам ставить инструмент и настраивать доступы, анализ идёт внутри бюджета времени CI-задания, и нет ни общего кеша, ни централизованной наблюдаемости.

Сервисная модель это решает: одно развёртывание, много репозиториев, работа поглощается асинхронно.

### Что сделали

```
Событие PR в GitHub (opened / synchronize / reopened)
      │  HTTPS + подпись HMAC-SHA256
      ▼
┌──────────────────────┐  Cloud Run · публичный · scale-to-zero
│  webhook-receiver    │  проверил подпись → отфильтровал → опубликовал → 202
└──────────┬───────────┘
           ▼
┌───────────────────────────────────────────────┐
│ Топик Pub/Sub: pr-analysis-jobs               │
│  push-подписка · ack deadline 600 с           │
│  5 попыток → pr-analysis-jobs-dead-letter     │
└──────────┬────────────────────────────────────┘
           │ push с аутентификацией OIDC
           ▼
┌──────────────────────┐  Cloud Run · приватный · concurrency = 1
│  analysis-worker     │  идемпотентность → clone → пайплайн → выгрузка
└───┬──────────────┬───┘
    ▼              ▼
 GCS-бакет     commit status в GitHub
```

### Обоснование каждого решения

**Почему два сервиса, а не один?** У них *противоположные* требования. Приёмник публичен и обязан ответить в пределах ~10-секундного таймаута вебхука GitHub. Воркер работает минутами (clone + LLM + pytest) и не должен быть доступен извне. Этот конфликт — правильное место для границы сервиса, а не «один сервис на существительное».

**Зачем очередь между ними?** Выравнивание нагрузки. Всплеск из десяти PR встаёт в очередь, а не сносит воркеры. Работа приёмника завершается за миллисекунды независимо от длительности анализа.

**Почему push-подписка, а не pull?** Воркер остаётся обычным HTTP-сервисом — та же модель, что у приёмника, без цикла подписчика, который нужно запускать и присматривать за ним. Изящное следствие: **HTTP-коды становятся протоколом очереди.**

| Ответ воркера | Поведение Pub/Sub | Когда используем |
|---|---|---|
| **200** | Подтвердить — готово | Задание успешно, пропущено как дубликат, или сообщение неисправимо некорректно |
| **500** | Повторить, после 5 попыток — в DLQ | Временный сбой: не удался clone, недоступен LLM, неожиданная ошибка |

Это различие важно и легко ошибиться: **некорректное сообщение возвращает 200**, а не 500. Повтор сообщения, которое невозможно разобрать, крутился бы вечно и жёг мощность ретраев. Повторов заслуживают только *временные* сбои.

**Почему concurrency = 1 у воркера?** Пайплайн вызывает внешние `git` и `pytest`. Одно задание на контейнер сохраняет простую ментальную модель — никаких гонок за общим состоянием, никакого перемешанного вывода подпроцессов. Масштабирование идёт *инстансами*, что Cloud Run делает автоматически.

**Как работает идемпотентность.** Pub/Sub гарантирует доставку at-least-once, поэтому дубликаты неизбежны, а не гипотетичны. Ключ дедупликации:
```
repo_full_name / pr_number / head_sha
```
он же префикс артефактов в GCS. Перед любой работой воркер проверяет наличие `<префикс>/reports/ai-test-report.json`. Если он есть — задание подтверждается без повторной обработки. Маркер пишется **только при успехе**, поэтому упавшее на середине задание корректно переигрывается.

**Безопасность:**
- Приёмник — единственная публичная поверхность, и проверка подписи HMAC-SHA256 является его барьером: неподписанные и неверно подписанные запросы получают 401 *до* разбора тела.
- Воркер приватный (`--no-allow-unauthenticated`), `roles/run.invoker` есть только у выделенного сервисного аккаунта.
- Токен GitHub, если задан, подставляется в URL клонирования, но **никогда** не попадает в сообщения об ошибках — мы сознательно перевыбрасываем ошибки git без `exc.cmd`, где содержался бы токен.

### Что это даёт

| Было (только CLI/Actions) | Стало (сервис) |
|---|---|
| Каждый репозиторий ставит и настраивает инструмент | Одно развёртывание обслуживает много репозиториев |
| Анализ внутри бюджета времени CI | Асинхронно, CI не блокируется |
| Кеш живёт один запуск процесса | Кеш на весь процесс, общий для заданий и репозиториев |
| Падение теряет работу | Сообщение переотправляется, задание переигрывается |
| Нет централизованной видимости | Один эндпоинт метрик, один дашборд |
| Стоимость = минуты CI | ≈ $0 в простое (scale-to-zero) + вызовы Gemini |

### Проверено в реальном развёртывании

| Проверка | Результат |
|---|---|
| Вебхук без подписи | **401** |
| Неверная подпись | **401** |
| Подписанный вебхук | **202** с настоящим `message_id` |
| Pub/Sub → приватный воркер (OIDC) | **200**, доставлено |
| Воркер → GCS | Загружены `ai-test-report.json` и `.md` |
| **Дублирующая доставка** | `jobs_processed_total{processed}=1, {skipped}=1` — идемпотентность сработала |
| **Ядовитое задание** (сломанная переменная окружения) | 5 повторов, ушло в `pr-analysis-jobs-dead-letter`, извлечено и разобрано |

---

## 7. Доработка 4 — мониторинг на Prometheus и Grafana (`monitoring/`)

### Проблема в нашем проекте

Как только работа ушла за очередь, вывод CLI перестал быть источником истины. Вопросы, на которые больше нельзя ответить, глядя в терминал: справляемся ли? сколько длятся задания? **экономит ли кеш хоть что-нибудь?** сколько это стоит в токенах? хороши ли сгенерированные тесты?

### Что измеряем и зачем

| Метрика | Тип | На какой вопрос отвечает |
|---|---|---|
| `jobs_processed_total{status}` | Counter | Пропускная способность и доля отказов |
| `job_duration_seconds` | Histogram | p95 длительности — не подходим ли к ack deadline 600 с? |
| `llm_calls_total` | Counter | Сколько вызовов реально дошло до Gemini |
| `llm_seconds_total` | Counter | Время ожидания LLM (÷ вызовы = средняя задержка) |
| `llm_prompt_tokens_total` / `llm_response_tokens_total` | Counter | **Прямой драйвер стоимости** |
| `llm_cache_hits_total` / `llm_cache_misses_total` | Counter | **Окупается ли кеш?** |
| `generated_test_files_total{result}` | Counter | KPI качества: доля проходящих сгенерированных тестов |

**Выбор типов:** всё монотонное — Counter, запрашиваемый через `rate()`. Длительность — **Histogram**, а не Summary, потому что корзины гистограммы корректно агрегируются между инстансами: `histogram_quantile(0.95, ...)` по многим воркерам осмыслен, а усреднённые поинстансные квантили — нет.

**Два осознанных «не-решения»:**
1. **Глубина очереди — не наша метрика.** Pub/Sub уже экспортирует `num_undelivered_messages` в Cloud Monitoring. Собственный замер дал бы строго худшие данные.
2. **Приёмник не инструментирован.** Он делает одну дешёвую вещь, а Cloud Run из коробки даёт счётчики запросов, задержку и ошибки. *Кастомные метрики нужны там, где кастомная логика.*

### Локальный стек

`monitoring/docker-compose.yml` поднимает три контейнера: **реальный образ воркера** (собранный тем же Dockerfile, что и продакшен, с `DRY_RUN=true`), **Prometheus** со сбором раз в 5 секунд и **Grafana** с источником данных и дашбордом, провижининг которых описан файлами в git.

**Почему это важно:** демонстрация наблюдаемости не требует ни облака, ни учётных данных и ничего не стоит — настоящий clone, настоящий пайплайн, настоящий pytest, заглушенный LLM. Воспроизводится одной командой.

**Дашборды как код.** Дашборды, накликанные в UI, недокументированы, нерецензируемы и теряются вместе с томом. Наши — в git, они diff'аются и воспроизводятся.

**Алерты** (`monitoring/alerts.yml`) — два правила, оба о последствиях, а не об эстетике: `HighJobFailureRate` (>20% падений за 15 минут) и `SlowAnalysisJobs` (p95 > 5 минут в течение 10 минут, потому что ack deadline составляет 600 с, и его пересечение вызывает переотправку и двойную работу). Оба используют `for:`, чтобы мгновенный всплеск никого не будил, и `clamp_min` против деления на ноль при отсутствии трафика.

### Что это даёт

- **Оптимизация кешем доказана, а не постулирована** — 75% хитрейта это число на дашборде.
- **Стоимость видна** — счётчики токенов превращают расходы на Gemini в график, а не в сюрприз в конце месяца.
- **Качество отслеживается** — `generated_test_files_total{result="passed"}` это главный KPI работоспособности инструмента.
- **Отладка ускорилась** — когда развёрнутый воркер начал падать, `jobs_processed_total{status="failed"}` и логи выявили причину за минуты.

---

## 8. Что мы сознательно НЕ делали

Сдержанность — тоже вклад в дизайн. Каждый пункт рассматривался и был отклонён с обоснованием:

| Не сделано | Почему |
|---|---|
| Мультиагентная архитектура | Задача — линейный пайплайн. Агенты добавили бы сложность координации и недетерминизм без выигрыша. |
| Плагины / DAG-исполнитель | Десять шагов в фиксированном порядке. Правильный исполнитель — цикл `for`. |
| База данных | Отчёты — файлы, артефакты — объекты в бакете. БД добавила бы эксплуатацию и не хранила бы ничего, что нужно запрашивать. |
| Подключение LFU в пайплайн | Нет нагрузки, где он превосходит LRU. Реализован и протестирован как задокументированная альтернатива. |
| Своя метрика глубины очереди | Платформа уже экспортирует её лучше. |
| Инструментирование приёмника | Встроенные метрики Cloud Run уже покрывают. |
| Автоприменение предложений по умолчанию | Перезапись рукописных тестов без ревью нарушает базовое правило проекта. Происходит только по явной метке. |
| Автокоммит сгенерированных тестов | Новые файлы — более крупное решение, чем правка существующего. Метка применяет только *предложенные обновления*. |
| Механика exactly-once доставки | Невозможна поверх ненадёжной сети. At-least-once + идемпотентный консьюмер дают exactly-once по эффекту. |

## 9. Реальные инциденты и чему они научили

Всё это случилось при разработке и проверке. Каждый случай — лучший урок, чем любой учебный пример.

| Инцидент | Первопричина | Урок |
|---|---|---|
| **Кеш не срабатывал между заданиями** | Абсолютные пути клона попадали в промпты → разный хеш у каждого задания | Ключ кеша строится из **нормализованных** входных данных; молчаливый отказ виден только по метрике |
| **Все облачные задания падали** | Некорректная переменная `GITHUB_TOKEN` (запятая разбила её на фиктивную вторую) ломала даже публичные clone | Ошибки конфигурации выглядят как ошибки кода. Заодно это дало настоящую демонстрацию dead-letter |
| **Отказы не видны в логах** | Текст ошибки уходил только в тело HTTP-ответа, которое Pub/Sub выбрасывает | Если вызывающий выбрасывает ваш ответ, ответ не является логом. Писать в stderr |
| **`/healthz` возвращал 404 в облаке** | `/healthz` — **зарезервированный путь** во фронтенде Google | Пути health и metrics взаимодействуют с платформой перед вами — проверять снаружи |
| **Бот-коммит содержал ключ сервисного аккаунта** | `git add -A` после экшена аутентификации GCP, который пишет `gha-creds-*.json` в рабочую директорию | Никогда не использовать `git add -A` в workflow с аутентификацией. Ключ отозван, workflow теперь удаляет учётные данные и добавляет только исходники |
| **Имена сгенерированных файлов конфликтовали** | Имя выводилось только из stem файла | Имена артефактов выводить из пути относительно репозитория |
| **`add` совпадал с `address`** | Подстрочный поиск при сканировании тестов | Использовать границы слов при поиске идентификаторов |

## 10. Измеренные результаты

| Показатель | Значение |
|---|---|
| Набор тестов | **77 проходят** |
| Размер библиотеки | 15 модулей, ~1700 строк |
| Сервисы | 435 строк (100 приёмник + 335 воркер) |
| Реальный прогон с Gemini (2 изменённых файла) | 2 модуля тестов, **оба прошли pytest с первой попытки** — починка не понадобилась |
| Пример покрытия | `pricing.py` → 15 тест-методов на нормальные, граничные и ошибочные случаи для `apply_discount` и `apply_tax` |
| Качество предложенного обновления | Корректно уточнило проверку `divide` под новое сообщение **и** сохранило непараметризованный стиль исходного файла |
| Эффект кеша (4 одинаковых задания) | 3 вызова LLM вместо 12; хитрейт 75% |
| Длительность задания (dry-run, локально) | ~1.07 с в среднем |
| Проверка идемпотентности в облаке | `processed=1, skipped=1` при дублирующей доставке |
| Проверка DLQ в облаке | 5 повторов → сообщение в dead-letter, извлечено и разобрано |
| Стоимость простоя в облаке | ≈ $0 (оба сервиса сворачиваются до нуля) |

## 11. Как запустить и проверить каждую часть

```bash
# 1. Всё офлайн, без учётных данных и затрат
python -m pytest -q                      # 77 тестов

# 2. Генерация по одному файлу через реальный Gemini
ai-test-assistant generate-tests --source calculator/pricing.py

# 3. Полный анализ PR
ai-test-assistant run-pr-assistant --base-ref main

# 4. То же, но без обращения к Gemini
ai-test-assistant run-pr-assistant --base-ref main --dry-run

# 5. Применить предложенные обновления (с защитой: только тестовые файлы)
ai-test-assistant apply-suggestions

# 6. Стек мониторинга: воркер + Prometheus + Grafana
cd monitoring && docker compose up --build
python send_test_job.py --repeat 5
#   воркер      http://localhost:8080/metrics
#   Prometheus  http://localhost:9090
#   Grafana     http://localhost:3000  (дашборд уже провижинен)

# 7. Развёртывание в облако (создаёт платные ресурсы)
bash infra/deploy.sh
```

## 12. Текущее состояние и честные ограничения

**Работает и проверено:** библиотека и все 77 тестов; CLI в реальном и dry-run режимах; workflow GitHub Actions; применение предложений по метке; локальный стек Prometheus/Grafana; полный облачный пайплайн, включая проверки идемпотентности и dead-letter.

**Известные ограничения:**
- Только Python и только pytest.
- Поиск связанных тестов эвристический — возможны пропуски и лишние срабатывания.
- Сгенерированные тесты **требуют ревью человеком**: они могут закрепить баг как ожидаемое поведение, чрезмерно замокать зависимости или содержать тавтологические проверки.
- Измерение покрытия вне области.
- Кеш ответов живёт в процессе — рестарт воркера его теряет, несколько инстансов не делят его. Для общего кеша нужен Redis.
- `CacheDeltaCounter` рассчитан на `concurrency = 1`; при конкурентных заданиях понадобилась бы блокировка.
- Облачному воркеру нужен валидный `GITHUB_TOKEN` для клонирования приватных репозиториев.
