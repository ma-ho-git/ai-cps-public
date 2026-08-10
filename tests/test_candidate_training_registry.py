from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_training_module(domain: str):
    """Laedt Registry-Helfer auch im schlanken CI-Job ohne TensorFlow."""
    path = ROOT / "training" / domain / "train.py"
    spec = importlib.util.spec_from_file_location(f"candidate_training_{domain}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    tensorflow_stubbed = "tensorflow" not in sys.modules and importlib.util.find_spec(
        "tensorflow"
    ) is None
    if tensorflow_stubbed:
        tensorflow = types.ModuleType("tensorflow")
        tensorflow.keras = types.SimpleNamespace(
            Model=object,
            layers=types.SimpleNamespace(Normalization=object),
        )
        sys.modules["tensorflow"] = tensorflow
    try:
        spec.loader.exec_module(module)
    finally:
        if tensorflow_stubbed:
            sys.modules.pop("tensorflow", None)
    return module


class CandidateTrainingRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.modules = {
            domain: load_training_module(domain)
            for domain in ("storage", "vgr", "hbw")
        }

    def test_candidate_mode_never_changes_latest(self) -> None:
        for domain, module in self.modules.items():
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as tmp:
                out_base = Path(tmp) / domain
                latest = out_base / "latest"
                version = out_base / "versions" / "candidate"
                latest.mkdir(parents=True)
                version.mkdir(parents=True)
                (latest / "model.keras").write_bytes(b"baseline")
                (version / "model.keras").write_bytes(b"candidate")

                result = module.finalize_model_version(
                    str(version), str(out_base), "2026-08-05_120000", False
                )

                self.assertIsNone(result)
                self.assertEqual((latest / "model.keras").read_bytes(), b"baseline")
                self.assertEqual((version / "model.keras").read_bytes(), b"candidate")
                self.assertEqual(list((out_base / "versions").iterdir()), [version])

    def test_default_mode_still_updates_latest_and_keeps_version(self) -> None:
        for domain, module in self.modules.items():
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as tmp:
                out_base = Path(tmp) / domain
                latest = out_base / "latest"
                version = out_base / "versions" / "candidate"
                latest.mkdir(parents=True)
                version.mkdir(parents=True)
                (latest / "model.keras").write_bytes(b"baseline")
                (version / "model.keras").write_bytes(b"candidate")

                result = module.finalize_model_version(
                    str(version), str(out_base), "2026-08-05_120000", True
                )

                self.assertEqual(result, str(latest))
                self.assertEqual((latest / "model.keras").read_bytes(), b"candidate")
                self.assertEqual((version / "model.keras").read_bytes(), b"candidate")

    def test_active_training_configs_are_safe_candidates(self) -> None:
        expected_datasets = {
            "storage": "training_empty_storage_truth_table.csv",
            "vgr": "_full_storage_guard_balanced.csv",
            "hbw": "_full_storage_guard.csv",
        }
        for domain in ("storage", "vgr", "hbw"):
            with self.subTest(domain=domain):
                active = json.loads((ROOT / "configs" / f"train_{domain}.json").read_text())
                self.assertFalse(active["publish_latest"])
                self.assertTrue(active["experiment_name"])
                self.assertTrue(active["csv_path"].endswith(expected_datasets[domain]))

    def test_compose_has_exactly_three_unambiguous_training_jobs(self) -> None:
        compose = (ROOT / "docker-compose.train.yml").read_text()
        for domain in ("storage", "vgr", "hbw"):
            self.assertIn(f"  train_{domain}:\n", compose)
            self.assertIn(f"/configs/train_{domain}.json", compose)
        self.assertNotIn("train_vgr_full_storage_guard", compose)
        self.assertNotIn("train_hbw_full_storage_guard", compose)

    def test_original_regression_configs_match_active_model_contracts(self) -> None:
        for domain in ("vgr", "hbw"):
            with self.subTest(domain=domain):
                active = json.loads((ROOT / "configs" / f"train_{domain}.json").read_text())
                regression = json.loads(
                    (ROOT / "configs" / f"regression_{domain}_original.json").read_text()
                )
                self.assertTrue(regression["csv_path"].endswith("_onehot.csv"))
                for key, value in regression.items():
                    if key == "csv_path":
                        continue
                    self.assertEqual(active[key], value, key)


if __name__ == "__main__":
    unittest.main()
