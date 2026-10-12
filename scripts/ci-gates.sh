#!/usr/bin/env bash
# Local gates. Replaces .github/workflows/ci.yml (GitHub Actions retired
# fleet-wide 2026-09-03). Run by .githooks/pre-push, or by hand:
# scripts/ci-gates.sh
#
# The workflow blocked on a py_compile pass and ran ruff with
# continue-on-error, so style findings never blocked a merge. That split
# stays: ruff's bug-class rules (syntax errors and undefined names) block,
# and the full style report prints as a note. The Django tests run too.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=""
for c in ./venv/bin/python ./.venv/bin/python; do [ -x "$c" ] && PY="$c" && break; done
if [ -z "$PY" ]; then
  echo "ci-gates: no venv found. Create one with:"
  echo "  uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt"
  exit 1
fi

# The deleted workflow did "pip install ruff" on a fresh runner every time.
# Prefer a repo venv, then whatever is on PATH, then uvx (no install needed).
RUFF=""
for c in ./venv/bin/ruff ./.venv/bin/ruff; do [ -x "$c" ] && RUFF="$c" && break; done
if [ -z "$RUFF" ] && command -v ruff >/dev/null 2>&1; then RUFF="ruff"; fi
if [ -z "$RUFF" ] && command -v uvx >/dev/null 2>&1; then RUFF="uvx ruff"; fi
[ -n "$RUFF" ] || { echo "ci-gates: no ruff found (try: uv tool install ruff)"; exit 1; }

echo "==> py_compile"
find . -name "*.py" -not -path "./venv/*" -not -path "./.venv/*" -print0 | xargs -0 "$PY" -m py_compile

echo "==> ruff check, syntax errors and undefined names (blocking)"
$RUFF check --select E9,F63,F7,F82 .

backlog=$($RUFF check . --statistics 2>/dev/null | awk '{s+=$1} END{print s+0}' || true)
if [ "${backlog:-0}" -gt 0 ]; then
  echo "    note: ${backlog} ruff style findings repo-wide, advisory as in the old workflow ($RUFF check .)"
fi

echo "==> django tests"
DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-ci-gates-only}" "$PY" manage.py test --verbosity=0

echo "==> gates passed"
