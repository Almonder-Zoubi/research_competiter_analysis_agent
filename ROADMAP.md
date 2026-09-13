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

### Day 8 — Observability + dashboard  ✅ (done)
Wire Langfuse tracing on every loop step (plan, each tool call, each LLM call:
tokens, cost, latency, decision). Streamlit dashboard: run list, brief view, facts
table with confidence, conflicts, and run metrics.
Detailed spec: DAY_8_observability_dashboard.md
Closed 2026-09-12: both built. Tracing via `@observe()` decorators (found the
installed langfuse SDK is 4.x/OpenTelemetry-based, not the 2.x the old pin
assumed — re-pinned and wrote agent/tracing.py against the real API,
confirmed empty-key construction is instant and safe); zero test-file
changes needed since it's a no-op when disabled. Dashboard (`dashboard.py`)
reads the same `memory.repository` functions the CLI does; tested offline
via Streamlit's own `AppTest` harness plus one real `streamlit run` smoke
test. Confirmed live: `research-agent run --company "Linear"` (run #10) with
the dashboard server running — the new run appeared immediately, no
restart; also surfaced 8 real conflicts. 95 tests, ruff + mypy green. Only
open item: real Langfuse keys (needs the user to create a free account) to
confirm actual trace export — not blocking.

### Days 9–10 — Evals + polish (what makes it a flagship)  ✅ (done)
5–10 golden test cases. Metrics led by groundedness (every claim traces to a
source?) and citation coverage, plus fact recall/precision and an LLM-as-judge for
brief quality. Then the portfolio layer: README with architecture diagram, demo
GIF, and a design-decisions + eval-results writeup. The writeup is what separates a
flagship from "some agent code."
Detailed spec: DAYS_9_10_evals_and_polish.md
Closed 2026-09-13: new `evals/` package scores 5 golden cases
retrospectively against real live runs already in the DB ($0, no fresh
searches) — `citation_coverage` (parses the real persisted brief text) and
`fact_recall` (pure), plus an opt-in LLM-as-judge (`--judge`, never called by
default; MODEL_SMART, one call per case). Real result straight from the DB:
0% citation coverage on the 3 pre-Days-6-7 runs, 100% on the 2
post-verification runs, 100% fact recall on every case with real facts.
Confirmed with a real `--judge` run: the judge's groundedness score climbs
1→1→2→4→3 in the *same order* as citation coverage — an independent
qualitative signal agreeing with the objective metric, while clarity stayed
high (4-5/5) throughout regardless, showing a brief can read well while
still being ungrounded. README gained a Mermaid architecture diagram +
this eval-results table. Found a second instance of the Days 6-7 packaging
bug (`evals/` also missing from `pyproject.toml`'s packages list) — caught
immediately this time and fixed a permanent regression test
(`tests/test_packaging.py`) into place so a third package can't repeat it.
115 tests, ruff + mypy green. Only remaining item: a demo GIF, left to the
user (no screen-recording capability in this environment) — not blocking.
This closes the core roadmap through the MVP cutline.

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
