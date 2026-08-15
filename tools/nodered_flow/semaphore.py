"""Jobcounter vergleichen und Tracezustand freigeben."""

from .common import (
    FUNCTION_INFO,
    SEMAPHORE_FUNCTION,
    _change,
    _comment,
    _debug,
    _delete,
    _function,
    _group,
    _json,
    _link_out,
    _mqtt_in,
    _mqtt_out,
    _object_rules,
    _set,
    _switch,
)

def _status_rules(state: str, *, completed: bool = False) -> list[dict]:
    """Semaphorstatus Feld fuer Feld bilden."""
    fields = [
        ("state", state, "str"), ("run_id", "_run.run_id", "msg"),
        ("trace_total", "$count(_run.trace)", "jsonata"), ("payloads_sent", "_run.releases", "msg"),
        ("raw_samples", "_run.raw_samples", "msg"), ("released_states", "_run.releases", "msg"),
        ("semaphore_state", "open", "str"), ("sent_counts", "_run.sent", "msg"),
        ("accepted_counts", "_run.accepted", "msg"),
        ("trace_profile", "_run.config.trace_profile", "msg"),
        ("trace_profile_name", "_run.config.trace_profile_name", "msg"),
        ("model_profile", "_run.config.model_profile", "msg"),
        ("model_profile_name", "_run.config.model_profile_name", "msg"),
        ("seed", "_run.config.seed", "msg"), ("base_runtime_ms", "_run.config.base_runtime_ms", "msg"),
        ("progress_percent", "100" if completed else "$round((_run.releases/$count(_run.trace))*10000)/100", "num" if completed else "jsonata"),
        ("ts_ms", "$millis()", "jsonata"),
    ]
    if not completed:
        fields[3:3] = [("payload_index", "_semaphore.release_index", "msg")]
        fields.extend([
            ("module_runtime_ms", "_run.module_runtime_ms", "msg"),
            ("command_topics", "_run.command_topics", "msg"),
        ])
    return _object_rules("_factory_status", "msg", fields)


