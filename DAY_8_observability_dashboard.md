# Day 8 — Observability + Dashboard (build spec for Claude Code)

Read CLAUDE.md first. This milestone doesn't change the loop's behavior or
cost — it makes what the loop already does visible: every plan/tool/LLM call
traced (optional, $0 unless you add a Langfuse account), and every stored run
browsable in a UI instead of only via `research-agent show --run-id N`.

## Part 1 — Langfuse tracing

### Real API drift found before writing any code

`requirements.txt` pinned `langfuse>=2.0`, but the installed/tested version is
4.15.2 — a completely different, OpenTelemetry-based client (`Langfuse(...)`,
`@observe()`, `get_client()`) from 2.x's explicit `client.trace()/span()`
calls. Confirmed by introspecting the installed package directly rather than
coding from memory (see CLAUDE.md's "Never guess SDK usage" spirit, applied
here to a non-Anthropic SDK too). Re-pinned to `langfuse>=4.0` with a comment
explaining why.

### Design: `@observe()` decorators, not a threaded client

The `@observe()` decorator wraps a function as a traced span/generation using
context-var-based (OpenTelemetry) propagation — no manual parent/child
threading needed, and **no function signature changes**. Confirmed
experimentally before committing to this design:
- A disabled client (no keys) constructs in <1ms, no network call.
- `@observe()` on a disabled client is a transparent pass-through — safe with
  arbitrary argument types, including this project's fake test clients
  (`_FakeAnthropicClient`, etc.) — confirmed directly.
- Net effect: **zero test file changes were needed** for the tracing rollout,
  unlike every prior milestone in this project.

This is why tracing touches so many files (loop.py, planner.py,
deep_research.py, cited_brief.py, llm.py, tools/search.py, tools/fetch.py,
tools/extract.py) with such a small diff each — one `@observe(...)` line per
function, no other change.

### Where things are traced

- **`agent/tracing.py`** (new) — `init_tracing(settings)` constructs the
  process-wide Langfuse client once (called from `cli.py`'s `_run_command`,
  before anything else); `flush_tracing()` flushes buffered traces before
  exit (called in a `finally`, so it runs even on an `AnthropicError`).
  Silences Langfuse's own noisy "client disabled" / "no active span"
  warnings, which fire on nearly every touch of a keyless client — harmless,
  confirmed via direct testing, but pure console noise while no Langfuse
  account is configured (the situation today).
- **`agent/llm.py::_call_once`** — the single choke point every structured
  LLM call goes through (planner, cited-brief, deep planner, deep synthesis,
  extraction). Decorated once as a `generation`, recording `model`,
  `input`/`output` text, and token usage (`response.usage.input_tokens` /
  `.output_tokens`) via `update_current_generation()`. One change, covers
  five callers — much higher leverage than instrumenting each call site.
- **`tools/search.py` / `tools/fetch.py` / `tools/extract.py`** — each `run()`
  decorated as a `tool` observation, satisfying "each tool call" from
  ROADMAP.md directly.
- **`agent/planner.py::plan_search_queries`**,
  **`agent/deep_research.py::plan_deep_research_queries` /
  `synthesize_deep_report`**, **`agent/cited_brief.py::synthesize_cited_brief`**
  — plain `@observe()` spans (default auto-capture of args/return is fine —
  these have simple, serializable signatures).
- **`agent/loop.py::run_research` / `run_deep_research`** — the root span for
  the whole run. `capture_input=False, capture_output=False` (several args —
  `settings`, the tools, `session_factory` — aren't meaningfully
  serializable), with the topic and final brief/report_path set explicitly
  via `update_current_span(input=..., output=...)`.
- **`verify/reconcile.py` deliberately NOT decorated** — its docstring states
  "no LLM/network calls" as a hallmark of the package's testability/purity;
  adding an external tracing dependency there, even a safe one, would
  compromise that stated design property for a step that's fast and
  synchronous anyway (still covered by the parent run-level span's duration).

### A real API-shape correction found via testing, not guessing

Initially used `client.set_current_trace_io(input=..., output=...)` — it
worked, but `mypy`/the SDK itself flagged it as **deprecated** ("removed in a
future major version," recommends `propagate_attributes()` for tags/user_id/
session_id — a different use case than what was needed here). Found the
actual non-deprecated equivalent for span-level input/output by inspecting
`update_current_span()`'s signature directly, and switched to it. Caught
during offline testing, before this was ever presented as done.

### What's verified vs. not

- Offline: constructs safely with empty keys, no hang, no crash, no test
  changes needed, deprecation-free. 92 tests still green, ruff + mypy clean.
- **Not verified**: no Langfuse account exists yet (`.env`'s
  `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are empty), so real trace
  export to the Langfuse UI has not been observed end-to-end. The code is
  written to activate automatically the moment real keys are added — no
  further code change needed, per config.py's existing optional fields.

## Part 2 — Streamlit dashboard

Plain Python, reads directly from the existing SQLite DB via
`memory.repository`'s existing functions (`list_runs`, `load_run`) — no new
backend/API layer, matching the project's "Streamlit reads from a database"
stack choice.

- New `dashboard.py` at repo root (parallel to `cli.py` — both are UI layers
  over the same `memory/` repository functions).
- Run list: a sortable/browsable table (topic, created, source/fact counts,
  has brief/report) — same data `research-agent list` already shows, now
  browsable instead of scrolling terminal output.
- Run detail (select a run): brief (rendered as the cited, per-line text it
  already is), sources, a facts table with a confidence column, and
  conflicts recomputed on the fly via the same pure, idempotent
  `reconcile_facts` `research-agent show` already uses — no new DB column,
  consistent with that earlier decision.
- $0: no LLM/network calls of its own, pure read-only DB access.

## Definition of done for Day 8

- [x] Langfuse tracing wired via `@observe()` across plan/tool/LLM-call/reconcile
      steps and the run-level span, degrading to a safe no-op without keys
- [x] `requirements.txt` re-pinned (`langfuse>=4.0`) to match the API actually used
- [x] 92 tests still green, zero test changes needed, ruff + mypy clean
- [x] Streamlit dashboard: run list + run detail (brief, sources, facts w/
      confidence, conflicts)
- [x] One real run with the dashboard open, to confirm it reflects a fresh
      run — `research-agent run --company "Linear"` (run #10) while
      `streamlit run dashboard.py` was live; confirmed the run appeared in
      the dashboard's run list immediately, no restart, no caching issue.
      Also surfaced 8 real conflicts (founders, headquarters phrasing,
      employee count, funding total, valuation, latest round) — a good
      demonstration case for the dashboard's conflict view.
- [ ] (Optional, needs the user to create a free account) Add real Langfuse
      keys to `.env` and confirm a trace actually appears in the Langfuse UI
- [x] PROGRESS.md updated
- [ ] committed — **note: per the user's standing instruction, Claude Code no
      longer commits/pushes in this repo; the user commits this themselves**

## Rules (from CLAUDE.md — repeated because they matter here)

- No live API calls in the test suite — tracing must stay a no-op in tests
  (confirmed).
- If a change would add a new paid dependency, flag it first — Langfuse and
  Streamlit were both already in requirements.txt and ROADMAP.md from Day 1;
  no new dependency introduced here, only a version-pin correction.
- Prefer the smallest change that moves the milestone forward — the
  `@observe()`-decorator design was chosen specifically because it requires
  zero signature changes and zero test-fixture churn, unlike the
  alternative (threading a tracer object through every function).
