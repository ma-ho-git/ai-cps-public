"""Zyklus- und Laufreports erzeugen."""

from .common import (
    REPORT_COLUMNS,
    _change,
    _delete,
    _json,
    _mqtt_in,
    _object_rules,
    _set,
    _switch,
)

ROW_ID_FIELDS = [
    ("row_index", "_row_index", "msg"), ("request_id_base", "_result.request_id", "msg"),
    ("cycle_id", "_result.cycle_id", "msg"), ("phase", "_meta.phase ? _meta.phase : 'live_state'", "jsonata"),
    ("trace_phase", "_meta.trace_phase", "msg"), ("attempt_repeat_idx", "_meta.attempt_repeat_idx", "msg"),
    ("guard_episode_idx", "_meta.guard_episode_idx", "msg"), ("guard_prefix_idx", "_meta.guard_prefix_idx", "msg"),
    ("guard_process_step_idx", "_meta.guard_process_step_idx", "msg"),
    ("guard_source_episode_id", "_meta.guard_source_episode_id", "msg"),
    ("source_id", "_result.source_id", "msg"), ("trace_profile", "_meta.trace_profile", "msg"),
    ("trace_profile_name", "_meta.trace_profile_name", "msg"), ("model_profile", "_result.model_profile", "msg"),
    ("model_profile_name", "_result.model_profile_name", "msg"), ("factory_seed", "_meta.factory_seed", "msg"),
    ("factory_base_runtime_vgr_ms", "_meta.factory_base_runtime_ms.vgr", "msg"),
    ("factory_base_runtime_hbw_ms", "_meta.factory_base_runtime_ms.hbw", "msg"),
    ("factory_base_runtime_mpo_ms", "_meta.factory_base_runtime_ms.mpo", "msg"),
    ("factory_base_runtime_sld_ms", "_meta.factory_base_runtime_ms.sld", "msg"),
]
ROW_MODEL_FIELDS = [
    ("storage_model_id", "_result.model_ids.storage", "msg"), ("vgr_model_id", "_result.model_ids.vgr", "msg"),
    ("hbw_model_id", "_result.model_ids.hbw", "msg"), ("expected_empty_storage", "_meta.expected_empty_storage", "msg"),
    ("vgr_storage_pred", "_result.empty_storage", "msg"), ("hbw_storage_pred", "_result.empty_storage", "msg"),
    ("storage_match_vgr", "$exists(_meta.expected_empty_storage)?$number(_result.empty_storage)=$number(_meta.expected_empty_storage):''", "jsonata"),
    ("storage_match_hbw", "$exists(_meta.expected_empty_storage)?$number(_result.empty_storage)=$number(_meta.expected_empty_storage):''", "jsonata"),
    ("storage_confidence", "_result.model_predictions.storage.top3[0].p", "msg"),
    ("expected_label_VGR", "_meta.expected_label_VGR", "msg"), ("predicted_label_VGR", "_result.vgr_cmd", "msg"),
    ("vgr_match", "$exists(_meta.expected_label_VGR)?$number(_result.vgr_cmd)=$number(_meta.expected_label_VGR):''", "jsonata"),
    ("vgr_ready", "_result.status='completed'", "jsonata"),
    ("vgr_confidence", "_result.model_predictions.vgr.top3[0].p", "msg"),
    ("vgr_latency_s", "$number(_result.vgr_latency_ms)/1000", "jsonata"),
    ("expected_label_HBW", "_meta.expected_label_HBW", "msg"), ("predicted_label_HBW", "_result.hbw_cmd", "msg"),
    ("hbw_match", "$exists(_meta.expected_label_HBW)?$number(_result.hbw_cmd)=$number(_meta.expected_label_HBW):''", "jsonata"),
    ("hbw_ready", "_result.status='completed'", "jsonata"),
    ("hbw_confidence", "_result.model_predictions.hbw.top3[0].p", "msg"),
    ("hbw_latency_s", "$number(_result.hbw_latency_ms)/1000", "jsonata"),
    ("timeout", "$contains($string(_result.error),'timeout')", "jsonata"), ("error", "_result.error", "msg"),
]
ROW_COMMAND_FIELDS = [
    ("control_enabled", "_result.command_output_enabled", "msg"),
    ("control_published", "_result.command_output_enabled and _result.status='completed' and _result.command_set_complete", "jsonata"),
    ("control_reason", "_result.status='completed'?(_result.command_output_enabled?'published_independently':'disabled'):_result.status", "jsonata"),
    ("control_command_set_complete", "_result.command_set_complete", "msg"),
    ("control_vgr_cmd", "_result.commands.vgr.cmd", "msg"), ("control_hbw_cmd", "_result.commands.hbw.cmd", "msg"),
    ("control_mpo_cmd", "_result.commands.mpo.cmd", "msg"), ("control_sld_cmd", "_result.commands.sld.cmd", "msg"),
    ("control_vgr_topic", "_result.commands.vgr.topic", "msg"), ("control_hbw_topic", "_result.commands.hbw.topic", "msg"),
    ("control_mpo_topic", "_result.commands.mpo.topic", "msg"), ("control_sld_topic", "_result.commands.sld.topic", "msg"),
    ("control_vgr_publisher", "_result.commands.vgr.publisher", "msg"),
    ("control_hbw_publisher", "_result.commands.hbw.publisher", "msg"),
    ("control_mpo_publisher", "_result.commands.mpo.publisher", "msg"),
    ("control_sld_publisher", "_result.commands.sld.publisher", "msg"),
    ("control_qos", "_result.qos", "msg"), ("control_retain", "_result.retain", "msg"),
    ("bootstrap_vgr_rows", "_result.bootstrap.vgr.seeded_rows", "msg"),
    ("bootstrap_hbw_rows", "_result.bootstrap.hbw.seeded_rows", "msg"),
]
ROW_MODULE_FIELDS = [
    ("module_runtime_vgr_ms", "_meta.module_runtime_ms.vgr", "msg"),
    ("module_runtime_hbw_ms", "_meta.module_runtime_ms.hbw", "msg"),
    ("module_runtime_mpo_ms", "_meta.module_runtime_ms.mpo", "msg"),
    ("module_runtime_sld_ms", "_meta.module_runtime_ms.sld", "msg"),
    ("job_sent_vgr", "_meta.module_job_counts.sent.vgr", "msg"),
    ("job_sent_hbw", "_meta.module_job_counts.sent.hbw", "msg"),
    ("job_sent_mpo", "_meta.module_job_counts.sent.mpo", "msg"),
    ("job_sent_sld", "_meta.module_job_counts.sent.sld", "msg"),
    ("job_accepted_vgr", "_meta.module_job_counts.accepted.vgr", "msg"),
    ("job_accepted_hbw", "_meta.module_job_counts.accepted.hbw", "msg"),
    ("job_accepted_mpo", "_meta.module_job_counts.accepted.mpo", "msg"),
    ("job_accepted_sld", "_meta.module_job_counts.accepted.sld", "msg"),
]
columns = ",".join(REPORT_COLUMNS)


