"""FlowFuse-Dashboard fuer Betrieb und Diagnose."""

from .common import _change, _json, _link_in, _link_out, _object_rules, _set, _switch

HMI_NODE_IDS = {
    "tab-virtual-hmi", "group-hmi-inputs", "group-hmi-core", "group-hmi-widgets",
    "group-hmi-controls", "in-hmi-model-status", "in-hmi-ai-status",
    "in-hmi-factory-status", "in-hmi-cycle-result", "change-hmi-status",
    "change-hmi-trace", "change-hmi-progress", "change-hmi-mode",
    "change-hmi-semaphore", "change-hmi-raw-count", "change-hmi-release-count",
    "switch-hmi-notification", "change-hmi-notification", "ui-hmi-status",
    "ui-hmi-trace", "ui-hmi-progress", "ui-hmi-mode", "ui-hmi-source-meta",
    "ui-hmi-modules", "ui-hmi-predictions", "ui-hmi-models", "ui-hmi-cycles",
    "ui-hmi-errors", "ui-hmi-latencies", "ui-hmi-notification",
    "ui-hmi-table-layout-style", "ui-hmi-semaphore", "ui-hmi-raw-count",
    "ui-hmi-release-count", "ui-hmi-run-form", "change-hmi-start",
    "ui-hmi-reset-button", "change-hmi-reset-prompt", "ui-hmi-reset-confirm",
    "change-hmi-reset-factory", "change-hmi-reset-ai", "json-hmi-control",
    "out-hmi-control",
}

INPUT_WIRES = {
    "in-hmi-model-status": [["json-hmi-model-status"]],
    "in-hmi-ai-status": [["json-hmi-ai-status"]],
    "in-hmi-factory-status": [["json-hmi-factory-status"]],
    "in-hmi-cycle-result": [["json-hmi-cycle-result"]],
}

WIDGET_POSITIONS = {
    "ui-hmi-status": (1740, 120), "ui-hmi-trace": (1740, 160),
    "ui-hmi-progress": (1740, 200), "ui-hmi-mode": (1740, 240),
    "ui-hmi-semaphore": (1740, 280), "ui-hmi-raw-count": (1740, 320),
    "ui-hmi-release-count": (1740, 360), "ui-hmi-source-meta": (1740, 80),
    "ui-hmi-modules": (1660, 420), "ui-hmi-predictions": (1660, 460),
    "ui-hmi-models": (1660, 500), "ui-hmi-cycles": (1660, 540),
    "ui-hmi-errors": (1660, 580), "ui-hmi-latencies": (1660, 620),
    "ui-hmi-notification": (1740, 660), "ui-hmi-table-layout-style": (1740, 700),
}

MAPPER_POSITIONS = {
    "change-hmi-status": (1430, 120), "change-hmi-trace": (1430, 160),
    "change-hmi-progress": (1430, 200), "change-hmi-mode": (1430, 240),
    "change-hmi-semaphore": (1430, 280), "change-hmi-raw-count": (1430, 320),
    "change-hmi-release-count": (1430, 360),
    "switch-hmi-notification": (1490, 660), "change-hmi-notification": (1660, 660),
}

def _error_rules(severity: str, code: str, title: str, detail: str, recommendation: str) -> list[dict]:
    """Einheitliche HMI-Meldung Feld fuer Feld bilden."""
    return _object_rules("_hmi_error", "msg", [
        ("timestamp", "$fromMillis($millis())", "jsonata"), ("severity", severity, "str"),
        ("code", code, "jsonata"), ("title", title, "str"), ("detail", detail, "jsonata"),
        ("recommendation", recommendation, "str"), ("count", "1", "num"),
    ])


