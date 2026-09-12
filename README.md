# Research / Competitor-Analysis Agent

A hand-rolled AI agent that researches a company or topic end-to-end: it plans
searches, fetches and reads web pages, extracts structured facts, **cross-checks
those facts across multiple sources**, writes a sourced brief, and stores
everything in a database a dashboard can read from.

Built as a portfolio flagship project for AI/ML engineering roles — the point isn't
just "call an LLM," it's a full agent control loop with verification, budget guards,
and persistence, owned end to end rather than assembled from a framework.

## Why this project exists

Most demo agents summarize one search result and call it a day. The interesting (and
hard) part of research is reconciling **conflicting** information from different
sources. This agent's headline feature is verification:

- Facts are extracted as atomic `(attribute, value, source)` triples, not free text.
- Facts about the same attribute are grouped and reconciled — agreement across
  sources raises confidence, disagreement is flagged as a conflict instead of
  silently picking one answer.
- The headline metric is **% of brief claims grounded in a cited source** — every
  sentence in the final brief should trace back to a specific page.

## Architecture

A hand-rolled control loop (deliberately **not** LangGraph/CrewAI/AutoGen — owning
the control flow is the point, both for correctness and so it's easy to explain in
an interview):

```
plan -> execute (tools) -> verify (cross-check) -> synthesize (brief) -> persist
```

- **`RunState`** — a typed dataclass that is the loop's working memory: the topic,
  the search plan, sources fetched, facts extracted, the final brief, and running
  counters against the budget guards. Threaded through every step of the loop.
- **SQL fact store** (SQLAlchemy + SQLite) — long-term memory. Persists sources and
  facts across runs and is used to skip re-fetching URLs already seen.
- **Tools** — plain Python functions with a Pydantic input/output schema, each
  wrapped in uniform error handling, so the planner can call them predictably.

## Status

This project is being built incrementally (see commit history for day-by-day
progress). Current state:

| Piece | Status |
|---|---|
| Config, secrets loading, budget guards (`agent/config.py`) | ✅ Done |
| Core schemas — `Source`, `Fact`, `Conflict`, `VerifiedBrief`, `RunRecord` (`agent/schemas.py`) | ✅ Done |
| `RunState` working memory (`agent/state.py`) | ✅ Done |
| Uniform tool contract — `ToolResult`, error categories (`tools/base.py`) | ✅ Done |
| Search tool, wrapping Tavily (`tools/search.py`) | ✅ Done |
| SQL persistence layer — models, engine, repository (`memory/`) | ✅ Done (sources, facts, and briefs all populated) |
| Thin end-to-end loop + planner (`agent/loop.py`, `agent/planner.py`) | ✅ Done — walking skeleton |
| CLI entrypoint — `research-agent run --company "<name>"` (`cli.py`) | ✅ Done |
| LLM-driven planner, subject-aware (`agent/planner.py`) | ✅ Done — company vs. engineering/research field vs. company-initiative; falls back to a fixed template on model failure |
| Source-quality filter — excludes video/social domains (`tools/search.py`) | ✅ Done (first pass — a blocklist, not full credibility scoring) |
| `--deep-research` mode — structured multi-section PDF report (`agent/deep_research.py`, `agent/report.py`) | ✅ Done — confirmed live on a real scandal case (Wirecard); see PROGRESS.md for a JSON-truncation bug it surfaced and how it was fixed |
| Fetch tool (standalone page fetch/clean, beyond Tavily's) (`tools/fetch.py`) | ✅ Done — httpx + trafilatura, robots-aware, retries on transient failures |
| Fact extraction (atomic `attribute/value/source` triples) (`tools/extract.py`) | ✅ Done — MODEL_FAST, validated + one repair retry; confirmed live (run #7: 60 facts extracted from 9 sources) |
| Circuit breaker (stops a run after repeated consecutive tool failures) | ✅ Done — `RunState.record_tool_failure`, shared across search/fetch/extract |
| Verification / cross-checking (`verify/reconcile.py`) | ✅ Done — corroboration across independent domains raises confidence, disagreement is flagged as a `Conflict`; confirmed live (run #9: 7 real conflicts found in 61 facts, confidence spread 0.3–1.0) |
| Cited, per-claim brief (`agent/cited_brief.py`, `verify/grounding.py`) | ✅ Done — every claim cites its exact source; ungrounded claims are dropped in code, not just prompted against |
| Langfuse tracing | 🔜 Not started |
| Streamlit dashboard | 🔜 Not started (Phase 2: FastAPI + React, only after core works) |

The goal after each milestone is a working **walking skeleton** end to end — it's
never left in a broken half-built state for long. As of Days 6-7, `research-agent
run --company "<name>"` runs the full `plan → search → fetch (if thin) → extract
facts → reconcile (confidence, conflicts) → store → synthesize a cited brief →
store` path against real Tavily + Anthropic calls. The brief is no longer one
ungrounded paragraph — it's one claim per reconciled fact, each citing its exact
source, with any conflicting facts across sources printed alongside it instead of
silently picked between.

## Tech stack

Chosen to be free or near-free to run:

| Concern | Choice | Why |
|---|---|---|
| Agent core | Python 3.11+ | — |
| LLM calls | [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) | `MODEL_FAST` (Haiku) for planning/extraction, `MODEL_SMART` (Sonnet) for synthesis/verification — routes cheap calls away from the expensive model |
| Web search | [Tavily](https://tavily.com) | Free tier (1,000 credits/mo); returns extracted page content, so it doubles as fetching |
| Page fetching/cleaning | `httpx` + `trafilatura` | For non-Tavily fetches, strips boilerplate down to readable text |
| Structured I/O | Pydantic | Every LLM output that should be structured is validated against a model, with one repair retry on invalid output |
| Storage | SQLAlchemy + SQLite | File-based, zero-config, `git clone` and run |
| PDF reports | [reportlab](https://www.reportlab.com/opensource/) | Pure Python, no system deps (unlike weasyprint's libcairo/pango) — used only by `--deep-research` |
| Tracing | [Langfuse](https://langfuse.com) | Hosted free tier; optional — degrades gracefully if keys are absent |
| Dashboard | Streamlit | Pure Python; a FastAPI + React frontend is an explicit Phase 2 |

## Getting started

### 1. Accounts & keys

- **Anthropic** — sign up at [console.anthropic.com](https://console.anthropic.com),
  create an API key, and **set a spend limit** (Billing → monthly cap) so a runaway
  loop can't cost real money.
- **Tavily** — sign up at [tavily.com](https://tavily.com) for a free API key (no
  card required; 1,000 credits/month).

### 2. Setup

Requires Python 3.11+.

```bash
bash setup.sh
```

This creates a `.venv`, installs dependencies from `requirements.txt`, and copies
`env.example` to `.env`. Open `.env` and paste in your two real keys:

```
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
```

`.env` is gitignored and never committed; `env.example` shows the shape without the
secrets.

### 3. Verify the environment

```bash
source .venv/bin/activate
python verify_setup.py
```

This makes one tiny real call to each API (a fraction of a cent) and confirms the
SQLite database is writable. All four checks should print green before you start
building on top of this.

See [DAY0_SETUP.md](DAY0_SETUP.md) for the full walkthrough, including wiring up the
Claude Code VS Code extension.

## Usage

```bash
research-agent run --company "Stripe"
```

This runs the full loop against real Tavily + Anthropic calls: asks Claude (Haiku)
to plan a few search queries suited to the subject, searches, stores the sources
it finds, asks Claude (Sonnet) for a short brief grounded in that text, stores the
brief, and prints both the brief and where it landed in the database. Works for
companies ("Stripe"), engineering/research fields ("harness engineering"), or a
specific initiative inside a larger company ("Mercedes-Benz Tech Innovation") —
the planner adapts its query strategy to which kind of subject it is. Expect
roughly one Tavily credit per query and a few cents of Claude usage per run (one
cheap Haiku call for planning, one Sonnet call for the brief) — the walking-
skeleton brief is a short summary paragraph, not yet the fully cited claim-by-claim
brief described above.

`setup.sh` installs the project in editable mode so the `research-agent` command is
available once the venv is active; equivalently, `python cli.py run --company "..."`
works without that install step.

### Deep research mode

```bash
research-agent run --company "Wirecard" --deep-research
```

The default brief is deliberately thin (one paragraph) — `--deep-research` is for
when that's not enough. It runs 5-6 targeted searches instead of 2-3 generic ones
(including an explicit controversies/scandal search — a plain "company overview"
query won't surface those), and synthesizes a structured, multi-section report
instead of a paragraph: for a company, origin & history, ownership, financials,
products, scale, and controversies & legal issues (stated as "none found" rather
than invented, if the sources don't support one); for an engineering/research
field or a company-initiative, an analogous but different section set. The report
is rendered to a PDF under `reports/` (gitignored, like `data/`) and its path is
stored on the run — `research-agent show --run-id N` prints it.

This costs meaningfully more than the default: roughly 5-6 Tavily credits and
**~4-9¢ of Claude usage** (vs. ~1¢ for the default), driven by the larger
synthesis call reading up to 15 sources at once. Still cents, not dollars — but
worth knowing before running it repeatedly. See PROGRESS.md for the full cost
breakdown and a real bug this mode surfaced (a data-rich topic can truncate the
synthesis call's JSON output; fixed by raising `max_tokens` and having the model
avoid literal quotes in its output).

### Recalling past research

Every run is persisted, so past research doesn't require another live call to see
again:

```bash
research-agent list             # every run: id, topic, when, source/fact counts, has a brief?
research-agent show --run-id 3  # full detail for one run: brief, every source url, every fact
```

Both read straight from the local SQLite file — no network calls, no cost.

## Configuration

All runtime config is loaded from `.env` via `agent/config.py` (`get_settings()`).
Budget guards are enforced by the control loop so a run can never spiral in cost:

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Claude API access |
| `TAVILY_API_KEY` | *(required)* | Web search API access |
| `MODEL_FAST` | `claude-haiku-4-5` | Cheap model for planning/extraction |
| `MODEL_SMART` | `claude-sonnet-5` | Stronger model for synthesis/verification |
| `MAX_STEPS` | `25` | Hard cap on loop iterations per run |
| `MAX_SOURCES` | `15` | Hard cap on pages fetched per run |
| `RUN_TIMEOUT_SECONDS` | `300` | Wall-clock cap per run |
| `DATABASE_URL` | `sqlite:///data/research.db` | SQLAlchemy connection string |
| `REPORTS_DIR` | `reports` | Where `--deep-research` PDFs land (gitignored) |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | *(optional)* | Enables LLM tracing when set |

## Project structure

```
agent/
  config.py     # Settings loaded from .env, with budget guards
  schemas.py    # Source, Fact, Conflict, CitedClaim, VerifiedBrief, RunRecord —
                # the shared Pydantic models
  state.py      # RunState — working memory threaded through the control loop
  planner.py    # topic -> search queries; MODEL_FAST picks a strategy per subject
                # type (company / engineering field / company-initiative), falls
                # back to a fixed template on model failure
  llm.py        # shared validate + repair-retry helper for structured LLM output
                # (used by planner.py, cited_brief.py, and deep_research.py)
  cited_brief.py   # reconciled facts -> one cited claim per fact (verification's
                   # brief-synthesis half); None-on-failure, loop.py owns fallbacks
  deep_research.py # --deep-research query planning + multi-section report synthesis
  report.py     # renders a DeepResearchReport to PDF (reportlab, no LLM/network)
  loop.py       # the control loop: plan -> search -> fetch (if thin) -> extract
                # -> reconcile -> store -> synthesize a cited brief -> store;
                # also run_deep_research()
tools/
  base.py       # Tool contract: ToolResult, error categories (transient/permanent/validation)
  search.py     # SearchTool, wrapping the Tavily client; excludes a small
                # blocklist of video/social domains (EXCLUDED_DOMAINS)
  fetch.py      # FetchTool: httpx + trafilatura direct page fetch, backfills
                # thin Tavily content; robots.txt checked via the same
                # injectable client so it stays offline-testable
  extract.py    # ExtractTool: MODEL_FAST -> validated list[Fact] per source,
                # using a soft canonical attribute vocabulary
verify/
  reconcile.py  # pure, $0: groups facts by attribute, corroboration across
                # independent domains raises confidence, disagreement -> Conflict
  grounding.py  # pure, $0: drops any brief claim citing a source it wasn't given
memory/
  models.py     # SQLAlchemy ORM: runs, sources, facts
  db.py         # engine/session setup; patches in columns added to an existing
                # table (create_all() only creates missing tables, not columns)
  repository.py # converts between ORM rows and the Pydantic schemas
cli.py          # research-agent run [--deep-research] / list / show
tests/
  test_config.py
  test_state.py
  test_tools_base.py
  test_search.py
  test_fetch.py
  test_extract.py
  test_reconcile.py
  test_grounding.py
  test_cited_brief.py
  test_repository.py
  test_loop.py
  test_deep_research.py
  test_report.py
  test_db.py
  fixtures/     # saved API responses / HTML pages used instead of live network calls
data/
  research.db   # SQLite fact store (local; see note below on git tracking)
reports/
  *.pdf         # --deep-research output (local, gitignored)
verify_setup.py # Day 0 environment check (real but tiny API calls)
setup.sh        # venv + deps + .env scaffold + editable install
pyproject.toml  # registers the research-agent console script; ruff/mypy config
env.example     # template for .env — safe to commit, no real secrets
CLAUDE.md       # project context read automatically by Claude Code
DAY0_SETUP.md   # detailed first-time setup walkthrough
ROADMAP.md      # whole-project milestone map
PROGRESS.md     # live status — read at the start of a session, update at the end
DAYS_2_3_walking_skeleton.md # build spec — done
DAYS_4_5_harden_tools.md     # build spec — done
DAYS_6_7_verification.md     # build spec — done
```

> **Note:** `data/research.db` was committed once, before the `.gitignore` rule
> for `data/` existed. It was untracked (`git rm --cached`) in the same commit
> that added the rule, so the local file now grows freely as the CLI runs
> without showing up in `git status`.

## Development

```bash
source .venv/bin/activate

pytest                                              # run the test suite (all offline — no live network calls)
ruff check . && ruff format --check .               # lint + format check
mypy agent tools memory verify cli.py tests conftest.py verify_setup.py  # type check
```

### Ground rules (enforced throughout)

- No live network calls in the test suite — tools are tested against saved HTML
  fixtures under `tests/fixtures/`.
- Every LLM output that should be structured is validated against a Pydantic model,
  with one repair retry on invalid output.
- Secrets are never printed, logged, or committed.
- Every claim in a generated brief must carry a source — an unsourced claim is
  considered a bug.

## License

Personal portfolio project — no license file yet.