def _report_row_rules() -> list[dict]:
    """Stabile CSV-Spalten einzeln abbilden."""
    fields = ROW_ID_FIELDS + ROW_MODEL_FIELDS + ROW_COMMAND_FIELDS + ROW_MODULE_FIELDS
    return _object_rules("_row", "msg", fields)


def _report_state_init_rules() -> list[dict]:
    """Zaehler fuer einen neuen Report initialisieren."""
    return _object_rules("report.state", "flow", [
        ("run_id", "_report_id", "msg"),
        ("run_dir", r"$replace($env('REPORT_ROOT'),/\/$/,'') & '/' & _report_id", "jsonata"),
        ("started_at", "$fromMillis($millis())", "jsonata"), ("rows", "0", "num"),
        ("matches", "{\"storage\":0,\"vgr\":0,\"hbw\":0}", "json"),
        ("faults", "0", "num"), ("command_rows", "0", "num"),
        ("idle_fallback_rows", "0", "num"), ("factory_run_id", "null", "json"),
        ("last_cycle_status", "null", "json"), ("model_ids", "{}", "json"),
        ("run_config", "{}", "json"),
    ])


def _report_state_update_rules() -> list[dict]:
    """Reportzaehler nach einem Zyklus fortschreiben."""
    return [
        _set("_report_state", "msg", "_state", "msg"),
        _set("_report_state.rows", "msg", "_state.rows+1", "jsonata"),
        _set("_report_state.matches.storage", "msg", "_state.matches.storage+(_row.storage_match_vgr=true?1:0)", "jsonata"),
        _set("_report_state.matches.vgr", "msg", "_state.matches.vgr+(_row.vgr_match=true?1:0)", "jsonata"),
        _set("_report_state.matches.hbw", "msg", "_state.matches.hbw+(_row.hbw_match=true?1:0)", "jsonata"),
        _set("_report_state.faults", "msg", "_state.faults+(_result.status='fault_latched'?1:0)", "jsonata"),
        _set("_report_state.command_rows", "msg", "_state.command_rows+(_row.control_published=true?1:0)", "jsonata"),
        _set("_report_state.factory_run_id", "msg", "_state.factory_run_id?_state.factory_run_id:(_meta.simulation_run_id?_meta.simulation_run_id:_meta.correlation_id)", "jsonata"),
        _set("_report_state.last_cycle_status", "msg", "_result.status", "msg"),
        _set("_report_state.model_ids", "msg", "_result.model_ids", "msg"),
        _set("_report_state.run_config.trace_profile", "msg", "_row.trace_profile", "msg"),
        _set("_report_state.run_config.trace_profile_name", "msg", "_row.trace_profile_name", "msg"),
        _set("_report_state.run_config.model_profile", "msg", "_row.model_profile", "msg"),
        _set("_report_state.run_config.model_profile_name", "msg", "_row.model_profile_name", "msg"),
        _set("_report_state.run_config.seed", "msg", "_row.factory_seed", "msg"),
        _set("_report_state.run_config.base_runtime_ms.vgr", "msg", "_row.factory_base_runtime_vgr_ms", "msg"),
        _set("_report_state.run_config.base_runtime_ms.hbw", "msg", "_row.factory_base_runtime_hbw_ms", "msg"),
        _set("_report_state.run_config.base_runtime_ms.mpo", "msg", "_row.factory_base_runtime_mpo_ms", "msg"),
        _set("_report_state.run_config.base_runtime_ms.sld", "msg", "_row.factory_base_runtime_sld_ms", "msg"),
    ]


