"""Storage-, LSTM- und Modell-Request-Pipeline."""

import json

from .common import (
    CONTRACT_FUNCTION,
    FUNCTION_INFO,
    _change,
    _comment,
    _debug,
    _delete,
    _function,
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
from .reporting import build_reporting_nodes

expected_request = "'ft/nn/' & _domain & '/request'"
expected_response = "'ft/nn/response/' & _domain"
valid_contract = (
    "payload.schema_version='1.0' and payload.domain=_domain and $type(payload.feature_cols)='array' and "
    "$type(payload.class_ids)='array' and payload.request_topic=" + expected_request + " and "
    "payload.response_topic=" + expected_response
)
def _readiness_rules() -> list[dict]:
    """Drei Dienstvertraege getrennt pruefen und melden."""
    rules: list[dict] = []
    for domain in ("storage", "vgr", "hbw"):
        rules.extend([
            _set(f"_{domain}_contract", "msg", f"$globalContext('ai.contracts').{domain}", "jsonata"),
            _set(f"_{domain}_status", "msg", f"$globalContext('ai.statuses').{domain}", "jsonata"),
            _set(f"_{domain}_online", "msg", f"_{domain}_status.state='online'", "jsonata"),
            _set(f"_{domain}_model_match", "msg", f"_{domain}_status.model_id=_{domain}_contract.model_id", "jsonata"),
            _set(f"_{domain}_ready", "msg", f"$exists(_{domain}_contract) and _{domain}_online and _{domain}_model_match", "jsonata"),
        ])
    rules.append(_set("_ready", "msg", "_storage_ready and _vgr_ready and _hbw_ready", "jsonata"))
    rules.extend(_object_rules("payload", "msg", [
        ("schema_version", "1.0", "str"),
        ("state", "_ready?'ready':'waiting_for_models'", "jsonata"),
        ("detail", "_ready?'contracts_and_status_ready':'contracts_or_status_missing'", "jsonata"),
        ("command_output_enabled", "$lowercase($env('COMMAND_OUTPUT_ENABLED'))='true'", "jsonata"),
        ("fault_latched", "$type($globalContext('sim.run').fault)='object'", "jsonata"),
        ("model_ids.storage", "$globalContext('ai.contracts').storage.model_id", "jsonata"),
        ("model_ids.vgr", "$globalContext('ai.contracts').vgr.model_id", "jsonata"),
        ("model_ids.hbw", "$globalContext('ai.contracts').hbw.model_id", "jsonata"),
        ("ts_ms", "$millis()", "jsonata"),
    ]))
    return rules


def _pending_rules() -> list[dict]:
    """Offenen KI-Zyklus Feld fuer Feld speichern."""
    return _object_rules("ai.pending", "global", [
        ("cycle_id", "_cycle_id", "msg"), ("parent_request_id", "_parent_id", "msg"),
        ("source_id", "_source_id", "msg"), ("raw_state", "_raw", "msg"),
        ("model_profile", "_profile", "msg"),
        ("model_profile_name", "_raw.model_profile_name ? _raw.model_profile_name : _profile", "jsonata"),
        ("contracts", "_contracts", "msg"), ("storage_request_id", "_cycle_id & ':storage'", "jsonata"),
        ("storage_started_ms", "_started", "msg"), ("deadline_ms", "_started+10000", "jsonata"),
        ("responses", "{}", "json"), ("bootstrap", "{}", "json"), ("issued_commands", "{}", "json"),
    ])


def _cycle_result_rules() -> list[dict]:
    """Diagnoseergebnis ohne gemeinsame Command-Barriere bilden."""
    return _object_rules("payload", "msg", [
        ("schema_version", "1.0", "str"), ("cycle_id", "_pending.cycle_id", "msg"),
        ("request_id", "_pending.parent_request_id", "msg"), ("source_id", "_pending.source_id", "msg"),
        ("status", "completed", "str"), ("model_profile", "_pending.model_profile", "msg"),
        ("model_profile_name", "_pending.model_profile_name", "msg"),
        ("model_ids.storage", "_storage.model_id", "msg"), ("model_ids.vgr", "_vgr.model_id", "msg"),
        ("model_ids.hbw", "_hbw.model_id", "msg"), ("model_contracts", "_pending.contracts", "msg"),
        ("empty_storage", "_pending.empty_storage", "msg"), ("vgr_cmd", "$number(_vgr.cmd)", "jsonata"),
        ("hbw_cmd", "$number(_hbw.cmd)", "jsonata"),
        ("model_predictions.storage.empty_storage", "_storage.empty_storage", "msg"),
        ("model_predictions.storage.top3", "_storage.top3 ? _storage.top3 : []", "jsonata"),
        ("model_predictions.vgr.cmd", "$number(_vgr.cmd)", "jsonata"),
        ("model_predictions.vgr.name", "_vgr.name", "msg"),
        ("model_predictions.vgr.top3", "_vgr.top3 ? _vgr.top3 : []", "jsonata"),
        ("model_predictions.hbw.cmd", "$number(_hbw.cmd)", "jsonata"),
        ("model_predictions.hbw.name", "_hbw.name", "msg"),
        ("model_predictions.hbw.top3", "_hbw.top3 ? _hbw.top3 : []", "jsonata"),
        ("commands.vgr.cmd", "$number(_vgr.cmd)", "jsonata"),
        ("commands.vgr.topic", "_vgr.command_output.topic", "msg"),
        ("commands.vgr.publisher", "model_service", "str"),
        ("commands.vgr.published", "_vgr.command_output.published=true", "jsonata"),
        ("commands.vgr.mid", "_vgr.command_output.mid", "msg"),
        ("commands.hbw.cmd", "$number(_hbw.cmd)", "jsonata"),
        ("commands.hbw.topic", "_hbw.command_output.topic", "msg"),
        ("commands.hbw.publisher", "model_service", "str"),
        ("commands.hbw.published", "_hbw.command_output.published=true", "jsonata"),
        ("commands.hbw.mid", "_hbw.command_output.mid", "msg"),
        ("commands.mpo.cmd", "0", "num"), ("commands.mpo.topic", "ai/mpo/cmd0", "str"),
        ("commands.mpo.publisher", "ai_flow", "str"), ("commands.mpo.published", "_enabled", "msg"),
        ("commands.sld.cmd", "0", "num"), ("commands.sld.topic", "ai/sld/cmd0", "str"),
        ("commands.sld.publisher", "ai_flow", "str"), ("commands.sld.published", "_enabled", "msg"),
        ("command_output_enabled", "_enabled", "msg"),
        ("command_set_complete", "((_vgr.command_output.published=true)=_enabled and (_hbw.command_output.published=true)=_enabled)", "jsonata"),
        ("bootstrap", "_pending.bootstrap", "msg"), ("storage_latency_ms", "_pending.storage_latency_ms", "msg"),
        ("vgr_latency_ms", "_vgr._diagnostic_latency_ms", "msg"),
        ("hbw_latency_ms", "_hbw._diagnostic_latency_ms", "msg"),
        ("duration_ms", "_finished-_pending.storage_started_ms", "jsonata"),
        ("input_metadata", "_pending.raw_state", "msg"), ("qos", "2", "num"),
        ("retain", "false", "bool"), ("ts_ms", "_finished", "msg"),
    ])


def _base_contract_nodes() -> list[dict]:
    """Gruppen und Contract-Eingang."""
    tab = "tab-pipeline"
    return [
        _group("group-contracts", tab, "Contracts und Status", 20, 20, 1980, 250),
        _group("group-storage", tab, "Storage", 20, 290, 1980, 260),
        _group("group-window", tab, "Windowing und parallele Requests", 20, 570, 1980, 250),
        _group("group-responses", tab, "Responses und Reporting", 20, 840, 1980, 500),
        _comment("comment-pipeline", tab,
                 "Contract Gate | Storage | VGR/HBW parallel | Responses nur Reporting", 410, 45),
        _mqtt_in("in-contracts", tab, "group-contracts", "Modellvertraege",
                 "ft/nn/+/contract", "1", 120, 95, [["json-contract"]]),
        _json("json-contract", tab, "group-contracts", "Contract JSON", 300, 95,
              [["switch-contract-topic"]], "obj"),
        _switch("switch-contract-topic", tab, "group-contracts", "Domain aus Topic", "topic", [
            {"t": "eq", "v": "ft/nn/storage/contract", "vt": "str"},
            {"t": "eq", "v": "ft/nn/vgr/contract", "vt": "str"},
            {"t": "eq", "v": "ft/nn/hbw/contract", "vt": "str"},
        ], 490, 95, [["change-contract-storage"], ["change-contract-vgr"], ["change-contract-hbw"]],
                info="Wildcard sichtbar auf drei Domaenen aufteilen"),
    ]


def _contract_domain_nodes() -> list[dict]:
    """Contract-Domain sichtbar markieren."""
    tab = "tab-pipeline"
    nodes: list[dict] = []
    for index, domain in enumerate(("storage", "vgr", "hbw")):
        nodes.append(_change(
            f"change-contract-{domain}", tab, "group-contracts", f"{domain.upper()} markieren",
            [_set("_domain", "msg", domain, "str")], 690, 60 + index * 40,
            [["switch-contract-shape"]], info="Domain explizit setzen",
        ))
    return nodes


def _contract_nodes() -> list[dict]:
    """Contracts pruefen, speichern und Status empfangen."""
    tab = "tab-pipeline"
    return [
            _switch("switch-contract-shape", tab, "group-contracts", "Grundvertrag gueltig?",
                    valid_contract, [{"t": "true"}, {"t": "false"}], 900, 95,
                    [["switch-contract-change"], ["change-contract-error"]], prop_type="jsonata",
                    info="Schema | Domain | Featureliste | Klassen | Request/Response-Topic"),
            _switch("switch-contract-change", tab, "group-contracts", "Modellwechsel im Lauf?",
                    "$exists($lookup($globalContext('ai.contracts'),_domain).model_id) and "
                    "$lookup($globalContext('ai.contracts'),_domain).model_id != payload.model_id and "
                    "($globalContext('sim.run').running or $type($globalContext('ai.pending'))='object')",
                    [{"t": "false"}, {"t": "true"}], 1120, 95,
                    [["change-contract-store"], ["change-contract-change-error"]], prop_type="jsonata",
                    info="Profilwechsel nur zwischen Laeufen"),
            _change("change-contract-store", tab, "group-contracts", "Contract speichern", [
                _set("ai.contracts", "global", "$merge([$globalContext('ai.contracts') ? $globalContext('ai.contracts') : {},{(_domain):payload}])", "jsonata"),
            ], 1340, 75, [["change-readiness-context"]], info="Retained Contract domainbezogen ersetzen"),
            _change("change-contract-error", tab, "group-contracts", "Contractfehler", [
                _set("payload", "msg", "{'code':'contract_invalid','detail':_domain,'ts_ms':$millis()}", "jsonata")
            ], 1340, 115, [["link-fault-pipeline"]]),
            _change("change-contract-change-error", tab, "group-contracts", "Modellwechsel blockieren", [
                _set("payload", "msg", "{'code':'model_changed_during_cycle','detail':_domain,'ts_ms':$millis()}", "jsonata")
            ], 1340, 150, [["link-fault-pipeline"]]),
            _mqtt_in("in-model-statuses", tab, "group-contracts", "Modellstatus",
                     "ft/nn/+/status", "1", 120, 190, [["json-model-status"]]),
            _json("json-model-status", tab, "group-contracts", "Status JSON", 300, 190,
                  [["switch-status-topic"]], "obj"),
            _switch("switch-status-topic", tab, "group-contracts", "Statusdomain", "topic", [
                {"t": "eq", "v": "ft/nn/storage/status", "vt": "str"},
                {"t": "eq", "v": "ft/nn/vgr/status", "vt": "str"},
                {"t": "eq", "v": "ft/nn/hbw/status", "vt": "str"},
        ], 490, 190, [["change-status-storage"], ["change-status-vgr"], ["change-status-hbw"]]),
    ]


def _status_domain_nodes() -> list[dict]:
    """Status-Domain sichtbar markieren."""
    tab = "tab-pipeline"
    nodes: list[dict] = []
    for index, domain in enumerate(("storage", "vgr", "hbw")):
        nodes.append(_change(
            f"change-status-{domain}", tab, "group-contracts", f"{domain.upper()} Status",
            [_set("_domain", "msg", domain, "str")], 690, 160 + index * 35,
            [["switch-status-offline"]], info="Domain explizit setzen",
        ))
    return nodes


def _status_and_reset_nodes() -> list[dict]:
    """Bereitschaft melden und KI-Reset ausfuehren."""
    tab = "tab-pipeline"
    return [
            _switch("switch-status-offline", tab, "group-contracts", "Offline im Lauf?",
                    "payload.state!='online' and $globalContext('sim.run').running=true",
                    [{"t": "false"}, {"t": "true"}], 900, 190,
                    [["change-status-store"], ["change-status-error"]], prop_type="jsonata"),
            _change("change-status-store", tab, "group-contracts", "Status speichern", [
                _set("ai.statuses", "global", "$merge([$globalContext('ai.statuses') ? $globalContext('ai.statuses') : {},{(_domain):payload}])", "jsonata")
            ], 1110, 180, [["change-readiness-context"]]),
            _change("change-status-error", tab, "group-contracts", "Offlinefehler", [
                _set("payload", "msg", "{'code':'model_offline','detail':_domain,'ts_ms':$millis()}", "jsonata")
            ], 1110, 220, [["link-fault-pipeline"]]),
            _change("change-readiness-context", tab, "group-contracts", "Bereitschaft abbilden", [
            ] + _readiness_rules(), 1550, 185, [["json-ai-ready"]],
                info="Drei Contracts + drei Online-Status gemeinsam anzeigen"),
            _json("json-ai-ready", tab, "group-contracts", "Status JSON", 1740, 185, [["out-ai-ready"]]),
            _mqtt_out("out-ai-ready", tab, "group-contracts", "Orchestrierungsstatus",
                      "ft/ai/orchestration/status", "1", "true", 1920, 185),
            _mqtt_in("in-ai-control", tab, "group-contracts", "KI Reset",
                     "ft/ai/orchestration/control", "1", 1510, 70, [["json-ai-control"]]),
            _json("json-ai-control", tab, "group-contracts", "Control JSON", 1690, 70,
                  [["switch-ai-reset"]], "obj"),
            _switch("switch-ai-reset", tab, "group-contracts", "Reset?", "payload.cmd",
                    [{"t": "eq", "v": "reset", "vt": "str"}], 1840, 70, [["change-ai-reset"]]),
            _change("change-ai-reset", tab, "group-contracts", "KI-Zustand leeren", [
                _delete("ai.pending", "global"),
                _set("ai.windows", "global", json.dumps({"vgr": {}, "hbw": {}}), "json"),
                _set("ai.seen_responses", "global", "[]", "json"),
                _set("reset", "msg", "true", "bool"),
            ], 1840, 115, [["trigger-ai-timeout"]], info="Pending | Windows | Deduplizierung | Timeout"),
    ]


def _storage_request_nodes() -> list[dict]:
    """Livezustand pruefen und Storage anfragen."""
    tab = "tab-pipeline"
    return [
            _mqtt_in("in-live-pipeline", tab, "group-storage", "Freigegebener Anlagenzustand",
                     "log/logging/state", "1", 130, 360, [["json-live-pipeline"]]),
            _json("json-live-pipeline", tab, "group-storage", "Anlagenzustand JSON", 330, 360,
                  [["fn-contract-gate"]], "obj"),
            _function("fn-contract-gate", tab, "Dynamischen Modellvertrag pruefen", CONTRACT_FUNCTION,
                      560, 360, [["switch-storage-pending"], ["link-fault-pipeline"]],
                      FUNCTION_INFO["contract"], group="group-storage", outputs=2),
            _switch("switch-storage-pending", tab, "group-storage", "Zyklus bereits offen?",
                    "$type($globalContext('ai.pending'))='object'", [{"t": "false"}, {"t": "true"}],
                    800, 360, [["change-storage-cycle"], ["change-storage-pending-error"]], prop_type="jsonata"),
            _change("change-storage-pending-error", tab, "group-storage", "Pendingfehler", [
                _set("payload", "msg", "{'code':'invalid_payload','detail':'new live state while cycle pending','ts_ms':$millis()}", "jsonata")
            ], 1020, 400, [["link-fault-pipeline"]]),
            _change("change-storage-cycle", tab, "group-storage", "Cycle-ID + Pending", [
                _set("_cycle_no", "msg", "$number($globalContext('ai.cycle_counter') ? $globalContext('ai.cycle_counter') : 0)+1", "jsonata"),
                _set("ai.cycle_counter", "global", "_cycle_no", "msg"),
                _set("_source_id", "msg", "$string(_raw.source_id ? _raw.source_id : 'plc_live')", "jsonata"),
                _set("_parent_id", "msg", "$string(_raw.request_id ? _raw.request_id : 'live-' & $string($millis()) & '-' & $string(_cycle_no))", "jsonata"),
                _set("_correlation", "msg", "$string(_raw.correlation_id ? _raw.correlation_id : _parent_id)", "jsonata"),
                _set("_cycle_id", "msg", "'cycle-' & _source_id & '-' & _correlation & '-' & $formatNumber(_cycle_no,'000000')", "jsonata"),
                _set("_started", "msg", "$millis()", "jsonata"),
            ] + _pending_rules(), 1030, 340, [["change-storage-request"]],
                info="Cycle-ID | Quelle | Profil | Deadline gemeinsam setzen"),
            _change("change-storage-request", tab, "group-storage", "Storage-Request bilden", [
                _set("_pending", "msg", "$globalContext('ai.pending')", "jsonata"),
                _set("topic", "msg", "_pending.contracts.storage.request_topic", "msg"),
                _set("qos", "msg", "1", "num"),
                _set("retain", "msg", "false", "bool"),
            ] + _object_rules("payload", "msg", [
                ("cycle_id", "_pending.cycle_id", "msg"),
                ("request_id", "_pending.storage_request_id", "msg"),
                ("parent_request_id", "_pending.parent_request_id", "msg"),
                ("source_id", "_pending.source_id", "msg"),
                ("model_id", "_pending.contracts.storage.model_id", "msg"),
                ("features", "$merge($map(_pending.contracts.storage.feature_cols,function($feature){{($feature):$number($lookup(_pending.raw_state,$feature))}}))", "jsonata"),
            ]), 1260, 340, [["json-storage-request", "change-timeout-arm"]],
                info="Features in Contract-Reihenfolge | MQTT-Metadaten"),
            _json("json-storage-request", tab, "group-storage", "Storage JSON", 1490, 330,
                  [["out-storage-request"]]),
            _mqtt_out("out-storage-request", tab, "group-storage", "Storage-Request",
                      "ft/nn/storage/request", "1", "false", 1700, 330),
        
    ]


def _storage_response_nodes() -> list[dict]:
    """Storage-Response korrelieren und Klasse waehlen."""
    tab = "tab-pipeline"
    return [
            _mqtt_in("in-storage-result", tab, "group-storage", "Storage-Ergebnis",
                     "ft/nn/response/storage", "1", 130, 470, [["json-storage-result"]]),
            _json("json-storage-result", tab, "group-storage", "Storage JSON", 320, 470,
                  [["change-storage-response-context"]], "obj"),
            _change("change-storage-response-context", tab, "group-storage", "Pending + Response lesen", [
                _set("_response", "msg", "payload", "msg"),
                _set("_pending", "msg", "$globalContext('ai.pending')", "jsonata"),
                _set("_seen", "msg", "$globalContext('ai.seen_responses') ? $globalContext('ai.seen_responses') : []", "jsonata"),
            ], 550, 470, [["switch-storage-duplicate"]]),
            _switch("switch-storage-duplicate", tab, "group-storage", "Schon verarbeitet?",
                    "_response.request_id in _seen", [{"t": "false"}], 780, 470,
                    [["switch-storage-correlation"]], prop_type="jsonata"),
            _switch("switch-storage-correlation", tab, "group-storage", "Korrelation gueltig?",
                    "$exists(_pending) and _response.request_id=_pending.storage_request_id and "
                    "_response.cycle_id=_pending.cycle_id and $not($exists(_response.error))",
                    [{"t": "true"}, {"t": "false"}], 1000, 470,
                    [["switch-storage-class"], ["change-storage-response-error"]], prop_type="jsonata"),
            _switch("switch-storage-class", tab, "group-storage", "Storage-Klasse", "payload.empty_storage",
                    [{"t": "eq", "v": str(value), "vt": "num"} for value in range(10)] + [{"t": "else"}],
                    1210, 470,
                    [[f"change-onehot-{value}"] for value in range(10)] + [["change-storage-response-error"]],
                    info="Zehn sichtbare Klassenwege | sonst Fault"),
    ]


def _one_hot_nodes() -> list[dict]:
    """Zehn Storage-Klassen als One-hot abbilden."""
    tab = "tab-pipeline"
    nodes: list[dict] = []
    for value in range(10):
        one_hot = {f"empty_storage_{index}": int(index == value) for index in range(10)}
        nodes.append(_change(
            f"change-onehot-{value}", tab, "group-storage", f"Fachklasse {value}", [
                _set("ai.pending.responses", "global", "$merge([_pending.responses,{'storage':_response}])", "jsonata"),
                _set("ai.pending.empty_storage", "global", str(value), "num"),
                _set("ai.pending.storage_latency_ms", "global", "$millis()-_pending.storage_started_ms", "jsonata"),
                _set("ai.pending.one_hot", "global", json.dumps(one_hot, separators=(",", ":")), "json"),
                _set("ai.seen_responses", "global", "$append(_seen,_response.request_id)", "jsonata"),
                _set("payload", "msg", "{'cycle_id':_pending.cycle_id,'empty_storage':$number(_response.empty_storage),'model_id':_response.model_id,'top3':_response.top3 ? _response.top3 : []}", "jsonata"),
            ], 1440, 405 + value * 12, [["link-storage-ready-out"]],
            info=f"empty_storage_{value}=1 | neun Werte=0",
        ))
    return nodes


def _window_request_nodes() -> list[dict]:
    """VGR/HBW-Fenster und MPO/SLD-Idle senden."""
    tab = "tab-pipeline"
    return [
            _link_out("link-storage-ready-out", tab, "group-storage", "Zu Windowing + Idle", [
                "link-storage-vgr-in", "link-storage-hbw-in", "link-storage-idle-in",
                "link-storage-debug-in",
            ], 1660, 455),
            _link_in("link-storage-debug-in", tab, "group-storage", "Storage-Debug", 1660, 505,
                     [["debug-storage"]]),
            _change("change-storage-response-error", tab, "group-storage", "Storage-Responsefehler", [
                _set("payload", "msg", "{'code':'model_response_error','detail':'storage correlation, class or inference error','cycle_id':_pending.cycle_id,'ts_ms':$millis()}", "jsonata")
            ], 1450, 530, [["link-fault-pipeline"]]),
            _debug("debug-storage", tab, "group-storage", "Storage-Ergebnis", 1740, 470),
        
            _link_in("link-storage-vgr-in", tab, "group-window", "Zu VGR-Fenster", 145, 650,
                     [["subflow-window-vgr"]]),
            _link_in("link-storage-hbw-in", tab, "group-window", "Zu HBW-Fenster", 145, 720,
                     [["subflow-window-hbw"]]),
            _link_in("link-storage-idle-in", tab, "group-window", "Zu MPO / SLD", 915, 690,
                     [["change-idle-modules"]]),
            {"id": "subflow-window-vgr", "type": "subflow:subflow-lstm-window", "z": tab, "g": "group-window",
             "name": "VGR W=10", "env": [{"name": "DOMAIN", "value": "vgr", "type": "str"}],
             "x": 350, "y": 650, "wires": [["json-vgr-request", "change-debug-request-vgr", "change-timeout-arm"]]},
            {"id": "subflow-window-hbw", "type": "subflow:subflow-lstm-window", "z": tab, "g": "group-window",
             "name": "HBW W=10", "env": [{"name": "DOMAIN", "value": "hbw", "type": "str"}],
             "x": 350, "y": 720, "wires": [["json-hbw-request", "change-debug-request-hbw", "change-timeout-arm"]]},
            _json("json-vgr-request", tab, "group-window", "VGR JSON", 600, 650, [["out-vgr-request"]]),
            _mqtt_out("out-vgr-request", tab, "group-window", "VGR-Request",
                      "ft/nn/vgr/request", "1", "false", 810, 650),
            _json("json-hbw-request", tab, "group-window", "HBW JSON", 600, 720, [["out-hbw-request"]]),
            _mqtt_out("out-hbw-request", tab, "group-window", "HBW-Request",
                      "ft/nn/hbw/request", "1", "false", 810, 720),
            _change("change-debug-request-vgr", tab, "group-window", "VGR Kurzinfo", [
                _set("payload", "msg", "_request_summary", "msg")
            ], 600, 610, [["debug-request-vgr"]]),
            _debug("debug-request-vgr", tab, "group-window", "VGR-Request Kurzinfo", 810, 610),
            _change("change-debug-request-hbw", tab, "group-window", "HBW Kurzinfo", [
                _set("payload", "msg", "_request_summary", "msg")
            ], 600, 770, [["debug-request-hbw"]]),
            _debug("debug-request-hbw", tab, "group-window", "HBW-Request Kurzinfo", 810, 770),
            _change("change-idle-modules", tab, "group-window", "MPO / SLD Idle", [
                _set("payload", "msg", json.dumps([
                    {"topic": "ai/mpo/cmd0", "payload": "", "qos": 2, "retain": False},
                    {"topic": "ai/sld/cmd0", "payload": "", "qos": 2, "retain": False},
                ], separators=(",", ":")), "json")
            ], 1080, 690, [["split-idle-modules"]]),
            {"id": "split-idle-modules", "type": "split", "z": tab, "g": "group-window",
             "name": "Idle-Commands trennen", "splt": "\\n", "spltType": "str", "arraySplt": 1,
             "arraySpltType": "len", "stream": False, "addname": "", "property": "payload",
             "x": 1300, "y": 690, "wires": [["change-idle-command"]]},
            _change("change-idle-command", tab, "group-window", "MQTT-Felder", [
                _set("topic", "msg", "payload.topic", "msg"), _set("qos", "msg", "payload.qos", "msg"),
                _set("retain", "msg", "payload.retain", "msg"), _set("payload", "msg", "", "str"),
            ], 1510, 690, [["out-idle-modules"]]),
            _mqtt_out("out-idle-modules", tab, "group-window", "MPO / SLD Idle", "", "", "", 1720, 690),
    ]


def _response_nodes() -> list[dict]:
    """VGR/HBW fuer Diagnose und Report verbinden."""
    tab = "tab-pipeline"
    return [
            _mqtt_in("in-vgr-response", tab, "group-responses", "VGR-Response",
                     "ft/nn/response/vgr", "1", 130, 910, [["json-vgr-response"]]),
            _json("json-vgr-response", tab, "group-responses", "VGR JSON", 310, 910,
                  [["subflow-response-vgr"]], "obj"),
            {"id": "subflow-response-vgr", "type": "subflow:subflow-model-response", "z": tab,
             "g": "group-responses", "name": "VGR pruefen", "env": [{"name": "DOMAIN", "value": "vgr", "type": "str"}],
             "x": 500, "y": 910, "wires": [["join-model-responses"], ["link-fault-pipeline"]]},
            _mqtt_in("in-hbw-response", tab, "group-responses", "HBW-Response",
                     "ft/nn/response/hbw", "1", 130, 970, [["json-hbw-response"]]),
            _json("json-hbw-response", tab, "group-responses", "HBW JSON", 310, 970,
                  [["subflow-response-hbw"]], "obj"),
            {"id": "subflow-response-hbw", "type": "subflow:subflow-model-response", "z": tab,
             "g": "group-responses", "name": "HBW pruefen", "env": [{"name": "DOMAIN", "value": "hbw", "type": "str"}],
             "x": 500, "y": 970, "wires": [["join-model-responses"], ["link-fault-pipeline"]]},
            {"id": "join-model-responses", "type": "join", "z": tab, "g": "group-responses",
             "name": "Responses fuer Report", "mode": "auto", "build": "object", "property": "payload",
             "propertyType": "msg", "key": "topic", "joiner": "\\n", "joinerType": "str",
             "accumulate": False, "timeout": "10", "count": "2", "reduceRight": False,
             "reduceExp": "", "reduceInit": "", "reduceInitType": "", "reduceFixup": "",
             "x": 750, "y": 940, "wires": [["change-cycle-context"]]},
            _change("change-cycle-context", tab, "group-responses", "Diagnose-Snapshot lesen", [
                _set("_pending", "msg", "$globalContext('ai.pending')", "jsonata"),
                _set("_finished", "msg", "$millis()", "jsonata"),
                _set("_vgr", "msg", "payload.vgr", "msg"), _set("_hbw", "msg", "payload.hbw", "msg"),
                _set("_storage", "msg", "$globalContext('ai.pending').responses.storage", "jsonata"),
                _set("_enabled", "msg", "$lowercase($env('COMMAND_OUTPUT_ENABLED'))='true'", "jsonata"),
            ], 980, 940, [["change-cycle-result"]], info="Nur Reporting | keine Command-Barriere"),
            _change("change-cycle-result", tab, "group-responses", "Zyklusergebnis bilden", [
            ] + _cycle_result_rules() + [
                _set("topic", "msg", "ft/ai/orchestration/cycle_result", "str"),
                _set("qos", "msg", "1", "num"), _set("retain", "msg", "false", "bool"),
                _delete("ai.pending", "global"), _set("reset", "msg", "true", "bool"),
            ], 1210, 940, [["json-cycle-result", "change-report-row", "trigger-ai-timeout"]],
                info="Zwei Responses + Pending-Snapshot | Pending danach leeren"),
            _json("json-cycle-result", tab, "group-responses", "Zyklus JSON", 1450, 890,
                  [["out-cycle-result"]]),
            _mqtt_out("out-cycle-result", tab, "group-responses", "Zyklusergebnis",
                      "ft/ai/orchestration/cycle_result", "1", "false", 1680, 890),
            _change("change-timeout-arm", tab, "group-responses", "Timeout neu starten", [
                _delete("reset"), _set("payload", "msg", "null", "json")
            ], 140, 1040, [["trigger-ai-timeout"]]),
            {"id": "trigger-ai-timeout", "type": "trigger", "z": tab, "g": "group-responses",
             "name": "10 s Response-Timeout", "op1": "", "op2": "true", "op1type": "nul",
             "op2type": "bool", "duration": "10", "extend": True, "overrideDelay": False,
             "units": "s", "reset": "", "bytopic": "all", "topic": "topic", "outputs": 1,
             "x": 390, "y": 1040, "wires": [["change-timeout-error"]]},
            _change("change-timeout-error", tab, "group-responses", "Timeoutfehler", [
                _set("_pending", "msg", "$globalContext('ai.pending')", "jsonata"),
                _delete("ai.pending", "global"),
                _set("payload", "msg", "{'code':'inference_timeout','detail':'model response deadline exceeded','cycle_id':_pending.cycle_id,'ts_ms':$millis()}", "jsonata"),
            ], 620, 1040, [["link-fault-pipeline"]]),
        _link_out("link-fault-pipeline", tab, "group-responses", "Zum Fault-Latch",
                      ["link-fault-central"], 850, 1040),
    ]


def _diagnostic_nodes() -> list[dict]:
    """Flow- und MQTT-Fehler weiterleiten."""
    tab = "tab-pipeline"
    return [
            {"id": "catch-pipeline", "type": "catch", "z": tab, "name": "Pipelinefehler",
             "scope": ["fn-contract-gate", "json-storage-request", "json-vgr-request", "json-hbw-request",
                       "change-storage-request", "change-cycle-result", "file-report-append-inline", "file-report-replace-inline"],
             "uncaught": False, "x": 1230, "y": 1300, "wires": [["change-catch-pipeline"]]},
            _change("change-catch-pipeline", tab, "", "Fehler normalisieren", [
                _set("payload", "msg", "{'code':'runtime_error','detail':error.message,'source':error.source.name}", "jsonata")
            ], 1450, 1300, [["link-fault-pipeline"]]),
            {"id": "status-mqtt-pipeline", "type": "status", "z": tab, "name": "MQTT-Zustand",
             "scope": ["in-contracts", "in-model-statuses", "in-live-pipeline", "out-storage-request",
                       "out-vgr-request", "out-hbw-request", "out-idle-modules"],
             "x": 1230, "y": 1335, "wires": [["switch-mqtt-pipeline"]]},
            _switch("switch-mqtt-pipeline", tab, "", "MQTT getrennt?", "status.text",
                    [{"t": "regex", "v": "disconnected|error", "vt": "str", "case": False}],
                    1450, 1335, [["change-mqtt-pipeline"]]),
            _change("change-mqtt-pipeline", tab, "", "MQTT-Fehler", [
                _set("payload", "msg", "{'code':'mqtt_disconnected','detail':status.text,'source':'NN-Pipeline'}", "jsonata")
            ], 1660, 1335, [["link-fault-pipeline"]]),
    ]


def build_pipeline_nodes() -> list[dict]:
    """Pipeline aus kleinen sichtbaren Pfaden zusammensetzen."""
    return (
        _base_contract_nodes()
        + _contract_domain_nodes()
        + _contract_nodes()
        + _status_domain_nodes()
        + _status_and_reset_nodes()
        + _storage_request_nodes()
        + _storage_response_nodes()
        + _one_hot_nodes()
        + _window_request_nodes()
        + _response_nodes()
        + build_reporting_nodes()
        + _diagnostic_nodes()
    )
