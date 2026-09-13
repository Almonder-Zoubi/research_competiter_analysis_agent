"""Regression test for a bug that has now happened twice: a new top-level
package (verify/, then evals/) shipped without being added to
pyproject.toml's explicit setuptools packages list. python -m cli kept
working fine (it puts the repo root on sys.path directly), which is exactly
why this went unnoticed both times — but the installed research-agent
console script crashed with ModuleNotFoundError on every subcommand. See
PROGRESS.md's decision log for both incidents.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_every_top_level_package_is_registered_in_pyproject() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        config = tomllib.load(f)
    registered = set(config["tool"]["setuptools"]["packages"])

    actual_packages = {
        path.name
        for path in REPO_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").exists()
    }

    missing = actual_packages - registered
    assert not missing, (
        f"{sorted(missing)} contain __init__.py but aren't in pyproject.toml's "
        "[tool.setuptools] packages list — the installed research-agent "
        "console script will crash with ModuleNotFoundError even though "
        "`python -m cli` keeps working. Add them to that list."
    )
