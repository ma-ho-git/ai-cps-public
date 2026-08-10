"""Tests fuer die Auswertung prozessartiger Vollspeicher-Regressionen."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.analyze_full_storage_process_guard_run import analyze_report, expectation_satisfied


FIELDS = [
    "row_index", "trace_phase", "guard_episode_idx", "guard_process_step_idx",
    "expected_empty_storage", "vgr_storage_pred", "predicted_label_VGR", "vgr_confidence",
    "predicted_label_HBW", "hbw_confidence", "control_published",
    "control_command_set_complete", "control_vgr_topic", "control_hbw_topic",
    "job_sent_vgr", "job_sent_hbw", "job_sent_mpo", "job_sent_sld",
    "job_accepted_vgr", "job_accepted_hbw", "job_accepted_mpo", "job_accepted_sld",
    "timeout", "error",
]


class AnalyzeFullStorageProcessGuardRunTests(unittest.TestCase):
    def make_report(self, *, unsafe: bool) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        report_dir = Path(temp_dir.name)
        summary = {
            "rows_completed": 308,
            "control_published_rows": 308,
            "control_published_commands": 1232,
            "faults": 0,
            "storage_matches_vgr": 308,
            "storage_matches_hbw": 308,
            "model_ids": {"storage": "s", "vgr": "v", "hbw": "h"},
        }
        (report_dir / "run_summary.json").write_text(json.dumps(summary))
        with (report_dir / "summary.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for row_index in range(137):
                writer.writerow({"row_index": row_index, "trace_phase": "process", "timeout": "false"})
            for guard_index in range(171):
                episode_idx = guard_index // 19 + 1
                within_episode = guard_index % 19
                process_step = within_episode - 9
                active = unsafe and episode_idx == 1 and process_step == 2
                count = 138 + guard_index
                writer.writerow({
                    "row_index": 137 + guard_index,
                    "trace_phase": (
                        "full_storage_process_guard_prefix"
                        if within_episode < 9 else "full_storage_process_guard"
                    ),
                    "guard_episode_idx": episode_idx,
                    "guard_process_step_idx": process_step if process_step >= 0 else "",
                    "expected_empty_storage": 0,
                    "vgr_storage_pred": 0,
                    "predicted_label_VGR": 0,
                    "vgr_confidence": 0.99,
                    "predicted_label_HBW": 102 if active else 0,
                    "hbw_confidence": 0.8,
                    "control_published": "true",
                    "control_command_set_complete": "true",
                    "control_vgr_topic": "ai/vgr/cmd0",
                    "control_hbw_topic": "ai/hbw/cmd102" if active else "ai/hbw/cmd000",
                    "job_sent_vgr": count,
                    "job_sent_hbw": count,
                    "job_sent_mpo": count,
                    "job_sent_sld": count,
                    "job_accepted_vgr": count,
                    "job_accepted_hbw": count,
                    "job_accepted_mpo": count,
                    "job_accepted_sld": count,
                    "timeout": "false",
                    "error": "",
                })
        return report_dir

    def test_reproduced_expectation_finds_process_command(self) -> None:
        analysis = analyze_report(self.make_report(unsafe=True))
        self.assertTrue(analysis["technical_ok"])
        self.assertEqual(analysis["guard_rows"], 171)
        self.assertEqual(analysis["unsafe_rows"], 1)
        self.assertEqual(analysis["vgr_unsafe_rows"], 0)
        self.assertEqual(analysis["hbw_unsafe_rows"], 1)
        self.assertEqual(analysis["first_unsafe"]["guard_episode_idx"], 1)
        self.assertEqual(analysis["first_unsafe"]["guard_process_step_idx"], 2)
        self.assertTrue(expectation_satisfied(analysis, "reproduced")[0])
        self.assertFalse(expectation_satisfied(analysis, "safe")[0])

    def test_safe_expectation_requires_all_guard_rows_idle(self) -> None:
        analysis = analyze_report(self.make_report(unsafe=False))
        self.assertTrue(analysis["technical_ok"])
        self.assertEqual(analysis["unsafe_rows"], 0)
        self.assertTrue(expectation_satisfied(analysis, "safe")[0])
        self.assertFalse(expectation_satisfied(analysis, "reproduced")[0])


if __name__ == "__main__":
    unittest.main()
