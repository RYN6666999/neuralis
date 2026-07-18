#!/bin/sh
# Pre-commit gate — run the test suite before every commit.
#
# Why this exists: guards are only as good as something that runs them. The
# ponytail regression that shipped a broken scream-task-executor to main
# (missing imports -> NameError, swallowed by try/except) passed CI's "188
# tests" because nothing ran the standalone scripts. This hook closes the
# "changed but never ran" failure class: no commit lands with red tests.
#
# Interpreter is pinned: the default `python3` on this machine lacks numpy
# (rtk shim), so use the homebrew python that has the deps. Override with
# NEURALIS_TEST_PY if your layout differs.
#
# Escape hatch: `git commit --no-verify` skips this. Use only for docs-only
# commits or a genuine emergency — never to dodge a real failure.
set -e

PY="${NEURALIS_TEST_PY:-/opt/homebrew/bin/python3}"
if [ ! -x "$PY" ]; then
    echo "[pre-commit] interpreter not found: $PY (set NEURALIS_TEST_PY)" >&2
    exit 1
fi

echo "[pre-commit] running tests via $PY ..."
if ! "$PY" -m pytest -q -p no:cacheprovider tests/; then
    echo "" >&2
    echo "[pre-commit] TESTS FAILED — commit blocked." >&2
    echo "  fix the failure, or 'git commit --no-verify' to override (emergencies only)." >&2
    exit 1
fi
echo "[pre-commit] tests green."
