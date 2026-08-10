"""Prueft die dauerhafte Bootstrap-Vorlage gegen den aktiven Modellvertrag."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = (
    ROOT
    / "scenarios/serve_ft_nns_external_broker/x86_64/node_red/config/idle_seed_templates.json"
)


class IdleSeedTemplateTests(unittest.TestCase):
    def test_versioned_template_covers_lstm_process_features(self):
        stored = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        vgr = json.loads(
            (ROOT / "model_registry/vgr/latest/activation.json").read_text(encoding="utf-8")
        )
        process_features = [
            feature
            for feature in vgr["feature_cols"]
            if not feature.startswith("empty_storage_")
        ]

        self.assertEqual(stored["row_count"], 9)
        self.assertEqual(stored["process_feature_cols"], process_features)
        self.assertEqual(len(stored["rows"]), 9)
        self.assertTrue(
            all(list(row) == stored["process_feature_cols"] for row in stored["rows"])
        )
        self.assertTrue(all(len(row) == 19 for row in stored["rows"]))
        self.assertFalse(any(key.startswith("storage_slot_") for key in stored["rows"][0]))


if __name__ == "__main__":
    unittest.main()
