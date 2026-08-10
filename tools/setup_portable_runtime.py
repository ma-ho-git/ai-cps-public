#!/usr/bin/env python3
"""Initialize an online, digest-pinned AI-CPS runtime installation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = PROJECT_ROOT / "scenarios/serve_ft_nns_external_broker/x86_64"
RELEASE_CONFIG = PROJECT_ROOT / "configs/runtime_release.json"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
DEFAULT_ENV = PROJECT_ROOT / ".env"
DEPLOYMENT_LOCK = PROJECT_ROOT / ".runtime/deployment-lock.json"
IMAGE_ENV_KEYS = {
    "storage": "STORAGE_IMAGE",
    "vgr": "VGR_IMAGE",
    "hbw": "HBW_IMAGE",
    "node_red": "NODE_RED_IMAGE",
}
DIGEST_REFERENCE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
COMPOSE_PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class SetupError(RuntimeError):
    """Portable setup cannot continue without risking an inconsistent install."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SetupError(f"JSON object expected: {path}")
    return value


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SetupError(f"{path}:{number}: KEY=VALUE expected")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def atomic_update_env(path: Path, updates: Mapping[str, str]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    output: list[str] = []
    seen: set[str] = set()
    for line in existing:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in updates and key and not stripped.startswith("#"):
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    missing = [key for key in updates if key not in seen]
    if missing and output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={updates[key]}" for key in missing)
    content = "\n".join(output) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def manifest_url(repository: str, release: str) -> str:
    return (
        f"https://github.com/{repository}/releases/download/"
        f"{release}/runtime-manifest.json"
    )


def obtain_manifest(
    *, release: str, config: Mapping[str, Any], manifest_path: Path | None
) -> dict[str, Any]:
    if manifest_path is not None:
        manifest = load_object(manifest_path)
    else:
        url = manifest_url(str(config["repository"]), release)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed GitHub host
                manifest = json.loads(response.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SetupError(f"cannot download release manifest from {url}: {exc}") from exc
    if manifest.get("release") != release:
        raise SetupError(
            f"manifest release {manifest.get('release')!r} does not match {release!r}"
        )
    if manifest.get("platform") != "linux/amd64":
        raise SetupError(f"unsupported release platform: {manifest.get('platform')!r}")
    images = manifest.get("images")
    if not isinstance(images, dict) or set(IMAGE_ENV_KEYS) - set(images):
        raise SetupError("release manifest does not contain all four runtime images")
    if any(
        DIGEST_REFERENCE.fullmatch(str(images[key])) is None
        for key in IMAGE_ENV_KEYS
    ):
        raise SetupError("release image references must be pinned by sha256 digest")
    return manifest


def verify_source_tree(manifest: Mapping[str, Any]) -> None:
    expected_commit = str(manifest.get("source_commit", "")).strip()
    if len(expected_commit) != 40:
        raise SetupError("release manifest contains no full source commit")
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0 or process.stdout.strip() != expected_commit:
        actual = process.stdout.strip() or "unavailable"
        raise SetupError(
            f"source checkout {actual} does not match release commit {expected_commit}"
        )
    protected = manifest.get("protected_files")
    if not isinstance(protected, dict) or not protected:
        raise SetupError("release manifest contains no protected file hashes")
    for relative, expected_hash in protected.items():
        path = PROJECT_ROOT / str(relative)
        if not path.is_file():
            raise SetupError(f"release file is missing: {relative}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise SetupError(f"release file hash mismatch: {relative}")


def write_deployment_lock(manifest: Mapping[str, Any]) -> None:
    DEPLOYMENT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".deployment-lock.", dir=DEPLOYMENT_LOCK.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, DEPLOYMENT_LOCK)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def report_path(settings: Mapping[str, str]) -> Path:
    configured = Path(settings.get("REPORT_ROOT_HOST", "../../../reports")).expanduser()
    return configured if configured.is_absolute() else (SCENARIO_ROOT / configured).resolve()


def validate_compose_project(value: str) -> str:
    project = value.strip()
    if COMPOSE_PROJECT.fullmatch(project) is None:
        raise SetupError(
            "compose project must start with a lowercase letter or digit and "
            "contain only lowercase letters, digits, '-' or '_'"
        )
    return project


def run_checked(command: list[str], *, cwd: Path = PROJECT_ROOT) -> None:
    process = subprocess.run(command, cwd=cwd, text=True, check=False)
    if process.returncode != 0:
        raise SetupError(f"command failed ({process.returncode}): {' '.join(command)}")


def create_venv() -> Path:
    venv = PROJECT_ROOT / ".venv"
    python = venv / "bin/python"
    if not python.exists():
        run_checked([sys.executable, "-m", "venv", str(venv)])
    run_checked(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--require-hashes",
            "--requirement",
            str(PROJECT_ROOT / ".github/requirements-runtime-ci.lock"),
        ]
    )
    return python


def compose_command(mode: str, env_file: Path) -> list[str]:
    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(SCENARIO_ROOT / "docker-compose.yml"),
    ]
    if mode == "virtual":
        command.extend(["-f", str(SCENARIO_ROOT / "docker-compose.virtual.yml")])
    return command