def _overview_rules() -> list[dict]:
    """Betriebskennzahlen aus dem letzten Fabrikstatus ableiten."""
    return [
        _set("_factory", "msg", "$flowContext('hmi.factory')?$flowContext('hmi.factory'):{}", "jsonata"),
        _set("_is_fault", "msg", "$flowContext('hmi.orchestration').state='fault_latched'", "jsonata"),
        _set("_is_completed", "msg", "_factory.state='completed'", "jsonata"),
        _set("_is_running", "msg", "_factory.state in ['bootstrap_commands_published','module_started','module_completed','live_state_published']", "jsonata"),
        _set("_is_ready", "msg", "$flowContext('hmi.orchestration').state='ready'", "jsonata"),
    ] + _object_rules("payload", "msg", [
        ("label", "_is_fault?'Verriegelt':_is_completed?'Abgeschlossen':_is_running?'Simulation laeuft':_is_ready?'Bereit':'Warte auf Systemstatus'", "jsonata"),
        ("trace_profile_name", "_factory.trace_profile_name?_factory.trace_profile_name:_factory.trace_profile", "jsonata"),
        ("model_profile_name", "_factory.model_profile_name?_factory.model_profile_name:'Aktueller Modellstand'", "jsonata"),
        ("trace_total", "$number(_factory.trace_total?_factory.trace_total:0)", "jsonata"),
        ("payloads_sent", "$number(_factory.payloads_sent?_factory.payloads_sent:0)", "jsonata"),
        ("progress_percent", "$number(_factory.progress_percent?_factory.progress_percent:0)", "jsonata"),
        ("command_mode", "$flowContext('hmi.orchestration').command_output_enabled=true?'Commands aktiv':$flowContext('hmi.orchestration').command_output_enabled=false?'Diagnose (keine Commands)':'Noch nicht bekannt'", "jsonata"),
        ("semaphore_state", "_factory.semaphore_state?_factory.semaphore_state:'unbekannt'", "jsonata"),
        ("raw_samples", "$number(_factory.raw_samples?_factory.raw_samples:0)", "jsonata"),
        ("released_states", "$number(_factory.released_states?_factory.released_states:0)", "jsonata"),
    ])


def _module_table_rules() -> list[dict]:
    """Vier Modulzeilen ohne kompaktes Listenprogramm bilden."""
    rules = [_set("_factory", "msg", "$flowContext('hmi.factory')?$flowContext('hmi.factory'):{}", "jsonata")]
    for module in ("vgr", "hbw", "mpo", "sld"):
        rules.extend([
            _set(f"_{module}_state", "msg", f"$number(_factory.sent_counts.{module})>$number(_factory.accepted_counts.{module})?'Laeuft':'Bereit'", "jsonata"),
            _set(f"_{module}_counts", "msg", f"$string(_factory.accepted_counts.{module}?_factory.accepted_counts.{module}:0) & '/' & $string(_factory.sent_counts.{module}?_factory.sent_counts.{module}:0)", "jsonata"),
            _set(f"_{module}_runtime", "msg", f"$string(_factory.module_runtime_ms.{module}?_factory.module_runtime_ms.{module}:'-')", "jsonata"),
        ])
        rules.extend(_object_rules(f"_{module}_row", "msg", [
            ("module", module.upper(), "str"),
            ("command", f"_factory.command_topics.{module}?_factory.command_topics.{module}:'-'", "jsonata"),
            ("summary", f"_{module}_state & ' | ' & _{module}_counts & ' | ' & _{module}_runtime", "jsonata"),
        ]))
    rules.append(_set("payload", "msg", "[_vgr_row,_hbw_row,_mpo_row,_sld_row]", "jsonata"))
    return rules


def _prediction_table_rules() -> list[dict]:
    """Drei Vorhersagezeilen sichtbar zusammensetzen."""
    rules: list[dict] = []
    for domain, label, prefix, field in (
        ("storage", "Storage", "Fach ", "empty_storage"),
        ("vgr", "VGR", "cmd ", "cmd"), ("hbw", "HBW", "cmd ", "cmd"),
    ):
        rules.extend([
            _set(f"_{domain}_value", "msg", f"$flowContext('hmi.predictions').{domain}.{field}?$flowContext('hmi.predictions').{domain}.{field}:'-'", "jsonata"),
            _set(f"_{domain}_quality", "msg", f"$string($round($number($flowContext('hmi.predictions').{domain}.top3[0].p)*1000)/10)", "jsonata"),
            _set(f"_{domain}_latency", "msg", f"$string($flowContext('hmi.last_latency').{domain}?$flowContext('hmi.last_latency').{domain}:'-')", "jsonata"),
        ])
        rules.extend(_object_rules(f"_{domain}_prediction", "msg", [
            ("model", label, "str"), ("prediction", f"'{prefix}' & $string(_{domain}_value)", "jsonata"),
            ("quality", f"_{domain}_quality & ' | ' & _{domain}_latency", "jsonata"),
        ]))
    rules.append(_set("payload", "msg", "[_storage_prediction,_vgr_prediction,_hbw_prediction]", "jsonata"))
    return rules


