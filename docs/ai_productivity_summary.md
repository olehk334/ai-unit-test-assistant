# AI Productivity Summary

This document covers the Soft 1 dimension: how AI tooling improves developer
productivity in everyday work.

## 1. How the tool improves developer productivity

Writing unit tests is mechanical work that consumes a disproportionate share
of pull-request time. The assistant takes the boring first pass:

- it scans the diff, picks the public targets that changed, and produces a
  reviewable pytest scaffold,
- it runs the scaffold and tries to repair the obvious mistakes before a
  human ever looks at it,
- it leaves a Markdown report so reviewers see at a glance what was generated
  and which tests passed.

Developers move from *writing tests from scratch* to *editing a well-shaped
draft*, which is usually faster and more pleasant.

## 2. How it helps with PR review

The assistant runs as part of CI and writes its output to the PR's run
summary and an artifact bundle:

- The reviewer can read the summary table in the GitHub Actions UI to see
  which files were analyzed and whether the generated tests passed.
- They can download the generated tests and use them as a checklist: every
  unfamiliar assertion is a candidate question for the author.
- Failing generated tests are a hint that the diff might have surprising
  behavior the author should clarify.

The assistant does not block merges; it adds context.

## 3. How it helps during refactoring

The "suggested update" mode is aimed at refactors. When a public function's
signature or behavior changes:

- the assistant finds the existing test files that exercise it,
- it asks Gemini to rewrite each one against the new code,
- the suggestions land under `reports/suggested-tests/` for the author to
  review.

This is the part that traditionally hurts the most during a refactor — the
"twenty tests broke and I have to fix each one by hand" phase. The assistant
gives the author a head start without ever overwriting their canonical test
files.

## 4. What humans still need to review manually

The assistant is fast but not authoritative. A reviewer must always:

- check that assertions match the **intended** behavior, not just the
  current implementation,
- ensure new tests cover meaningful edge cases (the LLM tends to test the
  happy path well and forget boundary conditions),
- delete tests that hide bugs by mocking the very thing under test,
- approve the move from `tests/generated/` into the real test tree, after
  any necessary edits.

Treat the assistant as a junior pair-programmer: helpful, fast, occasionally
confidently wrong, and always reviewed by a human before merge.
