#!/usr/bin/env python3
"""Export, inspect and restore one complete portable AI-CPS site state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = PROJECT_ROOT / "scenarios/serve_ft_nns_external_broker/x86_64"
BASE_COMPOSE = SCENARIO_ROOT / "docker-compose.yml"
VIRTUAL_COMPOSE = SCENARIO_ROOT / "docker-compose.virtual.yml"
RELEASE_CONFIG = PROJECT_ROOT / "configs/runtime_release.json"
DEFAULT_ENV = PROJECT_ROOT / ".env"
DEPLOYMENT_LOCK = PROJECT_ROOT / ".runtime/deployment-lock.json"
STATE_FILES = (
    Path("model_registry/model_selection_state.json"),
    Path("model_registry/model_selection_history.jsonl"),
)
VOLUMES = ("nodered_data", "mosquitto_data", "mosquitto_log")
MODEL_DOMAINS = ("storage", "vgr", "hbw")
DEFAULT_PROJECT = "ai-cps-nn-runtime"
COMPOSE_PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
HELPER_IMAGE = (
    "alpine:3.20.3@sha256:"
    "1e42bbe2508154c9126d48c2b8a75420c3544343bf86fd041fb7527e017a4b4a"
)


class MigrationError(RuntimeError):
    """A site bundle operation cannot continue safely."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MigrationError(f"JSON object expected: {path}")
    return value


def load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise MigrationError(f"environment file is missing: {path}")
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise MigrationError(f"{path}:{number}: KEY=VALUE expected")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head() -> str:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return process.stdout.strip() if process.returncode == 0 else "unknown"


def report_path(settings: Mapping[str, str]) -> Path:
    configured = Path(settings.get("REPORT_ROOT_HOST", "../../../reports")).expanduser()
    return configured.resolve() if configured.is_absolute() else (SCENARIO_ROOT / configured).resolve()


def compose_project(settings: Mapping[str, str]) -> str:
    return settings.get("COMPOSE_PROJECT_NAME", DEFAULT_PROJECT).strip() or DEFAULT_PROJECT


def validate_compose_project(value: str) -> str:
    project = value.strip()
    if COMPOSE_PROJECT.fullmatch(project) is None:
        raise MigrationError(
            "target project must start with a lowercase letter or digit and contain "
            "only lowercase letters, digits, '-' or '_'"
        )
    return project


