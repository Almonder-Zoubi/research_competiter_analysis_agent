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
| Core schemas — `Source`, `Fact`, `Brief`, `RunRecord` (`agent/schemas.py`) | ✅ Done |
| `RunState` working memory (`agent/state.py`) | ✅ Done |
| Uniform tool contract — `ToolResult`, error categories (`tools/base.py`) | ✅ Done |
| Search tool, wrapping Tavily (`tools/search.py`) | ✅ Done |
| SQL persistence layer — models, engine, repository (`memory/`) | ✅ Done (sources + brief; fact storage wired, not yet populated) |
| Thin end-to-end loop + planner (`agent/loop.py`, `agent/planner.py`) | ✅ Done — walking skeleton |
| CLI entrypoint — `research-agent run --company "<name>"` (`cli.py`) | ✅ Done |
| Fetch tool (standalone page fetch/clean, beyond Tavily's) | 🔜 Not started |
| Fact extraction (atomic `attribute/value/source` triples) | 🔜 Not started |
| Verification / cross-checking (`verify/`) | 🔜 Not started |
| LLM-driven planner (current planner is a hardcoded template) | 🔜 Not started |
| Streamlit dashboard | 🔜 Not started (Phase 2: FastAPI + React, only after core works) |

The goal after each milestone is a working **walking skeleton** end to end — it's
never left in a broken half-built state for long. As of Days 2-3, `research-agent
run --company "<name>"` runs the full `plan → search → store → synthesize → store`
path against real Tavily + Anthropic calls and prints a sourced (if crude) brief.
It's intentionally rough: one Claude call writes a short summary paragraph, not yet
the fully cited, per-claim brief that's the project's headline feature — that lands
once fact extraction and `verify/` exist.

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

This runs the full loop against real Tavily + Anthropic calls: plans a few search
queries, searches, stores the sources it finds, asks Claude for a short brief
grounded in that text, stores the brief, and prints both the brief and where it
landed in the database. Expect roughly one Tavily credit and a few cents of Claude
usage per run — the walking-skeleton brief is a short summary paragraph, not yet
the fully cited claim-by-claim brief described above.

`setup.sh` installs the project in editable mode so the `research-agent` command is
available once the venv is active; equivalently, `python cli.py run --company "..."`
works without that install step.

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
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | *(optional)* | Enables LLM tracing when set |

## Project structure

```
agent/
  config.py     # Settings loaded from .env, with budget guards
  schemas.py    # Source, Fact, Brief, RunRecord — the shared Pydantic models
  state.py      # RunState — working memory threaded through the control loop
  planner.py    # topic -> a handful of search queries (template for now)
  loop.py       # the control loop: plan -> search -> store -> synthesize -> store
tools/
  base.py       # Tool contract: ToolResult, error categories (transient/permanent/validation)
  search.py     # SearchTool, wrapping the Tavily client
memory/
  models.py     # SQLAlchemy ORM: runs, sources, facts
  db.py         # engine/session setup
  repository.py # converts between ORM rows and the Pydantic schemas
cli.py          # `research-agent run --company "<name>"`
tests/
  test_config.py
  test_state.py
  test_tools_base.py
  test_search.py
  test_repository.py
  test_loop.py
  fixtures/     # saved API responses used instead of live network calls
data/
  research.db   # SQLite fact store (local; see note below on git tracking)
verify_setup.py # Day 0 environment check (real but tiny API calls)
setup.sh        # venv + deps + .env scaffold + editable install
pyproject.toml  # registers the research-agent console script; ruff/mypy config
env.example     # template for .env — safe to commit, no real secrets
CLAUDE.md       # project context read automatically by Claude Code
DAY0_SETUP.md   # detailed first-time setup walkthrough
DAYS_2_3_walking_skeleton.md # build spec for this milestone
```

> **Note:** `.gitignore` excludes `data/` and `*.db`, but `data/research.db` was
> committed before that rule was added, so it's still tracked. Running the CLI
> writes to it, which will show up as changes to a tracked binary file. Worth
> untracking (`git rm --cached data/research.db`) next time you're touching git
> config — not done here since it wasn't asked for.

## Development

```bash
source .venv/bin/activate

pytest                                              # run the test suite (all offline — no live network calls)
ruff check . && ruff format --check .               # lint + format check
mypy agent tools memory cli.py tests conftest.py verify_setup.py  # type check
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
