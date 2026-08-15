"""Prueft einen Node-RED-Report mit prozessartigen Vollspeicherzustaenden."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.analyze_full_storage_attempt_run import (  # noqa: E402
    as_float,
    as_int,
    guard_row_errors,
    load_report,
    technical_run_errors,
    unsafe_rows,
)


EXPECTED_ROWS = 308
EXPECTED_GUARD_ROWS = 171
GUARD_PHASES = {"full_storage_process_guard_prefix", "full_storage_process_guard"}
DEFAULT_MANIFEST = (
    PROJECT_ROOT
    / "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/"
    "live_plc_full_storage_process_guard/manifest.csv"
)


def enrich_rows_from_manifest(
    rows: list[dict[str, str]], manifest_path: str | Path
) -> list[dict[str, str]]:
    """Ergaenzt Metadaten alter Reports ueber die eindeutige Request-ID."""
    with Path(manifest_path).open(encoding="utf-8", newline="") as handle:
        manifest = {
            row["request_id"]: row
            for row in csv.DictReader(handle)
        }
    enriched: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        metadata = manifest.get(item.get("request_id_base", ""), {})
        for key, value in metadata.items():
            if key == "request_id":
                continue
            if item.get(key) in (None, ""):
                item[key] = value
        enriched.append(item)
    return enriched


def analyze_report(
    report_dir: str | Path,
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    """Bewertet technische Vollstaendigkeit und aktive Guard-Commands getrennt."""
    run_summary, rows = load_report(report_dir)
    rows = enrich_rows_from_manifest(rows, manifest_path)
    guard_rows = [row for row in rows if row.get("trace_phase") in GUARD_PHASES]
    technical_errors = technical_run_errors(
        run_summary,
        rows,
        guard_rows,
        expected_rows=EXPECTED_ROWS,
        expected_special_rows=EXPECTED_GUARD_ROWS,
        special_name="process guard rows",
    )
    technical_errors.extend(guard_row_errors(guard_rows, row_name="guard row"))

    unsafe_vgr = [row for row in guard_rows if as_int(row.get("predicted_label_VGR")) != 0]
    unsafe_hbw = [row for row in guard_rows if as_int(row.get("predicted_label_HBW")) != 0]
    unsafe = unsafe_rows(guard_rows)

    return {
        "report_dir": str(Path(report_dir)),
        "technical_ok": not technical_errors,
        "technical_errors": technical_errors,
        "rows_completed": len(rows),
        "guard_rows": len(guard_rows),
        "unsafe_rows": len(unsafe),
        "vgr_unsafe_rows": len(unsafe_vgr),
        "hbw_unsafe_rows": len(unsafe_hbw),
        "first_unsafe": first_unsafe_process(unsafe, run_summary),
        "model_ids": run_summary.get("model_ids", {}),
    }


def first_unsafe_process(
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
        "guard_episode_idx": as_int(row.get("guard_episode_idx")),
        "guard_process_step_idx": as_int(row.get("guard_process_step_idx"), -1),
        "trace_phase": row.get("trace_phase", ""),
        "vgr_cmd": as_int(row.get("predicted_label_VGR")),
        "vgr_topic": row.get("control_vgr_topic", ""),
        "vgr_confidence": as_float(row.get("vgr_confidence")),
        "hbw_cmd": as_int(row.get("predicted_label_HBW")),
        "hbw_topic": row.get("control_hbw_topic", ""),
        "hbw_confidence": as_float(row.get("hbw_confidence")),
        "model_ids": model_ids,
    }


def expectation_satisfied(analysis: dict[str, Any], expected: str) -> tuple[bool, str]:
    if not analysis["technical_ok"]:
        return False, "technical acceptance failed"
    unsafe_rows = int(analysis["unsafe_rows"])
    if expected == "reproduced":
        return (
            unsafe_rows > 0,
            "unsafe process command reproduced" if unsafe_rows else "no unsafe command observed",
        )
    return (
        unsafe_rows == 0,
        "all process guard states remained idle" if not unsafe_rows else "unsafe command observed",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--expect", choices=("reproduced", "safe"), default="safe")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        analysis = analyze_report(args.report_dir, args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"[FULL-STORAGE-PROCESS][ERROR] {error}") from error
    passed, message = expectation_satisfied(analysis, args.expect)
    if args.as_json:
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
    else:
        print(
            f"[FULL-STORAGE-PROCESS] rows={analysis['rows_completed']} "
            f"guard={analysis['guard_rows']} unsafe={analysis['unsafe_rows']} "
            f"vgr_unsafe={analysis['vgr_unsafe_rows']} hbw_unsafe={analysis['hbw_unsafe_rows']} "
            f"technical_ok={analysis['technical_ok']}"
        )
        if analysis["first_unsafe"]:
            first = analysis["first_unsafe"]
            print(
                "[FULL-STORAGE-PROCESS] first unsafe: "
                f"episode={first['guard_episode_idx']} step={first['guard_process_step_idx']} "
                f"VGR={first['vgr_cmd']} p={first['vgr_confidence']} "
                f"HBW={first['hbw_cmd']} p={first['hbw_confidence']}"
            )
        for error in analysis["technical_errors"]:
            print(f"[FULL-STORAGE-PROCESS][ERROR] {error}")
        print(f"[FULL-STORAGE-PROCESS] expectation={args.expect}: {message}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
