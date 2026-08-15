"""Prueft einen Node-RED-Report des Vollspeicher-Grenzfallprofils."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


EXPECTED_ROWS = 157
EXPECTED_ATTEMPTS = 20
MODULES = ("vgr", "hbw", "mpo", "sld")


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_report(report_dir: str | Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    path = Path(report_dir)
    run_summary_path = path / "run_summary.json"
    summary_path = path / "summary.csv"
    if not run_summary_path.is_file() or not summary_path.is_file():
        raise ValueError(f"Report requires run_summary.json and summary.csv: {path}")
    run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    with summary_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return run_summary, rows


def technical_run_errors(
    run_summary: dict[str, Any],
    rows: list[dict[str, str]],
    special_rows: list[dict[str, str]],
    *,
    expected_rows: int,
    expected_special_rows: int,
    special_name: str,
) -> list[str]:
    """Prueft Zaehler und technische Fehler eines Simulationslaufs."""
    errors: list[str] = []
    if len(rows) != expected_rows or as_int(run_summary.get("rows_completed")) != expected_rows:
        errors.append(f"expected {expected_rows} completed rows")
    if len(special_rows) != expected_special_rows:
        errors.append(f"expected {expected_special_rows} {special_name}")
    if as_int(run_summary.get("faults")) != 0:
        errors.append("run contains faults")
    if as_int(run_summary.get("control_published_rows")) != expected_rows:
        errors.append("not every row published a complete command set")
    if as_int(run_summary.get("control_published_commands")) != expected_rows * 4:
        errors.append("regular command count differs from four commands per row")
    if as_int(run_summary.get("storage_matches_vgr")) != expected_rows:
        errors.append("storage results do not match all expected states")
    if as_int(run_summary.get("storage_matches_hbw")) != expected_rows:
        errors.append("storage results do not match all expected states")
    if any(as_bool(row.get("timeout")) or row.get("error") for row in rows):
        errors.append("summary contains timeout or error rows")
    return errors


def guard_row_errors(rows: list[dict[str, str]], *, row_name: str) -> list[str]:
    """Prueft Vollspeicherwert, Command-Set und Modulzaehler."""
    for row in rows:
        if as_int(row.get("expected_empty_storage"), -1) != 0:
            return [f"{row_name} does not expect full storage"]
        if as_int(row.get("vgr_storage_pred"), -1) != 0:
            return ["storage model did not predict full storage"]
        if not as_bool(row.get("control_published")) or not as_bool(row.get("control_command_set_complete")):
            return [f"{row_name} has an incomplete command set"]
        for module in MODULES:
            if as_int(row.get(f"job_sent_{module}"), -1) != as_int(row.get(f"job_accepted_{module}"), -2):
                return [f"{module} sent/accepted job counters differ"]
    return []


def unsafe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row for row in rows
        if as_int(row.get("predicted_label_VGR")) != 0
        or as_int(row.get("predicted_label_HBW")) != 0
    ]


def first_unsafe_attempt(
    rows: list[dict[str, str]], run_summary: dict[str, Any]
) -> dict[str, Any] | None:
    if not rows:
        return None
    row = rows[0]
    model_ids = {
        domain: row.get(f"{domain}_model_id") or run_summary.get("model_ids", {}).get(domain)
        for domain in ("vgr", "hbw")
    }
    return {
        "row_index": as_int(row.get("row_index")),
        "attempt_repeat_idx": as_int(row.get("attempt_repeat_idx")),
        "vgr_cmd": as_int(row.get("predicted_label_VGR")),
        "vgr_topic": row.get("control_vgr_topic", ""),
        "vgr_confidence": as_float(row.get("vgr_confidence")),
        "hbw_cmd": as_int(row.get("predicted_label_HBW")),
        "hbw_topic": row.get("control_hbw_topic", ""),
        "hbw_confidence": as_float(row.get("hbw_confidence")),
        "model_ids": model_ids,
    }


def analyze_report(report_dir: str | Path) -> dict[str, Any]:
    """Trennt technische Laufguete von der fachlichen Vollspeicherverletzung."""
    run_summary, rows = load_report(report_dir)
    attempts = [row for row in rows if row.get("trace_phase") == "full_storage_attempt"]
    errors = technical_run_errors(
        run_summary,
        rows,
        attempts,
        expected_rows=EXPECTED_ROWS,
        expected_special_rows=EXPECTED_ATTEMPTS,
        special_name="full-storage attempt rows",
    )
    errors.extend(guard_row_errors(attempts, row_name="attempt row"))
    unsafe = unsafe_rows(attempts)

    return {
        "report_dir": str(Path(report_dir)),
        "technical_ok": not errors,
        "technical_errors": errors,
        "rows_completed": len(rows),
        "attempt_rows": len(attempts),
        "unsafe_rows": len(unsafe),
        "first_unsafe": first_unsafe_attempt(unsafe, run_summary),
        "model_ids": run_summary.get("model_ids", {}),
    }


def expectation_satisfied(analysis: dict[str, Any], expected: str) -> tuple[bool, str]:
    if not analysis["technical_ok"]:
        return False, "technical acceptance failed"
    unsafe_rows = int(analysis["unsafe_rows"])
    if expected == "reproduced":
        return (unsafe_rows > 0, "unsafe full-storage command reproduced" if unsafe_rows else "no unsafe command observed")
    return (unsafe_rows == 0, "all full-storage attempts remained idle" if not unsafe_rows else "unsafe command observed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--expect", choices=("reproduced", "safe"), default="safe")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        analysis = analyze_report(args.report_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"[FULL-STORAGE][ERROR] {error}") from error
    passed, message = expectation_satisfied(analysis, args.expect)
    if args.as_json:
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
    else:
        print(
            f"[FULL-STORAGE] rows={analysis['rows_completed']} attempts={analysis['attempt_rows']} "
            f"unsafe={analysis['unsafe_rows']} technical_ok={analysis['technical_ok']}"
        )
        if analysis["first_unsafe"]:
            first = analysis["first_unsafe"]
            print(
                "[FULL-STORAGE] first unsafe: "
                f"repeat={first['attempt_repeat_idx']} "
                f"VGR={first['vgr_cmd']} p={first['vgr_confidence']} "
                f"model={first['model_ids']['vgr']} "
                f"HBW={first['hbw_cmd']} p={first['hbw_confidence']} "
                f"model={first['model_ids']['hbw']}"
            )
        for error in analysis["technical_errors"]:
            print(f"[FULL-STORAGE][ERROR] {error}")
        print(f"[FULL-STORAGE] expectation={args.expect}: {message}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
