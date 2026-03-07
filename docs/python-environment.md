# Python Environment Policy (uv-first)

This project uses a repo-local Python environment by default:

- environment path: `.venv/` (project-scoped)
- package manager/runner: `uv`
- command style: `scripts/uv_run.sh <command>` (or `uv run ...`)

## Why

- Prevent global Python pollution across projects.
- Avoid activation mistakes (`conda activate ...` forgotten/wrong shell).
- Keep command usage consistent for humans and AI agents.

## Setup

```bash
scripts/setup_python_env.sh
```

Optional overrides:

- `PYTHON_BIN=python3.11 scripts/setup_python_env.sh`
- `VENV_DIR=/custom/path/.venv scripts/setup_python_env.sh`

## Daily Commands

```bash
scripts/uv_run.sh pytest tests/
scripts/uv_run.sh ruff check app tests scripts
scripts/uv_run.sh alembic upgrade head
scripts/bootstrap_eval.sh --help
```

## Guardrails

- Do not run bare `python`, `pip`, or `pytest` in this repo.
- Do not use `uv pip install --system`.
- Keep installs inside the project venv only.

## Fallback

Conda remains optional as a personal fallback, but the project standard is uv + `.venv`.
