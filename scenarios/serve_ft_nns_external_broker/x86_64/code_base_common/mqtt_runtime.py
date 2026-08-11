"""Gemeinsamer MQTT-Laufzeitvertrag der zustandslosen NN-Dienste.

Die Inferenzcontainer bleiben bewusst frei von Orchestrierungszustand. Dieses
Modul beschreibt nur ihren Modellvertrag, ihren Online-Status und die
Korrelationsmetadaten, die Node-RED fuer einen sicheren Zyklus benoetigt.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
CORRELATION_FIELDS = (
    "cycle_id",
    "request_id",
    "source_id",
    "parent_request_id",
    "model_id",
    "model_profile",
)
COMMAND_QOS = 2
COMMAND_RETAIN = False


def file_sha256(path: str | Path) -> str:
    """Berechnet eine reproduzierbare Modellkennung aus dem Keras-Artefakt."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_model_contract(
    *,
    domain: str,
    activation: dict[str, Any],
    model_path: str | Path,
    request_topic: str,
    response_topic: str,
    command_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Leitet den maschinenlesbaren MQTT-Vertrag aus `activation.json` ab."""
    feature_cols = [str(col) for col in activation["feature_cols"]]
    class_ids = [int(value) for value in activation["class_ids"]]
    time_steps_raw = activation.get("time_steps")
    time_steps = None if time_steps_raw is None else int(time_steps_raw)
    input_shape = activation.get("input_shape") or activation.get("architecture", {}).get("input_shape")
    if input_shape is None:
        input_shape = [len(feature_cols)] if time_steps is None else [time_steps, len(feature_cols)]

    model_hash = file_sha256(model_path)
    trained_at = str(activation.get("trained_at", "unknown"))
    contract = {
        "schema_version": SCHEMA_VERSION,
        "domain": str(domain),
        "model_id": f"{domain}:{trained_at}:{model_hash[:12]}",
        "model_sha256": model_hash,
        "input_shape": [int(value) for value in input_shape],
        "time_steps": time_steps,
        "feature_cols": feature_cols,
        "class_ids": class_ids,
        "request_topic": str(request_topic),
        "response_topic": str(response_topic),
        "published_at": time.time(),
    }
    if command_output is not None:
        contract["command_output"] = dict(command_output)
    return contract


def env_flag(name: str, default: bool = False) -> bool:
    """Liest einen expliziten booleschen Schalter aus der Umgebung."""
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false, got {raw!r}")


def load_command_topic_map(path: str | Path, domain: str) -> dict[int, str]:
    """Liest das zentrale physische Command-Mapping fuer eine Modelldomaene."""
    config_path = Path(path)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read command topics from {config_path}: {exc}") from exc
    raw_mapping = config.get("command_topics", {}).get(str(domain))
    if not isinstance(raw_mapping, dict) or not raw_mapping:
        raise ValueError(f"{config_path} has no command mapping for {domain}")
    mapping: dict[int, str] = {}
    for raw_command, raw_topic in raw_mapping.items():
        command = int(raw_command)
        topic = str(raw_topic)
        if not topic:
            raise ValueError(f"empty command topic for {domain} command {command}")
        mapping[command] = topic
    return mapping


def command_output_contract(
    *,
    command_topics: dict[int, str],
    enabled: bool,
) -> dict[str, Any]:
    """Beschreibt die additive direkte Command-Faehigkeit eines NN-Dienstes."""
    return {
        "mode": "direct_mqtt",
        "enabled": bool(enabled),
        "payload": "empty",
        "qos": COMMAND_QOS,
        "retain": COMMAND_RETAIN,
        "topics": {str(command): topic for command, topic in sorted(command_topics.items())},
    }


def publish_direct_command(
    client: Any,
    *,
    domain: str,
    command: int,
    command_topics: dict[int, str],
    enabled: bool,
) -> dict[str, Any]:
    """Publiziert genau einen leeren Maschinenbefehl oder meldet Diagnosemodus."""
    command_value = int(command)
    topic = command_topics.get(command_value)
    if topic is None:
        raise ValueError(f"{domain} command {command_value} has no physical topic mapping")
    if not enabled:
        return {
            "enabled": False,
            "published": False,
            "reason": "disabled",
            "topic": topic,
            "qos": COMMAND_QOS,
            "retain": COMMAND_RETAIN,
        }

    info = client.publish(topic, "", qos=COMMAND_QOS, retain=COMMAND_RETAIN)
    rc = int(getattr(info, "rc", 0))
    if rc != 0:
        raise RuntimeError(f"{domain} command publish failed for {topic}: rc={rc}")
    return {
        "enabled": True,
        "published": True,
        "reason": "published",
        "topic": topic,
        "qos": COMMAND_QOS,
        "retain": COMMAND_RETAIN,
        "mid": getattr(info, "mid", None),
    }


class ResponseCache:
    """Begrenzt doppelte QoS-1-Requests auf eine einzige Command-Ausgabe."""

    def __init__(self, max_entries: int = 5000):
        self.max_entries = int(max_entries)
        self._responses: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def get(self, request_id: str) -> dict[str, Any] | None:
        response = self._responses.get(str(request_id))
        if response is None:
            return None
        self._responses.move_to_end(str(request_id))
        return dict(response)

    def remember(self, request_id: str, response: dict[str, Any]) -> None:
        key = str(request_id)
        if not key:
            raise ValueError("request_id is required for idempotent command output")
        self._responses[key] = dict(response)
        self._responses.move_to_end(key)
        while len(self._responses) > self.max_entries:
            self._responses.popitem(last=False)


def correlation_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Uebernimmt nur die fuer asynchrone Antwortkorrelation erlaubten Felder."""
    return {
        field: payload[field]
        for field in CORRELATION_FIELDS
        if field in payload and payload[field] not in (None, "")
    }


def response_payload(request: dict[str, Any], **values: Any) -> dict[str, Any]:
    """Erzeugt eine Response, die den Orchestrierungszyklus eindeutig behaelt."""
    return {**correlation_metadata(request), **values, "ts": time.time()}


def status_payload(*, domain: str, model_id: str, state: str, detail: str = "") -> dict[str, Any]:
    """Erzeugt einen retained Dienststatus fuer Node-RED und Diagnosewerkzeuge."""
    return {
        "schema_version": SCHEMA_VERSION,
        "domain": str(domain),
        "model_id": str(model_id),
        "state": str(state),
        "detail": str(detail),
        "instance_id": os.environ.get("HOSTNAME", socket.gethostname()),
        "ts": time.time(),
    }


def configure_last_will(client: Any, *, status_topic: str, domain: str, qos: int = 1) -> None:
    """Setzt den retained Offline-Status, bevor die Broker-Verbindung entsteht."""
    payload = status_payload(domain=domain, model_id="unknown", state="offline", detail="mqtt_disconnect")
    client.will_set(status_topic, json.dumps(payload), qos=qos, retain=True)


def publish_contract_and_status(
    client: Any,
    *,
    contract_topic: str,
    status_topic: str,
    contract: dict[str, Any],
    qos: int = 1,
) -> None:
    """Publiziert retained Vertrag und Online-Status nach jedem Reconnect."""
    client.publish(contract_topic, json.dumps(contract), qos=qos, retain=True)
    online = status_payload(
        domain=str(contract["domain"]),
        model_id=str(contract["model_id"]),
        state="online",
        detail="model_loaded",
    )
    client.publish(status_topic, json.dumps(online), qos=qos, retain=True)
