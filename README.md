# AI Unit Test Assistant

AI Unit Test Assistant is a lightweight Python CLI tool that uses Gemini through
Vertex AI to generate pytest unit tests for changed Python code and suggest
updates to existing tests after refactoring.

It is designed for GitHub PR workflows. The assistant detects changed
production files, analyzes public functions and methods, generates reviewable
test files, runs pytest, attempts to repair failed generated tests, and writes
a clear report with all generated artifacts.

The tool does not modify production code, does not overwrite existing tests,
and does not auto-commit AI-generated code. It is intended to improve developer
productivity while keeping human review in control.

## What this project covers

- **Tech 2 — CI/CD + Coding Agents**: a GitHub Actions workflow runs the
  assistant in PRs and uploads generated test artifacts plus a Markdown report
  to the run summary.
- **Tech 3 — AI Assistant for Unit Test Automation**: the tool generates tests
  for new or changed code, suggests updates for related existing tests, runs
  pytest, and repairs generated tests that fail.
- **Tech 5 — LLM Development Basics + Sample Project**: a Gemini/Vertex AI
  client, prompt templates, deterministic configuration (temperature 0.0),
  LLM response validation, and a repair loop combined in a small linear
  pipeline.
- **Soft 1 — AI Tools for Better Productivity**: a practical developer tool
  that reduces manual unit-test work and helps during PR review and
  refactoring.

## Installation

```bash
python -m pip install -U pip
pip install -e ".[dev]"
```

## Vertex AI / Gemini setup

The assistant uses the official `google-genai` SDK against Vertex AI.

1. Create or pick a Google Cloud project that has Vertex AI enabled.
2. Authenticate locally with `gcloud auth application-default login`.
3. Export the required environment variables:

   ```bash
   export GOOGLE_CLOUD_PROJECT=my-gcp-project
   export GOOGLE_CLOUD_LOCATION=us-central1
   export GEMINI_MODEL=gemini-2.5-flash
   ```

You can also place the same values in `ai-test-assistant.yml`. CLI flags take
priority over environment variables, which take priority over the config file.

If you want to try the pipeline without contacting Gemini, pass `--dry-run` and
the assistant returns a deterministic placeholder test.

## Local usage

Generate tests for a single source file:

```bash
ai-test-assistant generate-tests \
  --source examples/calculator.py \
  --output-dir tests/generated \
  --repair-attempts 2
```

Run the PR assistant locally against your `main` branch:

```bash
ai-test-assistant run-pr-assistant \
  --base-ref origin/main \
  --output-dir tests/generated \
  --suggestions-dir reports/suggested-tests \
  --report reports/ai-test-report.md
```

Dry run (no Gemini call):

```bash
ai-test-assistant run-pr-assistant --base-ref origin/main --dry-run
```

## GitHub Actions usage

Two workflows live under `.github/workflows/`:

- `ci.yml` runs the assistant project's own pytest suite on every PR / main
  push.
- `ai-test-assistant.yml` runs the assistant against changed Python files in
  the PR, writes the report into the GitHub run summary, and uploads
  generated tests + reports as build artifacts.

The PR workflow needs three secrets / variables to talk to Vertex AI:

- `secrets.GOOGLE_CLOUD_PROJECT`
- `secrets.GOOGLE_CLOUD_LOCATION`
- `vars.GEMINI_MODEL`

## Generated tests flow

1. The assistant lists Python files changed in the PR.
2. For each file it parses the AST and picks the public functions / methods
   whose line ranges intersect the diff. If the diff cannot be parsed it picks
   every public target.
3. It builds a prompt with the source code and target snippets and asks Gemini
   for a complete pytest module.
4. The response is cleaned (Markdown fences stripped) and validated (must
   parse, must contain at least one `test_` function or `Test...` class).
5. The generated module is written to `tests/generated/test_<stem>_generated.py`
   with a header that flags it as AI-generated.
6. pytest runs the generated module. If it fails the assistant feeds the
   failure back to Gemini up to `repair_attempts` times.

## Suggested test update flow

1. For every changed source file the assistant searches for related existing
   test files (direct name match, mirrored layout, or import / target-name
   references).
2. It asks Gemini for the full updated test file based on the new source code.
3. The result is written to `reports/suggested-tests/<original-test-path>`
   with a header asking the human reviewer to compare before replacing the
   original. The original test files are never overwritten automatically.

## Limitations

- Only Python projects are supported.
- Only pytest is supported.
- Related test detection uses simple filename and text heuristics.
- The tool suggests test updates but does not apply them automatically.
- Generated tests require human review.
- LLM output may be wrong and must be validated.
- Complex integration tests are out of scope.
- Coverage measurement is out of scope for the MVP.
