# Days 6–7 — Verification (build spec for Claude Code)

Read CLAUDE.md first — its hard rules apply to everything below. Read
DAYS_4_5_harden_tools.md too — this milestone consumes the `Fact` objects that
one produces. The walking skeleton (`research-agent run --company X`) must keep
working at every step (see CLAUDE.md: never leave the end-to-end path broken).

## Goal of this milestone

This is the project's headline feature (see CLAUDE.md and ROADMAP.md). Today,
Days 4–5 extracts atomic facts but never reconciles them, and the brief is
still synthesized from raw source text with no real per-claim grounding
guarantee. This milestone closes both gaps:

    ... -> extract facts -> RECONCILE (confidence, conflicts)
    -> synthesize a CITED brief from the reconciled facts -> DROP any claim
    citing a source it wasn't given -> store + print (brief + conflicts)

Everything in this milestone is a **pure, deterministic, $0 code change** —
`verify/` does no LLM/network calls at all — except the brief-synthesis call
itself, which already existed (it's just fed different input now: reconciled
facts instead of raw source text).

## Step 0 — Canonical attribute names in extraction

Why: reconciliation groups facts by attribute. Today's extraction prompt
(`tools/extract.py`) invents free-text attribute names per source, so the same
real-world fact shows up as `"headquarters"`, `"headquarters location"`, and
`"HQ"` across three sources — they'd never group together. Fixing this at the
schema/model layer (fuzzy-matching attribute names after the fact) is fragile;
fixing it at the extraction prompt is not.

