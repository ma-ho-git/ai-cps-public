"""Start, Reset und Trace-Initialisierung."""

import json

from .common import (
    MODEL_NAMES,
    MODULES,
    TRACE_FILES,
    TRACE_NAMES,
    _change,
    _comment,
    _debug,
    _delete,
    _group,
    _json,
    _link_in,
    _link_out,
    _mqtt_in,
    _mqtt_out,
    _object_rules,
    _set,
    _switch,
)


def _tabs() -> list[dict]:
    return [
        {"id": "tab-init", "type": "tab", "label": "00 Initialisierung", "disabled": False, "info": ""},
        {"id": "tab-state", "type": "tab", "label": "10 Zustandserfassung", "disabled": False, "info": ""},
        {"id": "tab-modules", "type": "tab", "label": "20 Virtuelle Module", "disabled": False, "info": ""},
        {"id": "tab-semaphore", "type": "tab", "label": "30 Semaphor", "disabled": False, "info": ""},
        {"id": "tab-pipeline", "type": "tab", "label": "40 NN-Pipeline", "disabled": False, "info": ""},
    ]

def _start_config_rules() -> list[dict]:
    """Startwerte und kurze Pruefflags setzen."""
    rules = _object_rules("_config", "msg", [
        ("trace_profile", "$string(payload.config.trace_profile ? payload.config.trace_profile : 'standard')", "jsonata"),
        ("model_profile", "$string(payload.config.model_profile ? payload.config.model_profile : 'deployment-current')", "jsonata"),
        ("seed", "$number($exists(payload.config.seed) ? payload.config.seed : 42)", "jsonata"),
        ("base_runtime_ms.vgr", "$number($exists(payload.config.base_runtime_ms.vgr) ? payload.config.base_runtime_ms.vgr : 100)", "jsonata"),
        ("base_runtime_ms.hbw", "$number($exists(payload.config.base_runtime_ms.hbw) ? payload.config.base_runtime_ms.hbw : 100)", "jsonata"),
        ("base_runtime_ms.mpo", "$number($exists(payload.config.base_runtime_ms.mpo) ? payload.config.base_runtime_ms.mpo : 100)", "jsonata"),
        ("base_runtime_ms.sld", "$number($exists(payload.config.base_runtime_ms.sld) ? payload.config.base_runtime_ms.sld : 100)", "jsonata"),
    ])
    rules.append(_set("_seed_valid", "msg", "$type(_config.seed)='number' and $floor(_config.seed)=_config.seed and _config.seed>=0 and _config.seed<=4294967295", "jsonata"))
    for module in MODULES:
        value = f"_config.base_runtime_ms.{module}"
        rules.extend([
            _set(f"_runtime_{module}_number", "msg", f"$type({value})='number'", "jsonata"),
            _set(f"_runtime_{module}_integer", "msg", f"$floor({value})={value}", "jsonata"),
            _set(f"_runtime_{module}_range", "msg", f"{value}>=50 and {value}<=60000", "jsonata"),
            _set(f"_runtime_{module}_valid", "msg", f"_runtime_{module}_number and _runtime_{module}_integer and _runtime_{module}_range", "jsonata"),
        ])
    return rules


def _run_state_rules() -> list[dict]:
    """Fluechtigen Laufzustand sichtbar initialisieren."""
    empty_counts = json.dumps({module: 0 for module in MODULES})
    return _object_rules("sim.run", "global", [
        ("running", "true", "bool"), ("completed", "false", "bool"),
        ("fault", "null", "json"), ("run_counter", "_run_counter", "msg"),
        ("run_id", "_run_id", "msg"), ("trace", "payload", "msg"),
        ("trace_index", "0", "num"), ("raw_samples", "0", "num"),
        ("releases", "0", "num"), ("sent", empty_counts, "json"),
        ("accepted", empty_counts, "json"), ("last_release_sent", empty_counts, "json"),
        ("command_topics", "{}", "json"), ("module_runtime_ms", "{}", "json"),
        ("command_deadline_ms", "$millis()+10000", "jsonata"), ("config", "_config", "msg"),
    ])


