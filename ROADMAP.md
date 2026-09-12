# ROADMAP — Research / Competitor-Analysis Agent

The whole arc of the project in one place. Claude Code should read this to
understand where any given day's work fits. Detailed per-milestone specs live in
their own files (e.g. DAYS_2_3_walking_skeleton.md); this is the map, not the
turn-by-turn.

See CLAUDE.md for architecture and hard rules. See PROGRESS.md for live status.

## The one-line goal

A research agent that, given a company or topic, plans searches → fetches and reads
pages → extracts structured facts → cross-checks them across sources → writes a
sourced brief → stores everything in a DB a dashboard reads from. Headline feature:
**verification** (agreement raises confidence, disagreement is flagged). Headline
metric: **% of brief claims grounded in a cited source.**

## Guiding principle

Thin vertical slice first, then depth. Always keep a working end-to-end path after
Day 3 — never break the walking skeleton. A narrow agent that reliably profiles one
company and traces every step beats an ambitious half-broken one.

## Milestones

### Day 1 — Skeleton & rails  ✅ (done)
Repo, config, Pydantic schemas, RunState, first ORM table, tests green. $0.

### Days 2–3 — Walking skeleton  ✅ (done)
One command produces a crude sourced brief end to end: plan → 1 search → store →
1 LLM call → store → print. Tool base with error categories, search tool tested
offline, DB round-trip tested offline, then ONE deliberate real run.
Detailed spec: DAYS_2_3_walking_skeleton.md
Closed 2026-09-11: `research-agent run --company "Stripe"` ran live end to end
(run #3 — 8 sources, 1066-char brief, all stored). Tests/ruff/mypy stayed green
through the live run.

### Days 4–5 — Harden the tools  ✅ (done)
Real multi-query search. Fetch tool (httpx + trafilatura) with retries, timeouts,
robots-awareness, HTML→text cleaning. Structured extraction tool: text → Fact
objects, validated against Pydantic with one repair retry. Full error-handling
layer + budget guards enforced everywhere. Circuit breaker so one bad tool doesn't
kill a run. This is where most engineering-maturity signal lives.
Detailed spec: DAYS_4_5_harden_tools.md
Closed 2026-09-12: `research-agent run --company "Notion"` ran live end to end
(run #7 — 9 sources, 60 extracted facts across all of them, brief synthesized,
all stored). 74 tests (19 new), ruff + mypy green through the live run.

### Days 6–7 — Verification (the headline feature)  ✅ (done)
Cross-check / reconcile facts across sources: group by attribute, agreement →
higher confidence, disagreement → recorded conflict. Confidence = corroborating
independent sources × source-quality heuristic. Then synthesize a properly cited
brief where every claim carries a source. Make verification visible in output.
Detailed spec: DAYS_6_7_verification.md
Closed 2026-09-12: new `verify/` package (`reconcile.py`, `grounding.py`),
`agent/cited_brief.py` replacing raw-text brief synthesis, conflicts surfaced
in both `run` and `show`. Confirmed live on Figma (run #9) — 18 grounded
cited claims, 7 real conflicts (differing founding years, funding rounds,
valuations over time, the Adobe acquisition), confidence spread 0.3–1.0
across 61 facts. A first attempt (run #8) found a real truncation bug
(`max_tokens` too low), same root cause as the earlier Wirecard bug at a
different call site — fixed and reconfirmed. 92 tests, ruff + mypy green.

### Day 8 — Observability + dashboard  ← CURRENT
Wire Langfuse tracing on every loop step (plan, each tool call, each LLM call:
tokens, cost, latency, decision). Streamlit dashboard: run list, brief view, facts
table with confidence, conflicts, and run metrics.

### Days 9–10 — Evals + polish (what makes it a flagship)
5–10 golden test cases. Metrics led by groundedness (every claim traces to a
source?) and citation coverage, plus fact recall/precision and an LLM-as-judge for
brief quality. Then the portfolio layer: README with architecture diagram, demo
GIF, and a design-decisions + eval-results writeup. The writeup is what separates a
flagship from "some agent code."

## MVP cutline

Ship at least through Day 8 (working agent + dashboard + observability). Days 9–10
are what make it stand out — do not skip the writeup if at all possible.

## Stretch goals (post-MVP, only if time)

- Swappable LLM backends (Ollama local + DeepSeek) benchmarked against Claude on the
  eval harness — cost / latency / groundedness. Strong portfolio story; the config
  already abstracts the model behind MODEL_FAST/MODEL_SMART.
- Vector-based semantic dedup of facts (this is where a small embedding model like
  MiniLM would fit — NOT as the agent's brain).
- Incremental re-runs / caching; concurrency.
- Phase 2 full-stack: FastAPI backend + React/TypeScript frontend replacing (or
  alongside) Streamlit. ~3–4 extra days. Only if targeting full-stack breadth over
  AI/ML depth. FastAPI (not Django) — thin wrapper over the existing agent.

## Cost posture

Whole project realistically $0–5. SQLite/Streamlit/Langfuse-self-host/FastAPI/React
all free. Tavily free tier (1,000 credits/mo). Only LLM calls cost money — cents per
run. Model routing (Haiku for grunt work, Sonnet for synthesis), cached fixtures for
dev, and a console spend cap keep it near zero.
