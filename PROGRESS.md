# PROGRESS.md — live project status

A running log Claude Code keeps up to date. At the end of each work session, update
the "Now" section and check off what's done. This is the fastest way for a new
Claude Code session (or a human reviewer) to see exactly where things stand.

Keep it short. This is a status board, not a diary.

---

## Now

**Current milestone:** Days 6–7 — Verification (the headline feature). No spec
  file written yet — next session should draft DAYS_6_7_verification.md before
  coding, same pattern as prior milestones.
**Next action:** Design the fact-reconciliation step: group `Fact` rows by
  attribute (per run), decide a corroboration/conflict rule, and add a
  confidence adjustment. Then rewrite brief synthesis to cite sources per claim
  instead of one ungrounded paragraph.
**Blockers:** none. Anthropic account funded ($5) 2026-09-11.
**Cost to date:** ~$0.30-0.35 spent through the deep-research diagnostic work
  (see decision log), plus one more live run this session (`research-agent run
  --company "Notion"`, run #7 — 9 sources, ~12 steps: light-mode routine cost,
  well under 5¢) to prove Days 4-5's hardened path end to end. Routine run cost
  is ~1-2¢ (light, now with extraction) / ~4-9¢ (deep).

---

## Done

- [x] Day 0 — environment setup; both API keys verified; DB writable.
- [x] Day 1 — config, schemas (Source, Fact), RunState + budget guards,
      tests (8 passing), ruff + mypy green. Committed.
- [x] Days 2–3 — walking skeleton. All 6 steps done, incl. the one deliberate
      real run (`research-agent run --company "Stripe"` → run #3, 8 sources,
      brief stored). 23 tests passing, ruff + mypy green. Code committed in
      `e4eaced`; the live run itself only touches the gitignored DB file.
