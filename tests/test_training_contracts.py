from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "plc"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_data_path(container_path: str) -> Path:
    prefix = "/data/plc/"
    if not container_path.startswith(prefix):
        raise AssertionError(f"Unexpected training path: {container_path}")
    return DATA_DIR / container_path.removeprefix(prefix)


class StorageTrainingContractTest(unittest.TestCase):
    def test_truth_table_is_complete_and_uses_first_free_slot_rule(self) -> None:
        config = load_json(ROOT / "configs" / "train_storage.json")
        frame = pd.read_csv(resolve_data_path(config["csv_path"]))
        features = config["feature_cols"]

        self.assertEqual(frame.shape, (512, 10))
        self.assertFalse(frame.isna().any().any())
        self.assertEqual(frame[features].drop_duplicates().shape[0], 512)
        self.assertEqual(sorted(frame[config["label_col"]].unique()), list(range(10)))

        def first_free(row: pd.Series) -> int:
            for slot, occupied in enumerate(row.tolist(), start=1):
                if int(occupied) == 0:
                    return slot
            return 0

        expected = frame[features].apply(first_free, axis=1)
        self.assertTrue(expected.equals(frame[config["label_col"]].astype(int)))


class LstmTrainingContractTest(unittest.TestCase):
    def test_active_and_original_datasets_match_deployment_contract(self) -> None:
        for domain in ("vgr", "hbw"):
            with self.subTest(domain=domain):
                config = load_json(ROOT / "configs" / f"train_{domain}.json")
                regression = load_json(
                    ROOT / "configs" / f"regression_{domain}_original.json"
                )
                activation = load_json(
                    ROOT / "model_registry" / domain / "latest" / "activation.json"
                )

                self.assertFalse(config["publish_latest"])
                self.assertEqual(config["time_steps"], 10)
                self.assertEqual(len(config["feature_cols"]), 29)
                self.assertEqual(config["feature_cols"], activation["feature_cols"])
                self.assertEqual(config["class_ids"], activation["class_ids"])
                self.assertEqual(regression["feature_cols"], config["feature_cols"])

                for dataset_config in (config, regression):
                    frame = pd.read_csv(resolve_data_path(dataset_config["csv_path"]))
                    required = [
                        "split",
                        dataset_config["group_col"],
                        *dataset_config["feature_cols"],
                        dataset_config["label_col"],
                    ]
                    self.assertFalse(frame[required].isna().any().any())
                    self.assertEqual(set(frame["split"]), {"train", "test"})
                    self.assertTrue(
                        set(frame[dataset_config["label_col"]].astype(int)).issubset(
                            set(dataset_config["class_ids"])
                        )
                    )
                    groups_by_split = frame.groupby("split")[
                        dataset_config["group_col"]
                    ].apply(set)
                    self.assertTrue(groups_by_split["train"].isdisjoint(groups_by_split["test"]))

    def test_guard_datasets_contain_full_storage_idle_examples(self) -> None:
        for domain in ("vgr", "hbw"):
            with self.subTest(domain=domain):
                config = load_json(ROOT / "configs" / f"train_{domain}.json")
                frame = pd.read_csv(resolve_data_path(config["csv_path"]))
                full = frame[frame["empty_storage_0"] == 1]
                self.assertGreaterEqual(len(full), 20)
                self.assertEqual(set(full[config["label_col"]].astype(int)), {0})


if __name__ == "__main__":
    unittest.main()
