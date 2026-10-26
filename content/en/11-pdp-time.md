# 11. PDP · Time Management and Self-Discipline {#en-time}

## In plain words

The project was built in phases over five months, next to regular work. What kept it on track was not working longer but deciding early what not to build, delivering in checked steps, and working on one thing at a time. This section shows those three habits with the project's own history.

![How the project was built: in phases, each one checked before the next.](images/phases.en.png)

## Prioritising tasks

The first version was scoped with a simple must / should / could / won't list. Everything in "won't" was tempting and would have doubled the work.

| Priority | Feature | Why |
| --- | --- | --- |
| Must | changed-file detection, AST targets, LLM generation, pytest run, repair loop, report, GitHub Actions | without any of these there is no product |
| Should | suggested updates for existing tests, dry-run mode, YAML config | make it usable and testable; cheap to add |
| Could | cloud service, metrics, cache | valuable, but only after the core works (they became phases 2–4) |
| Won't | web UI, database, auto-commit, multi-agent framework, other languages, coverage reports | high effort or high risk, no PDP value |

Rule of thumb used: **a feature is in the first version only if the product is useless without it.** Everything else waits for a phase of its own.

## Dealing with deadlines

Work was split into phases that each ended in something demonstrable, so a slipped phase never left nothing to show:

| Phase | When | Delivered | Proof |
| --- | --- | --- | --- |
| 1 MVP | May – June 2026 | CLI, GitHub Actions, report | unit tests, dry-run CI |
| 2 Cloud | July 2026 | receiver, Pub/Sub, worker, `deploy.sh` | service tests |
| 3 Monitoring | July 2026 | metrics, dashboard, alerts | counters visible in Grafana |
| 4 Algorithms | July 2026 | import order, LRU / LFU | unit tests per algorithm |
| 5 Simplification | October 2026 | 15 small pull requests | tests green after each one |
| 6 Verification | October 2026 | everything run locally, 5 bugs fixed | each fix with a failing test first |

Two habits that made deadlines survivable: estimate in phases, not in features, and keep a buffer phase (verification) that can absorb what earlier phases missed.

## Balancing focus and multitasking

- **One pull request at a time.** The October simplification was fifteen PRs, each small enough to review in minutes and each leaving the full test suite green. No PR mixed a refactoring with a behavior change; where behavior changed, the PR said so and had a test that failed before.
- **Safety net first.** Before any refactoring, an end-to-end test pinned the current output. That made every later step a mechanical check instead of a judgement call, which is what lets a person stop and resume without losing the thread.
- **Small modules reduce context switching.** With one job per file and dependencies pointing one way, fixing a bug means opening one file. The final review of the whole code base took one sitting.
- **Timebox the cloud.** Everything that costs money (Gemini calls, GCP deployment) is behind a flag or a script that is run on purpose; the default run is free and offline, so experiments do not need a budget discussion.

## Likely questions

**Q:** What was cut that you regret?

**A:** Coverage measurement. It would have been a cheap signal for reviewers. It was cut to keep the first version small and is the obvious next step.

**Q:** How do you avoid the "last 10 %" that never ends?

**A:** By defining done per phase as "demonstrable and tested", not "finished". Phase 6 was the explicit place for polish, with a fixed list, so polish did not leak into every other phase.
