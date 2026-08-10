#!/usr/bin/env python3
"""Prueft ein NN-Artefakt vor dem Einsatz in der MQTT-Orchestrierung.

Das Werkzeug veraendert weder `model_registry` noch Node-RED. Es vergleicht
den Kandidaten mit dem aktuellen Modellvertrag und prueft, ob Node-RED seine
Eingaben aus dem virtuellen Trace beziehungsweise dem eingefrorenen
physischen 28-Feld-Vertrag aufbauen kann.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = PROJECT_ROOT / "scenarios/serve_ft_nns_external_broker/x86_64"
TOPICS_PATH = SCENARIO_ROOT / "node_red/config/topics.json"
IDLE_SEEDS_PATH = SCENARIO_ROOT / "node_red/config/idle_seed_templates.json"
VIRTUAL_PAYLOADS_PATH = SCENARIO_ROOT / "test_payloads/live_plc_trace/payloads.jsonl"
PHYSICAL_CONTRACT_PATH = PROJECT_ROOT / "configs/plc_live_mqtt_adapter.json"
REQUIRED_ARTIFACTS = ("model.keras", "activation.json", "metrics.json")
DOMAINS = ("storage", "vgr", "hbw")
EMPTY_STORAGE_FEATURES = tuple(f"empty_storage_{index}" for index in range(10))


class ArtifactError(ValueError):
    """Kennzeichnet fehlende oder strukturell unlesbare Eingabeartefakte."""


@dataclass(frozen=True)
class CompatibilityCheck:
    """Ein einzelner Kompatibilitaetsbefund."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class CompatibilityReport:
    """Gesamtergebnis fuer einen Modellkandidaten."""

    domain: str
    mode: str
    candidate_dir: str
    classification: str
    feature_changes: dict[str, Any]
    checks: list[CompatibilityCheck]

    @property
    def compatible(self) -> bool:
        return all(check.ok for check in self.checks)


