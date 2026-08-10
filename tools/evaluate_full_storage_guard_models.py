"""Vergleicht Baseline und Guard-Kandidat auf Original- und Vollspeicherfenstern."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DOMAIN_DEFAULTS = {
    "vgr": {
        "original_config": PROJECT_ROOT / "configs/regression_vgr_original.json",
        "guard_config": PROJECT_ROOT / "configs/train_vgr.json",
    },
    "hbw": {
        "original_config": PROJECT_ROOT / "configs/regression_hbw_original.json",
        "guard_config": PROJECT_ROOT / "configs/train_hbw.json",
    },
}

IDLE_SEEDS_PATH = (
    PROJECT_ROOT
    / "scenarios/serve_ft_nns_external_broker/x86_64/node_red/config/idle_seed_templates.json"
)
PROFILE_PAYLOADS = {
    "standard": PROJECT_ROOT
    / "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/live_plc_trace/payloads.jsonl",
    "stationary_guard": PROJECT_ROOT
    / "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/live_plc_full_storage_attempt/payloads.jsonl",
    "process_guard": PROJECT_ROOT
    / "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/live_plc_full_storage_process_guard/payloads.jsonl",
}


def resolve_repo_path(path: str) -> Path:
    """Uebersetzt Containerpfade der Trainingsconfigs in lokale Repopfade."""
    if path.startswith("/data/"):
        return PROJECT_ROOT / path.removeprefix("/")
    if path.startswith("/configs/"):
        return PROJECT_ROOT / path.removeprefix("/")
    return Path(path)


def load_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_grouped_test_windows(
    frame: pd.DataFrame,
    *,
    feature_cols: list[str],
    label_col: str,
    time_steps: int,
    group_col: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Baut label-last-Testfenster ohne Schnitte ueber Sequenzgrenzen."""
    windows: list[np.ndarray] = []
    labels: list[int] = []
    test = frame[frame["split"].astype(str) == "test"]
    for _, group in test.groupby(group_col, sort=False):
        values = group[feature_cols].to_numpy(dtype=np.float32)
        targets = group[label_col].astype(int).to_numpy()
        for start in range(0, len(group) - time_steps + 1):
            end = start + time_steps
            windows.append(values[start:end])
            labels.append(int(targets[end - 1]))
    if not windows:
        return (
            np.empty((0, time_steps, len(feature_cols)), dtype=np.float32),
            np.array([], dtype=np.int32),
        )
    return np.stack(windows).astype(np.float32), np.array(labels, dtype=np.int32)


def prediction_metrics(expected: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(expected, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(expected, predicted)),
        "macro_f1": float(f1_score(expected, predicted, average="macro", zero_division=0)),
    }


