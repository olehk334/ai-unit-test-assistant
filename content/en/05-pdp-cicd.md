# 5. PDP · CI/CD + Coding Agents {#en-cicd}

## In plain words

Continuous Integration (CI) means every change is built and tested by a machine before people look at it. Continuous Delivery (CD) means a change that passed can be released by a machine too. A coding agent in CI is a program that does engineering work inside that pipeline, not just checks it. This project's agent writes tests, and the pipeline makes sure its output is visible but never merged on its own.

![What happens in GitHub Actions when a pull request changes Python code.](images/ci.en.png)

## Theory in brief

- **A pipeline is a chain of steps on a trigger.** Trigger (a push, a PR, a schedule), steps (checkout, install, test, build, publish), and outputs (logs, artifacts, a status on the commit).
- **Secrets are injected, never stored in the repository.** GitHub keeps them encrypted and exposes them to a job as environment variables. For cloud access the better practice is short-lived identity (OIDC / Workload Identity Federation) instead of a long-lived key.
- **Artifacts and summaries are how a job talks to people.** An artifact is a file the job uploads; the step summary is Markdown shown on the run page.
- **`if: always()`** runs a step even when an earlier step failed, which is how a report survives a failed run.
- **A coding agent needs a boundary.** It may read the repository and write artifacts; it may not push, merge or change secrets. Anything beyond that boundary should require a human action.

## How this project applies it

Two workflows live in `.github/workflows/`:

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `ci.yml` | every PR and push to `main` | installs the project and runs its own 103 tests (dry-run, no cloud) |
| `ai-test-assistant.yml` | a PR that changes any `.py` file | checks out full history, runs `run-pr-assistant`, appends the report to the step summary, uploads `tests/generated/` and `reports/` as artifacts |

The demo repository (`calculator`) adds a third workflow, `apply-ai-suggestions.yml`: when a maintainer puts the label `apply-ai-suggestions` on a PR, it regenerates the suggestions, applies them with `ai-test-assistant apply-suggestions`, and commits to the PR branch. The agent crosses the "write to the repository" boundary only because a person asked by name.

Two details worth knowing:

- `fetch-depth: 0` on checkout, because `git diff base...HEAD` needs the history of both branches. A shallow clone would silently find nothing, so since October the tool fails loudly when git cannot diff: the run goes red instead of green with "no changes".
- The `apply-suggestions` command refuses to write anything that is not a test file or that resolves outside the repository, even from a corrupted artifact. Production code cannot be overwritten through this path.

## Likely questions

**Q:** Why not let the agent commit the tests directly?

**A:** Because a test that passes can still be wrong, and a commit made by a bot is reviewed less carefully than a diff a person must click on. Artifacts plus a label keep the human step explicit and cheap.

**Q:** What does the pipeline do when Gemini is down?

**A:** Each file is reported with an error, the report is still written (`if: always()`), and the workflow fails visibly. Nothing is retried blindly in CI; retries belong to the queue in the cloud mode.

**Q:** How are the Vertex AI credentials handled?

**A:** In the demo repository's workflow, the Google auth action signs in with a service-account key stored as the secret `GCP_SA_KEY`; the project, location and model name come from secrets and variables. The better practice, and the next step, is Workload Identity Federation: a short-lived token instead of a stored key. Locally the tool uses Application Default Credentials. No key is ever written into a repository.
