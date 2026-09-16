#!/usr/bin/env bash
set -euo pipefail

echo "Setting up LLM-Town GPU environment..."

python3 -m venv .venv

source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel

python -m pip install -r requirements.txt -r requirements-dev.txt

echo ""
echo "Setup complete."
echo "To activate later, run:"
echo "source .venv/bin/activate"
echo ""
echo "Test with:"
echo "python main.py --fake-llm --days 1 --hours 8"
