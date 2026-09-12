"""
Fails if any backend/main.py route isn't exercised by backend/smoke_test.py.

Static and fast (no server, no imports beyond `main` itself) - suitable for
the pre-commit hook. Prevents a new endpoint from ever shipping without a
smoke test again: this is exactly how the Part B remediation gap ("no
scripted regression check for /api/regenerate or /api/crop-health-check")
happened the first time - add this check once and it can't happen again.

Usage:
    backend/.venv/Scripts/python.exe scripts/check_coverage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
SMOKE_TEST_PATH = BACKEND_DIR / "smoke_test.py"

sys.path.insert(0, str(BACKEND_DIR))

# Auto-generated docs routes, not application endpoints - never expected in
# a smoke test.
IGNORED_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def main() -> int:
    from main import app  # noqa: E402

    all_routes: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or methods is None or path in IGNORED_PATHS:
            continue
        for method in methods:
            if method == "HEAD":
                continue
            all_routes.add((method, path))

    smoke_test_source = SMOKE_TEST_PATH.read_text(encoding="utf-8")

    untested = sorted(
        (method, path) for method, path in all_routes if path not in smoke_test_source
    )

    if untested:
        print("The following routes have no reference in smoke_test.py:")
        for method, path in untested:
            print(f"   {method:<6} {path}")
        print("\nAdd a call exercising each one (see smoke_test.py's Part B sections for the pattern).")
        return 1

    print(f"All {len(all_routes)} routes are referenced in smoke_test.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
