#!/usr/bin/env bash
# One command for the whole verification suite: Part C unit tests
# (regeneration_score's own edge cases), Part A + Part B API checks
# (smoke_test.py), and the Part A + Part B UI checks (visual_check.spec.ts).
#
# Requires: backend running on :8001, frontend dev server running on :3000
# (this script does not start them - see README.md Quick start).
#
# Usage: ./verify.sh   (from the repo root, in a bash shell / Git Bash)

set -e
cd "$(dirname "$0")"

echo "=================================================================="
echo "1/3  Regeneration Score Engine unit tests (Part C edge cases)"
echo "=================================================================="
(cd backend && PYTHONUTF8=1 ".venv/Scripts/python.exe" -m regeneration_score.test_edge_cases)

echo
echo "=================================================================="
echo "2/3  Backend smoke test (Part A + Part B + Part C API checks)"
echo "=================================================================="
# PYTHONUTF8 - Windows defaults stdout to cp1252 when it's piped/redirected
# (not a real console), which crashes on the Hindi crop names otherwise.
PYTHONUTF8=1 "backend/.venv/Scripts/python.exe" backend/smoke_test.py

echo
echo "=================================================================="
echo "3/3  Frontend visual check (Playwright, Part A + Part B + Part C UI checks)"
echo "=================================================================="
cd frontend
"/c/Program Files/nodejs/npx.cmd" playwright test

echo
echo "All checks passed."