def _model_table_rules() -> list[dict]:
    """Drei Dienstzeilen aus dem HMI-Context bilden."""
    rules: list[dict] = []
    for domain, label in (("storage", "Storage"), ("vgr", "VGR"), ("hbw", "HBW")):
        rules.extend(_object_rules(f"_{domain}_model", "msg", [
            ("model", label, "str"),
            ("state", f"$flowContext('hmi.models').{domain}.state?$flowContext('hmi.models').{domain}.state:'unbekannt'", "jsonata"),
            ("model_id", f"$flowContext('hmi.model_ids').{domain}?$flowContext('hmi.model_ids').{domain}:'-'", "jsonata"),
        ]))
    rules.append(_set("payload", "msg", "[_storage_model,_vgr_model,_hbw_model]", "jsonata"))
    return rules


def _start_rules() -> list[dict]:
    """Atomaren Startvertrag Feld fuer Feld bilden."""
    return [
        _set("_form", "msg", "payload", "msg"),
        _set("topic", "msg", "ft/sim/factory/control", "str"),
        _set("qos", "msg", "1", "num"), _set("retain", "msg", "false", "bool"),
    ] + _object_rules("payload", "msg", [
        ("cmd", "start", "str"),
        ("config.model_profile", "_form.model_profile ? _form.model_profile : 'deployment-current'", "jsonata"),
        ("config.trace_profile", "_form.trace_profile ? _form.trace_profile : 'standard'", "jsonata"),
        ("config.seed", "$number(_form.seed ? _form.seed : 42)", "jsonata"),
        ("config.base_runtime_ms.vgr", "$number(_form.vgr_base_runtime_ms ? _form.vgr_base_runtime_ms : 100)", "jsonata"),
        ("config.base_runtime_ms.hbw", "$number(_form.hbw_base_runtime_ms ? _form.hbw_base_runtime_ms : 100)", "jsonata"),
        ("config.base_runtime_ms.mpo", "$number(_form.mpo_base_runtime_ms ? _form.mpo_base_runtime_ms : 100)", "jsonata"),
        ("config.base_runtime_ms.sld", "$number(_form.sld_base_runtime_ms ? _form.sld_base_runtime_ms : 100)", "jsonata"),
    ])


def _select_existing(existing: list[dict]) -> list[dict]:
    """Versionierte Dashboard-Nodes kopieren."""
    return [dict(node) for node in existing if node.get("id") in HMI_NODE_IDS]


def _move_nodes(by_id: dict[str, dict], positions: dict[str, tuple[int, int]]) -> None:
    """Editorpositionen lesbar setzen."""
    for node_id, (x, y) in positions.items():
        if node_id in by_id:
            by_id[node_id].update({"x": x, "y": y})


def _configure_existing(hmi: list[dict]) -> list[dict]:
    """Eingaenge, Releasehinweis und Editorlayout aktualisieren."""
    by_id = {node["id"]: node for node in hmi}
    for node_id, wires in INPUT_WIRES.items():
        by_id[node_id]["wires"] = wires
    footer = by_id.get("ui-hmi-source-meta")
    if footer:
        footer["format"] = str(footer.get("format", "")).replace(
            "runtime-v1.3.0-rc.1", "runtime-v1.3.0-rc.2"
        )
    if by_id.get("ui-hmi-trace"):
        by_id["ui-hmi-trace"]["className"] = "hmi-run-summary"
    if by_id.get("group-hmi-widgets"):
        by_id["group-hmi-widgets"].update({"x": 1084, "y": 39, "w": 900, "h": 720})
    if by_id.get("change-hmi-start"):
        by_id["change-hmi-start"]["rules"] = _start_rules()
    _move_nodes(by_id, WIDGET_POSITIONS)
    _move_nodes(by_id, MAPPER_POSITIONS)
    return hmi