def _base_init_nodes() -> list[dict]:
    """Gruppen und Control-Eingang."""
    tab = "tab-init"
    return [
        _group("group-init-control", tab, "Start und Trace", 20, 20, 1800, 390),
        _group("group-init-status", tab, "Status und Fault-Latch", 20, 430, 1800, 280),
        _comment("comment-init", tab, "Start | Parameter einzeln pruefen | Trace laden | vier Idle-Commands", 340, 45),
        _mqtt_in("in-init-control", tab, "group-init-control", "Start / Reset", "ft/sim/factory/control", "1", 120, 100, [["json-init-control"]]),
        _json("json-init-control", tab, "group-init-control", "Control JSON", 300, 100, [["switch-init-control"]], "obj"),
        _switch("switch-init-control", tab, "group-init-control", "Start oder Reset", "payload.cmd",
                [{"t":"eq","v":"start","vt":"str"},{"t":"eq","v":"reset","vt":"str"}],
                490, 100, [["change-start-defaults"],["change-reset-runtime"]], info="Start | Reset"),
        _change("change-start-defaults", tab, "group-init-control", "Defaults uebernehmen",
                _start_config_rules(), 700, 80, [["switch-trace-profile"]],
                info="Fehlende Werte: Standardprofil | aktuelles Modell | Seed 42 | 100 ms"),
        _switch("switch-trace-profile", tab, "group-init-control", "Testszenario vorhanden?", "_config.trace_profile",
                [{"t":"eq","v":"standard","vt":"str"},{"t":"eq","v":"full-storage-attempt","vt":"str"},
                 {"t":"eq","v":"full-storage-process-guard","vt":"str"},{"t":"else"}],
                920, 80,
                [["change-trace-standard"],["change-trace-attempt"],["change-trace-process"],["change-config-rejected"]],
                info="Drei versionierte Testszenarien | sonst ablehnen"),
    ]


def _trace_profile_nodes() -> list[dict]:
    """Tracepfad und Anzeigename waehlen."""
    tab = "tab-init"
    nodes: list[dict] = []
    for index, profile in enumerate(TRACE_NAMES):
        suffix = {"standard":"standard","full-storage-attempt":"attempt","full-storage-process-guard":"process"}[profile]
        nodes.append(_change(
            f"change-trace-{suffix}", tab, "group-init-control", f"Szenario: {profile}",
            [_set("filename", "msg", TRACE_FILES[profile], "str"),
             _set("_config.trace_profile_name", "msg", TRACE_NAMES[profile], "str")],
            1160, 45 + index * 40, [["switch-model-profile"]], info="Dateipfad | Anzeigename",
        ))
    return nodes


