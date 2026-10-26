# 3. Where it runs {#en-where}

## In plain words

The eight steps are a library. Three different things can call it: a developer at a terminal, a GitHub Actions workflow, and a cloud service. The library does not know which one is calling. Only the trigger and the place the result goes differ.

![The same core runs in three places.](images/two-ways.en.png)

## The three entry points

| Entry point | Command or event | Good for |
| --- | --- | --- |
| Terminal | `ai-test-assistant run-pr-assistant --base-ref origin/main` | trying it on your own branch; `--dry-run` works without any cloud access |
| GitHub Actions | a pull request that changes `.py` files | one repository; no infrastructure to run |
| Google Cloud | a GitHub webhook | many repositories; one shared service with metrics |

The single-file command, `ai-test-assistant generate-tests --source path/to/file.py`, runs the same steps for one file and writes only generated tests, never suggestions.

## One configuration, four layers

Settings come from four places, each one overriding the one before: built-in defaults, `ai-test-assistant.yml` in the repository, environment variables with the same names in upper case (`DRY_RUN`, `GEMINI_MODEL`), and command-line flags. A `.env` file in the repository is loaded into the environment first. The cloud worker sets `DRY_RUN` or `GEMINI_MODEL` through its environment; the CLI through flags; both read the same loader.

## Why three ways

The terminal is for the developer who wants to see what the tool does before trusting it. GitHub Actions is the cheapest way to put it into a team's workflow: one YAML file, no servers. The cloud service exists because a company with many repositories wants one place that serves all of them, with a queue, retries and a dashboard. Sections 8 and 9 cover that mode.

## Likely questions

**Q:** Do the three modes produce different results?

**A:** No. They call the same `run_pr_assistant` function. The end-to-end tests pin the report, the file names and the order, so a change that broke one mode would break the tests of all three.

**Q:** How do I run it without a Google Cloud account?

**A:** With `--dry-run`. The LLM is replaced by a fixed placeholder test, and everything else (git, parsing, pytest, reports) runs for real. That is how the project's own 103 tests work.
