# 6. PDP · AI Assistant for Unit Test Automation {#en-unit-tests}

## In plain words

A unit test calls one function with known input and checks the output. Good tests are small, independent, deterministic and named after what they check. An LLM can write such tests quickly, but it can also write tests that do not parse, that import the wrong module, or that assert the wrong value. The job of this project is to catch all of that before a person reads the result.

![How a generated test earns its place: every answer is checked before it is trusted.](images/test-birth.en.png)

## Theory in brief

- **pytest** finds files named `test_*.py`, runs every `test_*` function, and treats a plain `assert` as the check. Fixtures provide setup; `pytest.raises` checks errors; parametrization runs one test over many inputs.
- **A good unit test** exercises one behavior, has no hidden dependencies (network, clock, order of other tests), and fails for exactly one reason.
- **Generated tests need three gates:** syntactic (is it Python?), structural (does it contain tests?), and behavioral (do they pass against the real code?). The first two are cheap static checks; the third needs execution.
- **Repair loops must be bounded.** A model that fixes its own test can also loop forever or "fix" the test by deleting the assertion. A small fixed number of attempts and a human at the end keep this safe.

## How this project applies it

**Choosing what to test.** `test_targets.py` parses the file with `ast` and keeps public functions and methods (no leading underscore) whose line range intersects the diff. Module-level functions come first, then methods, so prompts are stable from run to run.

**Context for the model.** The prompt holds the full source file, the targets with their source, and the content of related existing tests, so the model follows the project's style and does not duplicate what exists. Paths in the prompt are module paths, never disk paths, so the same code gives the same prompt on every machine (that is what makes the cache work).

**The three gates** live in `llm_test_code.py`: strip Markdown fences, refuse shell shebangs, parse with `ast`, require at least one `test_` function or `Test` class. A failed gate raises `ValidationError`; nothing is written.

**Run and repair.** `pytest_runner.py` runs pytest in a subprocess with a 120-second timeout. On failure `test_generator.py` sends source, test and pytest output back to the model, at most two times (`repair_attempts`, configurable). After that the file stays, marked `failed`, and the report explains.

**Suggestions for existing tests.** For each related test file, `suggested_updates.py` asks for a full new version and writes it under `reports/suggested-tests/` with a header. When two changed files share one test file, the second update starts from the first suggestion, so nothing is lost. `apply-suggestions` copies suggestions over the originals only when a person runs it.

**File names.** Generated tests are named after the full path, `examples/calculator.py` → `tests/generated/test_examples_calculator_generated.py`, so two modules with the same name cannot collide.

## Likely questions

**Q:** Can the model make a failing test pass by weakening it?

**A:** It can, within the two repair attempts, and that is the main reason the output is reviewed. The repair prompt says "fix only the test code" and "remove invalid assumptions", and the reviewer sees the final file with its history in the report.

**Q:** Why not measure coverage?

**A:** It was cut from the first version on purpose: coverage numbers invite gaming, and the report already says per file whether tests exist and pass. It is a natural next step, not a missing piece.

**Q:** How is the tool itself tested?

**A:** 103 tests: unit tests per module, service tests for the receiver and worker, and end-to-end tests that run the whole pipeline on a temporary git repository in dry-run mode and pin the report. A scripted fake LLM covers the cases a fixed dry-run answer cannot show.