def build_live_profile_windows(
    payloads_path: str | Path,
    *,
    idle_seeds_path: str | Path,
    feature_cols: list[str],
    expected_label_key: str,
    time_steps: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Rekonstruiert exakt das Rolling Window des Node-RED-KI-Flows."""
    seeds = json.loads(Path(idle_seeds_path).read_text(encoding="utf-8"))["rows"]
    payloads = [
        json.loads(line)
        for line in Path(payloads_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    def vector(state: dict[str, Any], empty_storage: int) -> list[float]:
        values: list[float] = []
        for feature in feature_cols:
            if feature.startswith("empty_storage_"):
                class_id = int(feature.rsplit("_", 1)[1])
                values.append(float(class_id == empty_storage))
            else:
                values.append(float(state[feature]))
        return values

    buffers: dict[str, list[list[float]]] = {}
    windows: list[np.ndarray] = []
    labels: list[int] = []
    phases: list[str] = []
    request_ids: list[str] = []
    for payload in payloads:
        source_id = str(payload["source_id"])
        empty_storage = int(payload["expected_empty_storage"])
        if source_id not in buffers:
            required = time_steps - 1
            if len(seeds) < required:
                raise ValueError(f"Profile needs {required} idle seeds, found {len(seeds)}")
            buffers[source_id] = [vector(seed, empty_storage) for seed in seeds[:required]]
        buffers[source_id].append(vector(payload, empty_storage))
        buffers[source_id] = buffers[source_id][-time_steps:]
        if len(buffers[source_id]) != time_steps:
            raise ValueError(f"Incomplete window for source {source_id}")
        windows.append(np.asarray(buffers[source_id], dtype=np.float32))
        labels.append(int(payload[expected_label_key]))
        phases.append(str(payload.get("trace_phase", "")))
        request_ids.append(str(payload["request_id"]))

    return (
        np.stack(windows).astype(np.float32),
        np.asarray(labels, dtype=np.int32),
        np.asarray(phases, dtype=object),
        request_ids,
    )


def profile_guard_mask(profile_name: str, phases: np.ndarray) -> np.ndarray:
    """Markiert alle sicherheitsrelevanten Zeilen eines virtuellen Profils."""
    if profile_name == "stationary_guard":
        return phases == "full_storage_attempt"
    if profile_name == "process_guard":
        return np.isin(
            phases,
            ["full_storage_process_guard_prefix", "full_storage_process_guard"],
        )
    return np.zeros(len(phases), dtype=bool)


def model_id(model_dir: Path, activation: dict[str, Any]) -> str:
    import hashlib

    digest = hashlib.sha256((model_dir / "model.keras").read_bytes()).hexdigest()[:12]
    return f"{activation['domain']}:{activation.get('trained_at', 'unknown')}:{digest}"


def load_model_bundle(model_dir: str | Path) -> tuple[Any, dict[str, Any], str]:
    import tensorflow as tf

    path = Path(model_dir)
    activation = json.loads((path / "activation.json").read_text(encoding="utf-8"))
    model = tf.keras.models.load_model(path / "model.keras")
    return model, activation, model_id(path, activation)


def predict_class_ids(model: Any, windows: np.ndarray, class_ids: list[int]) -> np.ndarray:
    probabilities = model.predict(windows, verbose=0)
    indices = np.argmax(probabilities, axis=1)
    return np.asarray(class_ids, dtype=np.int32)[indices]


def validate_contract(
    baseline_activation: dict[str, Any],
    candidate_activation: dict[str, Any],
    config: dict[str, Any],
) -> None:
    for key in ("domain", "time_steps", "feature_cols", "class_ids"):
        expected = config[key]
        if baseline_activation.get(key) != expected:
            raise ValueError(f"Baseline {key} differs from training config")
        if candidate_activation.get(key) != expected:
            raise ValueError(f"Candidate {key} differs from training config")


def evaluate_domain(
    *,
    domain: str,
    baseline_dir: str | Path,
    candidate_dir: str | Path,
    original_config_path: str | Path,
    guard_config_path: str | Path,
) -> dict[str, Any]:
    original_config = load_config(original_config_path)
    guard_config = load_config(guard_config_path)
    baseline_model, baseline_activation, baseline_id = load_model_bundle(baseline_dir)
    candidate_model, candidate_activation, candidate_id = load_model_bundle(candidate_dir)
    validate_contract(baseline_activation, candidate_activation, original_config)

    feature_cols = list(original_config["feature_cols"])
    label_col = str(original_config["label_col"])
    time_steps = int(original_config["time_steps"])
    group_col = str(original_config["group_col"])
    class_ids = [int(value) for value in original_config["class_ids"]]

    original_frame = pd.read_csv(resolve_repo_path(str(original_config["csv_path"])))
    original_windows, original_expected = build_grouped_test_windows(
        original_frame,
        feature_cols=feature_cols,
        label_col=label_col,
        time_steps=time_steps,
        group_col=group_col,
    )
    baseline_original = predict_class_ids(baseline_model, original_windows, class_ids)
    candidate_original = predict_class_ids(candidate_model, original_windows, class_ids)

    guard_frame = pd.read_csv(resolve_repo_path(str(guard_config["csv_path"])))
    guard_windows, guard_expected = build_grouped_test_windows(
        guard_frame,
        feature_cols=feature_cols,
        label_col=label_col,
        time_steps=time_steps,
        group_col=group_col,
    )
    empty_zero_idx = feature_cols.index("empty_storage_0")
    full_storage_mask = np.all(guard_windows[:, :, empty_zero_idx] == 1.0, axis=1)
    full_storage_windows = guard_windows[full_storage_mask]
    full_storage_expected = guard_expected[full_storage_mask]
    if len(full_storage_windows) == 0 or np.any(full_storage_expected != 0):
        raise ValueError("Guard test must contain full-storage windows with label 0 only")
    baseline_guard = predict_class_ids(baseline_model, full_storage_windows, class_ids)
    candidate_guard = predict_class_ids(candidate_model, full_storage_windows, class_ids)

    profile_results: dict[str, Any] = {}
    expected_label_key = f"expected_label_{domain.upper()}"
    for profile_name, payloads_path in PROFILE_PAYLOADS.items():
        profile_windows, profile_expected, phases, request_ids = build_live_profile_windows(
            payloads_path,
            idle_seeds_path=IDLE_SEEDS_PATH,
            feature_cols=feature_cols,
            expected_label_key=expected_label_key,
            time_steps=time_steps,
        )
        baseline_profile = predict_class_ids(baseline_model, profile_windows, class_ids)
        candidate_profile = predict_class_ids(candidate_model, profile_windows, class_ids)
        profile_result: dict[str, Any] = {
            "windows": int(len(profile_windows)),
            "baseline_metrics": prediction_metrics(profile_expected, baseline_profile),
            "candidate_metrics": prediction_metrics(profile_expected, candidate_profile),
            "changed_predictions": int(np.sum(baseline_profile != candidate_profile)),
            "candidate_mismatches": int(np.sum(candidate_profile != profile_expected)),
        }
        guard_mask = profile_guard_mask(profile_name, phases)
        if np.any(guard_mask):
            unsafe_indices = np.flatnonzero(guard_mask & (candidate_profile != 0))
            profile_result.update({
                "guard_windows": int(np.sum(guard_mask)),
                "baseline_unsafe": int(np.sum(guard_mask & (baseline_profile != 0))),
                "candidate_unsafe": int(len(unsafe_indices)),
                "first_candidate_unsafe_request_id": (
                    request_ids[int(unsafe_indices[0])] if len(unsafe_indices) else None
                ),
            })
        profile_results[profile_name] = profile_result

    result = {
        "domain": domain,
        "baseline_model_id": baseline_id,
        "candidate_model_id": candidate_id,
        "original_test": {
            "windows": int(len(original_windows)),
            "baseline_metrics": prediction_metrics(original_expected, baseline_original),
            "candidate_metrics": prediction_metrics(original_expected, candidate_original),
            "changed_predictions": int(np.sum(baseline_original != candidate_original)),
        },
        "full_storage_guard_test": {
            "windows": int(len(full_storage_windows)),
            "baseline_unsafe": int(np.sum(baseline_guard != 0)),
            "candidate_unsafe": int(np.sum(candidate_guard != 0)),
        },
        "virtual_profiles": profile_results,
    }
    candidate_metrics = result["original_test"]["candidate_metrics"]
    standard = result["virtual_profiles"]["standard"]
    stationary = result["virtual_profiles"]["stationary_guard"]
    process = result["virtual_profiles"]["process_guard"]
    result["strict_pass"] = bool(
        all(float(candidate_metrics[key]) == 1.0 for key in candidate_metrics)
        and result["original_test"]["changed_predictions"] == 0
        and result["full_storage_guard_test"]["candidate_unsafe"] == 0
        and standard["candidate_mismatches"] == 0
        and standard["changed_predictions"] == 0
        and stationary["guard_windows"] == 20
        and stationary["candidate_unsafe"] == 0
        and process["guard_windows"] == 171
        and process["candidate_unsafe"] == 0
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=tuple(DOMAIN_DEFAULTS), required=True)
    parser.add_argument("--baseline-dir")
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--original-config")
    parser.add_argument("--guard-config")
    parser.add_argument("--json-out")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    defaults = DOMAIN_DEFAULTS[args.domain]
    result = evaluate_domain(
        domain=args.domain,
        baseline_dir=args.baseline_dir or PROJECT_ROOT / f"model_registry/{args.domain}/latest",
        candidate_dir=args.candidate_dir,
        original_config_path=args.original_config or defaults["original_config"],
        guard_config_path=args.guard_config or defaults["guard_config"],
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    raise SystemExit(0 if result["strict_pass"] else 1)


if __name__ == "__main__":
    main()
