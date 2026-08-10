#!/usr/bin/env python3
"""Verwaltet lokale, gepruefte Modellkandidaten fuer die NN-Container.

Das Werkzeug aendert nur Deployment-Artefakte und die lokale `.env`. MQTT-
Vertraege, Node-RED-Flows und Inferenzcode bleiben unveraendert. Ein Modell
wird nie waehrend eines laufenden Stacks gewechselt.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from tools import check_model_compatibility as compatibility
except ModuleNotFoundError:  # Direkter Aufruf als `python tools/...py`.
    import check_model_compatibility as compatibility


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = PROJECT_ROOT / "scenarios/serve_ft_nns_external_broker/x86_64"
BASE_COMPOSE = SCENARIO_ROOT / "docker-compose.yml"
VIRTUAL_COMPOSE = SCENARIO_ROOT / "docker-compose.virtual.yml"
DOMAINS = ("storage", "vgr", "hbw")
ARTIFACTS = ("model.keras", "activation.json", "metrics.json")
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STATE_RELATIVE_PATH = Path("model_registry/model_selection_state.json")
HISTORY_RELATIVE_PATH = Path("model_registry/model_selection_history.jsonl")


class CandidateError(RuntimeError):
    """Ein sicherheitsrelevanter Modellwechsel konnte nicht ausgefuehrt werden."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def filesystem_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateError(f"ungueltiges JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CandidateError(f"JSON-Objekt erwartet: {path}")
    return value


def model_identity(domain: str, model_dir: Path) -> tuple[str, str]:
    activation = load_json_object(model_dir / "activation.json")
    model_hash = file_sha256(model_dir / "model.keras")
    trained_at = str(activation.get("trained_at", "unknown"))
    return f"{domain}:{trained_at}:{model_hash[:12]}", model_hash


def validate_name(name: str) -> None:
    if not NAME_PATTERN.fullmatch(name):
        raise CandidateError(
            "Kandidatenname darf nur Buchstaben, Ziffern, Punkt, Unterstrich und Bindestrich enthalten."
        )


def candidate_dir(root: Path, domain: str, name: str) -> Path:
    validate_name(name)
    return root / "model_registry" / domain / "candidates" / name


def container_candidate_dir(domain: str, name: str) -> str:
    validate_name(name)
    return f"/model_registry/{domain}/candidates/{name}"


def default_container_dir(domain: str) -> str:
    return f"/model_registry/{domain}/latest"


def host_model_dir(root: Path, domain: str, configured: str | None) -> Path:
    value = configured or default_container_dir(domain)
    prefix = "/model_registry/"
    if not value.startswith(prefix):
        raise CandidateError(f"Modellpfad muss unter {prefix} liegen: {value!r}")
    relative = Path(value.removeprefix(prefix))
    if relative.is_absolute() or ".." in relative.parts:
        raise CandidateError(f"Unsicherer Modellpfad: {value!r}")
    return root / "model_registry" / relative


