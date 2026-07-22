# How This Project Works

A complete walkthrough of the AI Unit Test Assistant: what it does, what
each component is, why it was chosen, and what measurable improvement it
brings.

This document is the **project-first** companion to `docs/exam/`, which
covers the same technologies theory-first.

---

## 1. The problem and the shape of the solution

**The problem.** Writing unit tests is mechanical work that consumes a
disproportionate share of pull-request time, and refactoring is worse: change
one public behaviour and twenty existing tests break, each needing a manual
edit that is tedious but not intellectually hard.

**The solution.** A tool that reads the diff of a pull request, works out
which public functions changed, asks a language model for tests, *runs* those
tests, repairs them if they fail, and writes everything into review
artefacts — without ever touching production code or overwriting a
hand-written test.

**The core design constraint** that shapes everything else:

> The assistant produces **suggestions**, never facts. A human decides what
> enters the repository.

That constraint is why generated tests go to `tests/generated/`, why updated
tests go to `reports/suggested-tests/` instead of over the originals, why
nothing is auto-committed, and why applying suggestions requires an explicit
action (a CLI command or a PR label).

**Scale of the implementation:** ~2 470 lines of Python across 16 modules,
covered by 77 tests. Small enough to read in an afternoon — that is
deliberate.

---

## 2. The three ways it runs

The same pipeline code has three entry points. This matters: the business
logic exists **once**, as a library, and each surface is a thin wrapper.

### 2.1 Local CLI — the developer loop

```bash
ai-test-assistant run-pr-assistant --base-ref main
```

Fastest feedback, used while developing. Reads `.env` and
`ai-test-assistant.yml` from the working directory.

### 2.2 GitHub Actions — the team loop

Two workflows in the target repository:

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `ai-test-assistant.yml` | every PR touching `**/*.py` | Runs the assistant, writes the report to the run summary, uploads generated tests + reports as an artefact |
| `apply-ai-suggestions.yml` | adding the `apply-ai-suggestions` label to a PR | Re-runs the assistant, applies the suggested test updates, commits and pushes back to the PR branch |

The second workflow is the "one-click apply" button: instead of downloading an
artefact and copying files by hand, a maintainer adds a label and the bot
opens a reviewable commit.

### 2.3 Cloud service — the organisation loop

A deployed, event-driven system that any repository can point a webhook at,
with no per-repository CI configuration:

```
GitHub PR event
   │  HTTPS webhook, HMAC-SHA256 signed
   ▼
webhook-receiver        Cloud Run, public, scales to zero
   │  verify signature → filter event → publish job → 202 Accepted
   ▼
Pub/Sub  pr-analysis-jobs
   │  push subscription, OIDC auth, 600 s ack deadline,
   │  5 delivery attempts → dead-letter topic
   ▼
analysis-worker         Cloud Run, private, concurrency = 1
   │  idempotency check → clone → analyse → generate → pytest
   ├──▶ Cloud Storage    artefacts (reports, generated tests)
   └──▶ GitHub API       commit status (best-effort)
```

---

## 3. The core pipeline, stage by stage

Everything below lives in `ai_test_assistant/` and runs identically in all
three modes. `pipeline.run_pr_assistant()` is the orchestrator; it is
deliberately linear and readable top to bottom.

### Stage 1 — Detect changed files · `git_utils.py`

**What:** runs `git diff --name-only <base_ref>...HEAD`, then per file
`git diff --unified=0` to parse the changed **line numbers** from hunk
headers.

**Why line numbers matter:** they let the next stage test only what actually
changed, instead of regenerating tests for an entire file on every commit —
less LLM cost, less noise in the diff.

**Filtering** (`is_production_python_file`): keeps `*.py`, and excludes test
files (`test_*.py`, `*_test.py`), previously generated files
(`*_generated.py`), anything under `tests/`, and every path in
`exclude_paths`. This is the first line of defence for "never analyse or
modify our own output."

### Stage 2 — Order files by dependency · `import_graph.py`

**What:** builds an import graph over the changed files only and topologically
sorts it with **Kahn's algorithm**, so an imported module is analysed before
the modules that import it.

**Why:** if a PR changes `models.py` and `service.py` (which imports it),
processing them in arbitrary order means generating tests for `service`
against a stale understanding of its dependency — and the output order would
differ between runs.

**Design details:** imports are extracted with `ast` (not regex), including
relative imports and the `from package import module` form; ties break by the
original file order so runs are reproducible; **cycles do not fail the run** —
the affected files keep their original order and are reported as
`import_cycle_files` in both report formats. A cycle is a smell in the
*analysed* repository, not an error in the analyser.

### Stage 3 — Analyse source · `source_analyzer.py`

