#!/usr/bin/env python3
"""Preflight fuer portable AI-CPS-Laufzeitumgebungen.

Das Tool aendert keine Projektdateien. Es prueft vor einem virtuellen oder
physischen Start die Plattform, Docker, Modelle, Konfigurationen und die
erreichbare MQTT-Grenze. Node-RED, OPC UA und SPS des physischen Live-Systems
bleiben dabei eine Black-Box. So werden projektseitige Umgebungsfehler
sichtbar, bevor ein Steuerungszyklus begonnen wird.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = PROJECT_ROOT / "scenarios/serve_ft_nns_external_broker/x86_64"
MODEL_DOMAINS = ("storage", "vgr", "hbw")
MODEL_FILES = ("model.keras", "activation.json", "metrics.json")
CONFLICTING_SERVICES = {
    "pipeline_orchestrator",
    "hbw_pipeline_orchestrator",
    "orchestration_simulator",
}
NN_SERVICES = {"storage_infer", "vgr_infer", "hbw_infer"}
FACTORY_RUNTIME_KEYS = {
    "vgr": "FACTORY_VGR_BASE_RUNTIME_MS",
    "hbw": "FACTORY_HBW_BASE_RUNTIME_MS",
    "mpo": "FACTORY_MPO_BASE_RUNTIME_MS",
    "sld": "FACTORY_SLD_BASE_RUNTIME_MS",
}
DEFAULT_FACTORY_BASE_RUNTIME_MS = 100
MAX_JAVASCRIPT_SAFE_INTEGER = 9_007_199_254_740_991
DEFAULT_COMPOSE_PROJECT = "ai-cps-nn-runtime"
DEPLOYMENT_LOCK = PROJECT_ROOT / ".runtime/deployment-lock.json"


@dataclass(frozen=True)
class CheckResult:
    """Ein einzelner, maschinenlesbarer Preflight-Befund."""

    name: str
    ok: bool
    detail: str
    severity: str = "error"


def load_env_file(path: Path) -> dict[str, str]:
    """Liest einfache KEY=VALUE-Zeilen ohne Shell-Auswertung."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{path}:{line_number}: empty key")
        values[key] = value.strip().strip('"').strip("'")
    return values


def merged_settings(env_file: Mapping[str, str], process_env: Mapping[str, str]) -> dict[str, str]:
    """Prozessvariablen haben Vorrang vor der lokalen `.env`."""
    return {**env_file, **process_env}


def result(name: str, ok: bool, success: str, failure: str, *, severity: str = "error") -> CheckResult:
    return CheckResult(name=name, ok=ok, detail=success if ok else failure, severity=severity)


def check_architecture(machine: str | None = None) -> CheckResult:
    actual = (machine or platform.machine()).lower()
    supported = actual in {"x86_64", "amd64"}
    return result(
        "architecture",
        supported,
        f"supported linux/amd64 host architecture: {actual}",
        f"unsupported architecture: {actual}; only x86_64/amd64 is released",
    )


def selected_model_path(
    *,
    domain: str,
    settings: Mapping[str, str],
    root: Path,
) -> Path:
    """Uebersetzt den Compose-internen Modellpfad in den Hostpfad."""
    configured = settings.get(f"{domain.upper()}_MODEL_DIR", "").strip()
    if not configured:
        return root / "model_registry" / domain / "latest"
    prefix = "/model_registry/"
    if not configured.startswith(prefix):
        raise ValueError(
            f"{domain.upper()}_MODEL_DIR must be below {prefix}, got {configured!r}"
        )
    relative = Path(configured.removeprefix(prefix))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe model directory: {configured!r}")
    return root / "model_registry" / relative


