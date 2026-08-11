"""Sichert den MQTT-kompatiblen KI-Referenz-Subflow ab."""

import json
import unittest
from pathlib import Path

from tools.export_nodered_ai_flow import OUTPUT, SOURCE, extract_ai_flow


CORE_NODE_TYPES = {
    "change",
    "comment",
    "debug",
    "file",
    "function",
    "group",
    "inject",
    "json",
    "mqtt in",
    "mqtt out",
    "mqtt-broker",
    "split",
    "switch",
    "tab",
}

DASHBOARD_NODE_TYPES = {
    "ui-base",
    "ui-button",
    "ui-chart",
    "ui-form",
    "ui-group",
    "ui-notification",
    "ui-page",
    "ui-progress",
    "ui-table",
    "ui-template",
    "ui-text",
    "ui-theme",
}

FUNCTION_INFO_SECTIONS = (
    "### Aufgabe",
    "### Eingang",
    "### Zustand",
    "### Ausgang",
    "### Warum Function-Node?",
)


def nodes_by_id(flows):
    return {node["id"]: node for node in flows}


class NodeRedFlowExportTests(unittest.TestCase):
    def test_committed_ai_reference_export_matches_full_flow(self):
        source = json.loads(Path(SOURCE).read_text(encoding="utf-8"))
        exported = json.loads(Path(OUTPUT).read_text(encoding="utf-8"))

        self.assertEqual(exported, extract_ai_flow(source))
        self.assertTrue(any(node.get("id") == "tab-ai-orchestration" for node in exported))
        self.assertFalse(any(node.get("z") == "tab-virtual-factory" for node in exported))
        self.assertTrue(any(node.get("topic") == "log/logging/state" for node in exported))

    def test_full_flow_uses_only_node_red_core_building_blocks(self):
        flows = json.loads(Path(SOURCE).read_text(encoding="utf-8"))

        self.assertEqual(
            {node["type"] for node in flows} - CORE_NODE_TYPES - DASHBOARD_NODE_TYPES,
            set(),
        )
        for required_type in {"change", "group", "json", "split", "switch"}:
            self.assertTrue(any(node["type"] == required_type for node in flows), required_type)

    def test_monolithic_function_nodes_are_replaced_by_bounded_core_calls(self):
        flows = json.loads(Path(SOURCE).read_text(encoding="utf-8"))
        nodes = nodes_by_id(flows)

        self.assertNotIn("fn-ai-orchestration", nodes)
        self.assertNotIn("fn-virtual-factory", nodes)
        self.assertEqual(
            {node["id"] for node in flows if node["type"] == "function"},
            {"fn-ai-runtime", "fn-report-cycle", "fn-factory-runtime", "fn-hmi-view-model"},
        )

        ai_code = nodes["fn-ai-runtime"]["func"]
        self.assertIn("runtime.handleEvent", ai_code)
        self.assertNotIn("msg.topic ===", ai_code)
        self.assertNotIn("JSON.stringify", ai_code)
        self.assertNotIn("outputs =", ai_code)

        factory_code = nodes["fn-factory-runtime"]["func"]
        self.assertIn("factory.handleControl", factory_code)
        self.assertIn("factory.handleCommand", factory_code)
        self.assertNotIn("msg.topic ===", factory_code)
        self.assertNotIn("JSON.stringify", factory_code)
        self.assertNotIn("outputs =", factory_code)

        reporting_code = nodes["fn-report-cycle"]["func"]
        self.assertIn("reporting.recordCycle", reporting_code)
        self.assertIn("reporting.finalizeRun", reporting_code)
        self.assertNotIn("JSON.stringify", reporting_code)

        hmi_code = nodes["fn-hmi-view-model"]["func"]
        self.assertIn("hmi.handle", hmi_code)
        self.assertNotIn("mqtt", hmi_code.lower())
        self.assertNotIn("node.send", hmi_code)

    def test_remaining_function_nodes_explain_their_bounded_state(self):
        flows = json.loads(Path(SOURCE).read_text(encoding="utf-8"))
        nodes = nodes_by_id(flows)
        expected_references = {
            "fn-ai-runtime": ("lib/orchestration.js", "context.runtime"),
            "fn-report-cycle": ("lib/reporting.js", "context.reportState"),
            "fn-factory-runtime": ("lib/virtual_factory.js", "context.factory"),
            "fn-hmi-view-model": ("lib/hmi.js", "context.hmi"),
        }

        for node_id, references in expected_references.items():
            with self.subTest(node_id=node_id):
                node = nodes[node_id]
                self.assertEqual(node["type"], "function")
                for section in FUNCTION_INFO_SECTIONS:
                    self.assertIn(section, node["info"])
                for reference in references:
                    self.assertIn(reference, node["info"])
                self.assertIn("//", node["func"])

        self.assertIn("Warum bleibt hier ein Function-Node?", nodes["comment-ai-core"]["info"])
        self.assertIn("Warum bleibt hier ein Function-Node?", nodes["comment-factory-core"]["info"])

    def test_virtual_hmi_uses_dashboard_two_and_existing_mqtt_contracts(self):
        flows = json.loads(Path(SOURCE).read_text(encoding="utf-8"))
        nodes = nodes_by_id(flows)

        self.assertEqual(nodes["ui-hmi-base"]["path"], "/dashboard")
        self.assertEqual(nodes["ui-hmi-page-operation"]["path"], "/betrieb")
        self.assertEqual(nodes["ui-hmi-page-diagnosis"]["path"], "/diagnose")
        for node_type in {
            "ui-form", "ui-button", "ui-text", "ui-progress",
            "ui-table", "ui-chart", "ui-notification", "ui-template",
        }:
            self.assertTrue(any(node["type"] == node_type for node in flows), node_type)

        self.assertEqual(nodes["in-hmi-model-status"]["topic"], "ft/nn/+/status")
        self.assertEqual(nodes["in-hmi-ai-status"]["topic"], "ft/ai/orchestration/status")
        self.assertEqual(nodes["in-hmi-cycle-result"]["topic"], "ft/ai/orchestration/cycle_result")
        self.assertEqual(nodes["in-hmi-factory-status"]["topic"], "ft/sim/factory/status")
        self.assertEqual(nodes["out-hmi-control"]["broker"], "mqtt-ai-cps")
        self.assertIn("ft/sim/factory/control", str(nodes["change-hmi-start"]["rules"]))

        form = nodes["ui-hmi-run-form"]
        self.assertEqual(form["formValue"]["trace_profile"], "standard")
        self.assertEqual(form["formValue"]["seed"], 42)
        self.assertEqual(
            {option["value"] for option in form["dropdownOptions"]},
            {"standard", "full-storage-attempt", "full-storage-process-guard"},
        )
        self.assertIn("grid-row: 1 / -1", nodes["ui-hmi-table-layout-style"]["format"])
        for table_id in (
            "ui-hmi-modules",
            "ui-hmi-predictions",
            "ui-hmi-models",
            "ui-hmi-cycles",
            "ui-hmi-errors",
        ):
            self.assertFalse(nodes[table_id]["autocols"])
            self.assertTrue(nodes[table_id]["columns"])
        self.assertEqual(nodes["ui-hmi-latencies"]["category"], "series")
        self.assertEqual(nodes["ui-hmi-latencies"]["categoryType"], "property")
        for text_id in ("ui-hmi-status", "ui-hmi-trace", "ui-hmi-mode"):
            self.assertEqual(
                nodes[text_id]["layout"],
                "col-center",
                "Statuswerte muessen auch im schmalen Mobile-Viewport sichtbar bleiben",
            )
        source_meta = nodes["ui-hmi-source-meta"]["format"]
        self.assertIn("https://github.com/ma-ho-git/ai-cps-runtime", source_meta)
        self.assertIn("runtime-v1.1.1", source_meta)
        self.assertIn("AGPL-3.0", source_meta)

    def test_dashboard_dependency_is_pinned_outside_persistent_data(self):
        node_red_dir = Path(SOURCE).parent
        package = json.loads(
            (node_red_dir / "dashboard_runtime/package.json").read_text(encoding="utf-8")
        )
        lock = json.loads(
            (node_red_dir / "dashboard_runtime/package-lock.json").read_text(encoding="utf-8")
        )
        dockerfile = (node_red_dir / "Dockerfile").read_text(encoding="utf-8")
        settings = (node_red_dir / "settings.js").read_text(encoding="utf-8")

        self.assertEqual(package["dependencies"]["@flowfuse/node-red-dashboard"], "1.30.2")
        self.assertEqual(
            lock["packages"]["node_modules/@flowfuse/node-red-dashboard"]["version"],
            "1.30.2",
        )
        self.assertIn("/opt/ai-cps-dashboard", dockerfile)
        self.assertNotIn("npm install --prefix /data", dockerfile)
        self.assertIn("nodesDir", settings)
        self.assertIn("/opt/ai-cps-dashboard/node_modules/@flowfuse/node-red-dashboard", settings)

    def test_ingress_event_mapping_and_action_routing_are_visible_nodes(self):
        flows = json.loads(Path(SOURCE).read_text(encoding="utf-8"))
        nodes = nodes_by_id(flows)
        ai_ingress = {
            "in-live-state": "change-event-live-state",
            "in-model-contracts": "change-event-contract",
            "in-model-status": "change-event-status",
            "in-storage-response": "change-event-storage-response",
            "in-vgr-response": "change-event-vgr-response",
            "in-hbw-response": "change-event-hbw-response",
            "in-ai-control": "change-event-ai-control",
            "inject-ai-tick": "change-event-ai-tick",
        }
        factory_ingress = {
            "in-factory-control": "change-event-factory-control",
            "in-factory-commands": "change-event-factory-command",
            "in-factory-ai-status": "change-event-factory-status",
            "inject-factory-tick": "change-event-factory-tick",
        }

        for source, mapper in ai_ingress.items():
            self.assertEqual(nodes[source]["wires"], [[mapper]])
            self.assertEqual(nodes[mapper]["type"], "change")
            self.assertEqual(nodes[mapper]["wires"], [["fn-ai-runtime"]])
        for source, mapper in factory_ingress.items():
            self.assertEqual(nodes[source]["wires"], [[mapper]])
            self.assertEqual(nodes[mapper]["type"], "change")
            self.assertEqual(
                nodes[mapper]["wires"],
                [["change-factory-runtime-config"]],
            )

        runtime_config = nodes["change-factory-runtime-config"]
        self.assertEqual(runtime_config["type"], "change")
        self.assertEqual(runtime_config["wires"], [["fn-factory-runtime"]])
        self.assertEqual(
            runtime_config["rules"],
            [
                {
                    "t": "set",
                    "p": f"_factory_base_runtime_ms.{module}",
                    "pt": "msg",
                    "to": f"FACTORY_{module.upper()}_BASE_RUNTIME_MS",
                    "tot": "env",
                }
                for module in ("vgr", "hbw", "mpo", "sld")
            ],
        )
        self.assertEqual(nodes["inject-factory-tick"]["repeat"], "0.05")
        self.assertIn("baseRuntimeMs", nodes["fn-factory-runtime"]["func"])
        self.assertNotIn("minRuntimeMs", nodes["fn-factory-runtime"]["func"])
        self.assertNotIn("maxRuntimeMs", nodes["fn-factory-runtime"]["func"])

        self.assertEqual(nodes["fn-ai-runtime"]["wires"], [["split-ai-actions"]])
        self.assertEqual(nodes["split-ai-actions"]["wires"], [["change-ai-action"]])
        self.assertEqual(nodes["change-ai-action"]["wires"], [["switch-ai-action-role"]])
        self.assertEqual(
            nodes["switch-ai-action-role"]["wires"][1],
            ["out-physical-commands"],
            "Empty command payloads must bypass JSON serialization",
        )
        self.assertEqual(nodes["out-physical-commands"]["name"], "MPO-/SLD-Idle-Topics")
        self.assertIn("Direkte VGR-/HBW-Commands", nodes["comment-ai-actions"]["info"])
        self.assertIn(
            "VGR und HBW publizieren ihre Maschinencommands direkt",
            nodes["fn-ai-runtime"]["info"],
        )

    def test_reporting_and_group_references_are_consistent(self):
        flows = json.loads(Path(SOURCE).read_text(encoding="utf-8"))
        nodes = nodes_by_id(flows)

        self.assertEqual(nodes["file-report-append"]["overwriteFile"], "false")
        self.assertEqual(nodes["file-run-summary"]["overwriteFile"], "true")
        self.assertEqual(nodes["switch-report-file"]["outputs"], 2)
        self.assertEqual(nodes["in-report-factory-status"]["topic"], "ft/sim/factory/status")
        self.assertEqual(nodes["in-report-factory-status"]["qos"], "1")
        self.assertEqual(
            nodes["in-report-factory-status"]["wires"],
            [["switch-report-factory-status"]],
        )
        self.assertEqual(
            nodes["change-report-factory-status"]["wires"],
            [["fn-report-cycle"]],
        )

        for group in (node for node in flows if node["type"] == "group"):
            for member_id in group["nodes"]:
                self.assertIn(member_id, nodes)
                self.assertEqual(nodes[member_id].get("g"), group["id"])

    def test_existing_mqtt_ingress_contract_is_unchanged(self):
        flows = json.loads(Path(SOURCE).read_text(encoding="utf-8"))
        nodes = nodes_by_id(flows)
        expected = {
            "in-live-state": ("log/logging/state", "1"),
            "in-model-contracts": ("ft/nn/+/contract", "1"),
            "in-model-status": ("ft/nn/+/status", "1"),
            "in-storage-response": ("ft/nn/response/storage", "1"),
            "in-vgr-response": ("ft/nn/response/vgr", "1"),
            "in-hbw-response": ("ft/nn/response/hbw", "1"),
            "in-ai-control": ("ft/ai/orchestration/control", "1"),
            "in-factory-control": ("ft/sim/factory/control", "1"),
            "in-factory-commands": ("ai/+/+", "2"),
            "in-factory-ai-status": ("ft/ai/orchestration/status", "1"),
        }

        for node_id, (topic, qos) in expected.items():
            self.assertEqual(nodes[node_id]["topic"], topic)
            self.assertEqual(nodes[node_id]["qos"], qos)

        status_rules = nodes["change-factory-status-output"]["rules"]
        self.assertIn(
            {"t": "set", "p": "topic", "pt": "msg", "to": "ft/sim/factory/status", "tot": "str"},
            status_rules,
        )
        self.assertIn(
            {"t": "set", "p": "retain", "pt": "msg", "to": "true", "tot": "bool"},
            status_rules,
        )


if __name__ == "__main__":
    unittest.main()