def check(name: str, ok: bool, success: str, failure: str) -> CompatibilityCheck:
    return CompatibilityCheck(name=name, ok=ok, detail=success if ok else failure)


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ArtifactError(f"missing file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ArtifactError(f"expected JSON object in {path}")
    return value


def load_activation(path: Path) -> dict[str, Any]:
    activation = load_json_object(path)
    for key in ("domain", "feature_cols", "class_ids"):
        if key not in activation:
            raise ArtifactError(f"{path} is missing required key {key}")
    if not isinstance(activation["feature_cols"], list) or not activation["feature_cols"]:
        raise ArtifactError(f"{path}: feature_cols must be a non-empty list")
    if not isinstance(activation["class_ids"], list) or not activation["class_ids"]:
        raise ArtifactError(f"{path}: class_ids must be a non-empty list")
    return activation


def feature_cols(activation: dict[str, Any]) -> list[str]:
    values = activation["feature_cols"]
    if not all(isinstance(value, str) and value for value in values):
        raise ArtifactError("feature_cols must contain non-empty strings")
    return list(values)


def class_ids(activation: dict[str, Any]) -> list[int]:
    try:
        return [int(value) for value in activation["class_ids"]]
    except (TypeError, ValueError) as exc:
        raise ArtifactError("class_ids must contain integer command IDs") from exc


def time_steps(activation: dict[str, Any], domain: str) -> int | None:
    raw_value = activation.get("time_steps")
    if domain == "storage" and raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ArtifactError(f"{domain} activation requires an integer time_steps") from exc


def declared_input_shape(
    activation: dict[str, Any],
    domain: str,
    features: list[str],
    steps: int | None,
) -> list[int]:
    raw_shape = activation.get("input_shape")
    if raw_shape is None:
        raw_shape = activation.get("architecture", {}).get("input_shape")
    if raw_shape is None:
        return [len(features)] if domain == "storage" else [int(steps), len(features)]
    if not isinstance(raw_shape, list):
        raise ArtifactError("activation input_shape must be a list")
    try:
        return [int(value) for value in raw_shape]
    except (TypeError, ValueError) as exc:
        raise ArtifactError("activation input_shape must contain integers") from exc


def keras_shapes(path: Path) -> tuple[list[int], int]:
    """Liest Inputform und Output-Units direkt aus dem Keras-v3-Archiv."""
    if not path.is_file():
        raise ArtifactError(f"missing file: {path}")
    if not zipfile.is_zipfile(path):
        raise ArtifactError(f"{path} is not a readable Keras v3 archive")
    try:
        with zipfile.ZipFile(path) as archive:
            config = json.loads(archive.read("config.json"))
    except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise ArtifactError(f"cannot read Keras config from {path}: {exc}") from exc

    layers = config.get("config", {}).get("layers")
    if not isinstance(layers, list):
        raise ArtifactError(f"{path}: Keras config has no layer list")

    input_shape: list[int] | None = None
    output_units: int | None = None
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_config = layer.get("config", {})
        if layer.get("class_name") == "InputLayer" and input_shape is None:
            batch_shape = layer_config.get("batch_shape") or layer_config.get("batch_input_shape")
            if isinstance(batch_shape, list):
                input_shape = [int(value) for value in batch_shape if value is not None]
        units = layer_config.get("units")
        if units is not None:
            output_units = int(units)
    if input_shape is None or output_units is None:
        raise ArtifactError(f"{path}: cannot derive model input/output shape")
    return input_shape, output_units


def feature_change_summary(current: dict[str, Any], candidate: dict[str, Any], domain: str) -> dict[str, Any]:
    current_features = feature_cols(current)
    candidate_features = feature_cols(candidate)
    current_steps = time_steps(current, domain)
    candidate_steps = time_steps(candidate, domain)
    return {
        "added": [value for value in candidate_features if value not in current_features],
        "removed": [value for value in current_features if value not in candidate_features],
        "reordered": set(current_features) == set(candidate_features)
        and current_features != candidate_features,
        "time_steps_before": current_steps,
        "time_steps_after": candidate_steps,
        "classes_before": class_ids(current),
        "classes_after": class_ids(candidate),
    }


def raw_features(features: Iterable[str]) -> list[str]:
    return [feature for feature in features if not feature.startswith("empty_storage_")]


def physical_raw_fields(root: Path) -> set[str]:
    config = load_json_object(root / PHYSICAL_CONTRACT_PATH.relative_to(PROJECT_ROOT))
    mapping = config.get("field_map")
    if not isinstance(mapping, dict) or len(mapping) != 28:
        raise ArtifactError("physical field_map must define the frozen 28-field contract")
    return {str(key) for key in mapping}


def virtual_payload_states(root: Path) -> list[dict[str, Any]]:
    path = root / VIRTUAL_PAYLOADS_PATH.relative_to(PROJECT_ROOT)
    if not path.is_file():
        raise ArtifactError(f"missing virtual payload trace: {path}")
    states: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ArtifactError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ArtifactError(f"{path}:{line_number}: payload must be an object")
        state = payload.get("state") if isinstance(payload.get("state"), dict) else payload
        states.append(state)
    if not states:
        raise ArtifactError(f"virtual payload trace is empty: {path}")
    return states


def raw_feature_check(
    *,
    mode: str,
    required: list[str],
    root: Path,
) -> CompatibilityCheck:
    if mode == "physical":
        available = physical_raw_fields(root)
        missing = sorted(set(required) - available)
        return check(
            "raw-features:physical",
            not missing,
            f"all {len(required)} raw features are inside the frozen 28-field live contract",
            f"features outside the frozen 28-field live contract: {missing}",
        )

    states = virtual_payload_states(root)
    invalid: list[str] = []
    for row_index, state in enumerate(states, start=1):
        for feature in required:
            try:
                float(state[feature])
            except (KeyError, TypeError, ValueError):
                invalid.append(f"row {row_index}:{feature}")
                if len(invalid) >= 10:
                    break
        if len(invalid) >= 10:
            break
    return check(
        "raw-features:virtual",
        not invalid,
        f"all {len(required)} raw features are numeric in all {len(states)} virtual payloads",
        f"missing or non-numeric virtual features (first findings): {invalid}",
    )


def idle_seed_check(
    *,
    required: list[str],
    steps: int,
    root: Path,
) -> list[CompatibilityCheck]:
    seeds = load_json_object(root / IDLE_SEEDS_PATH.relative_to(PROJECT_ROOT))
    rows = seeds.get("rows")
    if not isinstance(rows, list):
        raise ArtifactError("idle seed template requires a rows list")
    required_rows = steps - 1
    row_count_ok = len(rows) >= required_rows
    invalid: list[str] = []
    for row_index, row in enumerate(rows[:required_rows], start=1):
        if not isinstance(row, dict):
            invalid.append(f"row {row_index}:not_an_object")
            continue
        for feature in required:
            try:
                float(row[feature])
            except (KeyError, TypeError, ValueError):
                invalid.append(f"row {row_index}:{feature}")
                if len(invalid) >= 10:
                    break
        if len(invalid) >= 10:
            break
    return [
        check(
            "idle-seeds:row-count",
            row_count_ok,
            f"{len(rows)} idle rows cover required time_steps-1={required_rows}",
            f"model needs {required_rows} idle rows, template contains {len(rows)}",
        ),
        check(
            "idle-seeds:features",
            row_count_ok and not invalid,
            f"all {len(required)} raw LSTM features exist in the bootstrap rows",
            f"idle seed features are missing or non-numeric: {invalid}",
        ),
    ]


def analyze_model(
    *,
    domain: str,
    candidate_dir: Path,
    mode: str,
    root: Path = PROJECT_ROOT,
) -> CompatibilityReport:
    if domain not in DOMAINS:
        raise ArtifactError(f"unsupported domain: {domain}")
    if mode not in {"virtual", "physical"}:
        raise ArtifactError(f"unsupported mode: {mode}")

    missing = [name for name in REQUIRED_ARTIFACTS if not (candidate_dir / name).is_file()]
    if missing:
        raise ArtifactError(f"candidate directory is missing artifacts: {missing}")
    candidate = load_activation(candidate_dir / "activation.json")
    load_json_object(candidate_dir / "metrics.json")
    current = load_activation(root / f"model_registry/{domain}/latest/activation.json")
    features = feature_cols(candidate)
    classes = class_ids(candidate)
    steps = time_steps(candidate, domain)
    expected_shape = [len(features)] if domain == "storage" else [int(steps), len(features)]
    activation_shape = declared_input_shape(candidate, domain, features, steps)
    model_shape, output_units = keras_shapes(candidate_dir / "model.keras")
    topics = load_json_object(root / TOPICS_PATH.relative_to(PROJECT_ROOT))
    cmd_map = candidate.get("cmd_map")
    if not isinstance(cmd_map, dict):
        cmd_map = {}

    changes = feature_change_summary(current, candidate, domain)
    same_contract = (
        not changes["added"]
        and not changes["removed"]
        and not changes["reordered"]
        and changes["time_steps_before"] == changes["time_steps_after"]
    )
    checks = [
        check(
            "domain",
            candidate.get("domain") == domain,
            f"candidate domain is {domain}",
            f"candidate domain {candidate.get('domain')!r} does not match {domain}",
        ),
        check(
            "features:unique",
            len(features) == len(set(features)),
            f"all {len(features)} feature names are unique",
            "feature_cols contains duplicate names",
        ),
        check(
            "classes:unique",
            len(classes) == len(set(classes)),
            f"all {len(classes)} class IDs are unique",
            "class_ids contains duplicate values",
        ),
        check(
            "activation:input-shape",
            activation_shape == expected_shape,
            f"activation input shape is {expected_shape}",
            f"activation input shape {activation_shape} does not match {expected_shape}",
        ),
        check(
            "keras:input-shape",
            model_shape == expected_shape,
            f"Keras input shape is {expected_shape}",
            f"Keras input shape {model_shape} does not match {expected_shape}",
        ),
        check(
            "keras:output-units",
            output_units == len(classes),
            f"Keras output has {output_units} units for {len(classes)} classes",
            f"Keras output has {output_units} units, activation declares {len(classes)} classes",
        ),
        check(
            "activation:n-classes",
            candidate.get("n_classes", len(classes)) == len(classes),
            f"n_classes matches {len(classes)} class IDs",
            f"n_classes={candidate.get('n_classes')} does not match {len(classes)} class IDs",
        ),
        check(
            "activation:cmd-map",
            not [value for value in classes if str(value) not in cmd_map],
            "activation cmd_map covers every class",
            f"activation cmd_map misses classes: {[value for value in classes if str(value) not in cmd_map]}",
        ),
    ]

    if domain == "storage":
        checks.append(
            check(
                "storage:classes",
                classes == list(range(10)),
                "Storage classes retain empty_storage semantics 0..9",
                f"Storage classes must be ordered 0..9, got {classes}",
            )
        )
        checks.append(
            check(
                "storage:time-steps",
                steps is None,
                "Storage remains a non-temporal MLP contract",
                f"Storage must not define time_steps, got {steps}",
            )
        )
    else:
        one_hot = [feature for feature in features if feature.startswith("empty_storage_")]
        checks.append(
            check(
                "lstm:empty-storage-one-hot",
                one_hot == list(EMPTY_STORAGE_FEATURES),
                "LSTM contract contains ordered empty_storage_0..9",
                f"expected ordered empty_storage_0..9, got {one_hot}",
            )
        )
        mapped = topics.get("command_topics", {}).get(domain, {})
        missing_topics = [value for value in classes if str(value) not in mapped]
        checks.append(
            check(
                "commands:topic-map",
                not missing_topics,
                "every model class has a physical command topic",
                f"command topic mapping misses classes: {missing_topics}",
            )
        )
        if steps is not None and steps > 0:
            checks.extend(
                idle_seed_check(required=raw_features(features), steps=steps, root=root)
            )
        else:
            checks.append(
                CompatibilityCheck("lstm:time-steps", False, "time_steps must be positive")
            )

    checks.append(
        raw_feature_check(mode=mode, required=raw_features(features), root=root)
    )
    return CompatibilityReport(
        domain=domain,
        mode=mode,
        candidate_dir=str(candidate_dir),
        classification="same_feature_contract" if same_contract else "changed_feature_contract",
        feature_changes=changes,
        checks=checks,
    )


def print_human(report: CompatibilityReport) -> None:
    print(
        f"Model candidate: domain={report.domain} mode={report.mode} "
        f"classification={report.classification}"
    )
    changes = report.feature_changes
    if report.classification == "changed_feature_contract":
        print(
            "Feature changes: "
            f"added={changes['added']} removed={changes['removed']} "
            f"reordered={changes['reordered']} "
            f"time_steps={changes['time_steps_before']}->{changes['time_steps_after']}"
        )
    for item in report.checks:
        marker = "OK" if item.ok else "FAIL"
        print(f"[{marker:4}] {item.name}: {item.detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Dieses Werkzeug ist der read-only Einzelcheck. Fuer Aufnahme,
Auswahl, Rollback und Promotion lokaler Kandidaten dient
tools/manage_model_candidates.py.

`physical` prueft den eingefrorenen 28-Feld-Live-Vertrag; der Kandidatenmanager
fuehrt fuer ein physisches Ziel zusaetzlich immer die virtuelle Trace-Pruefung aus.""",
    )
    parser.add_argument("--domain", required=True, choices=DOMAINS, help="Zu pruefende Modelldomain.")
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        help="Artefaktordner; ohne Angabe wird model_registry/<domain>/latest geprueft.",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("virtual", "physical"),
        help="Datenvertrag, gegen den Rohfeatures und Seeds geprueft werden.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Maschinenlesbare JSON-Ausgabe.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_dir = args.candidate_dir or PROJECT_ROOT / f"model_registry/{args.domain}/latest"
    try:
        report = analyze_model(
            domain=args.domain,
            candidate_dir=candidate_dir.resolve(),
            mode=args.mode,
        )
    except ArtifactError as exc:
        if args.as_json:
            print(json.dumps({"error": str(exc), "exit_code": 2}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        payload = asdict(report)
        payload["compatible"] = report.compatible
        print(json.dumps(payload, indent=2))
    else:
        print_human(report)
    return 0 if report.compatible else 1


if __name__ == "__main__":
    raise SystemExit(main())
