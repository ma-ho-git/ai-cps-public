#!/usr/bin/env python3
"""Zeigt MQTT-Modellinput und zugehoerige NN-Vorhersage kompakt an.

Der Beobachter ist ein rein passiver MQTT-Client. Er veraendert keine
Nachricht und publiziert nichts. Requests und Responses werden ausschliesslich
ueber ihre bestehende `request_id` korreliert.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import paho.mqtt.client as mqtt


DOMAINS = ("storage", "vgr", "hbw")
DOMAIN_LABELS = {"storage": "Storage", "vgr": "VGR", "hbw": "HBW"}
REQUEST_TOPICS = {domain: f"ft/nn/{domain}/request" for domain in DOMAINS}
RESPONSE_TOPICS = {domain: f"ft/nn/response/{domain}" for domain in DOMAINS}
REQUEST_DOMAINS = {topic: domain for domain, topic in REQUEST_TOPICS.items()}
RESPONSE_DOMAINS = {topic: domain for domain, topic in RESPONSE_TOPICS.items()}
CONTRACT_PATTERN = re.compile(r"^ft/nn/(storage|vgr|hbw)/contract$")
STORAGE_FEATURE_PATTERN = re.compile(r"^storage_slot_(\d+)_occupied$")
EMPTY_STORAGE_PATTERN = re.compile(r"^empty_storage_(\d+)$")
SUBSCRIPTIONS = (
    *REQUEST_TOPICS.values(),
    *RESPONSE_TOPICS.values(),
    "ft/nn/+/contract",
)


@dataclass(frozen=True)
class PendingMessage:
    """Haelt eine noch nicht korrelierte MQTT-Nachricht zeitlich begrenzt."""

    payload: dict[str, Any]
    received_at: float


def parse_json_payload(payload: bytes | str | dict[str, Any]) -> dict[str, Any]:
    """Dekodiert MQTT-Bytes und akzeptiert nur JSON-Objekte."""
    if isinstance(payload, dict):
        value: Any = payload
    else:
        text = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("payload_is_not_an_object")
    return value


def compact_error(value: Any, max_length: int = 120) -> str:
    """Haelt mehrzeilige oder sehr lange Fehler in einer Terminalzeile."""
    text = " ".join(str(value).split()) or "unknown_error"
    return text if len(text) <= max_length else text[: max_length - 3] + "..."


def compact_identifier(value: Any, max_length: int = 30) -> str:
    """Kuerzt lange Trace-IDs nur fuer die Anzeige und behaelt beide Enden."""
    text = str(value)
    if len(text) <= max_length:
        return text
    prefix_length = (max_length - 2) // 2
    suffix_length = max_length - 3 - prefix_length
    return f"{text[:prefix_length]}...{text[-suffix_length:]}"


def probability_for_prediction(response: dict[str, Any], key: str, prediction: Any) -> float | None:
    """Liest die Wahrscheinlichkeit der ausgewaehlten Klasse aus `top3`."""
    for candidate in response.get("top3", []):
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get(key)) != str(prediction):
            continue
        try:
            return float(candidate["p"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def bit_value(value: Any) -> str:
    """Verdichtet einen binaeren Storage-Wert auf `0`, `1` oder `?`."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "?"
    if number == 0.0:
        return "0"
    if number == 1.0:
        return "1"
    return "?"


def storage_input_summary(request: dict[str, Any], contract: dict[str, Any] | None) -> str:
    """Stellt die neun Lagerbelegungen als kurze Bitfolge dar."""
    features = request.get("features")
    if isinstance(features, list):
        return "slots:" + "".join(bit_value(value) for value in features)

    source = features if isinstance(features, dict) else request
    contract_cols = contract.get("feature_cols", []) if contract else []
    columns = [str(column) for column in contract_cols if str(column) in source]
    if not columns:
        indexed_columns = []
        for column in source:
            match = STORAGE_FEATURE_PATTERN.match(str(column))
            if match:
                indexed_columns.append((int(match.group(1)), str(column)))
        columns = [column for _, column in sorted(indexed_columns)]
    if not columns:
        return "slots:unknown"
    return "slots:" + "".join(bit_value(source[column]) for column in columns)


