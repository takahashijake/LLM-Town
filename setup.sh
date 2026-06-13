#!/usr/bin/env bash
set -e

echo "Setting up LLM-Town GPU environment..."

python3 -m venv .venv

source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel

pip install \
  torch \
  transformers \
  accelerate \
  sentencepiece \
  protobuf \
  numpy

echo ""
echo "Setup complete."
echo "To activate later, run:"
echo "source .venv/bin/activate"
echo ""
echo "Test with:"
echo "python main.py"