def _start_validation_nodes() -> list[dict]:
    """Startparameter und Bereitschaft pruefen."""
    tab = "tab-init"
    return [
            _switch("switch-model-profile", tab, "group-init-control", "Modellprofil vorhanden?", "_config.model_profile",
                    [{"t":"eq","v":"deployment-current","vt":"str"},
                     {"t":"eq","v":"historical-full-storage-error","vt":"str"},{"t":"else"}],
                    1380, 100, [["change-model-current"],["change-model-historical"],["change-config-rejected"]],
                    info="Aktueller Stand | historische Fehlerdemonstration"),
            _change("change-model-current", tab, "group-init-control", "Aktueller Modellstand",
                    [_set("_config.model_profile_name", "msg", MODEL_NAMES["deployment-current"], "str")],
                    1580, 70, [["switch-start-numbers"]]),
            _change("change-model-historical", tab, "group-init-control", "Historischer Modellstand",
                    [_set("_config.model_profile_name", "msg", MODEL_NAMES["historical-full-storage-error"], "str")],
                    1580, 120, [["switch-start-numbers"]]),
            _switch("switch-start-numbers", tab, "group-init-control", "Seed + Laufzeiten gueltig?",
                    "_seed_valid and _runtime_vgr_valid and _runtime_hbw_valid and _runtime_mpo_valid and _runtime_sld_valid",
                    [{"t":"true"},{"t":"false"}], 1580, 180,
                    [["switch-run-available"],["change-config-rejected"]], prop_type="jsonata",
                    info="Seed: 0..2^32-1 | Laufzeiten: 50..60000 ms"),
            _switch("switch-run-available", tab, "group-init-control", "Neuer Lauf erlaubt?",
                    "$not($exists($globalContext('sim.run'))) or "
                    "($not($globalContext('sim.run').running) and $not($globalContext('sim.run').completed))",
                    [{"t":"true"},{"t":"false"}], 1360, 230,
                    [["change-start-readiness"],["change-start-rejected"]], prop_type="jsonata",
                    info="Kein laufender Lauf | nach Abschluss zuerst Reset"),
            _switch("switch-model-available", tab, "group-init-control", "Profil in Contracts?",
                    "_config.model_profile='deployment-current' or (_historical_vgr_ready and _historical_hbw_ready)",
                    [{"t":"true"},{"t":"false"}], 1150, 230,
                    [["change-start-ready"],["change-config-rejected"]], prop_type="jsonata",
                    info="Historisches Profil in VGR- und HBW-Contract"),
            _change("change-start-readiness", tab, "group-init-control", "NN-Bereitschaft lesen", [
                    _set("_contracts_ready", "msg", "$exists($globalContext('ai.contracts').storage) and $exists($globalContext('ai.contracts').vgr) and $exists($globalContext('ai.contracts').hbw)", "jsonata"),
                    _set("_statuses_ready", "msg", "$globalContext('ai.statuses').storage.state='online' and $globalContext('ai.statuses').vgr.state='online' and $globalContext('ai.statuses').hbw.state='online'", "jsonata"),
                    _set("_historical_vgr_ready", "msg", "$exists($lookup($globalContext('ai.contracts').vgr.model_profiles,'historical-full-storage-error'))", "jsonata"),
                    _set("_historical_hbw_ready", "msg", "$exists($lookup($globalContext('ai.contracts').hbw.model_profiles,'historical-full-storage-error'))", "jsonata"),
            ], 1110, 230, [["switch-ai-ready"]], info="Contracts | Online-Status | historisches Profil"),
            _switch("switch-ai-ready", tab, "group-init-control", "Alle NN bereit?", "_contracts_ready and _statuses_ready",
                    [{"t":"true"},{"t":"false"}], 930, 230,
                    [["switch-model-available"],["change-start-pending"]], prop_type="jsonata",
                    info="Drei Contracts | drei Online-Status"),
            _change("change-start-ready", tab, "group-init-control", "Start freigeben",
                    [_delete("sim.pending_start", "global"),
                     _set("_run_config", "msg", "_config", "msg")],
                    710, 210, [["file-trace"]], info="Pending leeren | Trace lesen"),
            _change("change-start-pending", tab, "group-init-control", "Auf NN warten",
                    [_set("sim.pending_start", "global", "{'cmd':'start','config':_config}", "jsonata"),
                     _set("payload", "msg", "$merge([_config,{'state':'waiting_for_orchestration','detail':'NN contracts/status not ready','ts_ms':$millis()}])", "jsonata")],
                    710, 260, [["link-factory-status-out-init"]], info="Konfiguration merken | kein Tracezugriff"),
            _change("change-config-rejected", tab, "group-init-control", "Konfiguration ablehnen",
                    [_set("payload", "msg", "{'state':'configuration_rejected','detail':'trace, model profile, seed or module runtime invalid','ts_ms':$millis()}", "jsonata")],
                    1150, 310, [["link-factory-status-out-init"]]),
            _change("change-start-rejected", tab, "group-init-control", "Start ablehnen",
                    [_set("payload", "msg", "{'state':'start_rejected','detail':$globalContext('sim.run').running ? 'factory_already_running' : 'reset_required_after_completion','ts_ms':$millis()}", "jsonata")],
                    1370, 310, [["link-factory-status-out-init"]]),
    ]


