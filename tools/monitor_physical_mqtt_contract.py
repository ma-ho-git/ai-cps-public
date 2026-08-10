"""Zeichnet den eingefrorenen physischen MQTT-Grenzvertrag als JSONL auf.

Das Werkzeug veraendert keine Nachrichten. Es dokumentiert Topic,
Payloadlaenge, Payload-Hash, QoS und Retain-Flag, damit alter Python-Pfad und
neuer Node-RED-Pfad vor der Anlagenfreigabe objektiv verglichen werden koennen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt


DEFAULT_TOPICS = (
    "log/logging/state",
    "ai/vgr/#",
    "ai/hbw/#",
    "ai/mpo/#",
    "ai/sld/#",
)


def message_record(msg: Any, *, include_payload: bool = False) -> dict[str, Any]:
    """Verdichtet eine Paho-Nachricht auf auditierbare Schnittstellenmerkmale."""
    payload = bytes(msg.payload)
    record: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "topic": str(msg.topic),
        "payload_length": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "qos": int(msg.qos),
        "retain": bool(msg.retain),
    }
    if include_payload:
        record["payload_utf8"] = payload.decode("utf-8", errors="replace")
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-payload", action="store_true")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    handle = args.output.open("a", encoding="utf-8")

    def on_connect(client: mqtt.Client, _userdata: Any, _flags: Any, rc: int) -> None:
        if rc != 0:
            raise ConnectionError(f"MQTT connection failed with rc={rc}")
        for topic in DEFAULT_TOPICS:
            client.subscribe(topic, qos=2)
        print(f"[MONITOR] subscribed to {', '.join(DEFAULT_TOPICS)}", flush=True)

    def on_message(_client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        record = message_record(msg, include_payload=args.include_payload)
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        print(
            f"[MONITOR] {record['topic']} bytes={record['payload_length']} "
            f"qos={record['qos']} retain={record['retain']}",
            flush=True,
        )

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    try:
        time.sleep(max(0.0, args.duration_s))
    finally:
        client.loop_stop()
        client.disconnect()
        handle.close()
    print(f"[MONITOR] capture written to {args.output}", flush=True)


if __name__ == "__main__":
    main()
