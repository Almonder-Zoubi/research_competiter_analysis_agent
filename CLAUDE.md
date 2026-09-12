# CLAUDE.md — project context for Claude Code

Claude Code reads this file automatically at the start of every session in this repo.
It's how Claude "knows" the project without being re-briefed. Keep it accurate as the
project evolves.

## What this project is

A **research / competitor-analysis agent**, built as a portfolio flagship for AI/ML
roles. Given a company or topic, it: plans searches → fetches and reads pages →
extracts structured facts → cross-checks them across sources → writes a sourced brief
→ stores everything in a database that a dashboard reads from.

The headline feature is **verification**: atomic facts are extracted with their source,
grouped by attribute, and reconciled — agreement raises confidence, disagreement is
flagged as a conflict. The headline metric is **% of brief claims grounded in a cited
source**.

## Who I am

Junior developer. Explain non-obvious choices briefly rather than assuming. Prefer
clear, conventional code over clever code. When there's a fork, say which option you'd
pick and why in one line.

## Architecture (the control loop)

Hand-rolled loop (NOT LangGraph/CrewAI — I want to own the control flow for interviews):

    plan -> execute (tools) -> verify (cross-check) -> synthesize (brief) -> persist

- **RunState** (typed dataclass) is working memory, passed through the loop.
- The SQL fact store is long-term memory (also used to skip re-fetching URLs).
- Every tool is a plain function with a Pydantic schema, wrapped in uniform error
  handling.

## Stack (all chosen to be free / near-free)

- **Python 3.11+** — agent core
- **Anthropic SDK** — LLM calls. Model routing for cost: `MODEL_FAST` (Haiku) for
  planning/extraction, `MODEL_SMART` (Sonnet) for synthesis/verification.
- **Tavily** — web search (free tier, 1,000 credits/mo). Returns extracted content,
  so it doubles as part of fetching.
- **trafilatura + httpx** — page fetching/cleaning for non-Tavily fetches.
- **Pydantic** — all structured I/O and config.
- **SQLAlchemy + SQLite** — storage. File-based, zero-config, `git clone` and run.
- **reportlab** — PDF rendering for `--deep-research` reports. Pure Python, no
  system deps.
- **Langfuse** — LLM tracing (hosted free tier; optional, degrades gracefully if keys
  are absent).
- **Streamlit** — dashboard (pure Python). A FastAPI + React frontend is an explicit
  PHASE 2, only after the core works end to end.

## Hard rules

- **Never print, log, or commit API keys.** Secrets live in `.env` (gitignored).
- **Every LLM output that should be structured is validated against a Pydantic model**,
  with one repair retry on invalid output — never trust raw model JSON.
- **Budget guards are mandatory**: respect MAX_STEPS, MAX_SOURCES, RUN_TIMEOUT_SECONDS
  from config. The loop must be unable to run away (it costs real money).
- **Tools must be testable offline**: save HTML fixtures so tests don't hit the live
  network. No live network calls in the test suite.
- Every claim in a generated brief must carry a source. Unsourced claim = a bug.

## Conventions

- Type hints everywhere; code must pass `ruff` and `mypy`.
- Tests with `pytest`; put fixtures under `tests/fixtures/`.
- Keep functions small and single-purpose. Prefer pure functions in `verify/`.
- Commit messages: short imperative summary line.

## When suggesting work

- Keep the end-to-end path working after Day 3 — never leave the repo in a state where
  the walking skeleton is broken.
- If a change would add a new paid dependency or a heavyweight framework, flag it first.
- Prefer the smallest change that moves the current milestone forward.

## Planning docs in this repo (read these)

- **ROADMAP.md** — the whole project arc, all milestones through end of project.
- **PROGRESS.md** — live status. At the END of each work session, update the "Now"
  section, check off completed items, and add any decision to the decision log.
  Keep it short.
- **DAYS_2_3_walking_skeleton.md** and **DAYS_4_5_harden_tools.md** (both done)
  — turn-by-turn build specs per milestone. Each new milestone gets its own
  spec file; check PROGRESS.md for which milestone is current and whether its
  spec file has been written yet.

At the start of a session, read PROGRESS.md to see where things stand. At the end,
update it. This keeps every session (and any reviewer) oriented without re-briefing.