def _trace_load_nodes() -> list[dict]:
    """JSONL-Trace lesen und Lauf anlegen."""
    tab = "tab-init"
    return [
            {"id":"file-trace","type":"file in","z":tab,"g":"group-init-control","name":"Testszenario lesen","filename":"filename","filenameType":"msg","format":"utf8","chunk":False,"sendError":True,"encoding":"none","allProps":True,"x":510,"y":210,"wires":[["change-trim-trace"]]},
            _change("change-trim-trace", tab, "group-init-control", "Abschlusszeile entfernen",
                    [{"t":"change","p":"payload","pt":"msg","from":"\\s+$","fromt":"re","to":"","tot":"str"}],
                    510, 250, [["split-trace-lines"]]),
            {"id":"split-trace-lines","type":"split","z":tab,"g":"group-init-control","name":"JSONL zerlegen","splt":"\n","spltType":"str","arraySplt":1,"arraySpltType":"len","stream":False,"addname":"","property":"payload","x":510,"y":290,"wires":[["switch-trace-line"]]},
            _switch("switch-trace-line", tab, "group-init-control", "Leerzeile?", "payload",
                    [{"t":"nempty"}], 690, 290, [["json-trace-line"]]),
            _json("json-trace-line", tab, "group-init-control", "Tracezeile JSON", 860, 290, [["change-trace-parts"]], "obj"),
            _change("change-trace-parts", tab, "group-init-control", "Datensatzliste vorbereiten",
                    [_set("parts.type", "msg", "array", "str"), _delete("parts.ch")],
                    1050, 290, [["join-trace"]]),
            {"id":"join-trace","type":"join","z":tab,"g":"group-init-control","name":"Trace sammeln","mode":"auto","build":"array","property":"payload","propertyType":"msg","key":"topic","joiner":"\n","joinerType":"str","accumulate":False,"timeout":"","count":"","reduceRight":False,"reduceExp":"","reduceInit":"","reduceInitType":"","reduceFixup":"","x":1220,"y":290,"wires":[["change-run-counter"]]},
            _change("change-run-counter", tab, "group-init-control", "Run-ID bilden",
                    [_set("_run_counter", "msg", "$number($globalContext('sim.run').run_counter ? $globalContext('sim.run').run_counter : 0)+1", "jsonata"),
                     _set("_run_id", "msg", "$string($millis()) & '-' & $string(_run_counter)", "jsonata"),
                     _set("_config", "msg", "_run_config", "msg")],
                    1390, 290, [["change-run-init"]]),
            _change("change-run-init", tab, "group-init-control", "Laufzustand initialisieren",
                    _run_state_rules() + [
                     _delete("sim.pending_start", "global"),
                     _set("payload", "msg", "{'action':'start','run_id':_run_id}", "jsonata")],
                    1580, 290, [["link-init-vgr","link-init-hbw","link-init-mpo","link-init-sld","change-init-status","debug-init"]],
                    info="Trace | Run-ID | Counter 0 | Semaphor blockiert"),
            _debug("debug-init", tab, "group-init-control", "Initialisierung abgeschlossen", 1720, 350),
            _change("change-init-status", tab, "group-init-control", "Init-Status",
                    [_set("payload", "msg", "{'state':'bootstrap_commands_published','semaphore_state':'blocked'}", "jsonata")],
                    1580, 350, [["link-factory-status-out-init"]]),
    ]


def _module_init_links() -> list[dict]:
    """Vier Module getrennt initialisieren."""
    tab = "tab-init"
    nodes: list[dict] = []
    for module, y in zip(MODULES, (210, 240, 270, 300)):
        nodes.append(_link_out(f"link-init-{module}", tab, "group-init-control", f"{module.upper()} initialisieren", [f"link-module-{module}-init"], 1710, y))
    return nodes