def _summary_rules() -> list[dict]:
    """Laufzusammenfassung aus Reportzaehlern bilden."""
    return _object_rules("payload", "msg", [
        ("mode", "live_mqtt_nodered", "str"), ("completed", "_completed", "msg"),
        ("stopped", "_stopped", "msg"), ("stop_reason", "_stop_reason", "msg"),
        ("last_cycle_status", "_report_state.last_cycle_status", "msg"),
        ("rows_completed", "_report_state.rows", "msg"),
        ("control_published_rows", "_report_state.command_rows", "msg"),
        ("control_published_commands", "_report_state.command_rows*4", "jsonata"),
        ("control_idle_fallback_rows", "_report_state.idle_fallback_rows", "msg"),
        ("faults", "_report_state.faults", "msg"),
        ("storage_matches_vgr", "_report_state.matches.storage", "msg"),
        ("storage_matches_hbw", "_report_state.matches.storage", "msg"),
        ("vgr_matches", "_report_state.matches.vgr", "msg"), ("hbw_matches", "_report_state.matches.hbw", "msg"),
        ("model_ids", "_report_state.model_ids", "msg"), ("run_config", "_report_state.run_config", "msg"),
        ("started_at", "_report_state.started_at", "msg"), ("updated_at", "$fromMillis($millis())", "jsonata"),
        ("events_path", "_report_state.run_dir & '/events.jsonl'", "jsonata"),
        ("summary_path", "_report_state.run_dir & '/summary.csv'", "jsonata"),
    ])


