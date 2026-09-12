# Days 4–5 — Harden the tools (build spec for Claude Code)

Read CLAUDE.md first — its hard rules apply to everything below. Read
DAYS_2_3_walking_skeleton.md too — this milestone extends that code, it doesn't
replace it. The walking skeleton (`research-agent run --company X`) must keep
working at every step (see CLAUDE.md: never leave the end-to-end path broken).

## Goal of this milestone

Today the loop trusts Tavily's `content` field as-is and never extracts
structured facts — it just dumps raw source text at Claude and asks for one
prose paragraph. This milestone makes the tool layer robust and adds the first
real `Fact` extraction, which Days 6–7 (verification) depends on:

    plan -> search -> [fetch full page if content is thin] -> extract facts
    -> store facts -> synthesize brief -> store -> print

Steps 1–4 are $0 and offline (tested against fixtures). Step 5 is the one real
run that proves the hardened path, same pattern as the walking skeleton.

---

## Step 1 — Fetch tool (`tools/fetch.py`)

Why: Tavily's `content` is sometimes truncated or empty. A direct fetch fills
the gap without spending another Tavily credit.

- **Stack:** `httpx` for the request, `trafilatura` for HTML → clean text
  (both already in requirements.txt).
- Pydantic input: `FetchInput(url: str)`. Output: reuses `Source`.
- Same `Tool`/`ToolResult` contract as `tools/search.py` — never raises.
- Timeout (a few seconds) and a small retry count for transient failures.
- Respect robots.txt (`urllib.robotparser` is stdlib — no new dependency) —
  a disallowed URL is a `PERMANENT` failure, not a crash.
- Map failures: connection/timeout → `TRANSIENT`; 404/403 → `PERMANENT`;
  trafilatura returning nothing extractable → `VALIDATION`.
- **Offline test:** save a real page's HTML under `tests/fixtures/` (e.g.
  `tests/fixtures/example_page.html`), point the test at a local file:// URL
  or monkeypatch the httpx client — assert clean text comes out and each
  failure mode maps to the right category. Zero live calls.

## Step 2 — Extraction tool (`tools/extract.py`)

Why: this is the first piece of the headline feature. Verification (Days 6–7)
needs atomic, attributed facts to reconcile — it can't work off a paragraph.

- **Stack:** Anthropic SDK, `MODEL_FAST` (Haiku) — extraction is high-volume,
  keep it cheap.
- Pydantic input: `ExtractInput(source: Source, topic: str)`.
- Output: `list[Fact]` (reuse the existing schema — `attribute`, `value`,
  `source_url`, `confidence`).
- Prompt: given one source's text, pull out a handful of atomic facts
  (founded year, funding, HQ, founders, valuation, etc.) as JSON. Validate
  against a Pydantic wrapper model; **one repair retry** on invalid output,
  same pattern as `_call_for_brief` in `agent/loop.py` — don't reinvent it,
  factor the repair-retry logic into something both can call if it's an easy
  lift, otherwise duplicate it once (revisit if a third caller shows up).
- Uniform error handling via the base: a malformed/unparseable model response
  after the repair retry is `VALIDATION`, not a crash.
- **Offline test:** a saved fixture of a raw Anthropic-style JSON response
  (list of fact dicts) — assert it parses into `Fact` objects, and that
  invalid JSON triggers the repair path. Zero live calls.

## Step 3 — Wire fetch + extract into the loop (`agent/loop.py`)

- After search, for any `Source` whose `content` is suspiciously short
  (pick a simple threshold, e.g. < 200 chars), call the fetch tool to
  backfill before extraction — behind `can_take_step`/`can_fetch_source` like
  every other step.
- For each source (backfilled or not), call the extract tool and accumulate
  `Fact` objects on `RunState.facts`.
- Persist facts with the existing `save_facts()` in `memory/repository.py` —
  no schema change needed, the `facts` table has been there since Day 1.
- The prose brief synthesis step stays as-is for now (a properly cited,
  claim-by-claim brief is Days 6–7's job) — just keep it working.

## Step 4 — Circuit breaker

Why: one flaky source or a bad extraction prompt shouldn't be able to loop
the run into the ground or blow through the budget on retries.

- Simplest version that earns its keep: a per-run counter of consecutive
  tool failures. If it crosses a small threshold (e.g. 3 in a row), log a
  warning and stop pursuing further sources for that run — fall through to
  synthesis with whatever was gathered, same as today's "no sources found"
  path. Reset the counter on any success.
- This is a `RunState` field + a check next to the existing budget-guard
  checks in the loop, not a new subsystem.

## Step 5 — One real run to prove the hardened path

- Run the CLI once against a company you haven't used before (avoid reusing
  "Stripe" again — a fresh company is a better signal that nothing is
  hard-coded to that fixture data).
- Expect: a few Tavily credits, at most one or two extra fetches, several
  cheap Haiku extraction calls, one Sonnet brief call — still comfortably
  cents, not dollars.
- Confirm: sources stored, facts stored (non-empty `facts` table for that
  run — this is new since the walking skeleton), brief stored, tests/ruff/
  mypy still green.

---

## Definition of done for Days 4–5

- [x] `tools/fetch.py` with error categories, tested offline against an HTML
      fixture
- [x] `tools/extract.py` producing validated `Fact` lists, tested offline
      (incl. the repair-retry path)
- [x] loop wires fetch (conditionally) + extract into the existing flow,
      behind budget guards
- [x] circuit breaker stops a run after repeated consecutive tool failures
- [x] one real run on a new company persists sources + facts + brief —
      `research-agent run --company "Notion"`, run #7: 9 sources, 60 facts,
      brief stored
- [x] pytest / ruff / mypy all green — 74 tests (19 new)
- [x] PROGRESS.md updated (steps checked off, Now/Blockers/Cost refreshed)
- [ ] committed, with `.env` confirmed still ignored

## Rules (from CLAUDE.md — repeated because they matter here)

- No live API calls in the test suite; tools tested against fixtures.
- Every structured LLM output validated against Pydantic; one repair retry.
- Budget guards respected in the loop — it must be unable to run away.
- Never log or commit keys.
- Keep commits small: one per component, when green.
