# 2. How it works, step by step {#en-steps}

## In plain words

The tool answers eight questions in a fixed order, and each question has its own module. `pipeline.py` only calls them one after another; it holds no other logic. If you want to know where something happens, the question tells you the file.

![Inside the assistant: eight steps, one module each.](images/core.en.png)

## The eight steps

1. **What changed?** `changed_files.py` runs `git diff` against the base branch and keeps only production Python files: no test files, no generated files, no excluded folders. For each file it also records which lines changed.
2. **In which order?** `import_graph.py` looks at imports between the changed files and sorts them so a module is processed before the files that import it. Section 10 explains the algorithm.
3. **What needs tests?** `test_targets.py` parses each file with Python's `ast` module (nothing is executed) and picks the public functions and methods whose lines were changed. If a file is new, every public function is a target.
4. **What tests exist?** `test_finder.py` looks for related test files: `tests/test_<name>.py`, a mirrored folder layout, or any test file that mentions the module or its functions. The tool's own generated tests never count.
5. **Ask Gemini.** `prompts.py` builds the prompt, `llm_client.py` sends it. With temperature 0 the same prompt gives the same answer, so a cache (`cache.py`) can serve repeats for free.
6. **Do the tests pass?** `test_generator.py` writes the answer to `tests/generated/`, runs pytest on it, and on failure asks for a repair, at most twice. `llm_test_code.py` cleans and validates every answer first.
7. **Are old tests outdated?** `suggested_updates.py` asks for a new version of each related test file and writes it under `reports/suggested-tests/`. The original is never touched.
8. **What happened?** `report.py` writes `ai-test-report.md` for people and `ai-test-report.json` for machines.

## The module map

```
ai_test_assistant/
  cli.py                   3 commands → pipeline
  config.py                defaults → yml → env → flags
  pipeline.py              calls steps 1–8 in order, nothing else
  changed_files.py      1  git diff → changed files + lines
  import_graph.py       2  topological order (Kahn)
  test_targets.py       3  public code the diff touched
  test_finder.py        4  related existing tests
  prompts.py            5  the three prompts
  llm_client.py         5  Gemini call, dry-run, cache
  cache.py              5  LRU + LFU, written from scratch
  llm_test_code.py      6  ask → clean → validate → write
  test_generator.py     6  generate → pytest → repair
  pytest_runner.py      6  pytest in a subprocess
  suggested_updates.py  7  new versions of related tests
  report.py             8  Markdown + JSON
  models.py                data passed between steps
  repo_paths.py            path rules every step shares
```

## Four rules the code follows

- **One module, one job, one name.** Each file answers one question of the flow, and its name says which. There are no `utils` or `helpers` files.
- **Dependencies point one way.** `models` and `repo_paths` are at the bottom, the eight step modules above them, `pipeline` on top, `cli` above that. No cycles; no step module imports another step module.
- **Plain functions.** Nothing runs concurrently, so nothing is `async`. One PR is processed file by file, and one broken file never stops the others: its error goes into the report.
- **A person stays in charge.** Output is written to files; committing is a human decision.

## Likely questions

**Q:** Why process files one at a time and not in parallel?

**A:** Each file costs one or two LLM calls and a pytest run. A typical PR changes a handful of files, so the whole run takes a few minutes either way, and sequential code is far easier to read and debug. The cloud mode scales by running more workers, not more threads.

**Q:** What does "changed lines" give you?

**A:** Focus. If a file with twenty public functions has one changed function, only that function gets tests. The reviewer sees a small, relevant test file instead of a large generic one.

**Q:** What if the changed file has a syntax error?

**A:** Step 3 cannot parse it, the file is reported with status `error` and the message, and the run continues with the next file.
