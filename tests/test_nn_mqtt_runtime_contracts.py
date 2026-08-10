"""Vertragstests fuer die retained Metadaten der zustandslosen NN-Dienste."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "scenarios/serve_ft_nns_external_broker/x86_64/code_base_common/mqtt_runtime.py"
)
SPEC = importlib.util.spec_from_file_location("nn_mqtt_runtime", MODULE_PATH)
runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime)


class FakeClient:
    """Speichert MQTT-Aufrufe, ohne einen Broker zu benoetigen."""

    def __init__(self):
        self.published = []
        self.will = None

    def publish(self, topic, payload, qos=0, retain=False):
        decoded = "" if payload == "" else json.loads(payload)
        self.published.append((topic, decoded, qos, retain))
        return type("PublishInfo", (), {"rc": 0, "mid": len(self.published)})()

    def will_set(self, topic, payload, qos=0, retain=False):
        self.will = (topic, json.loads(payload), qos, retain)


class ModelContractTests(unittest.TestCase):
    def test_contract_is_derived_from_activation_and_model_hash(self):
        activation = {
            "feature_cols": ["a", "empty_storage_0"],
            "class_ids": [0, 101],
            "time_steps": 10,
            "input_shape": [10, 2],
            "trained_at": "2026-01-02_030405",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "model.keras"
            model_path.write_bytes(b"model-content")
            contract = runtime.build_model_contract(
                domain="vgr",
                activation=activation,
                model_path=model_path,
                request_topic="ft/nn/vgr/request",
                response_topic="ft/nn/response/vgr",
            )

        self.assertEqual(contract["schema_version"], "1.0")
        self.assertEqual(contract["domain"], "vgr")
        self.assertEqual(contract["input_shape"], [10, 2])
        self.assertEqual(contract["time_steps"], 10)
        self.assertEqual(contract["feature_cols"], activation["feature_cols"])
        self.assertEqual(contract["class_ids"], [0, 101])
        self.assertTrue(contract["model_id"].startswith("vgr:2026-01-02_030405:"))
        self.assertEqual(len(contract["model_sha256"]), 64)

    def test_response_keeps_cycle_and_source_metadata(self):
        response = runtime.response_payload(
            {
                "cycle_id": "cycle-7",
                "request_id": "req-7-vgr",
                "source_id": "factory-a",
                "ignored": "not echoed",
            },
            cmd=101,
        )

        self.assertEqual(response["cycle_id"], "cycle-7")
        self.assertEqual(response["request_id"], "req-7-vgr")
        self.assertEqual(response["source_id"], "factory-a")
        self.assertEqual(response["cmd"], 101)
        self.assertNotIn("ignored", response)

    def test_contract_status_and_last_will_are_retained_qos_one(self):
        client = FakeClient()
        contract = {"domain": "storage", "model_id": "storage:test"}

        runtime.configure_last_will(client, status_topic="ft/nn/storage/status", domain="storage")
        runtime.publish_contract_and_status(
            client,
            contract_topic="ft/nn/storage/contract",
            status_topic="ft/nn/storage/status",
            contract=contract,
        )

        self.assertEqual(client.will[0], "ft/nn/storage/status")
        self.assertEqual(client.will[1]["state"], "offline")
        self.assertEqual(client.will[2:], (1, True))
        self.assertEqual(client.published[0][0], "ft/nn/storage/contract")
        self.assertEqual(client.published[0][2:], (1, True))
        self.assertEqual(client.published[1][1]["state"], "online")
        self.assertEqual(client.published[1][2:], (1, True))

    def test_direct_command_uses_empty_payload_qos_two_and_no_retain(self):
        client = FakeClient()

        result = runtime.publish_direct_command(
            client,
            domain="vgr",
            command=101,
            command_topics={0: "ai/vgr/cmd0", 101: "ai/vgr/cmd101"},
            enabled=True,
        )

        self.assertEqual(client.published, [("ai/vgr/cmd101", "", 2, False)])
        self.assertEqual(result["published"], True)
        self.assertEqual(result["topic"], "ai/vgr/cmd101")

    def test_disabled_command_output_reports_topic_without_publishing(self):
        client = FakeClient()

        result = runtime.publish_direct_command(
            client,
            domain="hbw",
            command=0,
            command_topics={0: "ai/hbw/cmd000"},
            enabled=False,
        )

        self.assertEqual(client.published, [])
        self.assertEqual(result["reason"], "disabled")
        self.assertEqual(result["topic"], "ai/hbw/cmd000")

    def test_unknown_command_is_rejected_before_publish(self):
        client = FakeClient()

        with self.assertRaisesRegex(ValueError, "no physical topic mapping"):
            runtime.publish_direct_command(
                client,
                domain="vgr",
                command=999,
                command_topics={0: "ai/vgr/cmd0"},
                enabled=True,
            )

        self.assertEqual(client.published, [])

    def test_response_cache_replays_result_without_repeating_command_state(self):
        cache = runtime.ResponseCache(max_entries=2)
        cache.remember("request-1", {"cmd": 101, "command_output": {"published": True}})

        replay = cache.get("request-1")
        replay["cmd"] = 0

        self.assertEqual(cache.get("request-1")["cmd"], 101)
        cache.remember("request-2", {"cmd": 0})
        cache.remember("request-3", {"cmd": 111})
        self.assertIsNone(cache.get("request-1"))


if __name__ == "__main__":
    unittest.main()
