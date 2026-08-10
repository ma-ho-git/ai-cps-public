"""Tests fuer den Modellvertragscheck vor einem NN-Austausch."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import check_model_compatibility as compatibility


EMPTY_FEATURES = [f"empty_storage_{index}" for index in range(10)]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_keras_model(path: Path, input_shape: list[int], output_units: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "config": {
            "layers": [
                {
                    "class_name": "InputLayer",
                    "config": {"batch_shape": [None, *input_shape]},
                },
                {
                    "class_name": "Dense",
                    "config": {"units": output_units},
                },
            ]
        }
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("config.json", json.dumps(config))


class ModelCompatibilityTests(unittest.TestCase):
    def create_fixture(self, root: Path) -> Path:
        current_dir = root / "model_registry/vgr/latest"
        candidate_dir = root / "candidate/vgr"
        activation = {
            "domain": "vgr",
            "time_steps": 10,
            "feature_cols": ["sensor", *EMPTY_FEATURES],
            "class_ids": [0, 101],
            "n_classes": 2,
            "input_shape": [10, 11],
            "cmd_map": {"0": "idle", "101": "start"},
        }
        write_json(current_dir / "activation.json", activation)
        write_json(candidate_dir / "activation.json", activation)
        write_json(candidate_dir / "metrics.json", {"accuracy": 1.0})
        write_keras_model(candidate_dir / "model.keras", [10, 11], 2)

        write_json(
            root / "scenarios/serve_ft_nns_external_broker/x86_64/node_red/config/topics.json",
            {"command_topics": {"vgr": {"0": "ai/vgr/cmd0", "101": "ai/vgr/cmd101"}}},
        )
        write_json(
            root
            / "scenarios/serve_ft_nns_external_broker/x86_64/node_red/config/idle_seed_templates.json",
            {"rows": [{"sensor": 0.0} for _ in range(9)]},
        )
        trace_path = (
            root
            / "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/live_plc_trace/payloads.jsonl"
        )
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text('{"sensor": 0}\n{"sensor": 1}\n', encoding="utf-8")
        field_map = {"sensor": "sensor"}
        field_map.update({f"filler_{index}": f"filler_{index}" for index in range(27)})
        write_json(root / "configs/plc_live_mqtt_adapter.json", {"field_map": field_map})
        return candidate_dir

    def test_current_models_are_compatible_with_both_runtime_modes(self) -> None:
        for domain in compatibility.DOMAINS:
            candidate = compatibility.PROJECT_ROOT / f"model_registry/{domain}/latest"
            for mode in ("virtual", "physical"):
                with self.subTest(domain=domain, mode=mode):
                    report = compatibility.analyze_model(
                        domain=domain,
                        candidate_dir=candidate,
                        mode=mode,
                    )
                    self.assertTrue(
                        report.compatible,
                        [check.detail for check in report.checks if not check.ok],
                    )
                    self.assertEqual(report.classification, "same_feature_contract")

    def test_virtual_mode_rejects_feature_missing_from_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = self.create_fixture(root)
            activation = compatibility.load_activation(candidate / "activation.json")
            activation["feature_cols"].insert(1, "new_sensor")
            activation["input_shape"] = [10, 12]
            write_json(candidate / "activation.json", activation)
            write_keras_model(candidate / "model.keras", [10, 12], 2)

            report = compatibility.analyze_model(
                domain="vgr", candidate_dir=candidate, mode="virtual", root=root
            )

        raw_check = next(item for item in report.checks if item.name == "raw-features:virtual")
        self.assertFalse(raw_check.ok)
        self.assertEqual(report.classification, "changed_feature_contract")

    def test_wrong_keras_input_shape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = self.create_fixture(root)
            write_keras_model(candidate / "model.keras", [10, 12], 2)

            report = compatibility.analyze_model(
                domain="vgr", candidate_dir=candidate, mode="virtual", root=root
            )

        shape_check = next(item for item in report.checks if item.name == "keras:input-shape")
        self.assertFalse(shape_check.ok)

    def test_smaller_feature_set_is_supported_when_required_one_hot_stays_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = self.create_fixture(root)
            activation = compatibility.load_activation(candidate / "activation.json")
            activation["feature_cols"] = list(EMPTY_FEATURES)
            activation["input_shape"] = [10, 10]
            write_json(candidate / "activation.json", activation)
            write_keras_model(candidate / "model.keras", [10, 10], 2)

            report = compatibility.analyze_model(
                domain="vgr", candidate_dir=candidate, mode="virtual", root=root
            )

        self.assertTrue(report.compatible)
        self.assertEqual(report.classification, "changed_feature_contract")
        self.assertEqual(report.feature_changes["removed"], ["sensor"])

    def test_reordered_feature_set_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = self.create_fixture(root)
            activation = compatibility.load_activation(candidate / "activation.json")
            activation["feature_cols"] = [*EMPTY_FEATURES, "sensor"]
            write_json(candidate / "activation.json", activation)

            report = compatibility.analyze_model(
                domain="vgr", candidate_dir=candidate, mode="virtual", root=root
            )

        self.assertTrue(report.compatible)
        self.assertTrue(report.feature_changes["reordered"])

    def test_time_steps_larger_than_seed_template_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = self.create_fixture(root)
            activation = compatibility.load_activation(candidate / "activation.json")
            activation["time_steps"] = 11
            activation["input_shape"] = [11, 11]
            write_json(candidate / "activation.json", activation)
            write_keras_model(candidate / "model.keras", [11, 11], 2)

            report = compatibility.analyze_model(
                domain="vgr", candidate_dir=candidate, mode="virtual", root=root
            )

        seed_check = next(item for item in report.checks if item.name == "idle-seeds:row-count")
        self.assertFalse(seed_check.ok)

    def test_missing_command_topic_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = self.create_fixture(root)
            activation = compatibility.load_activation(candidate / "activation.json")
            activation["class_ids"] = [0, 101, 102]
            activation["n_classes"] = 3
            activation["cmd_map"]["102"] = "next"
            write_json(candidate / "activation.json", activation)
            write_keras_model(candidate / "model.keras", [10, 11], 3)

            report = compatibility.analyze_model(
                domain="vgr", candidate_dir=candidate, mode="physical", root=root
            )

        topic_check = next(item for item in report.checks if item.name == "commands:topic-map")
        self.assertFalse(topic_check.ok)

    def test_duplicate_features_and_classes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = self.create_fixture(root)
            activation = compatibility.load_activation(candidate / "activation.json")
            activation["feature_cols"].append("sensor")
            activation["class_ids"].append(101)
            activation["input_shape"] = [10, 12]
            activation["n_classes"] = 3
            write_json(candidate / "activation.json", activation)
            write_keras_model(candidate / "model.keras", [10, 12], 3)

            report = compatibility.analyze_model(
                domain="vgr", candidate_dir=candidate, mode="virtual", root=root
            )

        self.assertFalse(next(item for item in report.checks if item.name == "features:unique").ok)
        self.assertFalse(next(item for item in report.checks if item.name == "classes:unique").ok)

    def test_cli_help_distinguishes_read_only_check_from_candidate_management(self) -> None:
        process = subprocess.run(
            ["python3", str(Path(compatibility.__file__)), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0)
        self.assertIn("read-only Einzelcheck", process.stdout)
        self.assertIn("manage_model_candidates.py", process.stdout)
        self.assertIn("28-Feld-Live-Vertrag", process.stdout)


if __name__ == "__main__":
    unittest.main()
