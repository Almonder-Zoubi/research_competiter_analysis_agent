"""Langfuse tracing setup for the loop — optional, degrades gracefully if
keys are absent (see CLAUDE.md, config.py's langfuse_* fields).

Uses the @observe() decorator on individual functions (agent/planner.py,
agent/deep_research.py, agent/llm.py, tools/*.py, agent/loop.py) rather than
threading a client through every call site: when disabled, @observe is a
transparent no-op — confirmed experimentally: sub-millisecond overhead, no
network call, and safe with arbitrary argument types (including this
project's fake test clients) — so tracing adds zero signature changes and
zero test-fixture churn across the whole loop.

NOTE ON VERSION DRIFT: requirements.txt previously pinned langfuse>=2.0, but
the SDK actually installed (and what this module is written against) is 4.x
— a completely different, OpenTelemetry-based client from 2.x's explicit
`client.trace()/span()` calls. Flagging the drift and re-pinning rather than
leaving a stale pin that would silently install an incompatible version on a
fresh clone (see requirements.txt).
"""

from __future__ import annotations

import logging

from langfuse import Langfuse, get_client

from agent.config import Settings

# Import before silencing: langfuse's own logger.py module resets this
# logger's level to WARNING as a side effect of import, so suppressing
# first and importing after would just get clobbered back to WARNING —
# confirmed experimentally. The installed 4.x SDK logs an "Authentication
# error... client disabled" / "Context error: no active span" warning on
# nearly every touch of a keyless client — harmless (no crash, no hang,
# confirmed <1ms) but noisy for the common case of no Langfuse account
# configured yet, which is where this project stands today.
logging.getLogger("langfuse").setLevel(logging.ERROR)


def init_tracing(settings: Settings) -> None:
    """Initializes the process-wide client that @observe()-decorated
    functions send traces through (langfuse.get_client() resolves it).
    Call once at process startup (see cli.py). A disabled client (no keys)
    is exactly as safe to construct as an enabled one — confirmed empty-key
    construction completes in under a millisecond, no network call.
    """
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        tracing_enabled=bool(
            settings.langfuse_public_key and settings.langfuse_secret_key
        ),
    )


def flush_tracing() -> None:
    """Flushes any buffered traces before the process exits. Safe to call
    even when tracing is disabled — a no-op in that case."""
    get_client().flush()
