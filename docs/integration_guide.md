# Integration Guide

This guide explains how to integrate AI Unit Test Assistant into another
Python repository.

## 1. Add the tool to your repo

Install the package as a dev dependency. Until it is published, point at the
local checkout or a fork:

```bash
pip install -e "../ai-unit-test-assistant[dev]"
```

or add the equivalent line to your `requirements-dev.txt` / `pyproject.toml`.

## 2. Add `ai-test-assistant.yml`

Copy the sample config file to the root of the target repo and edit the values
to match your layout:

```yaml
source_roots:
  - src
  - app
test_roots:
  - tests
exclude_paths:
  - tests/generated
  - reports
  - .venv
  - build
  - dist
  - migrations
repair_attempts: 2
update_existing_tests: true
dry_run: false
gemini_model: gemini-2.5-flash
temperature: 0.0
```

The file is optional — every key falls back to a sensible default — but it is
the simplest way to keep settings in version control.

## 3. Add GitHub secrets

Configure the following in your repository (Settings → Secrets and variables
→ Actions):

- Secrets:
  - `GOOGLE_CLOUD_PROJECT` — the Google Cloud project ID that has Vertex AI
    enabled.
  - `GOOGLE_CLOUD_LOCATION` — Vertex AI region, e.g. `us-central1`.
- Variables:
  - `GEMINI_MODEL` — the Gemini model name, e.g. `gemini-2.5-flash`.

The PR workflow uses Workload Identity Federation through
`google-github-actions/auth` if you set it up; for local runs use
`gcloud auth application-default login`.

## 4. Add the PR workflow

Copy `.github/workflows/ai-test-assistant.yml` into the target repo. The
workflow:

- triggers on pull requests touching `**/*.py`,
- installs the package,
- runs `ai-test-assistant run-pr-assistant`,
- writes the Markdown report to the GitHub Actions run summary,
- uploads `tests/generated/` and `reports/` as an artifact.

No PR comment is required for the MVP — the run summary plus the downloadable
artifact is enough for review.

## 5. Review generated artifacts

After the workflow runs, open the PR's *Checks* tab and:

1. Read the **report summary** for a high-level overview (which files changed,
   which generated tests passed).
2. Download the **ai-test-assistant-output** artifact to inspect the generated
   tests under `tests/generated/` and any suggested updates under
   `reports/suggested-tests/`.
3. Move the tests you want to keep into your real test tree, after reviewing
   and editing them as needed.

The assistant never commits files automatically and never overwrites existing
manual tests, so the artifact is always advisory.
