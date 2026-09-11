#!/usr/bin/env bash
# Day 0 setup: virtual environment + dependencies + .env scaffold.
# Safe to re-run; it won't clobber an existing .env.
set -euo pipefail

echo "==> Checking Python version..."
if ! python3 -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  echo "!! Python 3.11+ required. Found: $(python3 --version 2>&1)"
  echo "   Install a newer Python from https://python.org and re-run."
  exit 1
fi
echo "   OK: $(python3 --version)"

echo "==> Creating virtual environment (.venv)..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "   Created .venv"
else
  echo "   .venv already exists, reusing"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Upgrading pip and installing dependencies..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
echo "   Dependencies installed."

echo "==> Installing project in editable mode (for the research-agent command)..."
python -m pip install --quiet -e . --no-deps
echo "   Done."

echo "==> Setting up .env..."
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "   Created .env from template — now open it and paste your real keys."
else
  echo "   .env already exists, leaving it alone."
fi

echo ""
echo "==> Done. Next steps:"
echo "    1. Open .env and paste your ANTHROPIC_API_KEY and TAVILY_API_KEY"
echo "    2. Run:  source .venv/bin/activate"
echo "    3. Run:  python verify_setup.py"
