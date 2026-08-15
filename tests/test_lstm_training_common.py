"""Vertraege der gemeinsam genutzten LSTM-Trainingshelfer."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from training import lstm_common


class FixedPredictionModel:
    def __init__(self, probabilities: list[list[float]]) -> None:
        self.probabilities = np.asarray(probabilities, dtype=np.float32)

    def predict(self, _values: np.ndarray, verbose: int = 0) -> np.ndarray:
        return self.probabilities


class LstmTrainingCommonTests(unittest.TestCase):
    def test_grouped_windows_keep_sequence_boundaries(self) -> None:
        frame = pd.DataFrame({
            "sequence": ["a"] * 3 + ["b"] * 3,
            "feature": [1, 2, 3, 10, 11, 12],
            "label": [0, 0, 101, 0, 0, 102],
        })
        windows, dense, commands, groups = lstm_common.make_windows_label_last_grouped(
            frame, ["feature"], "label", 3, {0: 0, 101: 1, 102: 2}, "sequence"
        )
        self.assertEqual(windows[:, :, 0].tolist(), [[1, 2, 3], [10, 11, 12]])
        self.assertEqual(dense.tolist(), [1, 2])
        self.assertEqual(commands.tolist(), [101, 102])
        self.assertEqual(groups.tolist(), ["a", "b"])

    def test_group_split_is_deterministic_and_disjoint(self) -> None:
        values = np.arange(8, dtype=np.float32).reshape(4, 2, 1)
        labels = np.array([0, 1, 0, 1], dtype=np.int32)
        groups = np.array(["a", "b", "c", "d"], dtype=object)
        first = lstm_common.train_validation_split_by_group(values, labels, groups, 0.25, 42)
        second = lstm_common.train_validation_split_by_group(values, labels, groups, 0.25, 42)
        self.assertEqual(first[5].tolist(), second[5].tolist())
        self.assertTrue(set(first[4]).isdisjoint(set(first[5])))

    def test_metrics_use_real_command_ids(self) -> None:
        model = FixedPredictionModel([[0.9, 0.1], [0.2, 0.8]])
        values = np.zeros((2, 2, 1), dtype=np.float32)
        metrics = lstm_common.evaluate_model(
            model, values, np.array([0, 1], dtype=np.int32), [0, 101]
        )
        self.assertEqual(metrics["accuracy"], 1.0)
        self.assertEqual(metrics["balanced_accuracy"], 1.0)
        self.assertEqual(metrics["macro_f1"], 1.0)

    def test_class_weights_keep_unseen_classes_neutral(self) -> None:
        weights = lstm_common.compute_balanced_class_weight(
            np.array([0, 0, 1], dtype=np.int32), 3
        )
        self.assertEqual(weights[2], 1.0)
        self.assertGreater(weights[1], weights[0])


if __name__ == "__main__":
    unittest.main()