def _reset_nodes() -> list[dict]:
    """Runtime und KI-Zustand zuruecksetzen."""
    tab = "tab-init"
    return [
            _change("change-reset-runtime", tab, "group-init-control", "Lauf + KI zuruecksetzen",
                    [_set("_previous_run_id", "msg", "$globalContext('sim.run').run_id", "jsonata"),
                     _set("_run_counter", "msg", "$number($globalContext('sim.run').run_counter ? $globalContext('sim.run').run_counter : 0)", "jsonata"),
                     _set("sim.run", "global", "{'running':false,'completed':false,'fault':null,'run_counter':_run_counter}", "jsonata"),
                     _delete("sim.pending_start", "global"),
                     _delete("ai.pending", "global"),
                     _set("ai.windows", "global", json.dumps({"vgr": {}, "hbw": {}}), "json"),
                     _set("ai.seen_responses", "global", "[]", "json"),
                     _set("payload", "msg", "{'action':'reset','previous_run_id':_previous_run_id}", "jsonata")],
                    700, 350, [["link-init-vgr","link-init-hbw","link-init-mpo","link-init-sld","change-reset-status"]],
                    info="Lauf | Pending | Windows | Deduplizierung"),
            _change("change-reset-status", tab, "group-init-control", "Reset-Status",
                    [_set("payload", "msg", "{'state':'reset','run_id':payload.previous_run_id,'semaphore_state':'blocked'}", "jsonata")],
                    930, 350, [["link-factory-status-out-init"]]),
            _mqtt_in("in-init-ai-ready", tab, "group-init-control", "KI bereit?", "ft/ai/orchestration/status", "1", 120, 360, [["switch-init-ai-ready"]]),
            _switch("switch-init-ai-ready", tab, "group-init-control", "Ready + Start wartet?",
                    "payload.state='ready' and $exists($globalContext('sim.pending_start'))",
                    [{"t":"true"}], 330, 360, [["change-resume-start"]], prop_type="jsonata"),
            _change("change-resume-start", tab, "group-init-control", "Start fortsetzen",
                    [_set("payload", "msg", "$globalContext('sim.pending_start')", "jsonata")],
                    530, 360, [["change-start-defaults"]]),
    ]


