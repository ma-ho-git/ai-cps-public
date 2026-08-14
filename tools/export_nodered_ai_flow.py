"""Extrahiert den virtuellen NN-Pipeline-Tab aus dem Gesamt-Flow.

Die Exportdatei wird in Git versioniert und nicht beim Node-RED-Start erzeugt.
Das Skript dient nur dazu, nach bewussten Flow-Aenderungen beide Artefakte
deterministisch synchron zu halten.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NODE_RED_DIR = PROJECT_ROOT / "scenarios/serve_ft_nns_external_broker/x86_64/node_red"
SOURCE = NODE_RED_DIR / "flows.json"
OUTPUT = NODE_RED_DIR / "flows_ai_orchestration.json"
TAB_ID = "tab-pipeline"
REQUIRED_CONFIG_IDS = {"mqtt-ai-cps"}
REQUIRED_SUBFLOW_IDS = {"subflow-lstm-window", "subflow-model-response"}


def extract_ai_flow(flows: list[dict]) -> list[dict]:
    """Waehlt AI-Tab, seine Nodes und explizit benoetigte Config-Nodes."""
    selected = [
        node
        for node in flows
        if node.get("id") == TAB_ID
        or node.get("z") == TAB_ID
        or node.get("id") in REQUIRED_CONFIG_IDS
        or node.get("id") in REQUIRED_SUBFLOW_IDS
        or node.get("z") in REQUIRED_SUBFLOW_IDS
    ]
    if not any(node.get("id") == TAB_ID for node in selected):
        raise ValueError(f"Missing Node-RED tab {TAB_ID}")
    if any(node.get("z") in {"tab-modules", "tab-semaphore"} for node in selected):
        raise ValueError("AI export must not contain virtual module or semaphore nodes")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Prueft den versionierten Export, ohne ihn zu veraendern.",
    )
    args = parser.parse_args()
    flows = json.loads(SOURCE.read_text(encoding="utf-8"))
    selected = extract_ai_flow(flows)
    rendered = json.dumps(selected, indent=2) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"Node-RED AI flow export is stale: {OUTPUT}")
        print(f"Node-RED AI flow export is current: {OUTPUT}")
        return
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {len(selected)} Node-RED objects to {OUTPUT}")


if __name__ == "__main__":
    main()
