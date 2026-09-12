"""RunState: working memory for a single research run.

Threaded through the control loop — plan -> execute -> verify -> synthesize
-> persist — accumulating sources and facts as tools run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.schemas import DeepResearchReport, Fact, Source

# Circuit breaker (DAYS_4_5_harden_tools.md Step 4): this many consecutive tool
# failures (search, fetch, or extract) stops a run from pursuing further
# sources — one flaky source or a bad prompt shouldn't be able to loop the run
# into the ground or blow through the budget on retries.
MAX_CONSECUTIVE_FAILURES = 3


@dataclass
class RunState:
    topic: str

    plan: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    brief: str | None = None

    # --deep-research only:
    subject_type: str | None = None
    deep_report: DeepResearchReport | None = None
    report_path: str | None = None

    run_id: int | None = None

    steps_used: int = 0
    sources_used: int = 0
    consecutive_failures: int = 0

    def can_take_step(self, max_steps: int) -> bool:
        return self.steps_used < max_steps

    def can_fetch_source(self, max_sources: int) -> bool:
        return self.sources_used < max_sources

    def record_tool_failure(self) -> bool:
        """Call on any failed tool result. Returns True once the circuit
        breaker has tripped (MAX_CONSECUTIVE_FAILURES in a row) — the caller
        should stop pursuing further sources for this run when that happens."""
        self.consecutive_failures += 1
        return self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES

    def record_tool_success(self) -> None:
        self.consecutive_failures = 0
