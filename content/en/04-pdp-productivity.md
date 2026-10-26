# 4. PDP · AI Tools for Better Productivity {#en-productivity}

## In plain words

AI tools help a developer in three ways: they finish what you started (completion), they answer questions about code (chat), and they do whole tasks on their own (agents). This project is an agent of the third kind, aimed at one task: writing the first draft of tests. The practical lesson of the project is not "AI writes tests" but "AI writes drafts, and the workflow makes sure a person judges them."

## Theory in brief

| Kind of tool | What it does | Where it helps most | Where it fails |
| --- | --- | --- | --- |
| Completion | finishes the line or function you are typing | boilerplate, repetitive code | code that needs context the tool does not have |
| Chat | explains, reviews, rewrites on request | understanding unfamiliar code, finding options | long sessions where it loses track |
| Agent | performs a task end to end with tools | repeatable tasks with a clear check (tests pass) | tasks without a check, where wrong output looks right |

Three rules make these tools pay off instead of costing time:

- **Give the tool a check it cannot fake.** For tests, the check is pytest. For code, it is the test suite. Without a check, a confident wrong answer costs more than no answer.
- **Keep the human decision small and explicit.** Review a diff, accept or reject. Do not ask people to supervise a running process.
- **Measure.** Count the calls, the time and the tokens; a tool that is not measured is a tool nobody can defend in a budget discussion.

## How this project applies it

- **The tool is the check-first kind.** A generated test is cleaned, validated, written, executed and repaired before a person sees it (section 6). The reviewer's job is to read a test that already passes, not to debug one.
- **The decision is one click.** Tests and suggestions arrive as artifacts; the developer keeps what is useful. In the demo repository a maintainer applies suggested updates by adding one label to the PR.
- **Everything is measured.** The cloud worker counts calls, seconds and tokens per job and shows them in Grafana (section 9). The cache shows how much repeated work was avoided: on the same job run twice, the second run made zero LLM calls.
- **Honest limits are written down.** Generated assertions can be wrong in a way that still passes (a test that asserts the bug). That is why the output is a draft for review, not a merged test.

## Likely questions

**Q:** How do you know the tool saves time?

**A:** The report shows what was produced per file and whether it passed; the metrics show the cost. The time saved is the time between "empty test file" and "a passing draft to edit", which for the demo repository is a few minutes per PR instead of an afternoon.

**Q:** Could the generated tests give false confidence?

**A:** Yes, if they are merged unread. That is the one failure mode the design cannot remove, so the design makes merging a deliberate human act and marks every file as AI-generated in its header.