def _model_input_nodes() -> list[dict]:
    """Modellstatus nach Domain verteilen."""
    tab = "tab-virtual-hmi"
    return [
            _json("json-hmi-model-status", tab, "group-hmi-inputs", "Status JSON", 310, 100,
                  [["switch-hmi-model-topic"]], "obj"),
            _switch("switch-hmi-model-topic", tab, "group-hmi-inputs", "Modelldomain", "topic", [
                {"t": "eq", "v": "ft/nn/storage/status", "vt": "str"},
                {"t": "eq", "v": "ft/nn/vgr/status", "vt": "str"},
                {"t": "eq", "v": "ft/nn/hbw/status", "vt": "str"},
            ], 500, 100, [["change-hmi-model-storage"], ["change-hmi-model-vgr"], ["change-hmi-model-hbw"]]),
    ]


def _model_store_nodes() -> list[dict]:
    """Drei Modellstatus getrennt merken."""
    tab = "tab-virtual-hmi"
    nodes: list[dict] = []
    for domain, y in zip(("storage", "vgr", "hbw"), (70, 105, 140)):
        nodes.append(_change(
            f"change-hmi-model-{domain}", tab, "group-hmi-core", f"{domain.upper()} merken", [
                _set(f"hmi.models.{domain}", "flow", "payload", "msg"),
                _set(f"hmi.model_ids.{domain}", "flow", "payload.model_id", "msg"),
                _set("_hmi_domain", "msg", domain, "str"),
            ], 710, y, [["switch-hmi-model-offline"]], info="Nur Anzeigezustand",
        ))
    return nodes


def _model_and_ai_status_nodes() -> list[dict]:
    """Modell- und KI-Status fuer Anzeige merken."""
    tab = "tab-virtual-hmi"
    return [
        _switch("switch-hmi-model-offline", tab, "group-hmi-core", "NN offline?", "payload.state",
                [{"t": "eq", "v": "offline", "vt": "str"}, {"t": "else"}], 920, 105,
                [["change-hmi-model-warning"], ["link-hmi-refresh-out"]]),
        _change("change-hmi-model-warning", tab, "group-hmi-core", "Offline-Warnung", [
        ] + _error_rules(
            "warning", "'model_service_offline:' & _hmi_domain", "NN-Dienst offline",
            "_hmi_domain & ' meldet offline'", "Container und MQTT pruefen; danach Reset",
        ) + [
            _set("hmi.errors", "flow", "$filter($append($flowContext('hmi.errors')?$flowContext('hmi.errors'):[],_hmi_error),function($value,$index,$array){$index >= $count($array)-20})", "jsonata"),
            _set("hmi.notification", "flow", "_hmi_error", "msg"),
        ], 1130, 80, [["link-hmi-refresh-out"]]),
        _json("json-hmi-ai-status", tab, "group-hmi-inputs", "KI-Status JSON", 310, 170,
              [["change-hmi-ai-store"]], "obj"),
        _change("change-hmi-ai-store", tab, "group-hmi-core", "KI-Status merken", [
            _set("hmi.orchestration", "flow", "payload", "msg")
        ], 520, 170, [["switch-hmi-ai-fault"]]),
        _switch("switch-hmi-ai-fault", tab, "group-hmi-core", "Fault-Latch?", "payload.state",
                [{"t": "eq", "v": "fault_latched", "vt": "str"}, {"t": "else"}], 730, 170,
                [["change-hmi-fault-error"], ["link-hmi-refresh-out"]]),
        _change("change-hmi-fault-error", tab, "group-hmi-core", "Fault anzeigen", [
        ] + _error_rules(
            "error", "payload.error?payload.error:'fault_latched'", "Prozess verriegelt",
            "payload.fault.detail?payload.fault.detail:payload.detail", "Ursache beheben; danach Reset",
        ) + [
            _set("hmi.errors", "flow", "$filter($append($flowContext('hmi.errors')?$flowContext('hmi.errors'):[],_hmi_error),function($value,$index,$array){$index >= $count($array)-20})", "jsonata"),
            _set("hmi.notification", "flow", "_hmi_error", "msg"),
        ], 950, 170, [["link-hmi-refresh-out"]]),
    ]


