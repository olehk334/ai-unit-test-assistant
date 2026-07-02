# Fix Plan (audit findings)

Continuation anchor: if a session stops mid-way, resume from the first
unchecked item. One focused local commit per item; run `python -m pytest -q`
after each. No pushes, no deploys without explicit permission.

## A. Correctness / safety

- [x] **A1** `apply_suggested_updates` must only write test files
      (mirror test_finder's naming rule: `test_*.py` / `*_test.py`) and only
      inside the repo root; return skipped paths, CLI echoes them. Tests.
- [x] **A2** Generated test filename derives from the repo-relative path
      (`examples/calculator.py` → `test_examples_calculator_generated.py`)
      so same-stem sources cannot collide. Update README naming mentions
      here and in the calculator demo repo. Tests.
- [x] **A3** `post_commit_status` becomes best-effort: network failure logs
      a warning instead of failing the job (docs already promise this). Test.
- [x] **A4** `infra/deploy.sh`: replace non-existent
      `gcloud builds submit --file` with per-service cloudbuild configs.
      `bash -n` syntax check (cannot run for real without cloud).
- [x] **A5** `import_graph`: `from package import module` must create an
      edge to `package.module`, not only `package`. Test.
- [ ] **A6** `test_finder`: match target names with word boundaries so
      `add` no longer matches `address`. Test.

## B. Minor rule violations

- [ ] **B1+B9** Type hygiene: `_generate_and_repair` returns
      `tuple[str, PytestResult | None]`; annotate `changed_file: ChangedFile`;
      tests stop passing `source_file=None` into `FileResult`.
- [ ] **B2** `load_config` docstring states the .env side effect on
      `os.environ`.
- [ ] **B3** Worker cache-delta tracking: replace `global` counters with a
      small `_CacheDeltaCounter` (still concurrency=1 by design).
- [ ] **B4** Receiver: reuse one lazily created Pub/Sub publisher instead of
      a client per request.
- [ ] **B5+B8** CLI: drop `_build_config` pass-through (each command builds
      its own overrides dict); `--dry-run/--no-dry-run` tri-state so the CLI
      can override a config-file `dry_run: true`.
- [ ] **B6** Remove the extra header from the dry-run template (files were
      getting two headers).
- [ ] **B7** `write_json_report`: rename `report_path` param to
      `markdown_report_path` to match what it actually receives.
- [ ] **B10** Renames: worker `process_job` → `run_analysis_job`,
      pipeline `_process_file` → `_run_assistant_on_file`.
      (`cache.py` filename stays — single clear responsibility, documented.)

## Wrap-up

- [ ] Refresh docs made stale by the fixes (RU guide: B3 global-vars note,
      A5 known-gap note, deploy.sh status; this file's checkboxes).
- [ ] Full test suite green; summarize what changed and remaining risks.