def _decision_nodes() -> list[dict]:
    """Counter pruefen, freigeben oder abschliessen."""
    tab = "tab-semaphore"
    group = "group-semaphore"
    return [
            _group(group, tab, "Jobcounter-Semaphor", 20, 20, 1780, 430),
            _comment("comment-semaphore", tab, "Rohzustand | 4 Counterpaare | genau eine Freigabe", 370, 45),
            _mqtt_in("in-raw-semaphore", tab, group, "Rohzustand empfangen",
                     "ft/sim/factory/raw_state", "1", 140, 120, [["json-raw-semaphore"]]),
            _json("json-raw-semaphore", tab, group, "Rohzustand JSON", 340, 120, [["fn-semaphore"]], "obj"),
            _function("fn-semaphore", tab, "Semaphor atomar entscheiden", SEMAPHORE_FUNCTION,
                      560, 120, [["change-semaphore-release"], ["change-semaphore-completed"], ["change-semaphore-fault"]],
                      FUNCTION_INFO["semaphore"], group=group, outputs=3),
            _change("change-semaphore-release", tab, group, "Anlagenzustand freigeben", [
                _set("_run", "msg", "$globalContext('sim.run')", "jsonata"),
                _delete("payload._final_wait"),
                _set("payload.factory_cycle", "msg", "_run.releases", "msg"),
                _set("payload.module_runtime_ms", "msg", "_run.module_runtime_ms", "msg"),
                _set("payload.module_job_counts", "msg", "{'sent':_run.sent,'accepted':_run.accepted}", "jsonata"),
            ] + _status_rules("live_state_published"), 810, 90, [["change-live-topic", "change-semaphore-debug", "link-semaphore-status"]],
                info="Index bereits atomar erhoeht | Payload bleibt fachlich unveraendert"),
            _change("change-live-topic", tab, group, "Live-Topic + QoS", [
                _set("topic", "msg", "log/logging/state", "str"),
                _set("qos", "msg", "1", "num"),
                _set("retain", "msg", "false", "bool"),
            ], 1060, 70, [["json-live-release"]]),
            _json("json-live-release", tab, group, "Anlagenzustand JSON", 1260, 70, [["out-live-release"]]),
            _mqtt_out("out-live-release", tab, group, "Freigegebener Anlagenzustand",
                      "log/logging/state", "1", "false", 1490, 70),
            _change("change-semaphore-debug", tab, group, "Freigabe Kurzinfo", [
                _set("payload", "msg", "{'run_id':_semaphore.run_id,'trace_index':_semaphore.release_index,'sent':_run.sent,'accepted':_run.accepted}", "jsonata")
            ], 1050, 125, [["debug-semaphore"]]),
            _debug("debug-semaphore", tab, group, "Semaphorfreigabe", 1260, 125),
            _link_out("link-semaphore-status", tab, group, "Status bilden", ["link-factory-status"], 1070, 170),
            _change("change-semaphore-completed", tab, group, "Laufabschluss bilden", [
                _set("_run", "msg", "$globalContext('sim.run')", "jsonata"),
            ] + _status_rules("completed", completed=True), 820, 225, [["link-semaphore-completed-status"]]),
            _link_out("link-semaphore-completed-status", tab, group, "Status bilden",
                      ["link-factory-status"], 1070, 225),
            _change("change-semaphore-fault", tab, group, "Semaphorfehler", [
                _set("payload", "msg", "{'code':'semaphore_stalled','detail':'command set incomplete','run_id':_semaphore.run_id,'sent_counts':_semaphore.sent,'accepted_counts':_semaphore.accepted,'ts_ms':_semaphore.ts_ms}", "jsonata")
            ], 820, 290, [["link-fault-semaphore"]]),
            _link_out("link-fault-semaphore", tab, group, "Zum Fault-Latch", ["link-fault-central"], 1060, 290),
    ]


def _diagnostic_nodes() -> list[dict]:
    """Flow- und MQTT-Fehler weiterleiten."""
    tab = "tab-semaphore"
    group = "group-semaphore"
    return [
            {"id": "catch-semaphore", "type": "catch", "z": tab, "g": group,
             "name": "Semaphorfehler", "scope": ["json-raw-semaphore", "fn-semaphore", "change-semaphore-release"],
             "uncaught": False, "x": 150, "y": 360, "wires": [["change-catch-semaphore"]]},
            _change("change-catch-semaphore", tab, group, "Fehler normalisieren", [
                _set("payload", "msg", "{'code':'runtime_error','detail':error.message,'source':error.source.name}", "jsonata")
            ], 370, 360, [["link-fault-semaphore-catch"]]),
            _link_out("link-fault-semaphore-catch", tab, group, "Zum Fault-Latch", ["link-fault-central"], 600, 360),
            {"id": "status-mqtt-semaphore", "type": "status", "z": tab, "g": group,
             "name": "MQTT-Zustand", "scope": ["in-raw-semaphore", "out-live-release"],
             "x": 820, "y": 360, "wires": [["switch-mqtt-semaphore"]]},
            _switch("switch-mqtt-semaphore", tab, group, "MQTT getrennt?", "status.text",
                    [{"t": "regex", "v": "disconnected|error", "vt": "str", "case": False}],
                    1030, 360, [["change-mqtt-semaphore"]]),
            _change("change-mqtt-semaphore", tab, group, "MQTT-Fehler", [
                _set("payload", "msg", "{'code':'mqtt_disconnected','detail':status.text,'source':'semaphore'}", "jsonata")
            ], 1240, 360, [["link-fault-semaphore"]]),
    ]


def build_semaphore_nodes() -> list[dict]:
    """Atomaren Semaphor und Diagnosepfad aufbauen."""
    return _decision_nodes() + _diagnostic_nodes()