def lstm_input_summary(request: dict[str, Any], contract: dict[str, Any] | None) -> str:
    """Zeigt Fensterform und, falls ableitbar, das aktuell freie Fach."""
    sequence = request.get("sequence")
    if not isinstance(sequence, list):
        return "window:unknown"
    rows = len(sequence)
    first_row = sequence[0] if sequence else []
    columns = len(first_row) if isinstance(first_row, list) else 0
    summary = f"window:{rows}x{columns}"

    if not sequence or not isinstance(sequence[-1], list) or not contract:
        return summary
    feature_cols = contract.get("feature_cols")
    last_row = sequence[-1]
    if not isinstance(feature_cols, list) or len(feature_cols) != len(last_row):
        return summary

    active_slots = []
    for index, feature in enumerate(feature_cols):
        match = EMPTY_STORAGE_PATTERN.match(str(feature))
        if match and bit_value(last_row[index]) == "1":
            active_slots.append(int(match.group(1)))
    if len(active_slots) == 1:
        summary += f" empty_storage={active_slots[0]}"
    return summary


def prediction_summary(domain: str, response: dict[str, Any]) -> str:
    """Verdichtet Storage- oder Command-Response auf den Top-1-Wert."""
    if response.get("error") not in (None, ""):
        return f"ERROR={compact_error(response['error'])}"

    if domain == "storage":
        prediction = response.get("empty_storage", "?")
        probability = probability_for_prediction(response, "empty_storage", prediction)
        result = f"empty_storage={prediction}"
    else:
        prediction = response.get("cmd", "?")
        probability = probability_for_prediction(response, "cmd", prediction)
        name = compact_error(response.get("name", ""), max_length=60)
        result = f"cmd={prediction}"
        if name != "unknown_error":
            result += f" {name}"
    if probability is not None:
        result += f" p={probability:.3f}"
    return result


