"""Vertragstests fuer die direkte Command-Ausgabe der beiden LSTM-Dienste."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios/serve_ft_nns_external_broker/x86_64"


class PublishInfo:
    def __init__(self, mid: int):
        self.rc = 0
        self.mid = mid


class FakeClient:
    def __init__(self):
        self.published: list[tuple[str, str, int, bool]] = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return PublishInfo(len(self.published))


def load_service(domain: str):
    path = SCENARIO / f"code_base_{domain}/mqtt_infer.py"
    spec = importlib.util.spec_from_file_location(f"test_{domain}_mqtt_infer", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    fake_tensorflow = types.SimpleNamespace(keras=types.SimpleNamespace(models=types.SimpleNamespace()))
    with (
        mock.patch.dict(os.environ, {"COMMAND_OUTPUT_ENABLED": "true"}, clear=False),
        mock.patch.dict(sys.modules, {"tensorflow": fake_tensorflow}),
    ):
        spec.loader.exec_module(module)
    return module


class DirectCommandOutputTests(unittest.TestCase):
    def test_vgr_and_hbw_publish_one_command_and_replay_only_json_for_duplicate(self):
        fixtures = {
            "vgr": (101, "vgr_start", "ai/vgr/cmd101"),
            "hbw": (111, "hbw_start", "ai/hbw/cmd111"),
        }
        for domain, (command, name, command_topic) in fixtures.items():
            with self.subTest(domain=domain):
                service = load_service(domain)
                service.CONTRACT = {"model_id": f"{domain}:test"}
                service.COMMAND_TOPICS = {0: f"ai/{domain}/cmd0", command: command_topic}
                service.RESPONSE_CACHE = service.ResponseCache()
                service.predict = lambda _sequence, values=(command, name): (
                    values[0],
                    values[1],
                    [{"cmd": values[0], "name": values[1], "p": 1.0}],
                )
                request = {
                    "cycle_id": "cycle-1",
                    "request_id": f"cycle-1:{domain}",
                    "source_id": "factory-a",
                    "sequence": [[0.0]],
                }
                message = types.SimpleNamespace(payload=json.dumps(request).encode("utf-8"))
                client = FakeClient()

                service.on_message(client, None, message)
                service.on_message(client, None, message)

                command_messages = [item for item in client.published if item[0].startswith("ai/")]
                response_messages = [
                    item for item in client.published if item[0] == service.MQTT_RES_TOPIC
                ]
                self.assertEqual(command_messages, [(command_topic, "", 2, False)])
                self.assertEqual(len(response_messages), 2)
                first_response = json.loads(response_messages[0][1])
                replayed_response = json.loads(response_messages[1][1])
                self.assertEqual(first_response, replayed_response)
                self.assertEqual(first_response["cmd"], command)
                self.assertTrue(first_response["command_output"]["published"])

    def test_diagnosis_mode_keeps_json_response_without_command(self):
        service = load_service("vgr")
        service.COMMAND_OUTPUT_ENABLED = False
        service.CONTRACT = {"model_id": "vgr:test"}
        service.COMMAND_TOPICS = {101: "ai/vgr/cmd101"}
        service.RESPONSE_CACHE = service.ResponseCache()
        service.predict = lambda _sequence: (
            101,
            "vgr_start",
            [{"cmd": 101, "name": "vgr_start", "p": 1.0}],
        )
        message = types.SimpleNamespace(
            payload=json.dumps(
                {
                    "cycle_id": "cycle-1",
                    "request_id": "cycle-1:vgr",
                    "sequence": [[0.0]],
                }
            ).encode("utf-8")
        )
        client = FakeClient()

        service.on_message(client, None, message)

        self.assertFalse(any(topic.startswith("ai/") for topic, *_ in client.published))
        response = json.loads(client.published[0][1])
        self.assertEqual(response["command_output"]["reason"], "disabled")

    def test_vgr_and_hbw_error_responses_keep_all_correlation_fields(self):
        for domain in ("vgr", "hbw"):
            with self.subTest(domain=domain):
                service = load_service(domain)
                service.CONTRACT = {"model_id": f"{domain}:test"}
                service.RESPONSE_CACHE = service.ResponseCache()
                request = {
                    "cycle_id": "cycle-error",
                    "request_id": f"cycle-error:{domain}",
                    "source_id": "factory-a",
                    # Eine fehlende Sequenz erzwingt einen verarbeitbaren Fehler
                    # nach erfolgreicher JSON- und Korrelationsfeld-Auswertung.
                }
                message = types.SimpleNamespace(payload=json.dumps(request).encode("utf-8"))
                client = FakeClient()

                service.on_message(client, None, message)

                self.assertEqual(len(client.published), 1)
                topic, payload, qos, retain = client.published[0]
                self.assertEqual(topic, service.MQTT_RES_TOPIC)
                self.assertEqual((qos, retain), (service.MQTT_QOS, False))
                response = json.loads(payload)
                self.assertEqual(response["request_id"], request["request_id"])
                self.assertEqual(response["cycle_id"], request["cycle_id"])
                self.assertEqual(response["source_id"], request["source_id"])
                self.assertEqual(response["model_id"], f"{domain}:test")
                self.assertIn("error", response)
                self.assertFalse(any(item[0].startswith("ai/") for item in client.published))


if __name__ == "__main__":
    unittest.main()