def update_env(path: Path, updates: Mapping[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in updates and key and not stripped.startswith("#"):
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    if output and output[-1] and set(updates) - seen:
        output.append("")
    output.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def volume_name(project: str, logical: str) -> str:
    return f"{project}_{logical}"


def run_checked(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        process = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MigrationError(f"command could not run: {' '.join(command)}: {exc}") from exc
    if process.returncode != 0:
        raise MigrationError(
            process.stderr.strip() or process.stdout.strip() or f"command failed: {' '.join(command)}"
        )
    return process


def ensure_stack_stopped(env_file: Path, settings: Mapping[str, str]) -> None:
    project = compose_project(settings)
    process = run_checked(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--format",
            '{{.Names}}|{{.Label "com.docker.compose.service"}}',
        ]
    )
    running = [line for line in process.stdout.splitlines() if line.strip()]
    if running:
        raise MigrationError(
            "runtime migration requires a stopped stack; running: " + ", ".join(running)
        )


def selected_candidate_paths(settings: Mapping[str, str]) -> list[Path]:
    selected: list[Path] = []
    for domain in MODEL_DOMAINS:
        configured = settings.get(f"{domain.upper()}_MODEL_DIR", "").strip()
        prefix = f"/model_registry/{domain}/candidates/"
        if not configured:
            continue
        if not configured.startswith(prefix):
            if configured != f"/model_registry/{domain}/latest":
                raise MigrationError(f"unsupported selected model path: {configured}")
            continue
        name = configured.removeprefix(prefix)
        relative = Path("model_registry") / domain / "candidates" / name
        if not name or ".." in relative.parts:
            raise MigrationError(f"unsafe selected candidate path: {configured}")
        source = PROJECT_ROOT / relative
        if not source.is_dir():
            raise MigrationError(f"selected candidate is missing: {source}")
        selected.append(relative)
    return selected


def copy_optional_file(source: Path, destination: Path) -> None:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def archive_directory(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        if source.is_dir():
            for child in sorted(source.iterdir()):
                archive.add(child, arcname=child.name, recursive=True)


def backup_volume(volume: str, destination: Path, *, allow_missing: bool) -> bool:
    inspect = subprocess.run(
        ["docker", "volume", "inspect", volume],
        text=True,
        capture_output=True,
        check=False,
    )
    if inspect.returncode != 0:
        if allow_missing:
            return False
        raise MigrationError(f"Docker volume is missing: {volume}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/source:ro",
            "-v",
            f"{destination.parent.resolve()}:/backup",
            HELPER_IMAGE,
            "tar",
            "-C",
            "/source",
            "-czf",
            f"/backup/{destination.name}",
            ".",
        ]
    )
    return True


def model_records(settings: Mapping[str, str]) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for domain in MODEL_DOMAINS:
        configured = settings.get(f"{domain.upper()}_MODEL_DIR", "").strip()
        relative = configured.removeprefix("/model_registry/") if configured else f"{domain}/latest"
        model_dir = PROJECT_ROOT / "model_registry" / relative
        activation = load_json(model_dir / "activation.json")
        model_hash = sha256_file(model_dir / "model.keras")
        records[domain] = {
            "path": configured or f"/model_registry/{domain}/latest",
            "model_id": f"{domain}:{activation.get('trained_at', 'unknown')}:{model_hash[:12]}",
            "sha256": model_hash,
        }
    return records


def build_file_checksums(stage: Path) -> dict[str, str]:
    return {
        path.relative_to(stage).as_posix(): sha256_file(path)
        for path in sorted(stage.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }


def export_bundle(
    *,
    output: Path,
    env_file: Path = DEFAULT_ENV,
    allow_missing_volumes: bool = False,
) -> dict[str, Any]:
    settings = load_env(env_file)
    ensure_stack_stopped(env_file, settings)
    config = load_json(RELEASE_CONFIG)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ai-cps-site-export-") as temp:
        stage = Path(temp) / "site"
        stage.mkdir()
        shutil.copy2(env_file, stage / ".env")
        os.chmod(stage / ".env", 0o600)
        copy_optional_file(DEPLOYMENT_LOCK, stage / ".runtime/deployment-lock.json")
        for relative in STATE_FILES:
            copy_optional_file(PROJECT_ROOT / relative, stage / relative)
        for relative in selected_candidate_paths(settings):
            shutil.copytree(PROJECT_ROOT / relative, stage / relative)
        archive_directory(report_path(settings), stage / "reports.tar.gz")

        project = compose_project(settings)
        included_volumes: list[str] = []
        for logical in VOLUMES:
            if backup_volume(
                volume_name(project, logical),
                stage / "volumes" / f"{logical}.tar.gz",
                allow_missing=allow_missing_volumes,
            ):
                included_volumes.append(logical)

        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "release": config["release"],
            "source_commit": git_head(),
            "platform": config["platform"],
            "compose_project": project,
            "report_path": str(report_path(settings)),
            "included_volumes": included_volumes,
            "selected_candidates": [path.as_posix() for path in selected_candidate_paths(settings)],
            "models": model_records(settings),
            "files": build_file_checksums(stage),
            "contains_plaintext_env": True,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_output = output.with_name(f".{output.name}.tmp")
        with tarfile.open(temporary_output, "w:gz") as archive:
            for child in sorted(stage.iterdir()):
                archive.add(child, arcname=child.name, recursive=True)
        os.replace(temporary_output, output)
    return manifest


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise MigrationError(f"unsafe archive member: {member.name}")
    archive.extractall(destination, filter="data")


def extract_and_verify(bundle: Path, destination: Path) -> dict[str, Any]:
    try:
        with tarfile.open(bundle, "r:gz") as archive:
            _safe_extract(archive, destination)
    except (OSError, tarfile.TarError) as exc:
        raise MigrationError(f"invalid site bundle: {exc}") from exc
    manifest = load_json(destination / "manifest.json")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise MigrationError("bundle manifest contains no checksums")
    actual_files = build_file_checksums(destination)
    if actual_files != files:
        missing = sorted(set(files) - set(actual_files))
        unexpected = sorted(set(actual_files) - set(files))
        changed = sorted(key for key in set(files) & set(actual_files) if files[key] != actual_files[key])
        raise MigrationError(
            f"bundle checksum mismatch; missing={missing}, unexpected={unexpected}, changed={changed}"
        )
    return manifest


def inspect_bundle(bundle: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ai-cps-site-inspect-") as temp:
        manifest = extract_and_verify(bundle.resolve(), Path(temp))
    return manifest


def validate_compatibility(manifest: Mapping[str, Any]) -> None:
    config = load_json(RELEASE_CONFIG)
    if manifest.get("release") != config.get("release"):
        raise MigrationError(
            f"bundle release {manifest.get('release')} does not match checkout {config.get('release')}"
        )
    if manifest.get("platform") != "linux/amd64":
        raise MigrationError(f"unsupported bundle platform: {manifest.get('platform')}")
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise MigrationError(f"unsupported target architecture: {platform.machine()}")

    included_volumes = manifest.get("included_volumes")
    if (
        not isinstance(included_volumes, list)
        or len(included_volumes) != len(set(included_volumes))
        or any(value not in VOLUMES for value in included_volumes)
    ):
        raise MigrationError("bundle contains an invalid volume list")

    selected = manifest.get("selected_candidates")
    if not isinstance(selected, list):
        raise MigrationError("bundle contains no valid candidate list")
    for value in selected:
        path = PurePosixPath(str(value))
        if (
            path.is_absolute()
            or ".." in path.parts
            or len(path.parts) != 4
            or path.parts[0] != "model_registry"
            or path.parts[1] not in MODEL_DOMAINS
            or path.parts[2] != "candidates"
            or not path.parts[3]
        ):
            raise MigrationError(f"unsafe candidate path in bundle: {value}")


def clear_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def restore_archive(archive_path: Path, destination: Path) -> None:
    clear_directory(destination)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            _safe_extract(archive, destination)
    except (OSError, tarfile.TarError) as exc:
        raise MigrationError(f"cannot restore {archive_path}: {exc}") from exc


def restore_volume(volume: str, archive_path: Path) -> None:
    run_checked(["docker", "volume", "create", volume])
    run_checked(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/target",
            "-v",
            f"{archive_path.parent.resolve()}:/backup:ro",
            HELPER_IMAGE,
            "/bin/sh",
            "-c",
            f"find /target -mindepth 1 -maxdepth 1 -exec rm -rf {{}} + && "
            f"tar -C /target -xzf /backup/{archive_path.name}",
        ]
    )


def import_bundle(
    *,
    bundle: Path,
    env_file: Path = DEFAULT_ENV,
    force: bool,
    target_project: str | None = None,
    target_report_root: Path | None = None,
) -> Path:
    if not force:
        raise MigrationError("import requires --force")
    current_settings = load_env(env_file) if env_file.is_file() else {"COMPOSE_PROJECT_NAME": DEFAULT_PROJECT}
    ensure_stack_stopped(env_file, current_settings)
    with tempfile.TemporaryDirectory(prefix="ai-cps-site-import-") as temp:
        stage = Path(temp)
        manifest = extract_and_verify(bundle.resolve(), stage)
        validate_compatibility(manifest)
        imported_env = load_env(stage / ".env")
        overrides: dict[str, str] = {}
        if target_project is not None:
            overrides["COMPOSE_PROJECT_NAME"] = validate_compose_project(target_project)
        if target_report_root is not None:
            overrides["REPORT_ROOT_HOST"] = str(target_report_root.expanduser().resolve())
        effective_env = {**imported_env, **overrides}
        ensure_stack_stopped(stage / ".env", effective_env)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = bundle.resolve().with_name(f"pre-import-{timestamp}.tar.gz")
        if env_file.is_file():
            export_bundle(
                output=backup,
                env_file=env_file,
                allow_missing_volumes=True,
            )

        env_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage / ".env", env_file)
        update_env(env_file, overrides)
        copy_optional_file(stage / ".runtime/deployment-lock.json", DEPLOYMENT_LOCK)

        for relative in manifest.get("selected_candidates", []):
            source = stage / relative
            target = PROJECT_ROOT / relative
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        for relative in STATE_FILES:
            source = stage / relative
            target = PROJECT_ROOT / relative
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

        restore_archive(stage / "reports.tar.gz", report_path(effective_env))
        project = compose_project(effective_env)
        for logical in manifest.get("included_volumes", []):
            restore_volume(
                volume_name(project, logical), stage / "volumes" / f"{logical}.tar.gz"
            )
    return backup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate an isolated AI-CPS test site. Bundles contain the complete .env "
            "in plaintext; encrypt them before sharing if real credentials are added."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export", help="Create a checksummed site bundle.")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    inspect = subparsers.add_parser("inspect", help="Verify and describe a site bundle.")
    inspect.add_argument("bundle", type=Path)
    restore = subparsers.add_parser("import", help="Restore a verified site bundle.")
    restore.add_argument("bundle", type=Path)
    restore.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    restore.add_argument(
        "--target-project",
        help="Restore volumes into this isolated Docker Compose namespace.",
    )
    restore.add_argument(
        "--target-report-root",
        type=Path,
        help="Restore reports into this dedicated host directory.",
    )
    restore.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "export":
            manifest = export_bundle(output=args.output, env_file=args.env_file)
            print(f"Site bundle created: {args.output.resolve()}")
            print(f"Release: {manifest['release']}; project: {manifest['compose_project']}")
        elif args.command == "inspect":
            print(json.dumps(inspect_bundle(args.bundle), indent=2, sort_keys=True))
        else:
            backup = import_bundle(
                bundle=args.bundle,
                env_file=args.env_file,
                force=args.force,
                target_project=args.target_project,
                target_report_root=args.target_report_root,
            )
            print(f"Site bundle restored. Pre-import backup: {backup}")
            print("The runtime remains stopped; run preflight before starting it.")
    except MigrationError as exc:
        print(f"[MIGRATION][ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