def _row_nodes() -> list[dict]:
    """Reportzustand laden und Zeile zaehlen."""
    tab = "tab-pipeline"
    group = "group-responses"
    return [
            _change("change-report-row", tab, group, "CSV-Felder abbilden", [
                _set("_result", "msg", "payload", "msg"),
                _set("_meta", "msg", "payload.input_metadata ? payload.input_metadata : {}", "jsonata"),
            ], 1450, 950, [["switch-report-state"]], info="Ein Feld je stabiler Reportspalte"),
            _switch("switch-report-state", tab, group, "Report bereits offen?",
                    "$type($flowContext('report.state'))='object'", [{"t": "true"}, {"t": "false"}],
                    1640, 950, [["change-report-state-read"], ["change-report-state-init"]], prop_type="jsonata"),
            _change("change-report-state-init", tab, group, "Reportpfad initialisieren", [
                _set("_report_id", "msg", "$replace($fromMillis($millis()),/[-:TZ.]/,'') & '_nodered'", "jsonata"),
            ] + _report_state_init_rules(), 1840, 985, [["change-report-state-read"]],
                info="Neuer Ordner je Lauf | Flow-Context"),
            _change("change-report-state-read", tab, group, "Reportzaehler lesen", [
                _set("_state", "msg", "$flowContext('report.state')", "jsonata"),
                _set("_row_index", "msg", "$flowContext('report.state').rows", "jsonata"),
            ], 1840, 930, [["change-report-row-map"]]),
            _change("change-report-row-map", tab, group, "Tabellenzeile bilden", [
            ] + _report_row_rules(), 1840, 890, [["change-report-state-update"]]),
            _change("change-report-state-update", tab, group, "Reportzaehler aktualisieren", [
            ] + _report_state_update_rules() + [
                _set("report.state", "flow", "_report_state", "msg"),
            ], 1640, 890, [["change-report-event", "switch-report-first-row", "change-report-summary-running"]],
                info="Zeile | Matches | Commands | Modell-IDs"),
    ]


def _event_and_csv_nodes() -> list[dict]:
    """Event und stabile CSV-Zeile schreiben."""
    tab = "tab-pipeline"
    group = "group-responses"
    return [
            _change("change-report-event", tab, group, "Event JSONL", [
                _set("filename", "msg", "_report_state.run_dir & '/events.jsonl'", "jsonata"),
                _set("payload", "msg", "_result", "msg"),
            ], 1450, 1080, [["json-report-event"]]),
            _json("json-report-event", tab, group, "Event JSON", 1630, 1080,
                  [["change-report-event-newline"]], "str"),
            _change("change-report-event-newline", tab, group, "Zeilenabschluss", [
                _set("payload", "msg", "payload & '\n'", "jsonata")
            ], 1830, 1080, [["file-report-append-inline"]]),
            _switch("switch-report-first-row", tab, group, "Erste CSV-Zeile?", "_row_index",
                    [{"t": "eq", "v": "0", "vt": "num"}, {"t": "else"}], 1420, 1140,
                    [["change-report-csv-first"], ["change-report-csv-next"]]),
            _change("change-report-csv-first", tab, group, "CSV + Header", [
                _set("payload", "msg", "_row", "msg"),
                _set("filename", "msg", "_report_state.run_dir & '/summary.csv'", "jsonata"),
            ], 1620, 1125, [["csv-report-first"]]),
            _change("change-report-csv-next", tab, group, "CSV-Zeile", [
                _set("payload", "msg", "_row", "msg"),
                _set("filename", "msg", "_report_state.run_dir & '/summary.csv'", "jsonata"),
            ], 1620, 1175, [["csv-report-next"]]),
            {"id": "csv-report-first", "type": "csv", "z": tab, "g": group, "name": "CSV mit Header",
             "sep": ",", "hdrin": "", "hdrout": "all", "multi": "one", "ret": "\\n",
             "temp": columns, "skip": "0", "strings": True, "include_empty_strings": "",
             "include_null_values": "", "x": 1820, "y": 1125, "wires": [["file-report-append-inline"]]},
            {"id": "csv-report-next", "type": "csv", "z": tab, "g": group, "name": "CSV ohne Header",
             "sep": ",", "hdrin": "", "hdrout": "none", "multi": "one", "ret": "\\n",
             "temp": columns, "skip": "0", "strings": True, "include_empty_strings": "",
             "include_null_values": "", "x": 1820, "y": 1175, "wires": [["file-report-append-inline"]]},
    ]