def _factory_status_nodes() -> list[dict]:
    """Fabrikstatus vereinheitlichen."""
    tab = "tab-init"
    return [
            _link_out("link-factory-status-out-init", tab, "group-init-control", "Status bilden", ["link-factory-status"], 1750, 390),
            _link_in("link-factory-status", tab, "group-init-status", "Statusereignisse", 80, 485, [["change-factory-status-source"]]),
            _change("change-factory-status-source", tab, "group-init-status", "Statusquellen merken",
                    [_set("_status_input", "msg", "_factory_status ? _factory_status : payload", "jsonata"),
                     _set("_status_run", "msg", "$globalContext('sim.run')", "jsonata"),
                     _set("payload", "msg", "{}", "json")],
                    270, 485, [["change-factory-status-fields"]]),
            _change("change-factory-status-fields", tab, "group-init-status", "Fabrikstatus abbilden",
                    [
                        _set("payload.state", "msg", "_status_input.state ? _status_input.state : (_factory_state ? _factory_state : 'running')", "jsonata"),
                        _set("payload.detail", "msg", "_status_input.detail ? _status_input.detail : ''", "jsonata"),
                        _set("payload.run_id", "msg", "$exists(_status_input.run_id) ? _status_input.run_id : _status_run.run_id", "jsonata"),
                        _set("payload.trace_profile", "msg", "$exists(_status_input.trace_profile) ? _status_input.trace_profile : (_status_run.config.trace_profile ? _status_run.config.trace_profile : 'standard')", "jsonata"),
                        _set("payload.trace_profile_name", "msg", "$exists(_status_input.trace_profile_name) ? _status_input.trace_profile_name : (_status_run.config.trace_profile_name ? _status_run.config.trace_profile_name : 'standard')", "jsonata"),
                        _set("payload.model_profile", "msg", "$exists(_status_input.model_profile) ? _status_input.model_profile : (_status_run.config.model_profile ? _status_run.config.model_profile : 'deployment-current')", "jsonata"),
                        _set("payload.model_profile_name", "msg", "$exists(_status_input.model_profile_name) ? _status_input.model_profile_name : (_status_run.config.model_profile_name ? _status_run.config.model_profile_name : 'Aktueller Modellstand')", "jsonata"),
                        _set("payload.trace_total", "msg", "$exists(_status_input.trace_total) ? _status_input.trace_total : $count(_status_run.trace)", "jsonata"),
                        _set("payload.payloads_sent", "msg", "$exists(_status_input.payloads_sent) ? _status_input.payloads_sent : $number(_status_run.releases ? _status_run.releases : 0)", "jsonata"),
                        _set("payload.raw_samples", "msg", "$exists(_status_input.raw_samples) ? _status_input.raw_samples : $number(_status_run.raw_samples ? _status_run.raw_samples : 0)", "jsonata"),
                        _set("payload.released_states", "msg", "$exists(_status_input.released_states) ? _status_input.released_states : $number(_status_run.releases ? _status_run.releases : 0)", "jsonata"),
                        _set("payload.progress_percent", "msg", "$exists(_status_input.progress_percent) ? _status_input.progress_percent : ($count(_status_run.trace)>0 ? $round(($number(_status_run.releases)/$count(_status_run.trace))*10000)/100 : 0)", "jsonata"),
                        _set("payload.semaphore_state", "msg", "$exists(_status_input.semaphore_state) ? _status_input.semaphore_state : (_status_run.fault ? 'fault' : 'blocked')", "jsonata"),
                        _set("payload.sent_counts", "msg", "$exists(_status_input.sent_counts) ? _status_input.sent_counts : _status_run.sent", "jsonata"),
                        _set("payload.accepted_counts", "msg", "$exists(_status_input.accepted_counts) ? _status_input.accepted_counts : _status_run.accepted", "jsonata"),
                        _set("payload.module_runtime_ms", "msg", "$exists(_status_input.module_runtime_ms) ? _status_input.module_runtime_ms : _status_run.module_runtime_ms", "jsonata"),
                        _set("payload.command_topics", "msg", "$exists(_status_input.command_topics) ? _status_input.command_topics : _status_run.command_topics", "jsonata"),
                        _set("payload.seed", "msg", "$exists(_status_input.seed) ? _status_input.seed : (_status_run.config.seed ? _status_run.config.seed : 42)", "jsonata"),
                        _set("payload.base_runtime_ms", "msg", "$exists(_status_input.base_runtime_ms) ? _status_input.base_runtime_ms : _status_run.config.base_runtime_ms", "jsonata"),
                        _set("payload.ts_ms", "msg", "_status_input.ts_ms ? _status_input.ts_ms : $millis()", "jsonata"),
                    ], 530, 485, [["json-factory-status"]], info="Ein Feld je sichtbarer Zuweisung"),
            _json("json-factory-status", tab, "group-init-status", "Status JSON", 760, 485, [["out-factory-status"]]),
            _mqtt_out("out-factory-status", tab, "group-init-status", "Fabrikstatus retained", "ft/sim/factory/status", "1", "true", 970, 485),
    ]