**What:** parses the file with `ast`, extracts public functions and public
methods of public classes (`FunctionInfo`, `ClassInfo`), reconstructs
signatures, and extracts each target's source with
`ast.get_source_segment`.

**Then selects targets:** if changed lines are known, only functions whose
line range intersects them; if not (e.g. the diff could not be parsed), all
public targets. Private names (`_foo`) are skipped — the assistant tests the
public contract, not implementation details.

**Why AST and not regex:** regex cannot reliably find where a function ends,
handle decorators, nested definitions, or multi-line signatures. The AST is
the same structure Python itself uses.

### Stage 4 — Find related existing tests · `test_finder.py`

**What:** two heuristics.

1. **Name conventions** — for `calculator/pricing.py` it checks
   `tests/test_pricing.py`, `tests/calculator/test_pricing.py`,
   `tests/pricing_test.py`.
2. **Content references** — scans test files for the module path, the module
   stem, or the target names, using **word-boundary regex** so a function
   named `add` does not match the word `address`.

**Why it matters:** these files become both context for generation ("do not
duplicate these") and the input for the suggested-update flow.

### Stage 5 — Build prompts · `prompts.py`

Three system instructions (generate / repair / update), each stating the
non-negotiable rules: return only valid Python, no Markdown fences, no
explanations, **do not modify production code**.

**A subtle but critical design rule:** prompts contain the **module path and
file name only — never absolute paths**. In the cloud, every job clones into a
different temporary directory; if those paths leaked into the prompt,
identical code would produce different prompts and the response cache could
never hit. A regression test (`test_prompt_stability.py`) locks this in.

### Stage 6 — Call the model · `llm_client.py`

**What:** a thin wrapper over `google-genai` in Vertex AI mode. Three
behaviours worth knowing:

- **Dry-run mode** returns a deterministic placeholder and never touches the
  network — this is what makes the entire test suite and the local monitoring
  demo free and offline.
- **Response cache** (optional, injected): before generating, it looks up a
  **SHA-256 of (model, temperature, system instruction, prompt)**.
- **Usage tracking**: calls, seconds, prompt tokens, response tokens — kept as
  plain integers so the library has no dependency on any metrics system.

### Stage 7 — Clean and validate · `test_generator.py`

LLM output is untrusted input and is treated as such:

1. **Clean** — strip Markdown fences and stray backticks.
2. **Validate** — must be non-empty, must `ast.parse()` successfully, must
   contain at least one `test_*` function or `Test*` class, must not contain a
   shell shebang.

If validation fails, that file's result is recorded as an error and the
pipeline **continues with the next file**. One bad response never sinks the
run.

### Stage 8 — Run pytest · `pytest_runner.py`

Runs `python -m pytest -q <path>` in a subprocess with a timeout, capturing
stdout/stderr and returning a `PytestResult`. **Failing tests are not an
exception** — a failure is data the next stage needs.

**Why a subprocess:** isolation. Generated code must never be imported into
the assistant's own process.

### Stage 9 — Repair loop · `pipeline.py`

If pytest fails, the source, the failing test code and the pytest output go
back to the model with the repair instruction, up to `repair_attempts`
(default 2). Each attempt overwrites only the file in `tests/generated/`.

**Why bounded:** an unbounded loop with a confidently-wrong model burns money
indefinitely. Two attempts fix the common cases (a wrong import, a wrong
expected value) and stop.

### Stage 10 — Suggest updates to existing tests · `pipeline.py`

For each related existing test file, the model is asked for the **full updated
file**, which is written to `reports/suggested-tests/<original path>` with a
header saying it is a suggestion. **The original is never touched.**

This is the refactoring flow — the one that saves the most time in practice.

### Stage 11 — Write reports · `report.py`

- `reports/ai-test-report.md` — human summary: counts, per-file status,
  generated file paths, suggested updates, pytest outcome.
- `reports/ai-test-report.json` — the same data machine-readable, for CI
  gates and dashboards.

### Stage 12 (opt-in) — Apply suggestions · `pipeline.apply_suggested_updates`

Copies each suggested file over its original — but **only** files that look
like tests (`test_*.py` / `*_test.py`) and resolve inside the repository root.
Anything else is refused and reported as skipped. This is the guard that makes
a one-click apply button safe even if an artefact were corrupted.

---

## 4. Technology choices and why

| Choice | Alternatives considered | Why this one |
| --- | --- | --- |
| **Python + `ast`** | regex parsing, tree-sitter | The target language is Python; the stdlib AST is exact, zero-dependency, and identical to what the interpreter sees |
| **Gemini 2.5 Flash on Vertex AI** | GPT/Claude via API, self-hosted model | Fast and cheap enough to run on every PR (cents), enterprise auth via Google IAM, no separate API-key management |
| **temperature = 0.0** | higher for "creativity" | Reproducible output, fewer invented APIs — and it is the precondition that makes response caching correct |
| **Typer** | argparse, click | Type hints become the CLI; less boilerplate than argparse, and the `--dry-run/--no-dry-run` tri-state falls out naturally |
| **FastAPI** | Flask, plain WSGI | Async support, automatic validation, tiny surface — each service is ~100–335 lines |
| **Cloud Run** | GKE, Cloud Functions, VMs | Scale-to-zero (idle cost = $0), standard container images (little lock-in), and it fits both a public HTTP endpoint and a private queue consumer |
| **Pub/Sub push** | pull subscription, direct HTTP call | Push works with scale-to-zero (no idle consumer to pay for); the broker handles retries via HTTP status codes |
| **GCS for artefacts** | database, artefact registry | Cheap, durable, and the object's existence doubles as the idempotency marker — no extra state store |
| **Prometheus + Grafana** | Cloud Monitoring only, Datadog | Open standards, runs locally in Docker for a free demo, and the same `/metrics` endpoint works in the cloud unchanged |
| **LRU cache, hand-written** | `functools.lru_cache`, Redis | Needed hit/miss counters as data and a cache shared across jobs; also a PDP deliverable (internals, not usage) |
| **Kahn's algorithm, hand-written** | `graphlib.TopologicalSorter` | Free cycle detection, deterministic tie-breaking, no recursion limit — and again, internals were the point |
| **Shell script for deployment** | Terraform | Readable, zero dependencies, idempotent via existence checks. Honest trade-off: no state, no drift detection, no clean destroy |

---

## 5. What each addition improved

The MVP was a CLI. Four subsystems were added on top, each solving a problem
the MVP actually had.

### 5.1 Import-ordered analysis (topological sort)

- **Problem:** arbitrary, non-reproducible processing order; dependents
  analysed before their dependencies.
- **Improvement:** deterministic dependency-first order in O(V+E), plus import
  cycles surfaced in the report as a free code-quality signal.
- **Cost:** 118 lines, no dependencies.

### 5.2 LLM response cache (LRU)

- **Problem:** re-running on a rebased branch re-sent byte-identical prompts;
  at temperature 0 the answer is deterministic, so every repeat was pure
  waste of money and latency.
- **Improvement — measured:** four identical jobs produced **3 model calls and
  9 cache hits**; jobs 2–4 cost **zero** tokens and zero wait.
- **Cost:** 154 lines (LRU + LFU), no dependencies.

### 5.3 Cloud services (event-driven architecture)

- **Problem:** CI-only mode requires per-repository workflow configuration and
  credentials; a burst of PRs runs unbounded parallel jobs.
- **Improvement:** one webhook per repository instead of a workflow;
  queue-based load levelling absorbs bursts; retries and dead-lettering make
  transient failures self-healing; idempotency makes duplicate delivery
  harmless; scale-to-zero keeps idle cost at zero.
- **Cost:** 435 lines across two services.

### 5.4 Monitoring (Prometheus + Grafana)

- **Problem:** no visibility into throughput, failure rate, cost, or whether
  the cache helped.
- **Improvement:** six metric families answering the questions that matter —
  throughput, latency vs the queue deadline, token spend, cache effectiveness,
  and the quality KPI (do generated tests pass?). Two alerts tied to real
  limits. A `docker compose up` demo that needs no cloud account.
- **Cost:** ~40 lines of instrumentation plus configuration files.

---

## 6. Measured results

Everything below was observed in this project, not estimated.

**Real Gemini run** (calculator repo, branch adding `percentage` and
`apply_tax`):

| Metric | Result |
| --- | --- |
| Changed files detected | 2 of 4 (correctly ignored README and the test file) |
| Test files generated | 2, containing 19 tests |
| Passed pytest first attempt | Both — repair loop never needed |
| Suggested updates | 1 (`tests/test_operations.py`) |
| Cost | 3 Gemini Flash calls ≈ fractions of a cent |

Notably, the suggested update **matched the existing file's style** (plain
assertions, not the parametrised style used in the generated file) — the
"keep the existing style" instruction demonstrably worked.