def require_physical_mqtt_host(value: str | None) -> str:
    """Return the explicitly selected broker or reject an implicit default."""
    mqtt_host = (value or "").strip()
    if not mqtt_host:
        raise SetupError("physical setup requires --mqtt-host for the target broker")
    return mqtt_host


def init_runtime(args: argparse.Namespace) -> None:
    config = load_object(RELEASE_CONFIG)
    if args.release != config.get("release"):
        raise SetupError(
            f"this source tree prepares {config.get('release')}, not {args.release}"
        )
    manifest = obtain_manifest(
        release=args.release, config=config, manifest_path=args.manifest
    )
    verify_source_tree(manifest)
    env_file = args.env_file.resolve()
    env_was_present = env_file.exists()
    if not env_was_present:
        shutil.copy2(ENV_EXAMPLE, env_file)
    settings = load_env(env_file)
    if args.mode == "physical":
        mqtt_host = require_physical_mqtt_host(args.mqtt_host)
    else:
        mqtt_host = settings.get("MQTT_HOST", "")

    secret = settings.get("NODE_RED_CREDENTIAL_SECRET", "")
    if not secret or secret == "replace-with-a-long-random-site-secret":
        secret = secrets.token_urlsafe(48)

    images = manifest["images"]
    compose_project = validate_compose_project(
        getattr(args, "compose_project", None)
        or settings.get("COMPOSE_PROJECT_NAME", "")
        or str(config["compose_project"])
    )
    updates = {
        "COMPOSE_PROJECT_NAME": compose_project,
        "AI_CPS_UID": str(os.getuid()),
        "AI_CPS_GID": str(os.getgid()),
        "IMAGE_TAG": args.release,
        "NODE_RED_CREDENTIAL_SECRET": secret,
        **{env_key: str(images[key]) for key, env_key in IMAGE_ENV_KEYS.items()},
    }
    requested_report_root = getattr(args, "report_root", None)
    if requested_report_root is not None:
        updates["REPORT_ROOT_HOST"] = str(requested_report_root.expanduser().resolve())
    if args.mode == "physical":
        updates.update(
            {
                "MQTT_HOST": mqtt_host,
                "MQTT_PORT": str(args.mqtt_port),
                "MQTT_USER": args.mqtt_user or settings.get("MQTT_USER", ""),
            }
        )
    if env_was_present and not args.force:
        conflicting = {
            key: settings[key]
            for key, value in updates.items()
            if key in settings
            and settings[key]
            and settings[key] != value
            and key in set(IMAGE_ENV_KEYS.values()) | {"IMAGE_TAG"}
        }
        if conflicting:
            raise SetupError(
                "existing image selection differs from the release; use --force: "
                + ", ".join(sorted(conflicting))
            )
    atomic_update_env(env_file, updates)
    write_deployment_lock(manifest)
    settings = load_env(env_file)
    reports = report_path(settings)
    reports.mkdir(parents=True, exist_ok=True)
    reports.chmod(reports.stat().st_mode | 0o770)

    python = Path(sys.executable) if args.skip_venv else create_venv()
    if not args.skip_pull:
        run_checked(compose_command(args.mode, env_file) + ["pull"])
    if not args.skip_preflight:
        run_checked(
            [
                str(python),
                str(PROJECT_ROOT / "tools/check_deployment_readiness.py"),
                "--mode",
                args.mode,
                "--env-file",
                str(env_file),
                "--images",
            ]
        )
    print(f"Portable {args.mode} runtime prepared in {PROJECT_ROOT}")
    print(f"Release: {args.release}")
    print(f"Configuration: {env_file}")


def parse_args() -> argparse.Namespace:
    config = load_object(RELEASE_CONFIG)
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="Prepare a released runtime checkout.")
    init.add_argument("--mode", choices=("virtual", "physical"), required=True)
    init.add_argument("--release", default=config["release"])
    init.add_argument("--manifest", type=Path)
    init.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    init.add_argument(
        "--compose-project",
        help="Isolated Docker Compose namespace written to COMPOSE_PROJECT_NAME.",
    )
    init.add_argument(
        "--report-root",
        type=Path,
        help="Dedicated host report directory; stored as an absolute path.",
    )
    init.add_argument("--mqtt-host")
    init.add_argument("--mqtt-port", type=int, default=1883)
    init.add_argument("--mqtt-user", default="")
    init.add_argument("--force", action="store_true")
    init.add_argument("--skip-venv", action="store_true", help=argparse.SUPPRESS)
    init.add_argument("--skip-pull", action="store_true", help=argparse.SUPPRESS)
    init.add_argument("--skip-preflight", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            init_runtime(args)
    except SetupError as exc:
        print(f"[SETUP][ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