def _factory_and_cycle_nodes() -> list[dict]:
    """Fabrikstatus und Zyklusdiagnose merken."""
    tab = "tab-virtual-hmi"
    return [
        _json("json-hmi-factory-status", tab, "group-hmi-inputs", "Fabrikstatus JSON", 310, 220,
              [["switch-hmi-factory-reset"]], "obj"),
        _switch("switch-hmi-factory-reset", tab, "group-hmi-core", "Resetstatus?", "payload.state",
                [{"t": "eq", "v": "reset", "vt": "str"}, {"t": "else"}], 520, 220,
                [["change-hmi-factory-reset"], ["change-hmi-factory-store"]]),
        _change("change-hmi-factory-reset", tab, "group-hmi-core", "Diagnoseanzeige leeren", [
            _set("hmi.factory", "flow", "payload", "msg"), _set("hmi.predictions", "flow", "{}", "json"),
            _set("hmi.model_ids", "flow", "{}", "json"), _set("hmi.cycles", "flow", "[]", "json"),
            _set("hmi.errors", "flow", "[]", "json"), _set("hmi.latencies", "flow", "[]", "json"),
        ], 750, 205, [["link-hmi-refresh-out"]]),
        _change("change-hmi-factory-store", tab, "group-hmi-core", "Fabrikstatus merken", [
            _set("hmi.factory", "flow", "$merge([$flowContext('hmi.factory')?$flowContext('hmi.factory'):{},payload])", "jsonata")
        ], 750, 250, [["switch-hmi-start-error"]]),
        _switch("switch-hmi-start-error", tab, "group-hmi-core", "Start abgelehnt?", "payload.state", [
            {"t": "eq", "v": "configuration_rejected", "vt": "str"},
            {"t": "eq", "v": "start_rejected", "vt": "str"}, {"t": "else"},
        ], 980, 250, [["change-hmi-start-warning"], ["change-hmi-start-warning"], ["link-hmi-refresh-out"]]),
        _change("change-hmi-start-warning", tab, "group-hmi-core", "Startwarnung", [
            _set("_hmi_error", "msg", "{'timestamp':$fromMillis($millis()),'severity':'warning','code':payload.state,'title':'Start abgelehnt','detail':payload.detail,'recommendation':'Konfiguration pruefen','count':1}", "jsonata"),
            _set("hmi.errors", "flow", "$filter($append($flowContext('hmi.errors')?$flowContext('hmi.errors'):[],_hmi_error),function($value,$index,$array){$index >= $count($array)-20})", "jsonata"),
            _set("hmi.notification", "flow", "_hmi_error", "msg"),
        ], 1210, 235, [["link-hmi-refresh-out"]]),
        _json("json-hmi-cycle-result", tab, "group-hmi-inputs", "Zyklus JSON", 310, 280,
              [["change-hmi-cycle-store"]], "obj"),
        _change("change-hmi-cycle-store", tab, "group-hmi-core", "Zyklusdiagnose merken", [
            _set("hmi.predictions", "flow", "$merge([$flowContext('hmi.predictions')?$flowContext('hmi.predictions'):{},payload.model_predictions])", "jsonata"),
            _set("hmi.model_ids", "flow", "$merge([$flowContext('hmi.model_ids')?$flowContext('hmi.model_ids'):{},payload.model_ids])", "jsonata"),
            _set("_cycle_commands", "msg", "'Fach ' & $string(payload.empty_storage) & ' | VGR ' & $string(payload.vgr_cmd) & ' | HBW ' & $string(payload.hbw_cmd)", "jsonata"),
            _set("_cycle_duration", "msg", "$string(payload.duration_ms) & ' ms'", "jsonata"),
        ] + _object_rules("_cycle_row", "msg", [
            ("timestamp", "$substring($fromMillis(payload.ts_ms?$number(payload.ts_ms):$millis()),11,8)", "jsonata"),
            ("summary", "payload.cycle_id & ': ' & payload.status & ' | ' & _cycle_commands & ' | ' & _cycle_duration", "jsonata"),
        ]) + [
            _set("hmi.cycles", "flow", "$filter($append($flowContext('hmi.cycles')?$flowContext('hmi.cycles'):[],_cycle_row),function($value,$index,$array){$index >= $count($array)-30})", "jsonata"),
            _set("hmi.last_latency", "flow", "{'storage':payload.storage_latency_ms,'vgr':payload.vgr_latency_ms,'hbw':payload.hbw_latency_ms}", "jsonata"),
            _set("_latency_rows", "msg", "[{'x':payload.ts_ms,'y':payload.storage_latency_ms,'series':'Storage'},{'x':payload.ts_ms,'y':payload.vgr_latency_ms,'series':'VGR'},{'x':payload.ts_ms,'y':payload.hbw_latency_ms,'series':'HBW'}]", "jsonata"),
            _set("hmi.latencies", "flow", "$filter($append($flowContext('hmi.latencies')?$flowContext('hmi.latencies'):[],_latency_rows),function($value,$index,$array){$index >= $count($array)-90})", "jsonata"),
        ], 570, 300, [["link-hmi-refresh-out"]], info="Vorhersagen | IDs | 30 Zyklen | 90 Latenzpunkte"),
        _link_out("link-hmi-refresh-out", tab, "group-hmi-core", "Widgets aktualisieren", [
            "link-hmi-overview-in", "link-hmi-modules-in", "link-hmi-predictions-in",
            "link-hmi-models-in", "link-hmi-cycles-in", "link-hmi-errors-in",
            "link-hmi-latency-in", "link-hmi-notification-in",
        ], 1000, 300),
    ]


