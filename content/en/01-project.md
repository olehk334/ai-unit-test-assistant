# 1. The project on one page {#en-project}

## In plain words

When a developer changes Python code and opens a pull request, the tests for that change are often written in a hurry, or not at all. **AI Unit Test Assistant** is a small Python tool that writes the first draft of those tests. It looks at what changed, asks Gemini (Google's LLM, through Vertex AI) for pytest tests, runs them, repairs the ones that fail, and leaves the result in the pull request for the developer to review.

It never commits code and never overwrites existing tests. Everything it produces is a suggestion.

![One pull request, from changed code to reviewed tests.](images/one-pr.en.png)

## What it does, in one sentence

Changed code goes in, reviewed tests come out.

## The numbers

| What | Value |
| --- | --- |
| Core library | 18 modules, 1,816 lines of Python |
| Cloud services | 2 services, 515 lines |
| Tests of the tool itself | 103, all run offline in dry-run mode |
| LLM | Gemini 2.5 Flash on Vertex AI, temperature 0 |
| Ways to run it | your terminal, GitHub Actions, Google Cloud |
| External dependencies of the core | google-genai, typer, pyyaml, python-dotenv, pytest |

## What it deliberately does not do

- It does not commit anything. Generated tests arrive as artifacts; a person decides.
- It does not overwrite existing tests. Suggested updates are written next to the report, and a separate command applies them only when asked.
- It does not touch production code. Only test files are ever written.
- It has no web UI, no database and no agent framework. One linear flow, readable top to bottom.

## How this document is organised

Sections 2 and 3 explain how the tool works and where it runs. Sections 4 to 11 take the eight PDP topics one by one: a short piece of theory, then how this project puts it into practice. Section 12 sums up what is covered and gives the talking points. Each section starts in plain words and adds detail gradually; the pictures carry the mechanism, the text carries the reasons.

## Likely questions

**Q:** Why an LLM for tests at all? Tests are precise work.

**A:** Because the hard part of writing tests is starting. The tool produces a draft in minutes; the developer spends their time judging the draft instead of staring at an empty file. Every draft is validated and executed before anyone sees it.

**Q:** What happens when the LLM is wrong?

**A:** The test fails. The tool feeds the failure back to the model up to two times; if it still fails, the report says so, and the file stays marked as failed. Nothing wrong reaches the code base, because nothing is committed automatically.

**Q:** How much does a run cost?

**A:** One Gemini call per changed file, plus one per repair and one per suggested update. Repeated prompts are served from a cache at no cost. The project's own CI runs in dry-run mode and costs nothing.
