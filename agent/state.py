"""RunState: working memory for a single research run.

Threaded through the control loop — plan -> execute -> verify -> synthesize
-> persist — accumulating sources and facts as tools run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.schemas import Fact, Source


@dataclass
class RunState:
    topic: str

    plan: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    brief: str | None = None

    run_id: int | None = None

    steps_used: int = 0
    sources_used: int = 0

    def can_take_step(self, max_steps: int) -> bool:
        return self.steps_used < max_steps

    def can_fetch_source(self, max_sources: int) -> bool:
        return self.sources_used < max_sources
