#!/usr/bin/env python3
"""Generate the self-contained low-code Node-RED runtime flow."""

from __future__ import annotations

import json
from pathlib import Path

from nodered_flow import build_low_code_flow


ROOT = Path(__file__).resolve().parents[1]
FLOW_PATH = (
    ROOT
    / "scenarios"
    / "serve_ft_nns_external_broker"
    / "x86_64"
    / "node_red"
    / "flows.json"
)


def assign_groups(nodes: list[dict]) -> None:
    """Synchronize group members and bidirectional link-node references."""
    memberships: dict[str, list[str]] = {}
    for node in nodes:
        group_id = node.get("g")
        if group_id:
            memberships.setdefault(group_id, []).append(node["id"])

    for node in nodes:
        if node.get("type") == "group":
            node["nodes"] = memberships.get(node["id"], [])

    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        if node.get("type") != "link out":
            continue
        for target_id in node.get("links", []):
            target = by_id.get(target_id)
            if target and target.get("type") == "link in":
                target.setdefault("links", []).append(node["id"])


def main() -> None:
    existing = json.loads(FLOW_PATH.read_text(encoding="utf-8"))
    nodes = build_low_code_flow(existing)
    assign_groups(nodes)
    FLOW_PATH.write_text(
        json.dumps(nodes, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
