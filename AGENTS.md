# Repository Guidelines

## Project Structure & Module Organization

LLM-Town is a Python social simulation with deterministic state management and optional local-LLM dialogue. Runtime code lives under `src/`: `agents/` models residents and memory, `behavior/` selects activities and goals, `simulation/` orchestrates runs and persistence, `systems/` owns economy/material/crime/justice state, `llm/` handles prompts and parsing, and `analysis/` provides evaluation tooling. Configuration and seed data are JSON files in `data/`. Tests mirror these domains under `tests/`; evaluation entry points live in `scripts/`. Treat `outputs/`, logs, save states, and timestamped status reports as generated artifacts unless a task explicitly updates a checked-in fixture or report.

## Build, Test, and Development Commands

- `./setup.sh`: create `.venv` and install runtime and development dependencies.
- `source .venv/bin/activate`: activate the project environment.
- `python main.py --fake-llm --days 1 --hours 8`: run a quick deterministic simulation without downloading a model.
- `./test.sh`: run the complete pytest suite.
- `./test.sh tests/systems/test_economy.py`: run one focused test module.
- `python scripts/quality_report.py`: generate the repository's quality/evaluation report.

Prefer `--fake-llm` for development and CI. Real-model runs require the heavier Transformers/PyTorch dependencies and may produce review artifacts.

## Coding Style & Naming Conventions

Use Python with four-space indentation and PEP 8 conventions. Name modules, functions, and variables in `snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`. Add type annotations to new or changed public APIs. Keep authoritative state mutations in the relevant deterministic system rather than in dialogue or prompt code. No formatter or linter is currently configured, so match nearby code and keep imports explicit and grouped.

## Testing Guidelines

Pytest is configured in `pytest.ini` with `tests/` as its root. Name files `test_*.py` and tests `test_<behavior>()`; place tests in the directory matching the source domain. Tests should be deterministic, isolated, and must not load or download a language model. Use the registered `integration` and `slow` markers where appropriate, for example `./test.sh -m "not slow"`. Add regression coverage for state persistence, idempotency, and authority boundaries when changing simulation systems.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries such as `Add grounded dialogue follow-through` and `Harden causal memory stress and model evaluation`. Follow that style and keep each commit focused. Pull requests should explain the behavior change, identify affected systems, list exact test commands run, and link relevant issues. Include before/after metrics or sample artifacts for evaluation changes; include screenshots only for visual output.
