"""Tests fuer die VGR-Windowing-Regeln.

Hier geht es nicht um Modellqualitaet, sondern um saubere Sequenzgrenzen.
Wenn Fenster ueber `sequence_id`-Grenzen laufen, wuerde das Training spaeter
kuenstliche Speicher- oder Prozesswechsel sehen.
"""

import unittest

import numpy as np
import pandas as pd

from training.vgr import train


class VgrWindowingTests(unittest.TestCase):
    """Sichert die gruppierten Windowing- und Validation-Hilfsfunktionen ab."""

    def test_grouped_windows_do_not_cross_sequence_boundaries(self):
        """Fenster werden innerhalb einer Sequenz gebildet, nicht quer darueber."""
        df = pd.DataFrame(
            {
                "sequence_id": ["a", "a", "a", "b", "b", "b"],
                "feature": [1, 2, 3, 4, 5, 6],
                "label_VGR": [0, 101, 102, 0, 104, 105],
            }
        )

        X, y_idx, y_ids, groups = train.make_windows_label_last_grouped(
            df,
            feature_cols=["feature"],
            label_col="label_VGR",
            time_steps=3,
            class_to_index={0: 0, 101: 1, 102: 2, 104: 3, 105: 4},
            group_col="sequence_id",
        )

        self.assertEqual(X.shape, (2, 3, 1))
        np.testing.assert_array_equal(y_ids, np.array([102, 105], dtype=np.int32))
        np.testing.assert_array_equal(y_idx, np.array([2, 4], dtype=np.int32))
        self.assertEqual(groups.tolist(), ["a", "b"])

    def test_group_validation_split_holds_out_complete_sequences(self):
        """Validation haelt komplette Sequenzen zurueck statt einzelne Fenster."""
        X = np.arange(5 * 2 * 1, dtype=np.float32).reshape(5, 2, 1)
        y = np.array([0, 1, 0, 1, 0], dtype=np.int32)
        groups = np.array(["g1", "g2", "g3", "g4", "g5"], dtype=object)

        X_fit, X_val, y_fit, y_val, groups_fit, groups_val = train.train_validation_split_by_group(
            X,
            y,
            groups,
            validation_fraction=0.2,
            seed=42,
        )

        self.assertEqual(len(X_fit), 4)
        self.assertEqual(len(X_val), 1)
        self.assertEqual(len(y_fit), 4)
        self.assertEqual(len(y_val), 1)
        self.assertTrue(set(groups_fit).isdisjoint(set(groups_val)))
        self.assertEqual(len(set(groups_val)), 1)


if __name__ == "__main__":
    unittest.main()
