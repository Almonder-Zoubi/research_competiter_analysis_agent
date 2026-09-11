# Days 2–3 — Walking skeleton (build spec for Claude Code)

Read CLAUDE.md first — its hard rules apply to everything below.

## Goal of this milestone

One command produces a crude, sourced brief end to end:

    plan → 1 real search → store sources → 1 real extract/synthesize call → store → print

By the end of Day 3, `research-agent run --company "Stripe"` (or similar) should
run start-to-finish and persist its result. Corners may be cut; it may be ugly.
The ONLY thing that matters: the whole path works and stores something. After this
milestone, never leave the end-to-end path broken.

Build order below is deliberate. Steps 1–4 are $0 and fully offline (tested against
fixtures). Step 5 is the FIRST and ONLY step that makes live API calls.

---

## Step 1 — Tool base contract (`tools/base.py`)

Build this first; search/fetch/extract all inherit its pattern.

- A `ToolError` category enum or set of typed results distinguishing:
  - `TRANSIENT` (network, timeout, rate-limit) → caller may retry
  - `PERMANENT` (bad request, 404, auth) → caller skips + logs
  - `VALIDATION` (output failed Pydantic parse) → caller may repair/re-ask
- A `ToolResult` wrapper (Pydantic or dataclass): either `ok=True` with a typed
  `value`, or `ok=False` with an error category + message. Tools NEVER raise raw
  exceptions to the loop — they catch and return a `ToolResult`.
- A minimal `Tool` protocol/base: a `name`, and a `run(input) -> ToolResult`.
- Unit test: a dummy tool that returns each category, asserting the wrapper shape.

Rationale note for the writeup: this mirrors the auth (401) vs billing (400) vs
bad-key distinction — different error categories get handled differently.

## Step 2 — Search tool (`tools/search.py`)

- Pydantic input: `SearchInput(query: str, max_results: int = 5)`.
- Pydantic output: `list[Source]` (reuse the existing `Source` schema).
- Wraps the Tavily client. Maps Tavily failures to the right `ToolError` category.
- Uniform error handling via the base — returns a `ToolResult`, never raises.
- Do NOT call the network in tests.

## Step 3 — Offline test for search (`tests/test_search.py` + fixture)

- Save a realistic Tavily JSON response at `tests/fixtures/tavily_stripe.json`
  (a few results, each with url/title/content). Hand-write or lightly adapt one.
- Test injects the fixture (monkeypatch the client / pass a fake) and asserts the
  tool parses it into `Source` objects correctly, and that a simulated failure
  returns the correct error category. Zero live calls.

## Step 4 — Persistence (`memory/db.py`, `memory/models.py`, `memory/repository.py`)

- SQLAlchemy engine/session from `DATABASE_URL` (SQLite).
- ORM models mirroring the Pydantic schemas: `runs`, `sources`, `facts`.
  (facts can be minimal for now — the walking skeleton may store just sources +
  a brief; full fact extraction is Days 4–7. But create the table.)
- `repository.py`: `save_run`, `save_sources`, `load_run` helpers that convert
  between ORM rows and Pydantic models.
- Test the save → load round-trip against a TEMPORARY sqlite file (tmp_path
  fixture), asserting what went in comes back out. Offline, $0.

## Step 5 — The thin loop + CLI (`agent/loop.py`, `agent/planner.py`, `cli.py`)

This is where it comes together. Keep each piece minimal.

- `planner.py`: for now, turn the company name into 1–3 search queries. A hardcoded
  template is fine ("<company> overview", "<company> funding", "<company> founders").
  No need for an LLM call here yet if you want to keep step 5's first run cheap —
  but an LLM planner is fine too.
- `loop.py`: orchestrate — plan → run search tool → store sources → make ONE Claude
  call that takes the fetched source text and writes a short brief (plain text or a
  simple `Brief` Pydantic model) → store it → return it. Respect the budget guards
  from RunState at each step (`can_take_step`, `can_fetch_source`).
- `cli.py`: `research-agent run --company "<name>"` — runs the loop, prints the brief
  and where it was stored.
- Model routing: use MODEL_FAST for planning/simple calls, MODEL_SMART for the brief.

## Step 6 — The one deliberate real run

Only after steps 1–4 are green offline:

- Run the CLI once against a real company.
- Expect: 1 Tavily credit used, a few cents of Claude usage, a brief printed, rows
  in the DB.
- If it works end to end: the walking skeleton is DONE. Commit it.

---

## Definition of done for Days 2–3

- [ ] `tools/base.py` with error categories + ToolResult, tested
- [ ] search tool parses a fixture into Sources, tested offline
- [ ] DB layer round-trips a run, tested offline against tmp sqlite
- [ ] `research-agent run --company X` runs end to end and persists
- [ ] pytest / ruff / mypy all green
- [ ] committed, with .env confirmed still ignored

## Rules (from CLAUDE.md — repeated because they matter here)

- No live API calls in the test suite; tools tested against fixtures.
- Every structured LLM output validated against Pydantic; one repair retry.
- Budget guards respected in the loop — it must be unable to run away.
- Never log or commit keys.
- Keep commits small: one per component, when green.