def _summary_nodes() -> list[dict]:
    """Laufende oder finale Summary schreiben."""
    tab = "tab-pipeline"
    group = "group-responses"
    return [
            _change("change-report-summary-running", tab, group, "Laufende Summary", [
                _set("_factory_status", "msg", "null", "json"), _set("_completed", "msg", "false", "bool"),
                _set("_stopped", "msg", "false", "bool"), _set("_stop_reason", "msg", "running", "str"),
            ], 1420, 1220, [["change-report-summary"]]),
            _mqtt_in("in-report-factory-status", tab, group, "Fabrikabschluss",
                     "ft/sim/factory/status", "1", 930, 1220, [["json-report-factory-status"]]),
            _json("json-report-factory-status", tab, group, "Status JSON", 1120, 1220,
                  [["switch-report-factory-status"]], "obj"),
            _switch("switch-report-factory-status", tab, group, "Abschluss oder Reset", "payload.state", [
                {"t": "eq", "v": "completed", "vt": "str"}, {"t": "eq", "v": "reset", "vt": "str"},
            ], 1300, 1260, [["switch-report-run-id"], ["switch-report-run-id"]]),
            _switch("switch-report-run-id", tab, group, "Passender Fabriklauf?",
                    "$type($flowContext('report.state'))='object' and payload.run_id=$flowContext('report.state').factory_run_id",
                    [{"t": "true"}], 1500, 1270, [["change-report-summary-final"]], prop_type="jsonata",
                    info="Retained Fremdstatus ignorieren"),
            _change("change-report-summary-final", tab, group, "Report finalisieren", [
                _set("_report_state", "msg", "$flowContext('report.state')", "jsonata"),
                _set("_factory_status", "msg", "payload", "msg"),
                _set("_completed", "msg", "payload.state='completed'", "jsonata"),
                _set("_stopped", "msg", "payload.state='reset'", "jsonata"),
                _set("_stop_reason", "msg", "payload.state", "msg"),
                _delete("report.state", "flow"),
            ], 1710, 1270, [["change-report-summary"]]),
            _change("change-report-summary", tab, group, "Run Summary bilden", [
                _set("filename", "msg", "_report_state.run_dir & '/run_summary.json'", "jsonata"),
            ] + _summary_rules(), 1620, 1220, [["switch-report-factory-summary"]],
                info="Running | Completed | Reset"),
            _switch("switch-report-factory-summary", tab, group, "Finaler Fabrikstatus?",
                    "$type(_factory_status)='object'", [{"t": "true"}, {"t": "false"}],
                    1790, 1270, [["change-report-factory-summary"], ["json-report-summary"]],
                    prop_type="jsonata"),
            _change("change-report-factory-summary", tab, group, "Fabrikstatus ergaenzen", [
                _set("payload.factory_status.run_id", "msg", "_factory_status.run_id", "msg"),
                _set("payload.factory_status.trace_total", "msg", "_factory_status.trace_total", "msg"),
                _set("payload.factory_status.payloads_sent", "msg", "_factory_status.payloads_sent", "msg"),
                _set("payload.factory_status.progress_percent", "msg", "_factory_status.progress_percent", "msg"),
                _set("payload.factory_status.sent_counts", "msg", "_factory_status.sent_counts", "msg"),
                _set("payload.factory_status.accepted_counts", "msg", "_factory_status.accepted_counts", "msg"),
            ], 1790, 1310, [["json-report-summary"]]),
            _json("json-report-summary", tab, group, "Summary JSON", 1810, 1220,
                  [["file-report-replace-inline"]], "str"),
            {"id": "file-report-append-inline", "type": "file", "z": tab, "g": group,
             "name": "Events / CSV", "filename": "filename", "filenameType": "msg",
             "appendNewline": False, "createDir": True, "overwriteFile": "false", "encoding": "none",
             "x": 1920, "y": 1080, "wires": [[]]},
            {"id": "file-report-replace-inline", "type": "file", "z": tab, "g": group,
             "name": "Run Summary", "filename": "filename", "filenameType": "msg",
             "appendNewline": False, "createDir": True, "overwriteFile": "true", "encoding": "none",
             "x": 1920, "y": 1220, "wires": [[]]},
    ]


def build_reporting_nodes() -> list[dict]:
    """Drei Reportpfade aus Core-Nodes zusammensetzen."""
    return _row_nodes() + _event_and_csv_nodes() + _summary_nodes()