def _status_store_nodes() -> list[dict]:
    """Alle Statuspfade in bestehender Reihenfolge."""
    return _model_and_ai_status_nodes() + _factory_and_cycle_nodes()


def _overview_nodes() -> list[dict]:
    """Uebersicht und Kennzahlen aktualisieren."""
    tab = "tab-virtual-hmi"
    return [
            _link_in("link-hmi-overview-in", tab, "group-hmi-widgets", "Uebersicht", 1110, 80,
                     [["change-hmi-overview"]]),
            _link_in("link-hmi-modules-in", tab, "group-hmi-widgets", "Modulstatus", 1110, 420,
                     [["change-hmi-modules-table"]]),
            _link_in("link-hmi-predictions-in", tab, "group-hmi-widgets", "Vorhersagen", 1110, 460,
                     [["change-hmi-predictions-table"]]),
            _link_in("link-hmi-models-in", tab, "group-hmi-widgets", "Modelldienste", 1110, 500,
                     [["change-hmi-models-table"]]),
            _link_in("link-hmi-cycles-in", tab, "group-hmi-widgets", "Zyklen", 1110, 540,
                     [["change-hmi-cycles-table"]]),
            _link_in("link-hmi-errors-in", tab, "group-hmi-widgets", "Fehler", 1110, 580,
                     [["change-hmi-errors-table"]]),
            _link_in("link-hmi-latency-in", tab, "group-hmi-widgets", "Latenzen", 1110, 620,
                     [["change-hmi-latency-chart"]]),
            _link_in("link-hmi-notification-in", tab, "group-hmi-widgets", "Meldung", 1110, 660,
                     [["change-hmi-notification-read"]]),
            _change("change-hmi-overview", tab, "group-hmi-widgets", "Uebersicht bilden", [
            ] + _overview_rules(), 1280, 80, [["link-hmi-overview-out"]]),
            _link_out("link-hmi-overview-out", tab, "group-hmi-widgets", "Kennzahlen verteilen", [
                "link-hmi-status-in", "link-hmi-trace-in", "link-hmi-progress-in", "link-hmi-mode-in",
                "link-hmi-semaphore-in", "link-hmi-raw-in", "link-hmi-release-in",
            ], 1450, 80),
            _link_in("link-hmi-status-in", tab, "group-hmi-widgets", "Zustand", 1190, 120,
                     [["change-hmi-status"]]),
            _link_in("link-hmi-trace-in", tab, "group-hmi-widgets", "Lauf", 1190, 160,
                     [["change-hmi-trace"]]),
            _link_in("link-hmi-progress-in", tab, "group-hmi-widgets", "Fortschritt", 1190, 200,
                     [["change-hmi-progress"]]),
            _link_in("link-hmi-mode-in", tab, "group-hmi-widgets", "Modus", 1190, 240,
                     [["change-hmi-mode"]]),
            _link_in("link-hmi-semaphore-in", tab, "group-hmi-widgets", "Semaphor", 1190, 280,
                     [["change-hmi-semaphore"]]),
            _link_in("link-hmi-raw-in", tab, "group-hmi-widgets", "Rohsamples", 1190, 320,
                     [["change-hmi-raw-count"]]),
            _link_in("link-hmi-release-in", tab, "group-hmi-widgets", "Freigaben", 1190, 360,
                     [["change-hmi-release-count"]]),
    ]


