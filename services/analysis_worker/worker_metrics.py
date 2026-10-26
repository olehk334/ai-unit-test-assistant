"""Prometheus metrics of the worker, served on /metrics."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

from ai_test_assistant.llm_client import LlmUsageStats
from ai_test_assistant.models import PipelineResult


JOBS_PROCESSED = Counter(
    "jobs_processed_total", "Analysis jobs by outcome", ["status"]
)
JOB_DURATION = Histogram(
    "job_duration_seconds",
    "End-to-end job duration (clone + pipeline + upload)",
    buckets=(5, 15, 30, 60, 120, 300, 600),
)
LLM_CALLS = Counter("llm_calls_total", "LLM generate calls (cache misses)")
LLM_SECONDS = Counter("llm_seconds_total", "Seconds spent waiting on the LLM")
LLM_PROMPT_TOKENS = Counter("llm_prompt_tokens_total", "Prompt tokens sent")
LLM_RESPONSE_TOKENS = Counter("llm_response_tokens_total", "Response tokens received")
CACHE_HITS = Counter("llm_cache_hits_total", "LLM response cache hits", ["policy"])
CACHE_MISSES = Counter("llm_cache_misses_total", "LLM response cache misses", ["policy"])
GENERATED_FILES = Counter(
    "generated_test_files_total", "Generated test files by pytest outcome", ["result"]
)

# Export every known label value at 0 from startup: rate() cannot see the first
# increment of a series that did not exist before it.
for _status in ("processed", "failed", "skipped", "ignored"):
    JOBS_PROCESSED.labels(status=_status)
for _result in ("passed", "failed"):
    GENERATED_FILES.labels(result=_result)


def record_cache_lookups(policy: str, hits: int, misses: int) -> None:
    CACHE_HITS.labels(policy=policy).inc(hits)
    CACHE_MISSES.labels(policy=policy).inc(misses)


def record_job_metrics(result: PipelineResult, usage: LlmUsageStats) -> None:
    LLM_CALLS.inc(usage.calls)
    LLM_SECONDS.inc(usage.total_seconds)
    LLM_PROMPT_TOKENS.inc(usage.prompt_tokens)
    LLM_RESPONSE_TOKENS.inc(usage.response_tokens)

    for file_result in result.file_results:
        if file_result.generated_test_file is not None:
            outcome = "passed" if file_result.status == "passed" else "failed"
            GENERATED_FILES.labels(result=outcome).inc()
