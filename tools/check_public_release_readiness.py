#!/usr/bin/env python3
"""Validate the publishable runtime tree and its explicit rights gate."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RIGHTS_FILE = PROJECT_ROOT / "configs/publication_rights.json"
RELEASE_CONFIG = PROJECT_ROOT / "configs/runtime_release.json"
EXPECTED_REPOSITORY = "ma-ho-git/ai-cps-runtime"
REQUIRED_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/PUBLICATION_RIGHTS_REVIEW.md",
    "docs/PUBLIC_RELEASE_PROCEDURE.md",
)
REQUIRED_RIGHTS = {
    "grum-ai-cps-origin",
    "project-contributors",
    "training-datasets",
    "model-artifacts",
    "runtime-traces",
    "uml-assets",
}
PROHIBITED_PATHS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)reports/"),
    re.compile(r"(^|/)learning_course/"),
    re.compile(r"\.ipynb$"),
    re.compile(r"model_registry/[^/]+/(candidates|versions)/"),
    re.compile(r"Grum_2024.*\.(md|pdf)$", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"marcus\.hopka@googlemail\.com", re.IGNORECASE),
    re.compile(r"thoene1@uni-potsdam\.de", re.IGNORECASE),
)


class ReadinessError(RuntimeError):
    """The source tree is not ready for a public release."""


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"JSON object expected: {path}")
    return value


def repository_files(root: Path) -> list[str]:
    if not (root / ".git").exists():
        return sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        )
    process = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise ReadinessError(process.stderr.strip() or "git file list is unavailable")
    return sorted(line for line in process.stdout.splitlines() if line)


def publication_entries(path: Path = RIGHTS_FILE) -> list[dict[str, Any]]:
    document = load_object(path)
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ReadinessError("publication rights file contains no entries")
    identifiers: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ReadinessError("publication rights entries must be objects")
        identifier = str(entry.get("id", "")).strip()
        status = str(entry.get("status", "")).strip()
        if not identifier or identifier in identifiers:
            raise ReadinessError(f"invalid or duplicate rights entry: {identifier!r}")
        if status not in {"approved", "pending", "rejected"}:
            raise ReadinessError(f"invalid status for {identifier}: {status!r}")
        identifiers.add(identifier)
        normalized.append(entry)
    return normalized


def scan_text_files(root: Path, files: Iterable[str]) -> list[str]:
    findings: list[str] = []
    for relative in files:
        path = root / relative
        if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            findings.append(relative)
    return findings


def evaluate(*, root: Path = PROJECT_ROOT, require_approved: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"required public file is missing: {relative}")

    config = load_object(root / "configs/runtime_release.json")
    if config.get("repository") != EXPECTED_REPOSITORY:
        errors.append(
            f"release repository must be {EXPECTED_REPOSITORY}, got {config.get('repository')!r}"
        )

    files = repository_files(root)
    for relative in files:
        if any(pattern.search(relative) for pattern in PROHIBITED_PATHS):
            errors.append(f"prohibited public path: {relative}")
    for relative in scan_text_files(root, files):
        errors.append(f"possible secret in tracked text file: {relative}")

    entries = publication_entries(root / "configs/publication_rights.json")
    rights_ids = {str(entry["id"]) for entry in entries}
    missing_rights = sorted(REQUIRED_RIGHTS - rights_ids)
    if missing_rights:
        errors.append("missing publication-rights entries: " + ", ".join(missing_rights))
    pending = [str(entry["id"]) for entry in entries if entry["status"] == "pending"]
    rejected = [str(entry["id"]) for entry in entries if entry["status"] == "rejected"]
    if rejected:
        errors.append("rejected publication rights: " + ", ".join(rejected))
    if pending:
        message = "pending publication rights: " + ", ".join(pending)
        (errors if require_approved else warnings).append(message)
    return errors, warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-approved",
        action="store_true",
        help="Fail when any publication-rights entry is still pending.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        errors, warnings = evaluate(require_approved=args.require_approved)
    except ReadinessError as exc:
        print(f"[PUBLIC][FAIL] {exc}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"[PUBLIC][PENDING] {warning}")
    for error in errors:
        print(f"[PUBLIC][FAIL] {error}", file=sys.stderr)
    if errors:
        return 1
    print("[PUBLIC][OK] publishable tree structure is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