def check_model_artifacts(
    root: Path = PROJECT_ROOT,
    settings: Mapping[str, str] | None = None,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    selected = settings or {}
    for domain in MODEL_DOMAINS:
        try:
            model_dir = selected_model_path(domain=domain, settings=selected, root=root)
        except ValueError as exc:
            checks.append(CheckResult(f"model:{domain}", False, str(exc)))
            continue
        missing = [name for name in MODEL_FILES if not (model_dir / name).is_file()]
        checks.append(
            result(
                f"model:{domain}",
                not missing,
                f"all deployment artifacts exist in {model_dir}",
                f"missing deployment artifacts in {model_dir}: {missing}",
            )
        )
        for json_name in ("activation.json", "metrics.json"):
            json_path = model_dir / json_name
            if not json_path.is_file():
                continue
            try:
                json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                checks.append(CheckResult(f"model-json:{domain}:{json_name}", False, str(exc)))
    return checks


def required_nodered_assets(root: Path = PROJECT_ROOT) -> list[Path]:
    scenario = root / "scenarios/serve_ft_nns_external_broker/x86_64"
    base = scenario / "node_red"
    return [
        base / "Dockerfile",
        base / "entrypoint.sh",
        base / "settings.js",
        base / "flows.json",
        base / "flows_ai_orchestration.json",
        base / "dashboard_runtime/package.json",
        base / "dashboard_runtime/package-lock.json",
        base / "config/topics.json",
        base / "config/idle_seed_templates.json",
        base / "config/model_contract.schema.json",
        base / "config/virtual_experiment_catalog.json",
        base / "mosquitto/mosquitto.conf",
        scenario / "test_payloads/live_plc_trace/payloads.jsonl",
        scenario / "test_payloads/live_plc_trace/manifest.csv",
        scenario / "test_payloads/live_plc_full_storage_attempt/payloads.jsonl",
        scenario / "test_payloads/live_plc_full_storage_attempt/manifest.csv",
        scenario / "test_payloads/live_plc_full_storage_process_guard/payloads.jsonl",
        scenario / "test_payloads/live_plc_full_storage_process_guard/manifest.csv",
    ]


def check_nodered_assets(root: Path = PROJECT_ROOT) -> CheckResult:
    missing = [str(path.relative_to(root)) for path in required_nodered_assets(root) if not path.is_file()]
    return result(
        "nodered-assets",
        not missing,
        "versioned Node-RED and Mosquitto runtime assets are complete",
        f"missing runtime assets: {missing}",
    )


def check_virtual_experiment_catalog(root: Path = PROJECT_ROOT) -> list[CheckResult]:
    """Prueft sichtbare Szenarien und fest versionierte historische Modelle."""
    scenario = root / "scenarios/serve_ft_nns_external_broker/x86_64"
    catalog_path = scenario / "node_red/config/virtual_experiment_catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [CheckResult("virtual-experiment-catalog", False, str(exc))]

    checks: list[CheckResult] = []
    profiles = catalog.get("model_profiles", {})
    default_profile = catalog.get("default_model_profile")
    checks.append(
        result(
            "virtual-model-profiles",
            catalog.get("schema_version") == "1.0"
            and isinstance(profiles, dict)
            and default_profile in profiles,
            f"model profiles available: {', '.join(sorted(profiles))}",
            "invalid virtual model profile catalog",
        )
    )
    for profile_id, profile in profiles.items() if isinstance(profiles, dict) else ():
        for domain in ("vgr", "hbw"):
            domain_config = profile.get("domains", {}).get(domain, {})
            if domain_config.get("source") == "active":
                continue
            relative = Path(str(domain_config.get("model_dir", "")))
            model_dir = root / "model_registry" / relative
            invalid: list[str] = []
            for filename, hash_key in (
                ("model.keras", "model_sha256"),
                ("activation.json", "activation_sha256"),
                ("metrics.json", "metrics_sha256"),
            ):
                artifact = model_dir / filename
                expected = str(domain_config.get(hash_key, ""))
                if not artifact.is_file() or not expected or sha256_file(artifact) != expected:
                    invalid.append(filename)
            model_hash = str(domain_config.get("model_sha256", ""))
            expected_id = str(domain_config.get("model_id", ""))
            try:
                activation = json.loads((model_dir / "activation.json").read_text(encoding="utf-8"))
                actual_id = f"{domain}:{activation.get('trained_at', 'unknown')}:{model_hash[:12]}"
            except (OSError, json.JSONDecodeError):
                actual_id = ""
            checks.append(
                result(
                    f"virtual-model-profile:{profile_id}:{domain}",
                    not invalid and actual_id == expected_id,
                    f"verified {expected_id}",
                    f"invalid artifacts={invalid} or model_id={expected_id!r}/{actual_id!r}",
                )
            )

    trace_profiles = catalog.get("trace_profiles", {})
    trace_paths = {
        "standard": scenario / "test_payloads/live_plc_trace/payloads.jsonl",
        "full-storage-attempt": scenario / "test_payloads/live_plc_full_storage_attempt/payloads.jsonl",
        "full-storage-process-guard": scenario / "test_payloads/live_plc_full_storage_process_guard/payloads.jsonl",
    }
    for profile_id, payload_path in trace_paths.items():
        configured = trace_profiles.get(profile_id, {}) if isinstance(trace_profiles, dict) else {}
        try:
            actual_count = sum(1 for line in payload_path.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            actual_count = -1
        expected_count = configured.get("state_count")
        display_name = configured.get("display_name")
        checks.append(
            result(
                f"virtual-trace-profile:{profile_id}",
                bool(display_name) and expected_count == actual_count,
                f"{display_name}: {actual_count} states",
                f"missing display name or state count mismatch: expected {expected_count}, got {actual_count}",
            )
        )
    return checks


def check_dependency_pins(root: Path = PROJECT_ROOT) -> list[CheckResult]:
    checks: list[CheckResult] = []
    scenario = root / "scenarios/serve_ft_nns_external_broker/x86_64"
    for domain in MODEL_DOMAINS:
        path = scenario / f"code_base_{domain}" / "requirements.txt"
        if not path.is_file():
            checks.append(CheckResult(f"dependency-pins:{domain}", False, f"missing {path}"))
            continue
        requirements = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        unpinned = [requirement for requirement in requirements if "==" not in requirement]
        checks.append(
            result(
                f"dependency-pins:{domain}",
                bool(requirements) and not unpinned,
                f"all {len(requirements)} Python runtime dependencies are pinned",
                f"unversioned dependencies in {path}: {unpinned}",
            )
        )
    lock_paths = [scenario / "code_base_common" / "requirements-runtime.lock"] + [
        root / "training" / domain / "requirements-training.lock"
        for domain in MODEL_DOMAINS
    ]
    for lock_path in lock_paths:
        name = (
            "dependency-lock"
            if lock_path.name == "requirements-runtime.lock"
            else f"training-lock:{lock_path.parent.name}"
        )
        if not lock_path.is_file():
            checks.append(CheckResult(name, False, f"missing {lock_path}"))
            continue
        content = lock_path.read_text(encoding="utf-8")
        package_lines = [
            line.strip()
            for line in content.splitlines()
            if line and not line[0].isspace() and not line.startswith("#")
        ]
        unpinned = [line for line in package_lines if "==" not in line]
        hash_count = content.count("--hash=sha256:")
        valid = bool(package_lines) and not unpinned and hash_count >= len(package_lines)
        checks.append(
            result(
                name,
                valid,
                f"{len(package_lines)} packages are version- and hash-pinned",
                f"incomplete hash lock {lock_path}: unpinned={unpinned}, hashes={hash_count}",
            )
        )
    return checks


def check_report_directory(settings: Mapping[str, str], root: Path = PROJECT_ROOT) -> CheckResult:
    configured = settings.get("REPORT_ROOT_HOST", "reports")
    configured_path = Path(configured).expanduser()
    path = configured_path if configured_path.is_absolute() else (
        root / "scenarios/serve_ft_nns_external_broker/x86_64" / configured_path
    )
    path = path.resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".ai-cps-preflight-", dir=path, delete=True):
            pass
    except OSError as exc:
        return CheckResult("report-directory", False, f"{path}: {exc}")
    return CheckResult("report-directory", True, f"writable report directory: {path}")


def run_command(
    args: list[str],
    *,
    timeout: int = 20,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False, env=env)


def check_docker() -> list[CheckResult]:
    if shutil.which("docker") is None:
        return [CheckResult("docker", False, "docker CLI not found")]

    version = run_command(["docker", "version", "--format", "{{json .Server}}"])
    if version.returncode != 0:
        return [CheckResult("docker", False, version.stderr.strip() or version.stdout.strip())]

    checks = [CheckResult("docker", True, "Docker daemon is reachable")]
    try:
        server = json.loads(version.stdout)
    except json.JSONDecodeError:
        server = {}
    os_name = str(server.get("Os", "")).lower()
    arch = str(server.get("Arch", "")).lower()
    checks.append(
        result(
            "docker-platform",
            os_name == "linux" and arch in {"amd64", "x86_64"},
            f"Docker server platform is {os_name}/{arch}",
            f"Docker server must be linux/amd64, got {os_name or '?'} / {arch or '?'}",
        )
    )

    info = run_command(["docker", "info", "--format", "{{.OperatingSystem}}"])
    operating_system = info.stdout.strip()
    desktop = "docker desktop" in operating_system.lower()
    checks.append(
        CheckResult(
            "docker-runtime",
            True,
            (
                f"supported Docker Desktop Linux engine: {operating_system}"
                if desktop
                else f"supported native Docker Engine: {operating_system or 'Linux'}"
            ),
        )
    )

    compose = run_command(["docker", "compose", "version"])
    checks.append(
        result(
            "docker-compose",
            compose.returncode == 0,
            compose.stdout.strip(),
            compose.stderr.strip() or "Docker Compose plugin not available",
        )
    )
    context = run_command(["docker", "context", "show"])
    checks.append(
        result(
            "docker-context",
            context.returncode == 0 and bool(context.stdout.strip()),
            f"active Docker context: {context.stdout.strip()}",
            context.stderr.strip() or "active Docker context is unavailable",
        )
    )
    return checks


def check_compose_configs(
    root: Path = PROJECT_ROOT,
    settings: Mapping[str, str] | None = None,
    mode: str = "virtual",
) -> list[CheckResult]:
    """Validiert nur die Compose-Dateien, die der gewaehlte Modus nutzt."""
    scenario = root / "scenarios/serve_ft_nns_external_broker/x86_64"
    base = scenario / "docker-compose.yml"
    virtual = scenario / "docker-compose.virtual.yml"
    commands = {
        "compose-physical": ["docker", "compose", "-f", str(base), "config"],
    }
    if mode == "virtual":
        commands["compose-virtual"] = [
            "docker",
            "compose",
            "-f",
            str(base),
            "-f",
            str(virtual),
            "config",
        ]
    command_env = {**os.environ, **(settings or {})}
    checks = []
    for name, command in commands.items():
        process = run_command(command, env=command_env)
        checks.append(
            result(
                name,
                process.returncode == 0,
                "Compose configuration is valid",
                process.stderr.strip() or process.stdout.strip(),
            )
        )
    return checks


def parse_conflicting_consumers(
    lines: Iterable[str], current_project: str = DEFAULT_COMPOSE_PROJECT
) -> list[str]:
    conflicts: list[str] = []
    for line in lines:
        name, _, remainder = line.partition("|")
        project, _, service = remainder.partition("|")
        if service in CONFLICTING_SERVICES or (
            service in NN_SERVICES and project != current_project
        ):
            conflicts.append(f"{name} ({project}/{service})")
    return conflicts


def check_conflicting_consumers(
    current_project: str = DEFAULT_COMPOSE_PROJECT,
) -> CheckResult:
    process = run_command(
        [
            "docker",
            "ps",
            "--format",
            '{{.Names}}|{{.Label "com.docker.compose.project"}}|{{.Label "com.docker.compose.service"}}',
        ]
    )
    if process.returncode != 0:
        return CheckResult("conflicting-consumers", False, process.stderr.strip())
    conflicts = parse_conflicting_consumers(process.stdout.splitlines(), current_project)
    return result(
        "conflicting-consumers",
        not conflicts,
        "no legacy orchestration consumers are running",
        f"stop conflicting consumers: {conflicts}",
    )


def _mqtt_utf8(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 65_535:
        raise ValueError("MQTT string is too long")
    return len(encoded).to_bytes(2, "big") + encoded


def _mqtt_remaining_length(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value % 128
        value //= 128
        if value:
            byte |= 0x80
        encoded.append(byte)
        if not value:
            return bytes(encoded)


def mqtt_connack(
    host: str,
    port: int,
    *,
    username: str = "",
    password: str = "",
    timeout: float = 3,
) -> int:
    """Open one MQTT 3.1.1 session and return the CONNACK reason code."""
    flags = 0x02
    payload = _mqtt_utf8(f"ai-cps-preflight-{os.getpid()}")
    if username:
        flags |= 0x80
        payload += _mqtt_utf8(username)
    if password:
        flags |= 0x40
        payload += _mqtt_utf8(password)
    variable = _mqtt_utf8("MQTT") + bytes((4, flags)) + (15).to_bytes(2, "big")
    body = variable + payload
    packet = bytes((0x10,)) + _mqtt_remaining_length(len(body)) + body
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(packet)
        response = connection.recv(4)
    if len(response) != 4 or response[0] != 0x20 or response[1] != 0x02:
        raise OSError(f"invalid MQTT CONNACK: {response.hex() or 'empty'}")
    return response[3]


def check_broker(settings: Mapping[str, str]) -> CheckResult:
    host = settings.get("MQTT_HOST", "").strip()
    try:
        port = int(settings.get("MQTT_PORT", "1883"))
    except ValueError:
        return CheckResult("mqtt-broker", False, "MQTT_PORT must be an integer")
    if not host:
        return CheckResult("mqtt-broker", False, "MQTT_HOST is empty")
    try:
        reason = mqtt_connack(
            host,
            port,
            username=settings.get("MQTT_USER", ""),
            password=settings.get("MQTT_PASS", ""),
        )
    except (OSError, ValueError) as exc:
        return CheckResult("mqtt-broker", False, f"MQTT connection to {host}:{port} failed: {exc}")
    reasons = {
        1: "unsupported protocol version",
        2: "client identifier rejected",
        3: "broker unavailable",
        4: "bad username or password",
        5: "not authorized",
    }
    if reason:
        return CheckResult(
            "mqtt-broker",
            False,
            f"MQTT CONNACK rejected by {host}:{port}: {reasons.get(reason, reason)}",
        )
    return CheckResult("mqtt-broker", True, f"MQTT CONNACK from {host}:{port} succeeded")


def check_env_file(path: Path, settings: Mapping[str, str]) -> list[CheckResult]:
    if not path.is_file():
        return [CheckResult("env-file", False, f"missing environment file: {path}")]
    permissions = path.stat().st_mode & 0o777
    checks = [
        result(
            "env-file-permissions",
            permissions & 0o077 == 0,
            f"{path} is restricted to its owner ({permissions:04o})",
            f"restrict {path} to mode 0600; current mode is {permissions:04o}",
        )
    ]
    project = settings.get("COMPOSE_PROJECT_NAME", DEFAULT_COMPOSE_PROJECT).strip()
    checks.append(
        result(
            "compose-project-name",
            bool(project) and all(character.isalnum() or character in "-_" for character in project),
            f"Compose project: {project}",
            f"invalid COMPOSE_PROJECT_NAME: {project!r}",
        )
    )
    for key in ("AI_CPS_UID", "AI_CPS_GID"):
        raw = settings.get(key, "1000")
        checks.append(
            result(
                f"runtime-identity:{key.lower()}",
                raw.isdigit() and int(raw) >= 0,
                f"{key}={raw}",
                f"{key} must be a non-negative integer, got {raw!r}",
            )
        )
    return checks


def check_virtual_ports(settings: Mapping[str, str]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    project = settings.get("COMPOSE_PROJECT_NAME", DEFAULT_COMPOSE_PROJECT).strip()
    expected_services = {"MQTT_PORT": "mosquitto", "NODE_RED_PORT": "node_red"}
    for key, default in (("MQTT_PORT", 1883), ("NODE_RED_PORT", 1880)):
        raw = settings.get(key, str(default))
        try:
            port = int(raw)
        except ValueError:
            checks.append(CheckResult(f"host-port:{key.lower()}", False, f"invalid port: {raw!r}"))
            continue
        if not 1 <= port <= 65_535:
            checks.append(CheckResult(f"host-port:{key.lower()}", False, f"invalid port: {port}"))
            continue
        available = True
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", port))
        except OSError:
            available = False
        owned_by_runtime = False
        if not available and shutil.which("docker") is not None:
            holders = run_command(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"publish={port}",
                    "--format",
                    '{{.Label "com.docker.compose.project"}}|'
                    '{{.Label "com.docker.compose.service"}}',
                ]
            )
            expected = f"{project}|{expected_services[key]}"
            active = [line.strip() for line in holders.stdout.splitlines() if line.strip()]
            owned_by_runtime = holders.returncode == 0 and active == [expected]
        checks.append(
            result(
                f"host-port:{key.lower()}",
                available or owned_by_runtime,
                f"host port {port} is available"
                if available
                else f"host port {port} is owned by {project}/{expected_services[key]}",
                f"host port {port} is already in use; stop the conflicting service",
            )
        )
    return checks


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_deployment_lock(
    settings: Mapping[str, str], root: Path = PROJECT_ROOT, *, include_node_red: bool
) -> list[CheckResult]:
    complete = {
        domain: settings.get(f"{domain.upper()}_IMAGE", "").strip()
        for domain in (*MODEL_DOMAINS, "node_red")
        if include_node_red or domain != "node_red"
    }
    if not complete or not all(complete.values()):
        return []
    lock_path = root / ".runtime/deployment-lock.json"
    if not lock_path.is_file():
        return [CheckResult("release-lock", False, f"missing release lock: {lock_path}")]
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [CheckResult("release-lock", False, f"invalid release lock: {exc}")]
    expected_images = lock.get("images", {})
    mismatches = [key for key, value in complete.items() if expected_images.get(key) != value]
    checks = [
        result(
            "release-images",
            not mismatches,
            f"image references match release {lock.get('release')}",
            f"image references differ from release lock: {mismatches}",
        )
    ]
    protected = lock.get("protected_files", {})
    invalid = []
    for relative, expected in protected.items() if isinstance(protected, dict) else ():
        path = root / relative
        if not path.is_file() or sha256_file(path) != expected:
            invalid.append(relative)
    checks.append(
        result(
            "release-files",
            not invalid,
            f"all {len(protected)} protected release files match their hashes",
            f"protected release files differ: {invalid}",
        )
    )
    return checks


def check_mqtt_credentials(settings: Mapping[str, str]) -> CheckResult:
    """Prueft nur die in beiden Modi verwendete MQTT-Credential-Kombination."""
    user = settings.get("MQTT_USER", "")
    password = settings.get("MQTT_PASS", "")
    return result(
        "mqtt-credentials",
        not password or bool(user),
        "MQTT credentials are internally consistent",
        "MQTT_PASS is set while MQTT_USER is empty",
    )


def check_nodered_credential_secret(settings: Mapping[str, str]) -> CheckResult:
    """Verlangt das lokale Node-RED-Secret ausschliesslich im virtuellen Modus."""
    secret = settings.get("NODE_RED_CREDENTIAL_SECRET", "")
    weak = not secret or secret in {"ai-cps-local-development", "replace-with-a-long-random-site-secret"}
    return result(
        "nodered-credential-secret",
        not weak,
        "a site-specific Node-RED credential secret is configured",
        "set a site-specific NODE_RED_CREDENTIAL_SECRET in .env",
    )


def check_factory_base_runtimes(settings: Mapping[str, str]) -> list[CheckResult]:
    """Prueft die vier nur virtuell verwendeten Modulbasiszeiten."""
    checks: list[CheckResult] = []
    for module, key in FACTORY_RUNTIME_KEYS.items():
        raw_value = str(settings.get(key, DEFAULT_FACTORY_BASE_RUNTIME_MS)).strip()
        valid_syntax = bool(raw_value) and raw_value.isascii() and raw_value.isdigit()
        runtime_ms = int(raw_value) if valid_syntax else 0
        valid = 0 < runtime_ms <= MAX_JAVASCRIPT_SAFE_INTEGER
        checks.append(
            result(
                f"factory-base-runtime:{module}",
                valid,
                f"{key}={runtime_ms} ms",
                f"{key} must be a positive finite integer in milliseconds, got {raw_value!r}",
            )
        )
    return checks


def check_image_settings(
    settings: Mapping[str, str],
    *,
    include_node_red: bool = False,
) -> list[CheckResult]:
    tag = settings.get("IMAGE_TAG", "").strip()
    image_domains = list(MODEL_DOMAINS) + (["node_red"] if include_node_red else [])
    complete_images = [
        settings.get(f"{domain.upper()}_IMAGE", "").strip()
        for domain in image_domains
    ]
    uses_complete_images = all(complete_images)
    checks = [
        result(
            "image-tag",
            uses_complete_images or (bool(tag) and tag != "local"),
            "complete immutable image references configured"
            if uses_complete_images
            else f"prebuilt image tag: {tag}",
            "set all *_IMAGE references or set IMAGE_TAG to an immutable release or sha-* tag",
        )
    ]
    for domain in image_domains:
        image_key = f"{domain.upper()}_IMAGE"
        image = settings.get(image_key, "").strip()
        key = f"{domain.upper()}_IMAGE_REPOSITORY"
        repository = settings.get(key, "")
        ok = bool(image) or repository.startswith("ghcr.io/")
        selected = image or repository
        checks.append(
            result(
                f"image-repository:{domain}",
                ok,
                selected,
                f"set {image_key} or use a ghcr.io value in {key} with --images",
            )
        )
        if image:
            checks.append(
                result(
                    f"image-digest:{domain}",
                    "@sha256:" in image and len(image.rsplit("@sha256:", 1)[1]) == 64,
                    f"digest-pinned image: {image}",
                    f"{image_key} must contain a full sha256 digest",
                )
            )
    return checks


def check_local_release_images(
    settings: Mapping[str, str], *, include_node_red: bool
) -> list[CheckResult]:
    domains = list(MODEL_DOMAINS) + (["node_red"] if include_node_red else [])
    lock: dict[str, object] = {}
    if DEPLOYMENT_LOCK.is_file():
        try:
            lock = json.loads(DEPLOYMENT_LOCK.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            lock = {}
    source_commit = str(lock.get("source_commit", ""))
    checks: list[CheckResult] = []
    for domain in domains:
        reference = settings.get(f"{domain.upper()}_IMAGE", "").strip()
        if not reference:
            continue
        process = run_command(
            [
                "docker",
                "image",
                "inspect",
                reference,
                "--format",
                "{{json .}}",
            ]
        )
        if process.returncode != 0:
            checks.append(
                CheckResult(
                    f"image-local:{domain}",
                    False,
                    process.stderr.strip() or f"image is not available locally: {reference}",
                )
            )
            continue
        try:
            descriptor = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            checks.append(CheckResult(f"image-local:{domain}", False, str(exc)))
            continue
        os_name = str(descriptor.get("Os", "")).lower()
        architecture = str(descriptor.get("Architecture", "")).lower()
        checks.append(
            result(
                f"image-platform:{domain}",
                os_name == "linux" and architecture == "amd64",
                f"{reference} is linux/amd64",
                f"{reference} has platform {os_name}/{architecture}",
            )
        )
        labels = descriptor.get("Config", {}).get("Labels", {}) or {}
        revision = str(labels.get("org.opencontainers.image.revision", ""))
        if source_commit:
            checks.append(
                result(
                    f"image-revision:{domain}",
                    revision == source_commit,
                    f"image source revision matches {source_commit}",
                    f"image revision {revision or 'missing'} differs from {source_commit}",
                )
            )
    return checks


def collect_checks(
    *,
    mode: str,
    settings: Mapping[str, str],
    use_images: bool,
    root: Path = PROJECT_ROOT,
    env_path: Path | None = None,
) -> list[CheckResult]:
    docker_checks = check_docker()
    docker_ready = any(check.name == "docker" and check.ok for check in docker_checks)
    checks = [
        check_architecture(),
        *docker_checks,
        *check_model_artifacts(root, settings),
        *check_dependency_pins(root),
        check_mqtt_credentials(settings),
    ]
    if env_path is not None:
        checks.extend(check_env_file(env_path, settings))
    if docker_ready:
        checks.extend(check_compose_configs(root, settings, mode))
    if mode == "virtual":
        checks.extend(
            [
                check_nodered_assets(root),
                *check_virtual_experiment_catalog(root),
                check_report_directory(settings, root),
                check_nodered_credential_secret(settings),
                *check_factory_base_runtimes(settings),
                *check_virtual_ports(settings),
            ]
        )
    if docker_ready:
        checks.append(
            check_conflicting_consumers(
                settings.get("COMPOSE_PROJECT_NAME", DEFAULT_COMPOSE_PROJECT)
            )
        )
    if mode == "physical":
        checks.append(check_broker(settings))
    if use_images:
        checks.extend(check_image_settings(settings, include_node_red=mode == "virtual"))
        checks.extend(
            check_deployment_lock(
                settings, root, include_node_red=mode == "virtual"
            )
        )
        if docker_ready:
            checks.extend(
                check_local_release_images(
                    settings, include_node_red=mode == "virtual"
                )
            )
    return checks


def print_human(checks: Iterable[CheckResult]) -> None:
    for check in checks:
        marker = "OK" if check.ok else "FAIL"
        print(f"[{marker:4}] {check.name}: {check.detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("virtual", "physical"))
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--images", action="store_true", help="Prebuilt GHCR image settings pruefen.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        file_values = load_env_file(args.env_file)
    except ValueError as exc:
        print(f"[FAIL] env-file: {exc}", file=sys.stderr)
        return 2
    settings = merged_settings(file_values, os.environ)
    checks = collect_checks(
        mode=args.mode,
        settings=settings,
        use_images=args.images,
        env_path=args.env_file,
    )
    if args.as_json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        print_human(checks)
    return 1 if any(not check.ok and check.severity == "error" for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
