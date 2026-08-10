"""Tests fuer den Vergleich zweier Modelllaeufe auf identischem Trace."""

from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import compare_model_runs as comparison


def write_run(
    path: Path,
    *,
    model_id: str,
    predictions: list[int],
    expected: list[int],
    faults: int = 0,
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "run_summary.json").write_text(
        json.dumps(
            {
                "completed": faults == 0,
                "rows_completed": len(predictions),
                "faults": faults,
                "model_ids": {"vgr": model_id},
            }
        ),
        encoding="utf-8",
    )
    fields = [
        "request_id_base",
        "source_id",
        "expected_label_VGR",
        "predicted_label_VGR",
        "vgr_match",
        "vgr_latency_s",
        "timeout",
        "error",
        "control_vgr_cmd",
        "control_hbw_cmd",
        "control_mpo_cmd",
        "control_sld_cmd",
    ]
    with (path / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, (actual, target) in enumerate(zip(predictions, expected, strict=True)):
            writer.writerow(
                {
                    "request_id_base": f"r{index}",
                    "source_id": "trace-1",
                    "expected_label_VGR": target,
                    "predicted_label_VGR": actual,
                    "vgr_match": actual == target,
                    "vgr_latency_s": 0.1 + index * 0.01,
                    "timeout": False,
                    "error": "",
                    "control_vgr_cmd": actual,
                    "control_hbw_cmd": 0,
                    "control_mpo_cmd": 0,
                    "control_sld_cmd": 0,
                }
            )


class CompareModelRunsTests(unittest.TestCase):
    def test_reports_improvements_regressions_commands_and_latency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline = root / "baseline"
            candidate = root / "candidate"
            write_run(
                baseline,
                model_id="vgr:baseline",
                predictions=[0, 0, 101],
                expected=[0, 101, 101],
            )
            write_run(
                candidate,
                model_id="vgr:candidate",
                predictions=[0, 101, 0],
                expected=[0, 101, 101],
            )

            result = comparison.compare_runs(
                domain="vgr", baseline=baseline, candidate=candidate
            )

        self.assertEqual(result["quality"]["changed_predictions"], 2)
        self.assertEqual(result["quality"]["improvements"], 1)
        self.assertEqual(result["quality"]["regressions"], 1)
        self.assertFalse(result["commands"]["identical"])
        self.assertEqual(result["latency"]["candidate"]["count"], 3)

    def test_rejects_non_identical_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline = root / "baseline"
            candidate = root / "candidate"
            write_run(baseline, model_id="a", predictions=[0], expected=[0])
            write_run(candidate, model_id="b", predictions=[0, 0], expected=[0, 0])

            with self.assertRaisesRegex(comparison.ComparisonError, "nicht dieselben"):
                comparison.compare_runs(domain="vgr", baseline=baseline, candidate=candidate)

    def test_cli_help_names_trace_quality_fault_and_latency_comparison(self) -> None:
        process = subprocess.run(
            ["python3", str(Path(comparison.__file__)), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0)
        for text in ("request_id_base", "Treffer", "Faults", "Timeouts", "p95-Latenz"):
            self.assertIn(text, process.stdout)


if __name__ == "__main__":
    unittest.main()
