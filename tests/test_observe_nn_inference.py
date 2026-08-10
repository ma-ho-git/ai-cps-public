"""Tests fuer die passive, kompakte MQTT-Inferenzbeobachtung."""

from __future__ import annotations

import json
import unittest

from tools.observe_nn_inference import InferenceObserver, compact_identifier


class MutableClock:
    """Stellt reproduzierbare Zeitwerte fuer Cache- und Ausgabechecks bereit."""

    def __init__(self) -> None:
        self.value = 10.0

    def monotonic(self) -> float:
        return self.value

    @staticmethod
    def label() -> str:
        return "12:34:56"


class InferenceObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()
        self.observer = InferenceObserver(
            pending_ttl_s=5.0,
            monotonic=self.clock.monotonic,
            time_label=self.clock.label,
        )

    def send(self, topic: str, payload: dict | str) -> list[str]:
        encoded = payload if isinstance(payload, str) else json.dumps(payload)
        return self.observer.handle_message(topic, encoded)

    def test_storage_request_and_response_are_printed_together_once(self) -> None:
        request = {
            "cycle_id": "cycle-1",
            "request_id": "cycle-1:storage",
            "source_id": "factory-a",
            "features": {
                f"storage_slot_{slot}_occupied": int(slot <= 2)
                for slot in range(1, 10)
            },
        }
        response = {
            "cycle_id": "cycle-1",
            "request_id": "cycle-1:storage",
            "source_id": "factory-a",
            "empty_storage": 3,
            "top3": [{"empty_storage": 3, "name": "first_free_slot_3", "p": 0.9996}],
        }

        self.assertEqual(self.send("ft/nn/storage/request", request), [])
        lines = self.send("ft/nn/response/storage", response)

        self.assertEqual(len(lines), 1)
        self.assertIn("[12:34:56] Storage", lines[0])
        self.assertIn("cycle=cycle-1", lines[0])
        self.assertIn("source=factory-a", lines[0])
        self.assertIn("input=slots:110000000", lines[0])
        self.assertIn("-> empty_storage=3 p=1.000", lines[0])
        self.assertEqual(self.send("ft/nn/response/storage", response), [])

    def test_lstm_contract_reconstructs_window_and_empty_storage(self) -> None:
        contract = {
            "domain": "vgr",
            "feature_cols": ["sensor", "empty_storage_0", "empty_storage_3"],
        }
        request = {
            "cycle_id": "cycle-2",
            "request_id": "cycle-2:vgr",
            "source_id": "factory-a",
            "sequence": [[0, 1, 0], [1, 0, 1]],
        }
        response = {
            "cycle_id": "cycle-2",
            "request_id": "cycle-2:vgr",
            "source_id": "factory-a",
            "cmd": 101,
            "name": "vgr_start_insourcing",
            "top3": [{"cmd": 101, "name": "vgr_start_insourcing", "p": 0.9986}],
        }

        self.send("ft/nn/vgr/contract", contract)
        self.send("ft/nn/vgr/request", request)
        lines = self.send("ft/nn/response/vgr", response)

        self.assertEqual(len(lines), 1)
        self.assertIn("VGR", lines[0])
        self.assertIn("input=window:2x3 empty_storage=3", lines[0])
        self.assertIn("-> cmd=101 vgr_start_insourcing p=0.999", lines[0])

    def test_hbw_response_before_request_is_correlated(self) -> None:
        response = {
            "cycle_id": "cycle-3",
            "request_id": "cycle-3:hbw",
            "source_id": "factory-a",
            "cmd": 111,
            "name": "hbw_slot_1_start",
            "top3": [{"cmd": 111, "name": "hbw_slot_1_start", "p": 0.95}],
        }
        request = {
            "cycle_id": "cycle-3",
            "request_id": "cycle-3:hbw",
            "source_id": "factory-a",
            "sequence": [[0, 1], [1, 0]],
        }

        self.assertEqual(self.send("ft/nn/response/hbw", response), [])
        lines = self.send("ft/nn/hbw/request", request)

        self.assertEqual(len(lines), 1)
        self.assertIn("HBW", lines[0])
        self.assertIn("input=window:2x2", lines[0])
        self.assertNotIn("empty_storage=", lines[0])
        self.assertIn("-> cmd=111 hbw_slot_1_start p=0.950", lines[0])

    def test_error_response_is_short_and_does_not_raise(self) -> None:
        request = {
            "cycle_id": "cycle-4",
            "request_id": "cycle-4:vgr",
            "source_id": "factory-a",
            "sequence": [[0]],
        }
        response = {
            "cycle_id": "cycle-4",
            "request_id": "cycle-4:vgr",
            "source_id": "factory-a",
            "error": "Sequence shape mismatch\nwith details",
        }

        self.send("ft/nn/vgr/request", request)
        lines = self.send("ft/nn/response/vgr", response)

        self.assertEqual(len(lines), 1)
        self.assertIn("ERROR=Sequence shape mismatch with details", lines[0])

    def test_invalid_json_and_missing_request_id_are_reported(self) -> None:
        malformed = self.send("ft/nn/storage/request", "{not-json")
        missing_id = self.send("ft/nn/storage/request", {"features": [0] * 9})

        self.assertIn("ERROR=invalid_json", malformed[0])
        self.assertIn("ERROR=missing_request_id", missing_id[0])

    def test_expired_orphan_is_not_combined_with_late_response(self) -> None:
        request = {
            "cycle_id": "cycle-5",
            "request_id": "cycle-5:storage",
            "source_id": "factory-a",
            "features": [0] * 9,
        }
        response = {
            "cycle_id": "cycle-5",
            "request_id": "cycle-5:storage",
            "empty_storage": 1,
        }

        self.send("ft/nn/storage/request", request)
        self.clock.value += 6.0

        self.assertEqual(self.send("ft/nn/response/storage", response), [])

    def test_long_identifiers_are_shortened_without_losing_their_ends(self) -> None:
        value = "cycle-live-plc-trace-with-a-very-long-source-name-000123"

        compact = compact_identifier(value, max_length=30)

        self.assertEqual(len(compact), 30)
        self.assertTrue(compact.startswith("cycle-live-plc"))
        self.assertTrue(compact.endswith("name-000123"))
        self.assertIn("...", compact)


if __name__ == "__main__":
    unittest.main()
