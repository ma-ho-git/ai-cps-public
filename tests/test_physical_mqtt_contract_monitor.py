"""Prueft den passiven Mitschnitt des physischen MQTT-Grenzvertrags."""

import unittest

from tools.compare_physical_mqtt_contract_captures import compare_captures
from tools.monitor_physical_mqtt_contract import message_record


class FakeMessage:
    topic = "ai/vgr/cmd101"
    payload = b""
    qos = 2
    retain = False


class PhysicalMqttContractMonitorTests(unittest.TestCase):
    def test_empty_command_payload_and_delivery_flags_are_recorded(self):
        record = message_record(FakeMessage())

        self.assertEqual(record["topic"], "ai/vgr/cmd101")
        self.assertEqual(record["payload_length"], 0)
        self.assertEqual(record["qos"], 2)
        self.assertFalse(record["retain"])
        self.assertEqual(len(record["payload_sha256"]), 64)
        self.assertNotIn("payload_utf8", record)

    def test_capture_comparison_ignores_time_but_detects_qos_changes(self):
        reference = [{
            "captured_at": "old",
            "topic": "ai/vgr/cmd101",
            "payload_length": 0,
            "payload_sha256": "x",
            "qos": 2,
            "retain": False,
        }]
        candidate = [{**reference[0], "captured_at": "new"}]
        self.assertEqual(compare_captures(reference, candidate), [])

        candidate[0]["qos"] = 1
        self.assertTrue(compare_captures(reference, candidate))


if __name__ == "__main__":
    unittest.main()
