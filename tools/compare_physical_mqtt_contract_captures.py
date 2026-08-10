"""Vergleicht zwei MQTT-Mitschnitte an der physischen Projektgrenze."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CONTRACT_FIELDS = ("topic", "payload_length", "payload_sha256", "qos", "retain")


def load_capture(path: str | Path) -> list[dict[str, Any]]:
    """Liest einen JSONL-Mitschnitt ohne seine Aufnahmezeitpunkte."""
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def contract_projection(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduziert auf Merkmale, die am Live-System unveraendert bleiben muessen."""
    return [
        {field: record.get(field) for field in CONTRACT_FIELDS}
        for record in records
    ]


def compare_captures(reference: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> list[str]:
    """Liefert nachvollziehbare Abweichungen statt nur eines Boolean-Werts."""
    left = contract_projection(reference)
    right = contract_projection(candidate)
    differences: list[str] = []
    if len(left) != len(right):
        differences.append(f"message_count: reference={len(left)} candidate={len(right)}")
    for index, (expected, actual) in enumerate(zip(left, right)):
        if expected != actual:
            differences.append(f"message[{index}]: reference={expected} candidate={actual}")
    return differences


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    differences = compare_captures(load_capture(args.reference), load_capture(args.candidate))
    if differences:
        print("Physical MQTT contract differs:")
        for difference in differences:
            print(f"- {difference}")
        raise SystemExit(1)
    print("Physical MQTT contract identical.")


if __name__ == "__main__":
    main()