def load_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CandidateError(f"{path}:{line_number}: KEY=VALUE erwartet")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def atomic_update_env(path: Path, updates: Mapping[str, str | None]) -> None:
    """Aendert nur angegebene Variablen und erhaelt alle anderen Zeilen."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    output: list[str] = []
    seen: set[str] = set()
    for line in existing:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in updates and key and not stripped.startswith("#"):
            seen.add(key)
            value = updates[key]
            if value is not None:
                output.append(f"{key}={value}")
            continue
        output.append(line)
    missing = [key for key, value in updates.items() if key not in seen and value is not None]
    if missing and output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={updates[key]}" for key in missing)
    content = "\n".join(output) + ("\n" if output else "")
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_state(root: Path) -> dict[str, Any]:
    path = root / STATE_RELATIVE_PATH
    if not path.exists():
        return {"schema_version": 1, "domains": {}}
    state = load_json_object(path)
    state.setdefault("schema_version", 1)
    state.setdefault("domains", {})
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    atomic_write_json(root / STATE_RELATIVE_PATH, state)


def append_history(root: Path, event: dict[str, Any]) -> None:
    path = root / HISTORY_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": utc_timestamp(), **event}, sort_keys=True) + "\n")


def validate_candidate(
    *,
    domain: str,
    path: Path,
    target: str,
    root: Path,
) -> list[compatibility.CompatibilityReport]:
    modes = ("virtual",) if target == "virtual" else ("virtual", "physical")
    reports = [
        compatibility.analyze_model(
            domain=domain,
            candidate_dir=path,
            mode=mode,
            root=root,
        )
        for mode in modes
    ]
    failures = [
        f"{report.mode}:{item.name}: {item.detail}"
        for report in reports
        for item in report.checks
        if not item.ok
    ]
    if failures:
        raise CandidateError("Modellkandidat ist nicht kompatibel:\n- " + "\n- ".join(failures))
    return reports


def ensure_stack_stopped(
    *,
    root: Path,
    env_file: Path,
    target: str,
) -> None:
    files = [BASE_COMPOSE]
    if target == "virtual":
        files.append(VIRTUAL_COMPOSE)
    command = ["docker", "compose"]
    if env_file.exists():
        command.extend(["--env-file", str(env_file)])
    for compose_file in files:
        command.extend(["-f", str(compose_file)])
    command.extend(["ps", "--services", "--status", "running"])
    try:
        process = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CandidateError(f"Stack-Status konnte nicht geprueft werden: {exc}") from exc
    if process.returncode != 0:
        raise CandidateError(
            "Stack-Status konnte nicht sicher bestimmt werden: "
            + (process.stderr.strip() or process.stdout.strip())
        )
    running = [line for line in process.stdout.splitlines() if line.strip()]
    if running:
        raise CandidateError(
            "Modellwechsel ist nur bei gestopptem Stack erlaubt. Laufende Dienste: "
            + ", ".join(running)
        )


def add_candidate(
    *,
    domain: str,
    name: str,
    source: Path,
    target: str,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    destination = candidate_dir(root, domain, name)
    if destination.exists():
        raise CandidateError(f"Kandidat existiert bereits: {destination}")
    missing = [artifact for artifact in ARTIFACTS if not (source / artifact).is_file()]
    if missing:
        raise CandidateError(f"Kandidatenartefakte fehlen in {source}: {missing}")
    reports = validate_candidate(domain=domain, path=source, target=target, root=root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = destination.parent / f".{name}.tmp-{uuid.uuid4().hex}"
    try:
        temp_dir.mkdir()
        for artifact in ARTIFACTS:
            shutil.copy2(source / artifact, temp_dir / artifact)
        model_id, model_hash = model_identity(domain, temp_dir)
        atomic_write_json(
            temp_dir / "candidate.json",
            {
                "schema_version": 1,
                "domain": domain,
                "name": name,
                "added_at": utc_timestamp(),
                "target": target,
                "model_id": model_id,
                "model_sha256": model_hash,
                "compatibility": [asdict(report) for report in reports],
            },
        )
        os.replace(temp_dir, destination)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    append_history(
        root,
        {
            "action": "add",
            "domain": domain,
            "candidate": name,
            "target": target,
            "model_id": model_id,
            "model_sha256": model_hash,
        },
    )
    return {
        "domain": domain,
        "name": name,
        "path": str(destination),
        "model_id": model_id,
        "model_sha256": model_hash,
    }


def select_candidate(
    *,
    domain: str,
    name: str,
    target: str,
    env_file: Path,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    path = candidate_dir(root, domain, name)
    if not path.is_dir():
        raise CandidateError(f"Unbekannter Kandidat: {path}")
    validate_candidate(domain=domain, path=path, target=target, root=root)
    ensure_stack_stopped(root=root, env_file=env_file, target=target)
    key = f"{domain.upper()}_MODEL_DIR"
    settings = load_env_values(env_file)
    previous = settings.get(key) or None
    selected = container_candidate_dir(domain, name)
    model_id, model_hash = model_identity(domain, path)
    state = load_state(root)
    domain_state = state["domains"].setdefault(domain, {"rollback": []})
    domain_state.setdefault("rollback", []).append(
        {
            "model_dir": previous,
            "target": domain_state.get("target", target),
            "candidate": domain_state.get("candidate"),
        }
    )
    domain_state.update(
        {
            "model_dir": selected,
            "target": target,
            "candidate": name,
            "model_id": model_id,
            "model_sha256": model_hash,
            "selected_at": utc_timestamp(),
        }
    )
    atomic_update_env(env_file, {key: selected})
    try:
        save_state(root, state)
    except Exception:
        atomic_update_env(env_file, {key: previous})
        raise
    append_history(
        root,
        {
            "action": "select",
            "domain": domain,
            "candidate": name,
            "target": target,
            "previous_model_dir": previous or default_container_dir(domain),
            "model_dir": selected,
            "model_id": model_id,
            "model_sha256": model_hash,
        },
    )
    return {"domain": domain, "candidate": name, "model_dir": selected, "model_id": model_id}


def rollback_candidate(
    *,
    domain: str,
    env_file: Path,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    state = load_state(root)
    domain_state = state.get("domains", {}).get(domain, {})
    rollback = domain_state.get("rollback", [])
    if not rollback:
        raise CandidateError(f"Keine rueckrollbare Auswahl fuer {domain} vorhanden.")
    target = str(domain_state.get("target", "virtual"))
    ensure_stack_stopped(root=root, env_file=env_file, target=target)
    previous = rollback.pop()
    previous_dir = previous.get("model_dir") or None
    previous_host = host_model_dir(root, domain, previous_dir)
    previous_target = str(previous.get("target") or target)
    validate_candidate(
        domain=domain,
        path=previous_host,
        target=previous_target,
        root=root,
    )
    key = f"{domain.upper()}_MODEL_DIR"
    current_dir = domain_state.get("model_dir") or default_container_dir(domain)
    atomic_update_env(env_file, {key: previous_dir})
    model_id, model_hash = model_identity(domain, previous_host)
    domain_state.update(
        {
            "model_dir": previous_dir,
            "target": previous_target,
            "candidate": previous.get("candidate"),
            "model_id": model_id,
            "model_sha256": model_hash,
            "selected_at": utc_timestamp(),
            "rollback": rollback,
        }
    )
    save_state(root, state)
    append_history(
        root,
        {
            "action": "rollback",
            "domain": domain,
            "previous_model_dir": current_dir,
            "model_dir": previous_dir or default_container_dir(domain),
            "model_id": model_id,
            "model_sha256": model_hash,
        },
    )
    return {
        "domain": domain,
        "model_dir": previous_dir or default_container_dir(domain),
        "model_id": model_id,
    }


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def validate_promotion_report(
    *,
    domain: str,
    model_id: str,
    report_dir: Path,
) -> dict[str, Any]:
    summary = load_json_object(report_dir / "run_summary.json")
    if not summary.get("completed") or int(summary.get("rows_completed", -1)) != 320:
        raise CandidateError("Promotion verlangt einen abgeschlossenen 320-Payload-Lauf.")
    if int(summary.get("faults", -1)) != 0:
        raise CandidateError(f"Promotion abgelehnt: faults={summary.get('faults')}")
    report_model_id = summary.get("model_ids", {}).get(domain)
    if report_model_id != model_id:
        raise CandidateError(
            f"Report nutzt {report_model_id!r}, Kandidat erwartet {model_id!r}."
        )
    summary_path = report_dir / "summary.csv"
    if not summary_path.is_file():
        raise CandidateError(f"Reportdatei fehlt: {summary_path}")
    with summary_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 320:
        raise CandidateError(f"summary.csv enthaelt {len(rows)} statt 320 Zeilen.")
    technical_errors = [
        row.get("request_id_base", str(index))
        for index, row in enumerate(rows, start=1)
        if truthy(row.get("timeout")) or str(row.get("error", "")).strip()
    ]
    if technical_errors:
        raise CandidateError(
            f"Promotion abgelehnt: technische Fehler in {len(technical_errors)} Zeilen."
        )
    quality_key = {
        "storage": "storage_matches_vgr",
        "vgr": "vgr_matches",
        "hbw": "hbw_matches",
    }[domain]
    return {
        "rows": len(rows),
        "faults": 0,
        "quality_matches": summary.get(quality_key),
        "quality_total": summary.get("rows_completed"),
        "model_id": report_model_id,
    }


def promote_candidate(
    *,
    domain: str,
    name: str,
    report_dir: Path,
    env_file: Path,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    source = candidate_dir(root, domain, name)
    if not source.is_dir():
        raise CandidateError(f"Unbekannter Kandidat: {source}")
    validate_candidate(domain=domain, path=source, target="physical", root=root)
    state = load_state(root)
    current = state.get("domains", {}).get(domain, {})
    target = str(current.get("target", "virtual"))
    ensure_stack_stopped(root=root, env_file=env_file, target=target)
    model_id, model_hash = model_identity(domain, source)
    quality = validate_promotion_report(
        domain=domain,
        model_id=model_id,
        report_dir=report_dir,
    )
    domain_root = root / "model_registry" / domain
    latest = domain_root / "latest"
    versions = domain_root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    backup = versions / f"{filesystem_timestamp()}_pre_promotion"
    if latest.is_dir():
        shutil.copytree(latest, backup)
    staged = domain_root / f".latest-promote-{uuid.uuid4().hex}"
    displaced = domain_root / f".latest-previous-{uuid.uuid4().hex}"
    staged.mkdir()
    for artifact in ARTIFACTS:
        shutil.copy2(source / artifact, staged / artifact)
    try:
        if latest.exists():
            os.replace(latest, displaced)
        os.replace(staged, latest)
    except Exception:
        if not latest.exists() and displaced.exists():
            os.replace(displaced, latest)
        raise
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    displaced_backup = None
    if displaced.exists():
        try:
            shutil.rmtree(displaced)
        except PermissionError:
            # Docker training may leave a root/nobody-owned latest directory.
            # The atomically displaced hidden directory is already outside the
            # active path and ignored by Git. Keep it as an additional local
            # rollback artifact rather than requiring sudo/chown.
            displaced_backup = displaced
    key = f"{domain.upper()}_MODEL_DIR"
    atomic_update_env(env_file, {key: None})
    state.setdefault("domains", {})[domain] = {
        "model_dir": None,
        "target": target,
        "candidate": None,
        "model_id": model_id,
        "model_sha256": model_hash,
        "selected_at": utc_timestamp(),
        "rollback": [],
    }
    save_state(root, state)
    append_history(
        root,
        {
            "action": "promote",
            "domain": domain,
            "candidate": name,
            "model_id": model_id,
            "model_sha256": model_hash,
            "backup": str(backup),
            "displaced_backup": str(displaced_backup) if displaced_backup else None,
            "report_dir": str(report_dir),
            "quality": quality,
        },
    )
    return {
        "domain": domain,
        "candidate": name,
        "model_id": model_id,
        "backup": str(backup),
        "displaced_backup": str(displaced_backup) if displaced_backup else None,
        "latest": str(latest),
        "quality": quality,
    }


def status(*, root: Path = PROJECT_ROOT, env_file: Path | None = None) -> dict[str, Any]:
    env_path = env_file or root / ".env"
    settings = load_env_values(env_path)
    state = load_state(root)
    domains: dict[str, Any] = {}
    for domain in DOMAINS:
        key = f"{domain.upper()}_MODEL_DIR"
        configured = settings.get(key) or None
        path = host_model_dir(root, domain, configured)
        item: dict[str, Any] = {
            "model_dir": configured or default_container_dir(domain),
            "host_path": str(path),
            "candidate": state.get("domains", {}).get(domain, {}).get("candidate"),
            "image": settings.get(f"{domain.upper()}_IMAGE") or None,
            "exists": all((path / artifact).is_file() for artifact in ARTIFACTS),
        }
        if item["exists"]:
            item["model_id"], item["model_sha256"] = model_identity(domain, path)
        domains[domain] = item
    return {"env_file": str(env_path), "domains": domains}


def print_result(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="Lokale Umgebungsdatei; andere Werte und Secrets bleiben erhalten (Standard: .env).",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Beispiele:
  python3 tools/manage_model_candidates.py add --domain vgr --name lstm32 \\
    --source /pfad/zum/modell --target virtual
  python3 tools/manage_model_candidates.py select --domain vgr --name lstm32 --target virtual
  python3 tools/manage_model_candidates.py status
  python3 tools/manage_model_candidates.py rollback --domain vgr
  python3 tools/manage_model_candidates.py promote --domain vgr --name lstm32 \\
    --report-dir reports/orchestration_simulation/<run_id>

Auswahl, Rollback und Promotion sind nur bei gestopptem Stack erlaubt.
`physical` prueft zusaetzlich zum virtuellen Trace den eingefrorenen Live-Vertrag.
Die Auswahl gilt ueber dieselbe .env fuer den jeweils naechsten Stackstart.""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser(
        "add",
        help="Kandidaten pruefen und lokal aufnehmen.",
        description="Prueft drei zusammengehoerige Artefakte und kopiert sie in die lokale Candidate-Registry.",
    )
    add_parser.add_argument("--domain", required=True, choices=DOMAINS, help="Zu ersetzender NN-Dienst.")
    add_parser.add_argument("--name", required=True, help="Lokaler, eindeutiger Kandidatenname.")
    add_parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Ordner mit model.keras, activation.json und metrics.json.",
    )
    add_parser.add_argument(
        "--target",
        required=True,
        choices=("virtual", "physical"),
        help="Pruefumfang; physical schliesst die virtuelle Pruefung ein.",
    )

    select_parser = subparsers.add_parser(
        "select",
        help="Kandidaten fuer den naechsten Start waehlen.",
        description="Validiert erneut und schreibt den Container-Modellpfad atomar in die lokale .env.",
    )
    select_parser.add_argument("--domain", required=True, choices=DOMAINS, help="Zu ersetzender NN-Dienst.")
    select_parser.add_argument("--name", required=True, help="Zuvor mit add aufgenommener Kandidat.")
    select_parser.add_argument(
        "--target",
        required=True,
        choices=("virtual", "physical"),
        help="Ziel des naechsten Starts; der betreffende Stack muss gestoppt sein.",
    )
    add_common_options(select_parser)

    status_parser = subparsers.add_parser(
        "status",
        help="Aktuelle Modell- und Imageauswahl anzeigen.",
        description="Zeigt aufgeloeste Modellpfade, Modell-IDs, Hashes und optionale Image-Overrides.",
    )
    add_common_options(status_parser)

    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Vorherige Modellauswahl wiederherstellen.",
        description="Stellt die letzte mit diesem Werkzeug protokollierte Auswahl wieder her; manuelle .env-Aenderungen sind nicht rollbackfaehig.",
    )
    rollback_parser.add_argument("--domain", required=True, choices=DOMAINS, help="Zurueckzurollender NN-Dienst.")
    add_common_options(rollback_parser)

    promote_parser = subparsers.add_parser(
        "promote",
        help="Geprueften Kandidaten nach latest uebernehmen.",
        description="Foerdert nur nach einem abgeschlossenen 320-Zustaende-Lauf ohne technische Faults und mit passender model_id.",
    )
    promote_parser.add_argument("--domain", required=True, choices=DOMAINS, help="Zu promovierender NN-Dienst.")
    promote_parser.add_argument("--name", required=True, help="Getesteter lokaler Kandidat.")
    promote_parser.add_argument(
        "--report-dir",
        required=True,
        type=Path,
        help="Reportordner mit run_summary.json und 320-zeiliger summary.csv.",
    )
    add_common_options(promote_parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "add":
            value = add_candidate(
                domain=args.domain,
                name=args.name,
                source=args.source.resolve(),
                target=args.target,
            )
        elif args.command == "select":
            value = select_candidate(
                domain=args.domain,
                name=args.name,
                target=args.target,
                env_file=args.env_file.resolve(),
            )
        elif args.command == "rollback":
            value = rollback_candidate(
                domain=args.domain,
                env_file=args.env_file.resolve(),
            )
        elif args.command == "promote":
            value = promote_candidate(
                domain=args.domain,
                name=args.name,
                report_dir=args.report_dir.resolve(),
                env_file=args.env_file.resolve(),
            )
        else:
            value = status(env_file=args.env_file.resolve())
    except (CandidateError, compatibility.ArtifactError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print_result(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