- Update `EXTRACT_SYSTEM_PROMPT` to ask for a small **soft** controlled
  vocabulary — `founded_year, headquarters, founders, ceo, employee_count,
  funding_total, latest_funding_round, valuation, revenue, ownership,
  products, industry, controversies` — with an explicit fallback: anything
  that doesn't fit gets a short descriptive name of its own. Soft, not a
  schema enum — `Fact.attribute` stays `str`, so an occasional model deviation
  degrades gracefully (that fact just doesn't group with others) instead of
  failing validation.
- No schema change, no new call — same extraction call, better prompt.

## Step 1 — `verify/reconcile.py` (pure)

Why: this is the actual headline logic — group facts by attribute, agreement
raises confidence, disagreement is flagged as a conflict, per ROADMAP.md.

- New top-level package `verify/` (CLAUDE.md's Conventions section already
  calls for "pure functions in `verify/`" — this is that package's first use).
- New schemas in `agent/schemas.py`: `ConflictingValue(value, source_url)`,
  `Conflict(attribute, values: list[ConflictingValue], min_length=2)`.
- `reconcile_facts(facts: list[Fact]) -> tuple[list[Fact], list[Conflict]]`:
  1. Group by a normalized attribute key (lowercase, collapsed whitespace/
     underscores) — display casing is kept from the first fact seen.
  2. Within each group, sub-group by normalized value (lowercase, stripped).
     **Known limitation, stated up front**: this is exact-normalized-string
     matching, not semantic equivalence — `"$343.2 million"` and `"343.2M"`
     won't be recognized as agreeing. A real fix needs either an LLM call or
     embedding similarity; both cost money and are deferred. Flag in
     PROGRESS.md if Days 9–10 evals show this hurts recall.
  3. One distinct value in the group → corroborated (or single-source).
     Confidence = `min(1.0, 0.6 + 0.2 * (distinct_domains - 1))`, where
     "distinct domains" counts independent publishers (netloc, `www.`
     stripped) agreeing on that value — two pages on the same domain are one
     independent source, not two, matching ROADMAP's own phrase
     "corroborating **independent** sources."
  4. More than one distinct value in the group → **conflict**. Emit one
     `Conflict` record (attribute + every distinct value with a
     representative source), and every fact in the group gets its
     corroboration-based confidence multiplied by a conflict penalty (0.5) —
     disagreement should visibly lower confidence, not just get silently
     recorded.
  5. Returns new `Fact` objects (same attribute/value/source_url, adjusted
     confidence) — never mutates its input list.
- **Pure and idempotent** by construction (confidence is recomputed from
  attribute/value/source_url only, never read from the input) — this matters
  for Step 4 below.
- Offline test: exact-match corroboration across 2+ distinct domains raises
  confidence; two URLs on the *same* domain count as one corroborating source,
  not two; a genuine disagreement produces a `Conflict` and lowers confidence
  on every conflicting fact; a single uncorroborated fact keeps the baseline.

## Step 2 — `verify/grounding.py` (pure)

Why: the project's headline metric is "% of brief claims grounded in a cited
source." That's not just a synthesis-prompt instruction — it needs an
enforced, code-level guarantee, the same way `_drop_hallucinated_urls` already
guards `--deep-research` against a model citing a source it wasn't given.

- New schemas: `CitedClaim(claim, source_url)`, `VerifiedBrief(topic,
  claims: list[CitedClaim], min_length=1)`.
- `drop_ungrounded_claims(claims: list[CitedClaim], valid_urls: set[str]) ->
  list[CitedClaim]` — keeps only claims whose `source_url` is actually among
  the run's fetched sources. Pure, no LLM call.
- Offline test: a claim citing a real source survives; a claim citing a URL
  never given to the model is dropped; an all-hallucinated input returns `[]`
  without raising (caller decides the fallback).

## Step 3 — `agent/cited_brief.py`

Why: brief synthesis needs to change from "summarize this raw text" to "write
one grounded claim per reconciled fact, citing it" — mirrors
`agent/deep_research.py`'s shape (prompt + `call_for_structured_output` +
fallback), not a new pattern.

- `synthesize_cited_brief(client, model, *, topic, facts: list[Fact]) ->
  VerifiedBrief | None` — **None-on-failure**, like `plan_search_queries`,
  not `synthesize_deep_report`'s always-non-None convention. Reason: the loop
  also has to fold in the grounding-filter step (`verify/grounding.py`)
  between "did synthesis succeed" and "what's the final text," and that
  composition — no facts / model failed / every claim got filtered as
  ungrounded, three distinct fallback messages — is easier to follow with one
  owner (`agent/loop.py`) than split across two internal-fallback layers.
- Prompt gives the model the reconciled facts as `attribute: value (source:
  URL)` lines and asks for one claim per source-worthy fact, each citing its
  exact source URL — not asked to write flowing prose, so there's nothing for
  it to say *without* a citation attached.
- `render_brief_text(brief: VerifiedBrief) -> str` (pure) — turns the claims
  into the final human-readable string that gets persisted. **Design call**:
  `RunRecord.brief` stays `str | None` — no DB migration. The verification
  substance (atomic, grounded claims) lives in the pipeline; what lands in
  `runs.brief` is that pipeline's rendered text output, one cited sentence per
  line. Same reasoning already applied to `--deep-research`: the rich
  structured `DeepResearchReport` is never persisted as JSON either — only the
  PDF it renders to.
- Offline test: same shape as `test_deep_research.py` — valid parse, one
  repair retry, fallback on total failure, no-facts short-circuit (zero
  Anthropic calls).

## Step 4 — Wire into `agent/loop.py`

- After `_backfill_and_extract()`: `state.facts, state.conflicts =
  reconcile_facts(state.facts)` — reconciled *before* `save_facts()`, so the
  DB stores final, corroboration-adjusted confidence, not the raw extraction
  guess.
- Replace `_synthesize_brief()`'s raw-source-text path with:
  `synthesize_cited_brief(...)` → `drop_ungrounded_claims(...)` against
  `{s.url for s in state.sources}` → `render_brief_text(...)` → `state.brief`.
- `RunState` gains `conflicts: list[Conflict] = field(default_factory=list)`.
- No budget-guard changes — reconciliation and grounding are pure/free; only
  the existing single brief-synthesis call spends anything, same as today.

## Step 5 — Surface verification in the CLI

- `_run_command`: after printing the brief, print any conflicts found
  (attribute + the differing values/sources) — "make verification visible in
  output" per ROADMAP.md.
- `_show_command`: recompute conflicts by calling `reconcile_facts(record.facts)`
  again — safe and cheap because Step 1 is pure and idempotent; avoids a DB
  migration to persist conflicts separately.

## Step 6 — One real run to prove it

- Run against a fresh company (or reuse Notion/Stripe — the point here is
  proving verification against already-known messy multi-source data, not
  novelty of subject).
- Expect: reconciled facts with varied confidence (not everything pinned at
  1.0 anymore), a cited brief (each line ends in a source URL), and — if the
  sources disagree on anything (revenue figures are a likely candidate,
  per the Notion run's 60 facts) — at least one printed conflict.
- Confirm: tests/ruff/mypy stay green; DB facts show adjusted confidence.

---

## Definition of done for Days 6–7

- [x] Step 0 — extraction prompt uses a soft canonical attribute vocabulary
- [x] Step 1 — `verify/reconcile.py`, tested offline (corroboration, conflict,
      same-domain-doesn't-double-count, idempotence). Two known limitations
      confirmed against real data (run #7's 60 Notion facts) rather than left
      hypothetical — see the module docstring.
- [x] Step 2 — `verify/grounding.py`, tested offline
- [x] Step 3 — `agent/cited_brief.py`, tested offline (repair-retry, fallback)
- [x] Step 4 — loop wires reconciliation + cited synthesis in, replacing raw-
      text brief synthesis
- [x] Step 5 — CLI prints conflicts on `run` and `show` (`show` recomputes
      them on the fly via the same pure, idempotent `reconcile_facts` —
      verified for free against run #7's real data, no DB migration needed)
- [x] Step 6 — one real run confirms reconciled confidence + a cited brief.
      First attempt (Figma, run #8) found a real bug: `max_tokens=1200` was
      too low once 40 facts each needed a claim + full source URL in the
      output — same root cause as the Wirecard truncation bug, different
      call site. Fixed (max_tokens -> 4000, `_MAX_FACTS` 40 -> 25) and
      confirmed with a second live run (run #9): 18 grounded cited claims,
      7 real conflicts detected, confidence spread 0.3/0.5/0.6/1.0 across 61
      facts persisted, matching the designed formula exactly.
- [x] pytest / ruff / mypy all green — 92 tests (18 new)
- [x] PROGRESS.md updated
- [ ] committed, with `.env` confirmed still ignored

## Rules (from CLAUDE.md — repeated because they matter here)

- Every claim in a generated brief must carry a source. Unsourced claim = a
  bug — this milestone is what turns that rule from an aspiration into an
  enforced guarantee.
- No live API calls in the test suite; `verify/` in particular must stay
  100% pure and network-free.
- Every structured LLM output validated against Pydantic; one repair retry.
- Budget guards respected — this milestone adds no new spend beyond the
  brief-synthesis call that already existed.
