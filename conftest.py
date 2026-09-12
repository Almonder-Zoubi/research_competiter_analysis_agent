"""Shared pytest bootstrap.

Silences Langfuse's noisy "client disabled" / "no active span" warnings
during the test suite — tracing is never configured with real keys in tests
(see CLAUDE.md: no live calls in the test suite), so every @observe-decorated
call would otherwise print a harmless but noisy warning. Mirrors
agent/tracing.py's own suppression, needed here too since individual test
files each import only what they need (e.g. tests/test_fetch.py never
imports agent.tracing) and so can't rely on that module having run first.
"""

from __future__ import annotations

import logging

import langfuse  # noqa: F401

# Importing langfuse first triggers its own logger.py's setLevel(WARNING)
# reset as a side effect; suppressing before that import would just get
# silently clobbered back to WARNING.
logging.getLogger("langfuse").setLevel(logging.ERROR)
