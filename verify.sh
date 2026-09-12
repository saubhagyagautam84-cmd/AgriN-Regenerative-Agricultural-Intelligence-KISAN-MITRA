#!/usr/bin/env bash
# One command for the whole verification suite: Part A + Part B API checks
# (smoke_test.py) and the Part A + Part B UI checks (visual_check.spec.ts).
#
# Requires: backend running on :8001, frontend dev server running on :3000
# (this script does not start them - see README.md Quick start).
#
# Usage: ./verify.sh   (from the repo root, in a bash shell / Git Bash)

set -e
cd "$(dirname "$0")"

echo "=================================================================="
echo "1/2  Backend smoke test (Part A + Part B API checks)"
echo "=================================================================="
# PYTHONUTF8 - Windows defaults stdout to cp1252 when it's piped/redirected
# (not a real console), which crashes on the Hindi crop names otherwise.
PYTHONUTF8=1 "backend/.venv/Scripts/python.exe" backend/smoke_test.py

echo
echo "=================================================================="
echo "2/2  Frontend visual check (Playwright, Part A + Part B UI checks)"
echo "=================================================================="
cd frontend
"/c/Program Files/nodejs/npx.cmd" playwright test

echo
echo "All checks passed."