def _fault_nodes() -> list[dict]:
    """Fehler speichern und veroeffentlichen."""
    tab = "tab-init"
    return [
            _link_in("link-fault-central", tab, "group-init-status", "Flowfehler", 80, 570, [["switch-fault-relevant"]]),
            _switch("switch-fault-relevant", tab, "group-init-status", "Fehler relevant?",
                    "$not(payload.code='mqtt_disconnected' and $not($globalContext('sim.run').running))",
                    [{"t":"true"}], 260, 570, [["switch-fault-first"]], prop_type="jsonata"),
            _switch("switch-fault-first", tab, "group-init-status", "Erster Fehler?",
                    "$type($globalContext('sim.run').fault)='object'", [{"t":"false"},{"t":"true"}],
                    440, 570, [["change-fault-first"],["change-fault-existing"]], prop_type="jsonata"),
            _change("change-fault-first", tab, "group-init-status", "Fault speichern",
                    _object_rules("_fault", "msg", [
                        ("reason", "$string(payload.code ? payload.code : (payload.error ? payload.error : 'runtime_error'))", "jsonata"),
                        ("detail", "$string(payload.detail ? payload.detail : '')", "jsonata"),
                        ("module", "payload.module", "msg"), ("cycle_id", "payload.cycle_id", "msg"),
                        ("ts_ms", "$millis()", "jsonata"),
                    ]) + [
                     _set("sim.run.fault", "global", "_fault", "msg"),
                     _set("sim.run.running", "global", "false", "bool")],
                    640, 550, [["change-fault-payload"]]),
            _change("change-fault-existing", tab, "group-init-status", "Ersten Fault behalten",
                    [_set("_fault", "msg", "$globalContext('sim.run').fault", "jsonata")],
                    640, 600, [["change-fault-payload"]]),
            _change("change-fault-payload", tab, "group-init-status", "Faultstatus bilden",
                    _object_rules("payload", "msg", [
                        ("schema_version", "1.0", "str"), ("state", "fault_latched", "str"),
                        ("detail", "_fault.reason", "msg"), ("error", "_fault.reason", "msg"),
                        ("fault", "_fault", "msg"), ("run_id", "$globalContext('sim.run').run_id", "jsonata"),
                        ("cycle_id", "_fault.cycle_id", "msg"), ("command_output_enabled", "true", "bool"),
                        ("fault_latched", "true", "bool"), ("ts_ms", "$millis()", "jsonata"),
                    ]),
                    850, 570, [["json-ai-fault","change-fault-factory","debug-fault"]]),
            _json("json-ai-fault", tab, "group-init-status", "Fault JSON", 1060, 540, [["out-ai-fault"]]),
            _mqtt_out("out-ai-fault", tab, "group-init-status", "Orchestrierungsfehler", "ft/ai/orchestration/status", "1", "true", 1280, 540),
            _change("change-fault-factory", tab, "group-init-status", "Fabrikfehler",
                    [_set("payload", "msg", "{'state':'fault_latched','detail':_fault.reason,'semaphore_state':'fault'}", "jsonata")],
                    1060, 590, [["link-factory-status-out-fault"]]),
            _link_out("link-factory-status-out-fault", tab, "group-init-status", "Status bilden", ["link-factory-status"], 1270, 590),
            _debug("debug-fault", tab, "group-init-status", "Fault-Latch", 1070, 640),
            {"id":"catch-init","type":"catch","z":tab,"g":"group-init-status","name":"Initialisierungsfehler","scope":["file-trace","json-trace-line","change-run-init","change-factory-status-fields"],"uncaught":False,"x":1430,"y":540,"wires":[["change-catch-init"]]},
            _change("change-catch-init", tab, "group-init-status", "Fehler normalisieren",
                    [_set("payload", "msg", "{'code':'runtime_error','detail':error.message,'source':error.source.name}", "jsonata")],
                    1600, 540, [["link-fault-out-init"]]),
            _link_out("link-fault-out-init", tab, "group-init-status", "Zum Fault-Latch", ["link-fault-central"], 1760, 540),
    ]


def build_init_nodes() -> list[dict]:
    """Initialisierung aus sichtbaren Teilpfaden aufbauen."""
    return (
        _base_init_nodes()
        + _trace_profile_nodes()
        + _start_validation_nodes()
        + _trace_load_nodes()
        + _module_init_links()
        + _reset_nodes()
        + _factory_status_nodes()
        + _fault_nodes()
    )
