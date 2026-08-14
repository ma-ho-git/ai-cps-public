"""Vertraege und Baukastenstruktur der virtuellen Node-RED-Laufzeit."""

import json
import unittest
from pathlib import Path

from tools.export_nodered_ai_flow import OUTPUT, SOURCE, extract_ai_flow


CORE_NODE_TYPES = {
    "catch", "change", "comment", "debug", "delay", "file", "file in",
    "function", "group", "inject", "join", "json", "link in", "link out",
    "mqtt in", "mqtt out", "mqtt-broker", "split", "status", "switch", "tab",
}
DASHBOARD_NODE_TYPES = {
    "ui-base", "ui-button", "ui-chart", "ui-form", "ui-group",
    "ui-notification", "ui-page", "ui-progress", "ui-table", "ui-template",
    "ui-text", "ui-theme",
}
FUNCTION_INFO_SECTIONS = (
    "### Aufgabe", "### Eingang", "### Ausgang", "### Warum Function-Node?",
)


def load_flows():
    return json.loads(Path(SOURCE).read_text(encoding="utf-8"))


def nodes_by_id(flows):
    return {node["id"]: node for node in flows}


class NodeRedFlowExportTests(unittest.TestCase):
    def test_committed_ai_reference_export_matches_full_flow(self):
        source = load_flows()
        exported = json.loads(Path(OUTPUT).read_text(encoding="utf-8"))

        self.assertEqual(exported, extract_ai_flow(source))
        self.assertTrue(any(node.get("id") == "tab-pipeline" for node in exported))
        self.assertFalse(any(node.get("z") == "tab-modules" for node in exported))
        self.assertTrue(any(node.get("topic") == "log/logging/state" for node in exported))

    def test_only_core_and_flowfuse_nodes_are_used(self):
        flows = load_flows()
        self.assertEqual(len({node["id"] for node in flows}), len(flows))
        self.assertEqual(
            {node["type"] for node in flows} - CORE_NODE_TYPES - DASHBOARD_NODE_TYPES,
            set(),
        )
        for required in {
            "catch", "change", "delay", "file in", "group", "join", "status",
            "switch",
        }:
            self.assertTrue(any(node["type"] == required for node in flows), required)

    def test_functional_tabs_and_four_module_groups_exist(self):
        flows = load_flows()
        nodes = nodes_by_id(flows)
        self.assertEqual(
            {nodes[node_id]["label"] for node_id in (
                "tab-init", "tab-state", "tab-modules", "tab-semaphore", "tab-pipeline",
            )},
            {
                "00 Initialisierung", "10 Zustandserfassung", "20 Virtuelle Module",
                "30 Semaphor", "40 NN-Pipeline",
            },
        )
        for module in ("vgr", "hbw", "mpo", "sld"):
            group = nodes[f"group-module-{module}"]
            self.assertIn(module.upper(), group["name"])
            self.assertEqual(nodes[f"delay-module-{module}"]["pauseType"], "delayv")
            self.assertIn(f"sent_count", nodes[f"fn-module-{module}-gate"]["func"])
            self.assertIn(f"accepted_count", nodes[f"fn-module-{module}-complete"]["func"])
            self.assertIn("flow.get", nodes[f"fn-module-{module}-gate"]["func"])
            self.assertIn("flow.set", nodes[f"fn-module-{module}-runtime"]["func"])

    def test_function_nodes_are_self_contained_and_documented(self):
        flows = load_flows()
        for node in (node for node in flows if node["type"] == "function"):
            with self.subTest(node_id=node["id"]):
                for section in FUNCTION_INFO_SECTIONS:
                    self.assertIn(section, node.get("info", ""))
                self.assertEqual(node.get("libs"), [])
                self.assertNotIn("global.get('aiCps", node["func"])
                self.assertNotIn('require("./lib/', node["func"])
                self.assertIn("//", node["func"])

        settings = Path(SOURCE).with_name("settings.js").read_text(encoding="utf-8")
        self.assertIn("functionGlobalContext: {}", settings)
        self.assertNotIn("require(\"./lib/", settings)

    def test_trace_is_the_only_file_input(self):
        flows = load_flows()
        file_inputs = [node for node in flows if node["type"] == "file in"]
        self.assertEqual([node["id"] for node in file_inputs], ["file-trace"])
        self.assertEqual(file_inputs[0]["filename"], "filename")
        self.assertEqual(file_inputs[0]["filenameType"], "msg")
        split = next(node for node in flows if node["id"] == "split-trace-lines")
        self.assertEqual(split["splt"], "\n")
        trim = next(node for node in flows if node["id"] == "change-trim-trace")
        self.assertEqual(trim["rules"], [{
            "t": "change", "p": "payload", "pt": "msg",
            "from": r"\s+$", "fromt": "re", "to": "", "tot": "str",
        }])
        parts = next(node for node in flows if node["id"] == "change-trace-parts")
        self.assertEqual(parts["rules"][0]["to"], "array")
        self.assertEqual(parts["rules"][1]["t"], "delete")

    def test_all_literal_change_node_json_values_are_valid(self):
        for node in (node for node in load_flows() if node["type"] == "change"):
            for rule in node.get("rules", []):
                if rule.get("tot") == "json":
                    with self.subTest(node_id=node["id"]):
                        json.loads(rule["to"])

    def test_raw_state_and_semaphore_contract(self):
        nodes = nodes_by_id(load_flows())
        self.assertEqual(nodes["inject-raw-state"]["repeat"], "0.05")
        self.assertEqual(nodes["out-raw-state"]["topic"], "ft/sim/factory/raw_state")
        self.assertEqual(nodes["out-raw-state"]["qos"], "1")
        self.assertEqual(nodes["out-raw-state"]["retain"], "false")
        self.assertEqual(nodes["in-raw-semaphore"]["topic"], "ft/sim/factory/raw_state")
        self.assertEqual(nodes["out-live-release"]["topic"], "log/logging/state")
        semaphore = nodes["fn-semaphore"]["func"]
        for marker in ("sent", "accepted", "last_release_sent", "trace_index", "semaphore_stalled"):
            self.assertIn(marker, semaphore)
        self.assertNotIn("raw_state", nodes["debug-semaphore"].get("complete", ""))
        self.assertEqual(nodes["change-debug-semaphore"]["wires"], [["debug-semaphore"]])

    def test_initialization_publishes_exactly_four_idle_commands(self):
        flows = load_flows()
        nodes = nodes_by_id(flows)
        expected = {
            "vgr": "ai/vgr/cmd0", "hbw": "ai/hbw/cmd000",
            "mpo": "ai/mpo/cmd0", "sld": "ai/sld/cmd0",
        }
        for module, topic in expected.items():
            out = nodes[f"out-module-{module}-idle"]
            self.assertEqual(out["topic"], topic)
            self.assertEqual(out["qos"], "2")
            self.assertEqual(out["retain"], "false")
        self.assertEqual(
            {node["id"] for node in flows if node.get("name") == "Initiales Idle"},
            {f"out-module-{module}-idle" for module in expected},
        )

    def test_pipeline_preserves_model_and_command_contracts(self):
        nodes = nodes_by_id(load_flows())
        expected = {
            "in-live-pipeline": ("log/logging/state", "1"),
            "in-contracts": ("ft/nn/+/contract", "1"),
            "in-model-statuses": ("ft/nn/+/status", "1"),
            "in-storage-result": ("ft/nn/response/storage", "1"),
            "in-vgr-response": ("ft/nn/response/vgr", "1"),
            "in-hbw-response": ("ft/nn/response/hbw", "1"),
        }
        for node_id, (topic, qos) in expected.items():
            self.assertEqual((nodes[node_id]["topic"], nodes[node_id]["qos"]), (topic, qos))
        self.assertIn("direct_mqtt", nodes["fn-contract-gate"]["func"])
        self.assertIn("commandTopics", nodes["fn-contract-gate"]["func"])
        self.assertEqual(nodes["fn-window-vgr"]["wires"][0][0], "json-vgr-request")
        self.assertEqual(nodes["fn-window-hbw"]["wires"][0][0], "json-hbw-request")
        self.assertIn("keine Command-Barriere", nodes["fn-cycle-result"]["info"])

    def test_targeted_error_status_and_debug_nodes_exist(self):
        flows = load_flows()
        self.assertGreaterEqual(sum(node["type"] == "catch" for node in flows), 5)
        self.assertGreaterEqual(sum(node["type"] == "status" for node in flows), 4)
        debug_names = {node["name"] for node in flows if node["type"] == "debug"}
        for name in {
            "Initialisierung abgeschlossen", "Semaphorfreigabe", "Storage-Ergebnis",
            "VGR-Request Kurzinfo", "HBW-Request Kurzinfo", "Fault-Latch",
        }:
            self.assertIn(name, debug_names)
        self.assertNotIn("Rohzustand", debug_names)

    def test_reporting_and_group_references_are_consistent(self):
        flows = load_flows()
        nodes = nodes_by_id(flows)
        self.assertEqual(nodes["file-report-append-inline"]["overwriteFile"], "false")
        self.assertEqual(nodes["file-report-replace-inline"]["overwriteFile"], "true")
        self.assertEqual(nodes["in-report-factory-status"]["topic"], "ft/sim/factory/status")
        self.assertNotIn("fn-report-cycle-inline", nodes)
        self.assertIn("CSV-Vertrag", nodes["fn-report-row"]["func"])
        self.assertIn("factory_run_id", nodes["fn-report-state"]["func"])
        self.assertIn("columns=[", nodes["fn-report-csv"]["func"])
        self.assertIn("factory_status", nodes["fn-report-summary"]["func"])
        for flow_group in (node for node in flows if node["type"] == "group"):
            for member_id in flow_group["nodes"]:
                self.assertIn(member_id, nodes)
                self.assertEqual(nodes[member_id].get("g"), flow_group["id"])

    def test_function_nodes_are_bounded_and_documented(self):
        functions = [node for node in load_flows() if node["type"] == "function"]
        self.assertLessEqual(max(len(node["func"].splitlines()) for node in functions), 60)
        for node in functions:
            self.assertIn("### Aufgabe", node.get("info", ""), node["name"])
            self.assertIn("### Eingang", node.get("info", ""), node["name"])
            self.assertIn("### Ausgang", node.get("info", ""), node["name"])
        names = {node["name"] for node in functions}
        self.assertIn("Widgetdaten bilden", names)
        self.assertIn("Reportzaehler aktualisieren", names)
        self.assertNotIn("HMI-Zustand aufbereiten", names)
        self.assertNotIn("Reportdateien bilden", names)

    def test_virtual_hmi_exposes_semaphore_and_existing_controls(self):
        flows = load_flows()
        nodes = nodes_by_id(flows)
        self.assertEqual(nodes["ui-hmi-base"]["path"], "/dashboard")
        self.assertEqual(nodes["ui-hmi-page-operation"]["path"], "/betrieb")
        self.assertEqual(nodes["ui-hmi-page-diagnosis"]["path"], "/diagnose")
        for node_id in ("ui-hmi-semaphore", "ui-hmi-raw-count", "ui-hmi-release-count"):
            self.assertEqual(nodes[node_id]["type"], "ui-text")
        form = nodes["ui-hmi-run-form"]
        self.assertEqual(form["formValue"]["trace_profile"], "standard")
        self.assertEqual(form["formValue"]["model_profile"], "deployment-current")
        self.assertIn("reproduziert Vollspeicherfehler", str(form["dropdownOptions"]))
        source_meta = nodes["ui-hmi-source-meta"]["format"]
        self.assertIn("runtime-v1.3.0-rc.1", source_meta)
        self.assertIn("AGPL-3.0", source_meta)
        self.assertEqual(nodes["ui-hmi-trace"]["className"], "hmi-run-summary")
        styles = nodes["ui-hmi-table-layout-style"]["format"]
        self.assertIn("@media (max-width: 600px)", styles)
        self.assertEqual(nodes["ui-hmi-errors"]["className"], "hmi-diagnosis-table")
        self.assertEqual(
            [column["key"] for column in nodes["ui-hmi-errors"]["columns"]],
            ["timestamp", "summary"],
        )
        self.assertEqual(nodes["ui-hmi-cycles"]["className"], "hmi-diagnosis-table")
        self.assertEqual(
            [column["key"] for column in nodes["ui-hmi-cycles"]["columns"]],
            ["timestamp", "summary"],
        )

    def test_dashboard_dependency_is_pinned_outside_persistent_data(self):
        node_red_dir = Path(SOURCE).parent
        package = json.loads((node_red_dir / "dashboard_runtime/package.json").read_text(encoding="utf-8"))
        lock = json.loads((node_red_dir / "dashboard_runtime/package-lock.json").read_text(encoding="utf-8"))
        dockerfile = (node_red_dir / "Dockerfile").read_text(encoding="utf-8")
        settings = (node_red_dir / "settings.js").read_text(encoding="utf-8")
        self.assertEqual(package["dependencies"]["@flowfuse/node-red-dashboard"], "1.30.2")
        self.assertEqual(lock["packages"]["node_modules/@flowfuse/node-red-dashboard"]["version"], "1.30.2")
        self.assertIn("/opt/ai-cps-dashboard", dockerfile)
        self.assertIn("nodesDir", settings)


if __name__ == "__main__":
    unittest.main()
