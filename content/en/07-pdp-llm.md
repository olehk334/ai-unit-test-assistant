# 7. PDP · LLM Development Basics {#en-llm}

## In plain words

Using an LLM in a product is mostly ordinary engineering: get access to a model, decide exactly what you send it, make the answer predictable, check the answer, and control the cost. The model is the only non-deterministic part, so the design pushes it into a corner where its output is small, checkable and cacheable.

![One call to Gemini: what goes in, what controls the answer, what comes out.](images/llm-call.en.png)

## Theory in brief

- **Setup.** Vertex AI is Google Cloud's managed way to call Gemini: you authenticate with your cloud identity (Application Default Credentials locally, a service account in CI), pick a model name and a region, and call it through the `google-genai` SDK. No API key in the code.
- **Prompts.** A *system instruction* sets the role and the rules; the *user prompt* carries the data. Keeping the rules fixed and the data structured makes answers consistent and easy to test.
- **Configs.** *Temperature* controls randomness: 0 means the most likely answer every time, which is what you want for code. The model name and temperature are configuration, not code.
- **Scale and cost.** You pay per token, in and out. The levers are: send less (only the relevant file and targets), send once (cache identical prompts), and bound the loops (at most two repairs).
- **Fine-tuning** trains a model on your examples. It helps when the task is narrow and the base model keeps getting the format wrong; it costs data, time and a frozen model version. For "write pytest for this function" the base model with a clear prompt is enough.
- **Multi-agent** means several models with different roles passing work to each other. It adds coordination code, latency and failure modes. Use it when one role cannot do the job, not as a default.

## How this project applies it

| Topic | In the code |
| --- | --- |
| Setup | `llm_client.py` creates the Vertex AI client lazily, from `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GEMINI_MODEL` |
| Prompts | three pairs in `prompts.py`: generate, repair, update; each a fixed system instruction plus a structured user prompt |
| Configs | `temperature: 0.0` and `gemini_model: gemini-2.5-flash` in `ai-test-assistant.yml`, overridable by env or flags |
| Validation | `llm_test_code.py` turns the answer into a validated pytest module or raises |
| Cost | `LlmUsageStats` counts calls, seconds and tokens; the worker exports them as metrics |
| Cache | key = SHA-256 of model, temperature, system instruction and prompt; LRU by default, LFU on request |
| Offline mode | `--dry-run` returns a fixed placeholder; the whole tool, and its CI, works without the cloud |
| Fine-tuning, multi-agent | deliberately not used; explained above |

**A bug that teaches the cache rule.** The first version put the absolute path of the temporary clone into the prompt. Every job cloned to a new folder, so every prompt was unique and the cache never hit, silently, because the answers were still correct. The fix was to use module paths only, with a test (`test_prompt_stability.py`) that asserts two clones of the same code produce identical prompts. A cache key must be built from normalised input.

## Likely questions

**Q:** Why temperature 0 and not a little creativity?

**A:** A test is a specification; two runs of the tool on the same code should produce the same tests. Determinism also makes the cache possible and the behavior debuggable.

**Q:** Does the model see secrets or private code?

**A:** It sees the changed source file and related tests, nothing else from the repository, and the call goes to the company's own Vertex AI project. Secrets live in the environment, never in prompts.

**Q:** Why Gemini 2.5 Flash?

**A:** It is fast and cheap enough to run on every pull request, and the task does not need a larger model: the hard checks are done by pytest, not by the model.
