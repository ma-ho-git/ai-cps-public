"""Kontinuierliche virtuelle Zustandserfassung."""

from .common import (
    _change,
    _comment,
    _group,
    _json,
    _link_out,
    _mqtt_out,
    _set,
    _switch,
)

ACTIVE_EXPRESSION = (
    "$globalContext('sim.run').running = true and "
    "$not($globalContext('sim.run').fault) and "
    "$count($globalContext('sim.run').trace) > 0"
)
def _publisher_nodes() -> list[dict]:
    """Rohzustand alle 50 ms publizieren."""
    tab = "tab-state"
    group = "group-state-publisher"
    return [
            _group(group, tab, "50-ms-Rohzustand", 20, 20, 1660, 300),
            _comment("comment-state", tab, "Tick | Index halten | Rohzustand per MQTT", 330, 45),
            {
                "id": "inject-raw-state", "type": "inject", "z": tab, "g": group,
                "name": "Zustand alle 50 ms", "props": [{"p": "payload"}],
                "repeat": "0.05", "crontab": "", "once": True, "onceDelay": 0.1,
                "topic": "", "payload": "", "payloadType": "date",
                "x": 160, "y": 110, "wires": [["switch-raw-active"]],
            },
            _switch("switch-raw-active", tab, group, "Simulation aktiv?", ACTIVE_EXPRESSION,
                    [{"t": "true"}], 350, 110, [["change-raw-context"]],
                    prop_type="jsonata", info="Lauf aktiv | Trace geladen | kein Fault"),
            _change("change-raw-context", tab, group, "Lauf + Index lesen", [
                _set("_run", "msg", "$globalContext('sim.run')", "jsonata"),
                _set("_trace_index", "msg", "$min([$number(_run.trace_index),$count(_run.trace)-1])", "jsonata"),
                _set("sim.run.raw_samples", "global", "$number(_run.raw_samples)+1", "jsonata"),
            ], 560, 110, [["change-raw-payload"]], info="Run lesen | raw_samples++ | Traceindex nicht erhoehen"),
            _change("change-raw-payload", tab, group, "Rohzustand abbilden", [
                _set("payload", "msg", "_run.trace[$$._trace_index]", "jsonata"),
                _set("payload.simulation_run_id", "msg", "_run.run_id", "msg"),
                _set("payload.correlation_id", "msg", "_run.run_id", "msg"),
                _set("payload.trace_index", "msg", "_trace_index", "msg"),
                _set("payload.trace_profile", "msg", "_run.config.trace_profile", "msg"),
                _set("payload.trace_profile_name", "msg", "_run.config.trace_profile_name", "msg"),
                _set("payload.model_profile", "msg", "_run.config.model_profile", "msg"),
                _set("payload.model_profile_name", "msg", "_run.config.model_profile_name", "msg"),
                _set("payload.factory_seed", "msg", "_run.config.seed", "msg"),
                _set("payload.factory_base_runtime_ms", "msg", "_run.config.base_runtime_ms", "msg"),
                _set("payload.module_runtime_ms", "msg", "_run.module_runtime_ms", "msg"),
                _set("payload.module_job_counts.sent", "msg", "_run.sent", "msg"),
                _set("payload.module_job_counts.accepted", "msg", "_run.accepted", "msg"),
                _set("payload._final_wait", "msg", "_run.trace_index >= $count(_run.trace)", "jsonata"),
                _set("topic", "msg", "ft/sim/factory/raw_state", "str"),
                _set("qos", "msg", "1", "num"),
                _set("retain", "msg", "false", "bool"),
            ], 790, 110, [["json-raw-state"]], info="Tracezeile + Laufmetadaten | kein Indexwechsel"),
            _json("json-raw-state", tab, group, "Rohzustand JSON", 1010, 110, [["out-raw-state"]]),
            _mqtt_out("out-raw-state", tab, group, "Virtueller Rohzustand",
                      "ft/sim/factory/raw_state", "1", "false", 1230, 110),
    ]


def _diagnostic_nodes() -> list[dict]:
    """Flow- und MQTT-Fehler weiterleiten."""
    tab = "tab-state"
    group = "group-state-publisher"
    return [
            {"id": "catch-state", "type": "catch", "z": tab, "g": group,
             "name": "Zustandsfehler", "scope": ["change-raw-context", "change-raw-payload", "json-raw-state"],
             "uncaught": False, "x": 170, "y": 220, "wires": [["change-catch-state"]]},
            _change("change-catch-state", tab, group, "Fehler normalisieren", [
                _set("payload", "msg", "{'code':'runtime_error','detail':error.message,'source':error.source.name}", "jsonata")
            ], 380, 220, [["link-fault-state"]]),
            _link_out("link-fault-state", tab, group, "Zum Fault-Latch", ["link-fault-central"], 580, 220),
            {"id": "status-mqtt-state", "type": "status", "z": tab, "g": group,
             "name": "MQTT-Zustand", "scope": ["out-raw-state"], "x": 810, "y": 220,
             "wires": [["switch-mqtt-state"]]},
            _switch("switch-mqtt-state", tab, group, "MQTT getrennt?", "status.text",
                    [{"t": "regex", "v": "disconnected|error", "vt": "str", "case": False}],
                    1010, 220, [["change-mqtt-state"]]),
            _change("change-mqtt-state", tab, group, "MQTT-Fehler", [
                _set("payload", "msg", "{'code':'mqtt_disconnected','detail':status.text,'source':'state_publisher'}", "jsonata")
            ], 1200, 220, [["link-fault-state-mqtt"]]),
            _link_out("link-fault-state-mqtt", tab, group, "Zum Fault-Latch", ["link-fault-central"], 1400, 220),
    ]


def build_state_nodes() -> list[dict]:
    """Zustandserfassung aus zwei sichtbaren Pfaden."""
    return _publisher_nodes() + _diagnostic_nodes()
