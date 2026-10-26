# 12. PDP coverage and talking points {#en-coverage}

## In plain words

One project, eight PDP topics. Every topic has a piece of theory in this document, a piece of working code in the repository, and a way to show it live. The picture below is the map; the table gives the evidence.

![Every PDP topic keeps a working example in the code and a way to show it live.](images/pdp.en.png)

## Coverage table

| PDP topic | Theory | Example in this project | Evidence |
| --- | --- | --- | --- |
| AI Tools for Better Productivity | section 4 | the assistant itself; check-first design; measured cost | report, metrics |
| CI/CD + Coding Agents | section 5 | two workflows, label-triggered apply, artifacts | `.github/workflows/` |
| AI Assistant for Unit Test Automation | section 6 | generate → validate → pytest → repair; suggestions | `test_generator.py`, `tests/generated/` |
| LLM Development Basics | section 7 | Vertex AI setup, three prompts, temperature 0, cache, dry-run | `llm_client.py`, `prompts.py` |
| Distributed Systems & Cloud Architecture | section 8 | receiver → Pub/Sub → worker, idempotency, dead letters, GCP / AWS / Azure map | `services/`, `infra/deploy.sh` |
| Monitoring (Prometheus, Grafana) | section 9 | 9 metrics, provisioned dashboard, tested alert rules | `monitoring/` |
| Topological sort & LRU / LFU | section 10 | Kahn with a heap, LRU and LFU from scratch, switchable policy | `import_graph.py`, `cache.py` |
| Time Management | section 11 | scope list, six phases, one PR at a time | git history |

Not covered by this project, on purpose: video stabilisation and the Kalman filter / exponential smoothing topics. They belong to a separate computer-vision project.

## Ten talking points

1. The tool does one thing: changed code in, reviewed tests out. Everything else is a way to trigger it or deliver the result.
2. Every LLM answer passes three gates before anyone reads it: it parses, it contains tests, it passes pytest. Failures are repaired at most twice, then reported.
3. Nothing is committed automatically. Artifacts plus a label keep the human decision explicit and cheap.
4. Temperature 0 makes the output deterministic, which makes it testable and cacheable. A repeated prompt costs zero tokens.
5. The code is eight steps in eight files, called in order by a 114-line `pipeline.py`. Dependencies point one way; there are no cycles.
6. The cloud mode is a textbook event-driven system: public receiver, queue with retries and dead letters, private idempotent worker. It was verified end to end with the Pub/Sub emulator.
7. Monitoring is nine metrics, a dashboard from a file and two alert rules with unit tests. One of those tests exists because the original alert fired on any single failure.
8. The algorithms are not academic: the topological sort orders real files, and the caches serve real prompts, with the hit ratio on the dashboard.
9. Simplicity was engineered, not assumed: a review found the design sound and removed what a reader had to read around, in 15 small pull requests with the tests green after each.
10. Everything in this document can be shown live without a cloud account: `--dry-run`, the test suite, `docker compose up`.

> The value of the project is not that an AI writes tests. It is that an AI can be put into a real engineering workflow safely: checked by machines, judged by people, measured in numbers.