**Cache effectiveness** (four identical jobs, local monitoring stack):

```
jobs_processed_total{status="processed"}     4
llm_calls_total                              3     ← only job 1 called the model
llm_cache_hits_total                         9
llm_cache_misses_total                       3
generated_test_files_total{result="passed"}  8
```

**Cloud pipeline verification** (real GCP deployment):

| Check | Result |
| --- | --- |
| Unsigned / wrongly-signed webhook | Rejected with 401 |
| Signed webhook | 202 + Pub/Sub message ID |
| Push delivery to private worker | Authenticated via OIDC, HTTP 200 |
| Artefacts in GCS | `ai-test-report.json` + `.md` at `repo/PR/sha/` |
| Idempotency drill (duplicate webhook) | `processed=1, skipped=1` |
| Dead-letter drill | Failing job retried 5×, landed in the DLQ, inspected |

---

## 7. The safety model

Eight guarantees, and the mechanism that enforces each:

| Guarantee | Enforced by |
| --- | --- |
| Production code is never modified | The assistant only ever writes into `tests/generated/` and `reports/`; `apply-suggestions` refuses non-test filenames |
| Existing tests are never overwritten automatically | Updates go to `reports/suggested-tests/`; applying is a separate, explicit action |
| Nothing is auto-committed | Only the label-triggered workflow commits, and only files matching test patterns |
| LLM output is never executed in-process | Validated by `ast.parse`, then run only via a pytest subprocess |
| No shell commands from LLM output | Validation rejects shebangs; the code path never `exec`s a model response |
| Secrets are never printed | Clone URLs with embedded tokens are stripped from error messages; env values are never logged |
| One failure never stops the run | Per-file try/except records an error result and continues |
| Public endpoint cannot be abused | HMAC-SHA256 signature verification before any work; the worker is private and callable only by Pub/Sub |

