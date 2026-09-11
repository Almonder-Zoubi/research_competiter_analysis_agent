"""Day 0 verification: prove the environment is ready before Day 1.

Runs four checks and prints a green/red line for each:
  1. Python version
  2. Anthropic key + a real 1-token test call
  3. Tavily key + a real 1-credit test search
  4. SQLite database is writable

Each real API call here is deliberately tiny (costs a fraction of a cent /
one credit) so verifying is effectively free. Exit code is non-zero if any
check fails, so you can't accidentally proceed on a broken setup.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET}  {msg}")


def fail(msg: str, fix: str) -> None:
    print(f"{RED}[!!]{RESET}  {msg}")
    print(f"       fix: {fix}")


def check_python() -> bool:
    if sys.version_info >= (3, 11):
        ok(f"Python {sys.version_info.major}.{sys.version_info.minor} OK")
        return True
    fail(
        f"Python {sys.version_info.major}.{sys.version_info.minor} is too old",
        "install Python 3.11+ from https://python.org",
    )
    return False


def check_anthropic() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or key.startswith("sk-ant-your"):
        fail("ANTHROPIC_API_KEY not set", "paste your real key into .env")
        return False
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=key)
        # Smallest possible real call: 1 output token on the cheap model.
        model = os.getenv("MODEL_FAST", "claude-haiku-4-5")
        client.messages.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        ok(f"Anthropic key works — test call to {model} succeeded")
        return True
    except Exception as e:  # noqa: BLE001 - we want to surface any failure
        fail(f"Anthropic call failed: {e}", "check the key, and that billing/credits are set up")
        return False


def check_tavily() -> bool:
    key = os.getenv("TAVILY_API_KEY", "")
    if not key or key.startswith("tvly-your"):
        fail("TAVILY_API_KEY not set", "paste your real key into .env")
        return False
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=key)
        client.search(query="test", max_results=1)  # ~1 credit
        ok("Tavily key works — test search succeeded")
        return True
    except Exception as e:  # noqa: BLE001
        fail(f"Tavily call failed: {e}", "check the key at https://tavily.com")
        return False


def check_database() -> bool:
    try:
        from sqlalchemy import create_engine, text

        Path("data").mkdir(exist_ok=True)
        url = os.getenv("DATABASE_URL", "sqlite:///data/research.db")
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS _healthcheck (id INTEGER)"))
            conn.execute(text("DROP TABLE _healthcheck"))
            conn.commit()
        ok("SQLite database is writable")
        return True
    except Exception as e:  # noqa: BLE001
        fail(f"Database check failed: {e}", "make sure the data/ folder is writable")
        return False


def main() -> int:
    print("Verifying Day 0 setup...\n")
    results = [
        check_python(),
        check_anthropic(),
        check_tavily(),
        check_database(),
    ]
    print()
    if all(results):
        print(f"{GREEN}All checks passed. You're ready for Day 1.{RESET}")
        return 0
    print(f"{RED}Some checks failed. Fix the items above, then re-run.{RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