class InferenceObserver:
    """Korreliert MQTT-Requests und -Responses ohne Prozessseiteneffekte."""

    def __init__(
        self,
        *,
        pending_ttl_s: float = 300.0,
        max_pending: int = 2000,
        max_completed: int = 5000,
        monotonic: Callable[[], float] = time.monotonic,
        time_label: Callable[[], str] = lambda: datetime.now().strftime("%H:%M:%S"),
    ) -> None:
        self.pending_ttl_s = float(pending_ttl_s)
        self.max_pending = int(max_pending)
        self.max_completed = int(max_completed)
        self.monotonic = monotonic
        self.time_label = time_label
        self.contracts: dict[str, dict[str, Any]] = {}
        self.requests: dict[tuple[str, str], PendingMessage] = {}
        self.responses: dict[tuple[str, str], PendingMessage] = {}
        self.completed: set[tuple[str, str]] = set()
        self.completed_order: deque[tuple[str, str]] = deque()

    def _error_line(self, topic: str, reason: str) -> str:
        return f"[{self.time_label()}] Observer topic={topic} ERROR={compact_error(reason)}"

    def _purge_expired(self, now: float) -> None:
        for cache in (self.requests, self.responses):
            expired = [
                key
                for key, message in cache.items()
                if now - message.received_at > self.pending_ttl_s
            ]
            for key in expired:
                cache.pop(key, None)

    def _limit_pending(self, cache: dict[tuple[str, str], PendingMessage]) -> None:
        while len(cache) > self.max_pending:
            cache.pop(next(iter(cache)))

    def _remember_completed(self, key: tuple[str, str]) -> None:
        self.completed.add(key)
        self.completed_order.append(key)
        while len(self.completed_order) > self.max_completed:
            self.completed.discard(self.completed_order.popleft())

    def _format_pair(
        self,
        domain: str,
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> str:
        cycle_id = compact_identifier(response.get("cycle_id", request.get("cycle_id", "-")))
        source_id = compact_identifier(response.get("source_id", request.get("source_id", "-")))
        if domain == "storage":
            input_summary = storage_input_summary(request, self.contracts.get(domain))
        else:
            input_summary = lstm_input_summary(request, self.contracts.get(domain))
        prediction = prediction_summary(domain, response)
        label = f"{DOMAIN_LABELS[domain]:<7}"
        return (
            f"[{self.time_label()}] {label} cycle={cycle_id} source={source_id} "
            f"input={input_summary} -> {prediction}"
        )

    def _handle_correlated(
        self,
        domain: str,
        payload: dict[str, Any],
        *,
        is_request: bool,
        now: float,
    ) -> list[str]:
        request_id = payload.get("request_id")
        if request_id in (None, ""):
            topic = REQUEST_TOPICS[domain] if is_request else RESPONSE_TOPICS[domain]
            return [self._error_line(topic, "missing_request_id")]

        key = (domain, str(request_id))
        if key in self.completed:
            return []
        own_cache = self.requests if is_request else self.responses
        other_cache = self.responses if is_request else self.requests
        if key in own_cache:
            return []

        counterpart = other_cache.pop(key, None)
        if counterpart is None:
            own_cache[key] = PendingMessage(payload=payload, received_at=now)
            self._limit_pending(own_cache)
            return []

        self._remember_completed(key)
        request = payload if is_request else counterpart.payload
        response = counterpart.payload if is_request else payload
        return [self._format_pair(domain, request, response)]

    def handle_message(self, topic: str, payload: bytes | str | dict[str, Any]) -> list[str]:
        """Verarbeitet eine MQTT-Nachricht und liefert null oder eine Ausgabezeile."""
        now = self.monotonic()
        self._purge_expired(now)
        try:
            decoded = parse_json_payload(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            reason = "invalid_json" if isinstance(error, json.JSONDecodeError) else str(error)
            return [self._error_line(topic, reason)]

        contract_match = CONTRACT_PATTERN.match(topic)
        if contract_match:
            self.contracts[contract_match.group(1)] = decoded
            return []
        if topic in REQUEST_DOMAINS:
            return self._handle_correlated(
                REQUEST_DOMAINS[topic], decoded, is_request=True, now=now
            )
        if topic in RESPONSE_DOMAINS:
            return self._handle_correlated(
                RESPONSE_DOMAINS[topic], decoded, is_request=False, now=now
            )
        return []


def parse_args() -> argparse.Namespace:
    """Liest Brokerparameter mit denselben Umgebungsvariablen wie die Dienste."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    parser.add_argument("--username", default=os.environ.get("MQTT_USER", ""))
    parser.add_argument("--password", default=os.environ.get("MQTT_PASS", ""))
    parser.add_argument(
        "--pending-ttl-s",
        type=float,
        default=300.0,
        help="Sekunden bis unvollstaendige Request-/Response-Paare verworfen werden.",
    )
    return parser.parse_args()


def main() -> None:
    """Verbindet den passiven Beobachter und gibt Treffer bis Ctrl+C aus."""
    args = parse_args()
    observer = InferenceObserver(pending_ttl_s=args.pending_ttl_s)
    client_id = f"ai-cps-inference-observer-{socket.gethostname()}-{os.getpid()}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

    def on_connect(
        connected_client: mqtt.Client,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        if getattr(reason_code, "is_failure", False):
            print(f"[OBSERVER] MQTT connection failed: {reason_code}", flush=True)
            return
        for topic in SUBSCRIPTIONS:
            connected_client.subscribe(topic, qos=1)
        print(
            f"[OBSERVER] passive connection to {args.host}:{args.port}; "
            "waiting for Storage/VGR/HBW requests and responses (Ctrl+C to stop)",
            flush=True,
        )

    def on_message(
        _client: mqtt.Client,
        _userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        for line in observer.handle_message(str(message.topic), message.payload):
            print(line, flush=True)

    client.on_connect = on_connect
    client.on_message = on_message
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.connect(args.host, args.port, keepalive=60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[OBSERVER] stopped", flush=True)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
