#!/usr/bin/env python3
"""Build a deterministic CycloneDX inventory from pinned source lock files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_LOCKS = (
    "scenarios/serve_ft_nns_external_broker/x86_64/code_base_common/requirements-runtime.lock",
    "training/storage/requirements-training.lock",
    "training/vgr/requirements-training.lock",
    "training/hbw/requirements-training.lock",
)
NODE_LOCK = (
    "scenarios/serve_ft_nns_external_broker/x86_64/"
    "node_red/dashboard_runtime/package-lock.json"
)
PYTHON_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")


def normalize_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_components(root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    records: dict[tuple[str, str], set[str]] = {}
    for relative in PYTHON_LOCKS:
        path = root / relative
        for line in path.read_text(encoding="utf-8").splitlines():
            match = PYTHON_REQUIREMENT.match(line)
            if match is None:
                continue
            name = normalize_python_name(match.group(1))
            version = match.group(2)
            records.setdefault((name, version), set()).add(relative)
    return [
        {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{name}@{version}",
            "properties": [
                {"name": "ai-cps:lock-file", "value": source}
                for source in sorted(sources)
            ],
        }
        for (name, version), sources in sorted(records.items())
    ]


def node_components(root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    document = json.loads((root / NODE_LOCK).read_text(encoding="utf-8"))
    packages = document.get("packages", {})
    components: list[dict[str, Any]] = []
    for location, record in sorted(packages.items()):
        if not location.startswith("node_modules/") or not isinstance(record, dict):
            continue
        name = location.removeprefix("node_modules/")
        version = str(record.get("version", "")).strip()
        if not version:
            continue
        encoded_name = name.replace("@", "%40")
        component: dict[str, Any] = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:npm/{encoded_name}@{version}",
            "properties": [{"name": "ai-cps:lock-file", "value": NODE_LOCK}],
        }
        license_name = str(record.get("license", "")).strip()
        if license_name:
            component["licenses"] = [{"license": {"id": license_name}}]
        components.append(component)
    return components


def build_sbom(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    config = json.loads((root / "configs/runtime_release.json").read_text(encoding="utf-8"))
    components = python_components(root) + node_components(root)
    components.sort(key=lambda item: (item["purl"], item["version"]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "ai-cps-runtime",
                "version": str(config["release"]).removeprefix("runtime-v"),
                "licenses": [{"license": {"id": "AGPL-3.0-only"}}],
                "externalReferences": [
                    {
                        "type": "vcs",
                        "url": f"https://github.com/{config['repository']}",
                    }
                ],
            }
        },
        "components": components,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    document = build_sbom()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
