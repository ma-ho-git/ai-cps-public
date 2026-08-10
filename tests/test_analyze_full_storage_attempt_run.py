"""Tests fuer die Auswertung des virtuellen Vollspeicher-Grenzfalls."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.analyze_full_storage_attempt_run import analyze_report, expectation_satisfied


FIELDS = [
    "row_index",
    "trace_phase",
    "attempt_repeat_idx",
    "expected_empty_storage",
    "vgr_storage_pred",
    "expected_label_VGR",
    "predicted_label_VGR",
    "vgr_confidence",
    "expected_label_HBW",
    "predicted_label_HBW",
    "hbw_confidence",
    "control_published",
    "control_command_set_complete",
    "control_vgr_topic",
    "control_hbw_topic",
    "job_sent_vgr",
    "job_sent_hbw",
    "job_sent_mpo",
    "job_sent_sld",
    "job_accepted_vgr",
    "job_accepted_hbw",
    "job_accepted_mpo",
    "job_accepted_sld",
    "timeout",
    "error",
]


class AnalyzeFullStorageAttemptRunTests(unittest.TestCase):
    def make_report(self, *, unsafe: bool) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        report_dir = Path(temp_dir.name)
        summary = {
            "rows_completed": 157,
            "control_published_rows": 157,
            "control_published_commands": 628,
            "faults": 0,
            "storage_matches_vgr": 157,
            "storage_matches_hbw": 157,
            "model_ids": {"storage": "s", "vgr": "v", "hbw": "h"},
        }
        (report_dir / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        with (report_dir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for row_index in range(137):
                writer.writerow({
                    "row_index": row_index,
                    "trace_phase": "process",
                    "timeout": "false",
                    "error": "",
                })
            for repeat_idx in range(1, 21):
                active = unsafe and repeat_idx >= 2
                writer.writerow({
                    "row_index": 136 + repeat_idx,
                    "trace_phase": "full_storage_attempt",
                    "attempt_repeat_idx": repeat_idx,
                    "expected_empty_storage": 0,
                    "vgr_storage_pred": 0,
                    "expected_label_VGR": 0,
                    "predicted_label_VGR": 101 if active else 0,
                    "vgr_confidence": 0.88 if active else 0.99,
                    "expected_label_HBW": 0,
                    "predicted_label_HBW": 0,
                    "hbw_confidence": 0.95,
                    "control_published": "true",
                    "control_command_set_complete": "true",
                    "control_vgr_topic": "ai/vgr/cmd101" if active else "ai/vgr/cmd0",
                    "control_hbw_topic": "ai/hbw/cmd000",
                    "job_sent_vgr": 138 + repeat_idx,
                    "job_sent_hbw": 138 + repeat_idx,
                    "job_sent_mpo": 138 + repeat_idx,
                    "job_sent_sld": 138 + repeat_idx,
                    "job_accepted_vgr": 138 + repeat_idx,
                    "job_accepted_hbw": 138 + repeat_idx,
                    "job_accepted_mpo": 138 + repeat_idx,
                    "job_accepted_sld": 138 + repeat_idx,
                    "timeout": "false",
                    "error": "",
                })
        return report_dir

    def test_reproduced_expectation_identifies_first_active_command(self) -> None:
        analysis = analyze_report(self.make_report(unsafe=True))

        self.assertTrue(analysis["technical_ok"])
        self.assertEqual(analysis["attempt_rows"], 20)
        self.assertEqual(analysis["unsafe_rows"], 19)
        self.assertEqual(analysis["first_unsafe"]["attempt_repeat_idx"], 2)
        self.assertEqual(analysis["first_unsafe"]["vgr_cmd"], 101)
        self.assertEqual(analysis["first_unsafe"]["model_ids"]["vgr"], "v")
        self.assertTrue(expectation_satisfied(analysis, "reproduced")[0])
        self.assertFalse(expectation_satisfied(analysis, "safe")[0])

    def test_safe_expectation_accepts_only_idle_predictions(self) -> None:
        analysis = analyze_report(self.make_report(unsafe=False))

        self.assertTrue(analysis["technical_ok"])
        self.assertEqual(analysis["unsafe_rows"], 0)
        self.assertTrue(expectation_satisfied(analysis, "safe")[0])
        self.assertFalse(expectation_satisfied(analysis, "reproduced")[0])


if __name__ == "__main__":
    unittest.main()