---

## 8. What we deliberately did *not* build

Restraint is a design decision worth defending:

- **No multi-agent architecture.** A single linear pipeline is traceable top
  to bottom; agents negotiating with each other would be harder to debug and
  no more accurate.
- **No database.** All state is files (artefacts in GCS) and the queue. Adding
  Postgres would add operations without answering a question we have.
- **No LFU in production.** It is implemented and tested, but LRU matches the
  actual access pattern (bursty re-runs). Wiring in a policy that cannot win
  on the current workload would be a speculative abstraction.
- **No plugin system, no DAG executor, no service mesh.** With two services,
  a mesh costs more than it returns.
- **No auto-merge of suggestions.** The whole value proposition depends on
  human review staying in the loop.

---

## 9. Limitations, honestly stated

1. **Python and pytest only.** The AST analysis is language-specific.
2. **Related-test detection is heuristic.** Name conventions and text
   references find most cases and will miss unusual layouts.
3. **Generated tests can be confidently wrong.** They may assert current
   behaviour rather than intended behaviour — which is exactly why they land
   in a review directory.
4. **Dynamic imports are invisible** to the static import graph
   (`importlib`, `__import__`).
5. **Metrics live in process memory.** A Cloud Run instance scaling to zero
   resets counters; `rate()` handles this correctly but all-time totals do
   not survive. Fix would be remote write to a durable backend.
6. **The cache is per-process.** Multiple worker instances do not share it;
   a shared cache would need Redis.
7. **Coverage measurement is out of scope.** The assistant reports whether
   tests pass, not what fraction of code they exercise.
8. **`deploy.sh` has no state.** It creates and updates but cannot detect
   drift or cleanly destroy; Terraform would be the production answer.

---

## 10. Where to look for what

| Concern | File |
| --- | --- |
| CLI commands | `ai_test_assistant/cli.py` |
| Configuration and precedence | `ai_test_assistant/config.py` |
| Shared data structures | `ai_test_assistant/models.py` |
| Changed-file detection | `ai_test_assistant/git_utils.py` |
| Dependency ordering (Kahn) | `ai_test_assistant/import_graph.py` |
| AST analysis, target selection | `ai_test_assistant/source_analyzer.py` |
| Related-test heuristics | `ai_test_assistant/test_finder.py` |
| Prompt text | `ai_test_assistant/prompts.py` |
| Vertex AI client, cache, usage | `ai_test_assistant/llm_client.py` |
| LRU / LFU internals | `ai_test_assistant/cache.py` |
| Cleaning + validation | `ai_test_assistant/test_generator.py` |
| pytest subprocess | `ai_test_assistant/pytest_runner.py` |
| Orchestration, apply-suggestions | `ai_test_assistant/pipeline.py` |
| Report writers | `ai_test_assistant/report.py` |
| Webhook receiver | `services/webhook_receiver/receiver_app.py` |
| Analysis worker, metrics | `services/analysis_worker/worker_app.py` |
| Deployment | `infra/deploy.sh`, `infra/cloudbuild-*.yaml` |
| Local observability stack | `monitoring/` |
| Architecture and failure modes | `docs/architecture.md` |
| Cloud service equivalence | `docs/cloud_equivalence.md` |
| Metrics reference | `docs/monitoring.md` |
| Algorithm internals | `docs/algorithms.md` |
| Theory study material | `docs/exam/` |
