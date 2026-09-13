# Days 9–10 — Evals + Polish (build spec for Claude Code)

Read CLAUDE.md first. This is the last milestone before the MVP cutline
(ROADMAP.md) — it's what turns a working agent into a flagship: proof it
works, not just a claim that it does.

## Goal of this milestone

Every prior milestone was proven by a hand-run live call and eyeballing the
output. That doesn't scale and isn't repeatable. This milestone adds an eval
harness that measures the project's own headline metric (% of brief claims
grounded in a cited source) plus fact recall, and — opt-in, since it costs
money — an LLM-as-judge quality score. Then the portfolio layer: an
architecture diagram in the README and a design-decisions + eval-results
writeup.

## Key design call: evaluate retrospectively, not by re-running live

The DB already holds 10 real live runs from every prior milestone's own
proof-of-work (Stripe, harness engineering, Wirecard ×2, Notion, Figma ×2,
Linear). Re-running fresh searches to build an eval set would cost real
money for no reason — the eval harness instead looks up the **latest
existing run for each golden topic** and scores what's already there. This
also means the two core metrics (citation coverage, fact recall) are **$0,
fully offline, and rerunnable any time** — only the optional LLM-judge step
touches the API.

## Step 1 — Golden cases (`evals/golden_cases.py`)

- `GoldenCase(topic: str, expected_facts: list[str])` — 6-8 cases drawn from
  topics already researched (Stripe, Notion, Figma, Wirecard, harness
  engineering, Linear), each with a handful of short, real-world-verifiable
  substrings that should show up somewhere in that run's extracted facts
  (e.g. Stripe → "2010", "Collison"; Wirecard → "fraud" or "1.9"; harness
  engineering → a company/technology term actually seen in that run's real
  output). Pulled from the actual stored data, not invented — CLAUDE.md's
  "never trust unverified claims" spirit applies to the eval set too.

## Step 2 — Pure metrics (`evals/metrics.py`)

No LLM/network calls — same purity bar as `verify/`.

- `citation_coverage(record: RunRecord) -> float`: parses the **actual
  persisted brief text** (not internal state) — each non-empty line should
  end in `[<url>]` with a URL that's genuinely among `record.sources`.
  Fraction of lines that pass. Re-derives from the stored artifact rather
  than trusting the pipeline's own invariant, so it's a real check, not a
  tautology.
- `fact_recall(record: RunRecord, expected_facts: list[str]) -> float`:
  fraction of `expected_facts` found (case-insensitive substring) somewhere
  across `record.facts`' values.

## Step 3 — LLM-as-judge (`evals/judge.py`) — opt-in, costs money

- `judge_brief_quality(client, model, *, topic, brief_text) -> BriefQualityJudgment | None`
  (`clarity_score`/`groundedness_score` 1-5, `reasoning: str`), same
  validate+repair-retry pattern via `agent/llm.py`. Uses MODEL_SMART — a
  qualitative judgment call, not high-volume, so cost stays small (one call
  per golden case, not per source).
- Never runs by default. Gated behind `research-agent eval --judge`.

## Step 4 — CLI: `research-agent eval [--judge]`

- New subcommand. For each golden case: load the latest run for that topic
  from the DB (skip with a clear message if none exists), compute both pure
  metrics, optionally call the judge, print a summary table + an aggregate
  score. $0 without `--judge`; a handful of cents with it.

## Step 5 — Portfolio polish

- README: architecture diagram as a Mermaid code fence (renders natively on
  GitHub) — the control loop plus verification's reconcile/ground step.
- `EVAL_RESULTS.md` or a section in README: what the eval harness actually
  found, run once for real and reported honestly (including any golden case
  that scores lower than expected — this is a portfolio piece, not a sales
  pitch).
- Demo GIF: flagged as something the user does themselves (recording a
  screen requires a browser/terminal capture tool this environment doesn't
  have) — not blocking the rest of the milestone.

## Tests

- `tests/test_eval_metrics.py` — pure, synthetic `RunRecord` fixtures, no DB/
  live calls.
- `tests/test_judge.py` — same fake-Anthropic-client pattern as every other
  LLM-facing module in this project.

## Definition of done

- [x] Step 1 — golden cases drawn from real stored data (5 cases: Stripe,
      harness engineering, Notion, Figma, Linear — spanning pre- and
      post-verification runs on purpose)
- [x] Step 2 — pure metrics, tested offline (10 tests)
- [x] Step 3 — LLM-judge, tested offline (repair-retry, None-on-failure,
      out-of-range-score repair), never called without `--judge` (4 tests)
- [x] Step 4 — `research-agent eval [--judge]` subcommand, tested via a real
      temp SQLite DB (5 tests). **Real finding, $0**: run against the actual
      DB, citation coverage is exactly 0% on the 3 pre-Days-6-7 runs and
      100% on the 2 post-verification runs — the intended before/after
      story, confirmed with real data, not asserted.
- [x] Packaging bug (again): `evals/` wasn't in `pyproject.toml`'s packages
      list either — same class of bug as `verify/`'s, caught immediately
      this time by testing the real console script first. Added a permanent
      regression test (`tests/test_packaging.py`) so a third package doesn't
      repeat this.
- [x] Step 5 — README architecture diagram (Mermaid, renders natively on
      GitHub) + eval-results writeup with the real numbers from
      `research-agent eval`, both $0. Demo GIF flagged as the user's task —
      this environment has no screen-recording capability, not blocking.
- [x] One real `--judge` run, after explicit user go-ahead on the cost.
      Result: groundedness scores climb 1 → 1 → 2 → 4 → 3 across the 5 cases
      in the same order as citation coverage's 0% → 0% → 0% → 100% → 100% —
      an independent qualitative signal (the judge never sees the
      citation-coverage metric) confirming the same real improvement.
      Clarity stayed high (4-5/5) throughout regardless of groundedness — a
      brief can read well while still being ungrounded, which is why this
      metric needed to exist rather than trusting "sounds good."
- [x] pytest / ruff / mypy all green — 115 tests (20 new)
- [x] PROGRESS.md updated

## Rules (from CLAUDE.md)

- No live API calls in the test suite — `evals/metrics.py` in particular
  must stay pure.
- Ask before spending — the `--judge` run needs explicit go-ahead, same
  pattern as every other milestone's live proof run.
