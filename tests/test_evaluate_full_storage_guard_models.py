from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from tools.evaluate_full_storage_guard_models import (
    build_live_profile_windows,
    build_grouped_test_windows,
    prediction_metrics,
    profile_guard_mask,
)


class EvaluateFullStorageGuardModelsTests(unittest.TestCase):
    def test_grouped_windows_never_cross_sequence_boundaries(self) -> None:
        frame = pd.DataFrame({
            "split": ["test"] * 6,
            "sequence_id": ["a"] * 3 + ["b"] * 3,
            "feature": [1, 2, 3, 10, 11, 12],
            "label": [0, 0, 1, 0, 0, 2],
        })
        windows, labels = build_grouped_test_windows(
            frame,
            feature_cols=["feature"],
            label_col="label",
            time_steps=2,
            group_col="sequence_id",
        )
        self.assertEqual(windows.shape, (4, 2, 1))
        self.assertEqual(labels.tolist(), [0, 1, 0, 2])
        self.assertNotIn([3.0, 10.0], windows[:, :, 0].tolist())

    def test_prediction_metrics_are_exact_for_identical_labels(self) -> None:
        expected = np.array([0, 1, 2, 2], dtype=np.int32)
        metrics = prediction_metrics(expected, expected.copy())
        self.assertEqual(metrics, {
            "accuracy": 1.0,
            "balanced_accuracy": 1.0,
            "macro_f1": 1.0,
        })

    def test_live_profile_windows_bootstrap_and_roll_per_source(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        seeds = {"rows": [{"sensor": 0.0}, {"sensor": 0.0}]}
        payloads = [
            {
                "request_id": "a-1",
                "source_id": "a",
                "sensor": 1.0,
                "expected_empty_storage": 2,
                "expected_label_VGR": 101,
                "trace_phase": "process",
            },
            {
                "request_id": "a-2",
                "source_id": "a",
                "sensor": 2.0,
                "expected_empty_storage": 3,
                "expected_label_VGR": 102,
                "trace_phase": "process",
            },
            {
                "request_id": "b-1",
                "source_id": "b",
                "sensor": 3.0,
                "expected_empty_storage": 4,
                "expected_label_VGR": 103,
                "trace_phase": "process",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed_path = root / "seeds.json"
            payload_path = root / "payloads.jsonl"
            seed_path.write_text(json.dumps(seeds))
            payload_path.write_text("\n".join(json.dumps(row) for row in payloads))
            windows, labels, phases, request_ids = build_live_profile_windows(
                payload_path,
                idle_seeds_path=seed_path,
                feature_cols=["sensor", "empty_storage_2", "empty_storage_3", "empty_storage_4"],
                expected_label_key="expected_label_VGR",
                time_steps=3,
            )

        self.assertEqual(windows.shape, (3, 3, 4))
        self.assertEqual(labels.tolist(), [101, 102, 103])
        self.assertEqual(phases.tolist(), ["process", "process", "process"])
        self.assertEqual(request_ids, ["a-1", "a-2", "b-1"])
        self.assertEqual(windows[0, :, 0].tolist(), [0.0, 0.0, 1.0])
        self.assertEqual(windows[1, :, 0].tolist(), [0.0, 1.0, 2.0])
        self.assertEqual(windows[2, :, 0].tolist(), [0.0, 0.0, 3.0])
        self.assertEqual(windows[0, :, 1].tolist(), [1.0, 1.0, 1.0])

    def test_process_guard_mask_includes_prefix_and_process_rows(self) -> None:
        phases = np.array([
            "process",
            "full_storage_process_guard_prefix",
            "full_storage_process_guard",
        ], dtype=object)
        self.assertEqual(
            profile_guard_mask("process_guard", phases).tolist(),
            [False, True, True],
        )


if __name__ == "__main__":
    unittest.main()
