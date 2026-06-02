# LLM Basics

This document explains the LLM design choices behind the assistant. It is
intentionally short — the goal is to show that we apply common patterns from
Tech 5 (LLM Development Basics), not to build a research framework.

## 1. Gemini model setup

The assistant uses Google's `google-genai` SDK with Vertex AI mode. The model
defaults to `gemini-2.5-flash`, which is fast and cheap enough for PR-time
test generation. The model name, project, and location are read from
`AppConfig`, which loads them from the YAML config or environment variables.

## 2. System instructions

Three system instructions live in `ai_test_assistant/prompts.py`:

- **Generate tests** — frames the model as a senior Python engineer producing
  pytest tests; bans Markdown fences, explanations, and production-code edits.
- **Repair tests** — used when the generated tests fail under pytest. Tells
  the model to fix the test file only.
- **Update tests** — used to refresh related existing test files after a
  refactor; demands the full file back, not a diff.

Keeping the instructions in code (instead of inline strings inside the
pipeline) makes them easy to review and to tweak without touching the rest of
the system.

## 3. Prompt building

Each user prompt is built from structured inputs:

- the production source code,
- a list of `TestTarget` records (function/method snippets plus a short
  "why this was selected" reason),
- the contents of any related existing tests (for context, not to copy).

The prompt builders return `(system_instruction, user_prompt)` tuples, which
keeps the LLM call site dumb.

## 4. Deterministic configuration

`temperature` defaults to `0.0`. We want reproducible test scaffolds rather
than creative variations. Lower temperature also reduces the chance of the
model "inventing" public functions that do not exist.

## 5. LLM response validation

Every LLM response goes through two steps:

1. **Cleaning** — `clean_llm_python_response` strips Markdown code fences,
   stray leading/trailing backticks, and outer whitespace.
2. **Validation** — `validate_python_test_code` checks that the result is not
   empty, parses with `ast.parse`, contains at least one `test_` function or
   `Test...` class, and does not look like a shell script.

If validation fails the pipeline records an error for that file and moves on.

## 6. Repair loop

If the generated tests fail when pytest runs them, the pipeline calls Gemini
again with the **repair** prompt — passing the source, the current test code,
and the pytest output. We retry up to `config.repair_attempts` times. Each
retry overwrites only the file under `tests/generated/`; the original source
and any human-written tests are untouched.

## 7. Why generated code still needs human review

LLM output is plausible-looking but unreliable. Common failure modes we have
seen:

- assertions that match implementation bugs instead of intended behavior,
- imports of functions that do not exist,
- mocks that hide real integration issues,
- tests that always pass because they assert tautologies.

The pipeline writes everything to clearly-labeled artifact directories
(`tests/generated/`, `reports/suggested-tests/`) and never auto-commits.
A human is expected to read each generated test and either accept, edit, or
discard it.
