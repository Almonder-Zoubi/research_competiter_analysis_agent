# PROGRESS.md — live project status

A running log Claude Code keeps up to date. At the end of each work session, update
the "Now" section and check off what's done. This is the fastest way for a new
Claude Code session (or a human reviewer) to see exactly where things stand.

Keep it short. This is a status board, not a diary.

---

## Now

**Current milestone:** Days 2–3 — Walking skeleton (spec: DAYS_2_3_walking_skeleton.md)
**Next action:** Step 1 — tool base contract (tools/base.py) with error categories.
**Blockers:** none.
**Cost to date:** $0.00 (no live API calls yet).

---

## Done

- [x] Day 0 — environment setup; both API keys verified; DB writable.
- [x] Day 1 — config, schemas (Source, Fact), RunState + budget guards,
      tests (8 passing), ruff + mypy green. Committed.

## In progress

- [ ] Days 2–3 — walking skeleton
  - [ ] Step 1 — tools/base.py (error categories + ToolResult) + test
  - [ ] Step 2 — tools/search.py (Tavily, Pydantic I/O, uniform errors)
  - [ ] Step 3 — offline search test against tests/fixtures/tavily_*.json
  - [ ] Step 4 — memory/ (SQLAlchemy models + repository), round-trip test
  - [ ] Step 5 — thin loop + planner + CLI
  - [ ] Step 6 — one deliberate real run (first billed run)

## Upcoming (see ROADMAP.md for detail)

- [ ] Days 4–5 — harden tools (fetch, extract, full error handling)
- [ ] Days 6–7 — verification + cited synthesis (headline feature)
- [ ] Day 8 — observability (Langfuse) + Streamlit dashboard
- [ ] Days 9–10 — evals + README/writeup (flagship polish)

## Decision log

Short record of choices, so they aren't relitigated.

- Hand-rolled control loop, not LangGraph/CrewAI — want to own control flow for
  interviews.
- Core build stays on Anthropic/Claude. DeepSeek considered and set aside for the
  core (savings negligible at this scale; China-based data processing is a poor fit
  for the portfolio narrative). DeepSeek kept as benchmark ammo for the pluggable-
  backend stretch goal.
- SQLite + SQLAlchemy for storage (zero-config, clone-and-run; Postgres later via
  same ORM if needed).
- Streamlit for dashboard now; FastAPI + React only as an explicit phase-2 stretch.
- Model routing: MODEL_FAST (Haiku) for planning/extraction, MODEL_SMART (Sonnet)
  for synthesis/verification.
