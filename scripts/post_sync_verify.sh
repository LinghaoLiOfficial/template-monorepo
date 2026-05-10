#!/usr/bin/env bash
set -euo pipefail

# Unified post-sync verification for consumer repositories.

echo "[verify] Project map sync"
python3 scripts/generate_project_map.py
python3 scripts/check_project_map.py

echo "[verify] Backend quality gates"
uv run --project backend ruff check backend
uv run --project backend ruff format --check backend
uv run --project backend pytest -q

echo "[verify] Frontend quality gates"
pnpm --dir frontend run lint
pnpm --dir frontend run type-check

echo "All post-sync checks passed."
