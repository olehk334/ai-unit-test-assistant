# Exam Preparation Reports

Study material for three PDP topics. Each topic has **two documents in two
languages**, and each document has **two parts**:

- **Part A — Summary-hint.** A spoken-answer script. Dense, ordered, and
  complete enough to survive follow-up questions from basic to advanced.
  Read this the hour before the exam.
- **Part B — Full report.** The teaching material behind the hint: why each
  mechanism exists, how it works internally, trade-offs, failure modes,
  worked examples, and a study plan. Read this over days, not hours.

| Topic | English | Russian |
| --- | --- | --- |
| 1. Distributed Systems & Cloud Architecture | [01-distributed-systems.en.md](01-distributed-systems.en.md) | [01-distributed-systems.ru.md](01-distributed-systems.ru.md) |
| 2. Monitoring (Prometheus, Grafana) | [02-monitoring.en.md](02-monitoring.en.md) | [02-monitoring.ru.md](02-monitoring.ru.md) |
| 3. Topological sort & LRU/LFU caches | [03-algorithms.en.md](03-algorithms.en.md) | [03-algorithms.ru.md](03-algorithms.ru.md) |

The Russian documents are **technical adaptations**, not literal
translations: standard Russian terminology with the English term kept in
parentheses on first use, and all code, PromQL, and CLI text left in the
original.

## How to use these

1. Read Part B of one topic. Do not memorise — aim to be able to redraw the
   diagrams and re-derive the trade-offs.
2. Reduce Part B to Part A in your own words. If you cannot, you have not
   understood a section — go back to it.
3. Answer the "Rapid-fire Q&A" at the end of each Part A out loud, without
   looking. Anything you stumble on is your revision list.
4. Anchor every abstract concept to something you have actually run. This
   repository is the anchor: it uses Cloud Run + Pub/Sub + GCS (topic 1),
   exports Prometheus metrics to a provisioned Grafana dashboard (topic 2),
   and implements Kahn's algorithm and LRU/LFU by hand (topic 3). Each
   report ends with a section mapping theory to that code.

## Examiner-proofing

Three habits that separate a pass from a good answer:

- **Name the trade-off, not just the feature.** "Pub/Sub decouples producer
  and consumer *at the cost of* eventual consistency and duplicate
  delivery" beats "Pub/Sub is a message queue."
- **Give the complexity or the number.** O(V+E). p95, not average. 1–2 bytes
  per sample. Cold start 100 ms–2 s.
- **Say when you would *not* use it.** Every technology in these documents
  has a section on when it is the wrong choice. That is usually the question
  that separates candidates.
