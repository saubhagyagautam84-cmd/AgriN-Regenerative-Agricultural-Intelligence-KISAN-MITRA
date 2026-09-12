"""
Regenerates README.md's API Reference and Project structure sections from
the actual code - never hand-type either again.

    API Reference    <- backend/main.py's live FastAPI OpenAPI schema
    Project structure <- a real directory walk of the repo, with excludes

Usage:
    backend/.venv/Scripts/python.exe scripts/generate_readme.py          # write
    backend/.venv/Scripts/python.exe scripts/generate_readme.py --check  # CI/pre-commit: exit 1 if README is stale

Wired into .githooks/pre-commit - see README's Contributing section.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
README_PATH = REPO_ROOT / "README.md"

sys.path.insert(0, str(BACKEND_DIR))

# Directories/files a tree walk should never descend into or list - build
# artifacts, dependency caches, generated data and secrets. Kept in sync
# with .gitignore's spirit (not literally parsed from it, since .gitignore
# also excludes things worth *showing* in a structure diagram, like data/).
EXCLUDE_NAMES = {
    ".git",
    ".next",
    "node_modules",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    "out",
    "test-results",
    "PlantVillage-Dataset",
    "subset_small",
    "visual_checks",
    ".DS_Store",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".tsbuildinfo"}

MAX_DEPTH = 3  # keep the README tree scannable; deeper detail lives in the code itself


# --------------------------------------------------------------------------
# API Reference, from the live FastAPI app
# --------------------------------------------------------------------------


def generate_api_table() -> str:
    from main import app  # noqa: E402  (import after sys.path setup)

    spec = app.openapi()
    rows: list[tuple[str, str, str]] = []

    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            summary = operation.get("summary") or ""
            description = (operation.get("description") or "").strip().splitlines()
            purpose = summary or (description[0] if description else "")
            rows.append((method.upper(), path, purpose))

    lines = ["| Method | Endpoint | Purpose |", "|---|---|---|"]
    for method, path, purpose in rows:
        lines.append(f"| `{method}` | `{path}` | {purpose} |")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Project structure, from a real directory walk
# --------------------------------------------------------------------------


def _should_skip(name: str) -> bool:
    if name in EXCLUDE_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES)


def _walk(directory: Path, prefix: str, depth: int, lines: list[str]) -> None:
    if depth > MAX_DEPTH:
        return
    entries = sorted(
        (e for e in directory.iterdir() if not _should_skip(e.name)),
        key=lambda e: (e.is_file(), e.name.lower()),
    )
    for index, entry in enumerate(entries):
        is_last = index == len(entries) - 1
        connector = "└── " if is_last else "├── "
        label = entry.name + ("/" if entry.is_dir() else "")
        lines.append(f"{prefix}{connector}{label}")
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _walk(entry, prefix + extension, depth + 1, lines)


def generate_file_tree() -> str:
    lines = ["agri-monitor/"]
    _walk(REPO_ROOT, "", 1, lines)
    return "```\n" + "\n".join(lines) + "\n```"


# --------------------------------------------------------------------------
# README stitching
# --------------------------------------------------------------------------

MARKERS = {
    "API_REFERENCE": generate_api_table,
    "FILE_STRUCTURE": generate_file_tree,
}


def replace_between_markers(text: str, marker_name: str, new_content: str) -> str:
    begin = f"<!-- BEGIN:{marker_name}"
    end = f"<!-- END:{marker_name} -->"
    begin_idx = text.index(begin)
    begin_line_end = text.index("-->", begin_idx) + len("-->")
    end_idx = text.index(end, begin_line_end)
    return text[: begin_line_end + 1] + new_content + "\n" + text[end_idx:]


def main() -> int:
    check_only = "--check" in sys.argv

    original = README_PATH.read_text(encoding="utf-8")
    updated = original
    for marker_name, generator in MARKERS.items():
        updated = replace_between_markers(updated, marker_name, generator())

    if updated == original:
        print("README.md is up to date.")
        return 0

    if check_only:
        print("README.md is STALE - run scripts/generate_readme.py to regenerate.")
        return 1

    README_PATH.write_text(updated, encoding="utf-8")
    print("README.md regenerated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