- [x] Days 4–5 — harden the tools (spec: DAYS_4_5_harden_tools.md). New
      `tools/fetch.py` (httpx + trafilatura, robots.txt checked through the
      same injectable HTTP client so it stays offline-testable, retries on
      timeout/5xx, 404/403/401/410 → PERMANENT, no-extractable-text →
      VALIDATION) and `tools/extract.py` (MODEL_FAST → `list[Fact]` via
      `agent/llm.py`'s existing validate+repair-retry; the model is only asked
      for attribute/value — `source_url` is filled in by the tool itself,
      never trusted from the model). Wired into `run_research()`: sources
      under 200 chars get backfilled via fetch before extraction, both gated
      by `can_take_step`/`can_fetch_source`; every source then goes through
      extraction and its facts get persisted via the existing `save_facts()`.
      New circuit breaker (`RunState.record_tool_failure/record_tool_success`,
      `MAX_CONSECUTIVE_FAILURES = 3`) wired into search, fetch, and extract —
      3 consecutive failures at any stage stops the run from pursuing further
      sources and falls through to synthesis with whatever was gathered, same
      "always have something to persist" guarantee brief synthesis already
      had. 74 tests passing (19 new), ruff + mypy green. **Real run**:
      `research-agent run --company "Notion"` (run #7) — 9 sources, **60
      facts extracted and persisted** (the new capability this milestone
      exists for), brief synthesized, 12 steps used, still cents.

## Done (ad hoc, outside milestone sequence)

- [x] `research-agent list` / `research-agent show --run-id N` — recall past runs
      from the DB (brief, sources, facts) without another live call. Added
      `RunSummary` schema + `list_runs()` in memory/repository.py. 25 tests
      passing (2 new), ruff + mypy green.
- [x] LLM-driven planner + source-quality filter (user flagged: template
      queries assumed every subject was a funded startup, and search returned
      un-authoritative sources like a YouTube video). `agent/planner.py` now
      calls MODEL_FAST to pick a query strategy per subject type (company vs.
      engineering/research field vs. an initiative inside a larger company),
      falling back to a subject-agnostic template if the call fails.
      `tools/search.py` excludes a small blocklist of video/social domains via
      Tavily's `exclude_domains`. New `agent/llm.py` factors the
      validate-plus-repair-retry pattern shared by the planner and brief
      synthesis. Verified live on "harness engineering" (a non-company
      subject) — run #4: 9 sources, all real articles/blogs/PDFs, zero
      video/social results. 35 tests passing (10 new), ruff + mypy green.
- [x] `--deep-research` mode (user critique: a one-paragraph brief is too thin
      to justify the engineering — anyone gets that from a chatbot). Opt-in
      flag on `run` that does 5-6 targeted searches (incl. an explicit
      controversies/scandal query) and renders a structured, multi-section
      PDF report to `reports/` (origin, ownership, financials, scale,
      controversies for a company; analogous sections for a field/initiative).
      New: `agent/deep_research.py` (query planning + section synthesis),
      `agent/report.py` (reportlab PDF rendering — new dependency), a
      `report_path` column on `runs` (with an in-place SQLite migration in
      `memory/db.py` since `create_all()` doesn't add columns to existing
      tables — preserves the DB's existing real runs instead of deleting it).
      **Real bug found and fixed via a live run** (`research-agent run
      --company "Wirecard" --deep-research`, a company with genuine
      documented scandal history — the exact case this feature targets):
      the first attempt failed both the primary call and its repair retry.
      Diagnosis (see decision log) found two compounding issues, both fixed:
      `max_tokens=2500` truncated mid-JSON on a data-rich topic (confirmed via
      `stop_reason: "max_tokens"`), and even after raising it, the model
      produced malformed JSON from unescaped quotes when relaying a source's
      exact wording (common on scandal coverage, which quotes people/filings
      a lot). Fixed: `max_tokens` → 4000, an explicit "don't use literal
      double quotes in string values" instruction in the prompt, and — since
      this is shared infra — `agent/llm.py`'s repair-retry now echoes back the
      actual validation error and the quote warning to *every* caller
      (planner, brief, deep planner, deep synthesis), not just this one.
      55 tests passing (18 new), ruff + mypy green. **Confirmed fixed with a
      second live run** (run #6, same company): all 6 sections generated
      correctly, including a detailed, well-sourced Controversies & Legal
      Issues section (the €1.9B fraud, EY/KPMG audit failures, executive
      prosecutions, BaFin criticism) — the exact outcome this feature was
      built for. 3-page PDF at `reports/run_6_wirecard.pdf`.

## In progress

- [ ] Days 6–7 — verification + cited synthesis (headline feature). No spec
      file yet — write DAYS_6_7_verification.md first. Rough shape from
      ROADMAP.md: group `Fact` rows by attribute per run, corroboration across
      independent sources raises confidence, disagreement is recorded as a
      conflict rather than silently dropped; then rewrite brief synthesis so
      every claim in the output carries its source (the project's headline
      metric: % of brief claims grounded in a cited source).

## Upcoming (see ROADMAP.md for detail)

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
- Planner uses MODEL_FAST to choose a query strategy per subject type instead of
  a single fixed template — a hardcoded "company overview/funding/founders"
  template breaks down for non-company subjects (e.g. "harness engineering").
  Falls back to a subject-agnostic template on model failure so this can't
  crash a run.
- Source-quality filtering is a small domain *blocklist* (video/social
  platforms), not an allowlist — research subjects vary too widely (a company
  vs. an engineering field) for any fixed "trusted domains" list to fit both.
  Deeper credibility weighting (official site > major outlet > blog) is
  deferred to Days 6-7 verification, once corroboration across sources exists.
- Tavily `search_depth` left at its default ("basic", 1 credit) rather than
  "advanced" (2 credits) — keeps the domain-filter improvement free. Easy to
  flip in tools/search.py if source quality still needs work after Days 4-5.
- Deep-research report is one flexible `ReportSection` schema (heading,
  content, source_urls) reused across every subject type, not one Pydantic
  model per type (company/field/initiative) — which headings get asked for is
  prompt guidance, not schema variation. Avoids a combinatorial pile of
  near-duplicate models for a difference that's really just "which 5-6
  headings," not a structural one.
- `reportlab` added as a new dependency for PDF rendering — pure Python, no
  system deps (unlike weasyprint's libcairo/pango requirement), already
  hand-verified working on this machine.
- DB schema changes are patched in place (`memory/db.py`'s
  `_ensure_report_path_column`, a manual `ALTER TABLE` behind a `PRAGMA
  table_info` check) rather than via Alembic — one nullable column doesn't
  justify a migration framework yet, and deleting the dev DB to dodge the
  problem would have destroyed real proof-of-work (the Stripe/harness-
  engineering runs). Revisit with a real migration tool if more columns pile
  up.
- Wirecard live-run diagnosis (2026-09-12): confirmed via `response.stop_reason`
  that `max_tokens=2500` was too low for a data-rich deep-research topic, and
  separately that the model can emit unescaped literal quotes when relaying a
  source's exact wording, breaking JSON well past that fix. Rather than patch
  only the deep-research call, generalized the fix into `agent/llm.py`'s
  shared repair-retry: it now includes the actual pydantic error and a quote
  warning in the retry prompt, benefiting all four callers. A generic "that
  wasn't valid JSON, try again" retry is weak — telling the model what
  specifically broke is what actually improves the retry's odds.
- Fact extraction never asks the model for `source_url` — only
  attribute/value. We already know which source we're extracting from;
  filling it in ourselves is strictly more reliable than trusting the model to
  echo a URL back correctly, and matches the same reasoning behind
  `_drop_hallucinated_urls` in deep_research.py.
- `tools/fetch.py`'s robots.txt check goes through the tool's own injectable
  HTTP client rather than `urllib.robotparser`'s built-in fetch (`.read()`) —
  the built-in version bypasses whatever client a test injects, which would
  make robots-checking untestable offline. Fetching robots.txt through the
  same client keeps the whole tool testable with one fake, and a robots.txt
  that itself fails to fetch is treated as "allowed" (fail open) rather than
  blocking the page — common crawler convention, and safer than silently
  refusing to fetch pages on sites with a broken or absent robots.txt.
- Circuit breaker is one counter on RunState (`consecutive_failures`,
  `record_tool_failure`/`record_tool_success`), shared across search, fetch,
  and extract — not a per-tool breaker. A run failing repeatedly for any
  reason (flaky network, a bad extraction prompt, a hostile site) should stop
  pursuing further sources the same way; splitting the counter per tool would
  let one tool fail forever while resetting via the others' successes, which
  defeats the point.
- Backfill fetch only replaces a source's `content` (and `title` if it was
  empty) — it never creates a new `Source`/doesn't increment `sources_used`.
  It's refreshing an existing source's content, not fetching a new one; only
  `can_take_step`/`can_fetch_source` gate whether the backfill is even
  attempted, per the spec.
