#!/usr/bin/env python3
"""Vergleicht zwei Node-RED-Orchestrierungsreports auf identischen Trace-Zustaenden."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable


DOMAINS = ("storage", "vgr", "hbw")


class ComparisonError(ValueError):
    """Die Reports sind unvollstaendig oder nicht direkt vergleichbar."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComparisonError(f"ungueltiges JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ComparisonError(f"JSON-Objekt erwartet: {path}")
    return value


def load_rows(report_dir: Path) -> list[dict[str, str]]:
    path = report_dir / "summary.csv"
    if not path.is_file():
        raise ComparisonError(f"Reportdatei fehlt: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ComparisonError(f"Report enthaelt keine Zeilen: {path}")
    return rows


def keyed_rows(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row.get("request_id_base", "").strip()
        if not key:
            raise ComparisonError("summary.csv enthaelt eine Zeile ohne request_id_base")
        if key in result:
            raise ComparisonError(f"doppelte request_id_base im Report: {key}")
        result[key] = row
    return result


def parse_int(value: object) -> int | None:
    text = str(value).strip()
    if text == "":
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        raise ComparisonError(f"Integerwert erwartet, erhalten: {value!r}") from exc


def parse_float(value: object) -> float | None:
    text = str(value).strip()
    if text == "":
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise ComparisonError(f"Zahlenwert erwartet, erhalten: {value!r}") from exc
    return number if math.isfinite(number) else None


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def prediction_fields(domain: str) -> tuple[str, str, str]:
    if domain == "storage":
        return "expected_empty_storage", "vgr_storage_pred", "storage_match_vgr"
    suffix = domain.upper()
    return f"expected_label_{suffix}", f"predicted_label_{suffix}", f"{domain}_match"


def load_storage_latencies(report_dir: Path) -> dict[str, float]:
    path = report_dir / "events.jsonl"
    if not path.is_file():
        return {}
    result: dict[str, float] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ComparisonError(f"{path}:{line_number}: {exc}") from exc
        key = str(event.get("request_id", "")).strip()
        value = parse_float(event.get("storage_latency_ms"))
        if key and value is not None:
            result[key] = value / 1000.0
    return result


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def latency_stats(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "median_s": statistics.median(values) if values else None,
        "p95_s": percentile(values, 0.95),
    }


def technical_stats(summary: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "completed": bool(summary.get("completed")),
        "rows_completed": int(summary.get("rows_completed", len(rows))),
        "faults": int(summary.get("faults", 0)),
        "timeouts": sum(truthy(row.get("timeout")) for row in rows),
        "errors": sum(bool(str(row.get("error", "")).strip()) for row in rows),
    }


COMMAND_COLUMNS = (
    "control_vgr_cmd",
    "control_hbw_cmd",
    "control_mpo_cmd",
    "control_sld_cmd",
    "control_vgr_topic",
    "control_hbw_topic",
    "control_mpo_topic",
    "control_sld_topic",
)


def require_same_trace(
    baseline_rows: dict[str, dict[str, str]],
    candidate_rows: dict[str, dict[str, str]],
) -> set[str]:
    baseline_ids = set(baseline_rows)
    candidate_ids = set(candidate_rows)
    if baseline_ids == candidate_ids:
        return baseline_ids
    raise ComparisonError(
        "Reports enthalten nicht dieselben Trace-Zustaende: "
        f"nur baseline={sorted(baseline_ids - candidate_ids)[:5]}, "
        f"nur candidate={sorted(candidate_ids - baseline_ids)[:5]}"
    )


def compare_trace_rows(
    domain: str,
    trace_ids: set[str],
    baseline_rows: dict[str, dict[str, str]],
    candidate_rows: dict[str, dict[str, str]],
) -> dict[str, Any]:
    expected_field, prediction_field, _ = prediction_fields(domain)
    result: dict[str, Any] = {
        "baseline_matches": 0,
        "candidate_matches": 0,
        "changed": [],
        "improved": [],
        "regressed": [],
        "changed_commands": [],
        "storage_disagreements": {"baseline": 0, "candidate": 0},
    }
    for key in sorted(trace_ids):
        left = baseline_rows[key]
        right = candidate_rows[key]
        require_same_row_metadata(key, left, right, expected_field)
        update_prediction_counts(result, key, left, right, expected_field, prediction_field)
        if any(left.get(column, "") != right.get(column, "") for column in COMMAND_COLUMNS):
            result["changed_commands"].append(key)
        if domain == "storage":
            update_storage_disagreements(result["storage_disagreements"], left, right)
    return result


def require_same_row_metadata(
    key: str,
    baseline: dict[str, str],
    candidate: dict[str, str],
    expected_field: str,
) -> None:
    same_source = baseline.get("source_id") == candidate.get("source_id")
    same_expected = parse_int(baseline.get(expected_field)) == parse_int(candidate.get(expected_field))
    if not same_source or not same_expected:
        raise ComparisonError(f"Trace-Metadaten unterscheiden sich fuer {key}")


def update_prediction_counts(
    result: dict[str, Any],
    key: str,
    baseline: dict[str, str],
    candidate: dict[str, str],
    expected_field: str,
    prediction_field: str,
) -> None:
    expected = parse_int(baseline.get(expected_field))
    left_prediction = parse_int(baseline.get(prediction_field))
    right_prediction = parse_int(candidate.get(prediction_field))
    left_ok = left_prediction == expected
    right_ok = right_prediction == expected
    result["baseline_matches"] += int(left_ok)
    result["candidate_matches"] += int(right_ok)
    if left_prediction != right_prediction:
        result["changed"].append(key)
    if not left_ok and right_ok:
        result["improved"].append(key)
    if left_ok and not right_ok:
        result["regressed"].append(key)


def update_storage_disagreements(
    counts: dict[str, int],
    baseline: dict[str, str],
    candidate: dict[str, str],
) -> None:
    for name, row in (("baseline", baseline), ("candidate", candidate)):
        vgr_value = parse_int(row.get("vgr_storage_pred"))
        hbw_value = parse_int(row.get("hbw_storage_pred"))
        counts[name] += int(vgr_value != hbw_value)


def run_latencies(
    domain: str,
    report_dir: Path,
    rows: list[dict[str, str]],
    trace_ids: set[str],
) -> list[float]:
    if domain == "storage":
        values = load_storage_latencies(report_dir)
        return [values[key] for key in trace_ids if key in values]
    field = f"{domain}_latency_s"
    return [
        value
        for row in rows
        if (value := parse_float(row.get(field))) is not None
    ]


def compare_runs(*, domain: str, baseline: Path, candidate: Path) -> dict[str, Any]:
    baseline_summary = load_json(baseline / "run_summary.json")
    candidate_summary = load_json(candidate / "run_summary.json")
    baseline_rows = load_rows(baseline)
    candidate_rows = load_rows(candidate)
    baseline_by_id = keyed_rows(baseline_rows)
    candidate_by_id = keyed_rows(candidate_rows)
    trace_ids = require_same_trace(baseline_by_id, candidate_by_id)
    counts = compare_trace_rows(domain, trace_ids, baseline_by_id, candidate_by_id)
    baseline_latencies = run_latencies(domain, baseline, baseline_rows, trace_ids)
    candidate_latencies = run_latencies(domain, candidate, candidate_rows, trace_ids)
    _, _, match_field = prediction_fields(domain)

    return {
        "domain": domain,
        "trace_rows": len(trace_ids),
        "same_trace": True,
        "model_ids": {
            "baseline": baseline_summary.get("model_ids", {}).get(domain),
            "candidate": candidate_summary.get("model_ids", {}).get(domain),
        },
        "technical": {
            "baseline": technical_stats(baseline_summary, baseline_rows),
            "candidate": technical_stats(candidate_summary, candidate_rows),
        },
        "quality": {
            "baseline_matches": counts["baseline_matches"],
            "candidate_matches": counts["candidate_matches"],
            "changed_predictions": len(counts["changed"]),
            "improvements": len(counts["improved"]),
            "regressions": len(counts["regressed"]),
            "changed_prediction_ids": counts["changed"],
            "improved_ids": counts["improved"],
            "regressed_ids": counts["regressed"],
        },
        "commands": {
            "identical": not counts["changed_commands"],
            "changed_rows": len(counts["changed_commands"]),
            "changed_ids": counts["changed_commands"],
        },
        "latency": {
            "baseline": latency_stats(baseline_latencies),
            "candidate": latency_stats(candidate_latencies),
        },
        "storage_consumer_disagreements": (
            counts["storage_disagreements"] if domain == "storage" else None
        ),
        "reported_match_field": match_field,
    }


def print_human(comparison: dict[str, Any]) -> None:
    quality = comparison["quality"]
    technical = comparison["technical"]
    latency = comparison["latency"]
    print(
        f"{comparison['domain'].upper()}: {comparison['trace_rows']} identische Trace-Zustaende | "
        f"model {comparison['model_ids']['baseline']} -> {comparison['model_ids']['candidate']}"
    )
    print(
        "Treffer: "
        f"{quality['baseline_matches']} -> {quality['candidate_matches']} | "
        f"geaendert={quality['changed_predictions']} verbessert={quality['improvements']} "
        f"verschlechtert={quality['regressions']}"
    )
    print(
        "Technik candidate: "
        f"completed={technical['candidate']['completed']} faults={technical['candidate']['faults']} "
        f"timeouts={technical['candidate']['timeouts']} errors={technical['candidate']['errors']}"
    )
    print(
        "Latenz candidate: "
        f"median={latency['candidate']['median_s']}s p95={latency['candidate']['p95_s']}s | "
        f"Commands identisch={comparison['commands']['identical']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Beispiel:
  python3 tools/compare_model_runs.py --domain vgr \\
    --baseline reports/orchestration_simulation/20260718130315106_nodered \\
    --candidate reports/orchestration_simulation/<kandidatenlauf>

Verglichen werden identische request_id_base-Zustaende, Modell-IDs, Treffer,
Veraenderungen, Faults, Timeouts, Commands sowie Median- und p95-Latenz.
Das Werkzeug veraendert weder Reports noch Modellauswahl.""",
    )
    parser.add_argument("--domain", required=True, choices=DOMAINS, help="Auszuwertendes NN.")
    parser.add_argument(
        "--baseline",
        required=True,
        type=Path,
        help="Referenzreport mit run_summary.json und summary.csv.",
    )
    parser.add_argument(
        "--candidate",
        required=True,
        type=Path,
        help="Report des Kandidatenlaufs auf demselben Trace.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Maschinenlesbare JSON-Ausgabe.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        comparison = compare_runs(
            domain=args.domain,
            baseline=args.baseline.resolve(),
            candidate=args.candidate.resolve(),
        )
    except ComparisonError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(comparison, indent=2))
    else:
        print_human(comparison)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
