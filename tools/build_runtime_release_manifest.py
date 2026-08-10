#!/usr/bin/env python3
"""Build the machine-readable manifest for a tagged portable runtime release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_CONFIG = PROJECT_ROOT / "configs/runtime_release.json"
DOMAINS = ("storage", "vgr", "hbw")
IMAGE_NAMES = {
    "storage": "ai-cps-runtime-storage-infer",
    "vgr": "ai-cps-runtime-vgr-infer",
    "hbw": "ai-cps-runtime-hbw-infer",
    "node_red": "ai-cps-runtime-node-red",
}
PROTECTED_FILES = (
    "scenarios/serve_ft_nns_external_broker/x86_64/node_red/flows.json",
    "scenarios/serve_ft_nns_external_broker/x86_64/node_red/flows_ai_orchestration.json",
    "scenarios/serve_ft_nns_external_broker/x86_64/node_red/config/topics.json",
    "scenarios/serve_ft_nns_external_broker/x86_64/node_red/config/idle_seed_templates.json",
    "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/live_plc_trace/payloads.jsonl",
    "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/live_plc_full_storage_attempt/payloads.jsonl",
    "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/live_plc_full_storage_process_guard/payloads.jsonl",
)


class ManifestError(RuntimeError):
    """The release manifest could not be assembled safely."""


DIGEST_REFERENCE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ManifestError(f"JSON object expected: {path}")
    return value


def git_head(root: Path = PROJECT_ROOT) -> str:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise ManifestError(process.stderr.strip() or "git HEAD is unavailable")
    return process.stdout.strip()


def model_record(domain: str, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    model_dir = root / "model_registry" / domain / "latest"
    activation = load_object(model_dir / "activation.json")
    files = {
        name: sha256_file(model_dir / name)
        for name in ("model.keras", "activation.json", "metrics.json")
    }
    model_id = f"{domain}:{activation.get('trained_at', 'unknown')}:{files['model.keras'][:12]}"
    return {"model_id": model_id, "files": files}


def parse_image_assignments(values: list[str]) -> dict[str, str]:
    images: dict[str, str] = {}
    for value in values:
        key, separator, reference = value.partition("=")
        if (
            not separator
            or key not in IMAGE_NAMES
            or DIGEST_REFERENCE.fullmatch(reference) is None
        ):
            raise ManifestError(
                "--image expects domain=repository@sha256:digest for "
                + ", ".join(IMAGE_NAMES)
            )
        images[key] = reference
    missing = sorted(set(IMAGE_NAMES) - set(images))
    if missing:
        raise ManifestError(f"missing image references: {missing}")
    return images


def resolve_image_reference(tag_reference: str) -> str:
    process = subprocess.run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            tag_reference,
            "--format",
            "{{json .Manifest}}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise ManifestError(process.stderr.strip() or f"cannot inspect {tag_reference}")
    descriptor = json.loads(process.stdout)
    digest = descriptor.get("digest") or descriptor.get("Digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise ManifestError(f"registry digest missing for {tag_reference}")
    return f"{tag_reference.rsplit(':', 1)[0]}@{digest}"


def resolve_release_images(release: str, owner: str) -> dict[str, str]:
    return {
        domain: resolve_image_reference(
            f"ghcr.io/{owner}/{image_name}:{release}"
        )
        for domain, image_name in IMAGE_NAMES.items()
    }


def build_manifest(
    *,
    release: str,
    source_commit: str,
    images: dict[str, str],
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    config = load_object(root / "configs/runtime_release.json")
    if release != config.get("release"):
        raise ManifestError(
            f"release mismatch: config={config.get('release')!r}, requested={release!r}"
        )
    if COMMIT_SHA.fullmatch(source_commit) is None:
        raise ManifestError("source commit must be a full 40-character SHA")
    invalid_images = [
        key
        for key in IMAGE_NAMES
        if DIGEST_REFERENCE.fullmatch(str(images.get(key, ""))) is None
    ]
    if invalid_images:
        raise ManifestError(f"invalid digest-pinned images: {invalid_images}")
    protected = {
        relative: sha256_file(root / relative) for relative in PROTECTED_FILES
    }
    return {
        "schema_version": 1,
        "release": release,
        "source_commit": source_commit,
        "repository": config["repository"],
        "source_url": f"https://github.com/{config['repository']}",
        "license": "AGPL-3.0-only",
        "platform": config["platform"],
        "compose_project": config["compose_project"],
        "node_red_runtime_version": config["node_red_runtime_version"],
        "images": images,
        "models": {domain: model_record(domain, root) for domain in DOMAINS},
        "protected_files": protected,
    }


def parse_args() -> argparse.Namespace:
    config = load_object(RELEASE_CONFIG)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default=config["release"])
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--resolve-images", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_object(RELEASE_CONFIG)
    if args.resolve_images and args.image:
        raise ManifestError("use either --resolve-images or explicit --image values")
    images = (
        resolve_release_images(args.release, config["ghcr_owner"])
        if args.resolve_images
        else parse_image_assignments(args.image)
    )
    manifest = build_manifest(
        release=args.release,
        source_commit=args.source_commit or git_head(),
        images=images,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