def _widget_nodes() -> list[dict]:
    """Tabellen, Chart und Fehlerpfad aktualisieren."""
    tab = "tab-virtual-hmi"
    return [
            _change("change-hmi-modules-table", tab, "group-hmi-widgets", "Modultabelle", [
            ] + _module_table_rules(), 1320, 420, [["ui-hmi-modules"]]),
            _change("change-hmi-predictions-table", tab, "group-hmi-widgets", "Vorhersagetabelle", [
            ] + _prediction_table_rules(), 1320, 460, [["ui-hmi-predictions"]]),
            _change("change-hmi-models-table", tab, "group-hmi-widgets", "Modelltabelle", [
            ] + _model_table_rules(), 1320, 500, [["ui-hmi-models"]]),
            _change("change-hmi-cycles-table", tab, "group-hmi-widgets", "Zyklustabelle", [
                _set("payload", "msg", "$flowContext('hmi.cycles')?$flowContext('hmi.cycles'):[]", "jsonata")
            ], 1320, 540, [["ui-hmi-cycles"]]),
            _change("change-hmi-errors-table", tab, "group-hmi-widgets", "Fehlertabelle", [
                _set("payload", "msg", "$flowContext('hmi.errors')?$flowContext('hmi.errors'):[]", "jsonata")
            ], 1320, 580, [["ui-hmi-errors"]]),
            _change("change-hmi-latency-chart", tab, "group-hmi-widgets", "Latenzchart", [
                _set("payload", "msg", "$flowContext('hmi.latencies')?$flowContext('hmi.latencies'):[]", "jsonata")
            ], 1320, 620, [["ui-hmi-latencies"]]),
            _change("change-hmi-notification-read", tab, "group-hmi-widgets", "Neue Meldung lesen", [
                _set("payload", "msg", "$flowContext('hmi.notification')", "jsonata"),
                _set("hmi.notification", "flow", "null", "json"),
            ], 1320, 660, [["switch-hmi-notification"]]),
            {"id": "catch-hmi", "type": "catch", "z": tab, "g": "group-hmi-core", "name": "HMI-Fehler",
             "scope": ["change-hmi-cycle-store", "change-hmi-overview", "change-hmi-modules-table"],
             "uncaught": False, "x": 1180, "y": 310, "wires": [["change-catch-hmi"]]},
            _change("change-catch-hmi", tab, "group-hmi-core", "HMI-Fehler normalisieren", [
                _set("payload", "msg", "{'code':'hmi_runtime_error','detail':error.message,'source':error.source.name}", "jsonata")
            ], 1400, 310, [["link-fault-hmi"]]),
            _link_out("link-fault-hmi", tab, "group-hmi-core", "Zum Fault-Latch", ["link-fault-central"], 1580, 310),
            {"id": "status-mqtt-hmi", "type": "status", "z": tab, "g": "group-hmi-inputs", "name": "MQTT-Zustand",
             "scope": list(INPUT_WIRES), "x": 310, "y": 330, "wires": [["switch-mqtt-hmi"]]},
            _switch("switch-mqtt-hmi", tab, "group-hmi-inputs", "MQTT getrennt?", "status.text",
                    [{"t": "regex", "v": "disconnected|error", "vt": "str", "case": False}],
                    520, 330, [["change-mqtt-hmi"]]),
            _change("change-mqtt-hmi", tab, "group-hmi-inputs", "MQTT-Fehler", [
                _set("payload", "msg", "{'code':'mqtt_disconnected','detail':status.text,'source':'Virtual HMI'}", "jsonata")
            ], 730, 330, [["link-fault-hmi"]]),
    ]


def update_low_code_hmi(existing: list[dict]) -> list[dict]:
    """Dashboard aus bestehenden Widgets und Core-Pfaden aufbauen."""
    hmi = _configure_existing(_select_existing(existing))
    return (
        hmi
        + _model_input_nodes()
        + _model_store_nodes()
        + _status_store_nodes()
        + _overview_nodes()
        + _widget_nodes()
    )
