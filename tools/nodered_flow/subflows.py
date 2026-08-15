"""Wiederverwendbare Modul- und LSTM-Subflows."""

from .common import (
    FUNCTION_INFO,
    RUNTIME_FUNCTION,
    WINDOW_FUNCTION,
    _change,
    _function,
    _object_rules,
    _set,
    _switch,
)

def _module_definition() -> dict:
    """Subflow-Schnittstelle und sichtbare Hilfe."""
    return {
        "id": "subflow-virtual-module",
        "type": "subflow",
        "name": "Virtuelles Modul",
        "info": """### Ablauf
- Init / Reset / Command trennen
- Busy pruefen
- `sent_count++`
- Laufzeit bestimmen
- Core-Delay
- `accepted_count++`

Einzige Function: deterministische Laufzeit.""",
        "category": "AI-CPS",
        "in": [{"x": 40, "y": 120, "wires": [{"id": "sub-module-event"}]}],
        "out": [
            {"x": 1120, "y": 80, "wires": [
                {"id": "sub-module-start-status", "port": 0},
                {"id": "sub-module-complete", "port": 0},
            ]},
            {"x": 1120, "y": 150, "wires": [{"id": "sub-module-duplicate", "port": 0}]},
            {"x": 1120, "y": 220, "wires": [{"id": "sub-module-idle", "port": 0}]},
        ],
        "env": [{"name": "MODULE", "type": "str", "value": "vgr"}],
        "meta": {},
        "color": "#DDAA99",
    }


def _module_input_nodes() -> list[dict]:
    """Init, Reset und Command unterscheiden."""
    return [
            _switch(
                "sub-module-event", "subflow-virtual-module", "", "Ereignis waehlen",
                "_event",
                [{"t": "eq", "v": "init", "vt": "str"},
                 {"t": "eq", "v": "reset", "vt": "str"},
                 {"t": "eq", "v": "command", "vt": "str"}],
                180, 120,
                [["sub-module-idle"], ["sub-module-reset"], ["sub-module-active"]],
                info="Init | Reset | Command",
            ),
            _change(
                "sub-module-idle", "subflow-virtual-module", "", "Variablen + Idle",
                [
                    _set("busy", "flow", "false", "bool"),
                    _set("last_command", "flow", "", "str"),
                    _set("runtime_ms", "flow", "0", "num"),
                    _set("_module", "msg", "$env('MODULE')", "jsonata"),
                    _set("topic", "msg", "$lookup({'vgr':'ai/vgr/cmd0','hbw':'ai/hbw/cmd000','mpo':'ai/mpo/cmd0','sld':'ai/sld/cmd0'},$env('MODULE'))", "jsonata"),
                    _set("payload", "msg", "", "str"),
                    _set("qos", "msg", "2", "num"),
                    _set("retain", "msg", "false", "bool"),
                ],
                410, 60, [], info="Busy=false | Idle-Topic | QoS 2",
            ),
            _change(
                "sub-module-reset", "subflow-virtual-module", "", "Delay + Zustand leeren",
                [
                    _set("busy", "flow", "false", "bool"),
                    _set("last_command", "flow", "", "str"),
                    _set("runtime_ms", "flow", "0", "num"),
                    _set("reset", "msg", "true", "bool"),
                ],
                410, 105, [["sub-module-delay"]], info="Busy=false | Delay-Queue leeren",
            ),
    ]


def _module_start_nodes() -> list[dict]:
    """Command annehmen und Laufzeit starten."""
    return [
            _switch(
                "sub-module-active", "subflow-virtual-module", "", "Lauf aktiv?",
                "$globalContext('sim.run').running = true and $not($globalContext('sim.run').fault)",
                [{"t": "true"}], 400, 150, [["sub-module-free"]], prop_type="jsonata",
                info="Nur laufende, fehlerfreie Simulation",
            ),
            _switch(
                "sub-module-free", "subflow-virtual-module", "", "Modul frei?",
                "busy", [{"t": "false"}, {"t": "true"}], 590, 150,
                [["sub-module-accept"], ["sub-module-duplicate"]], prop_type="flow",
                info="Frei: annehmen | Busy: Fault",
            ),
            _change(
                "sub-module-accept", "subflow-virtual-module", "", "Command + sent_count++",
                [
                    _set("_module", "msg", "$env('MODULE')", "jsonata"),
                    _set("_run", "msg", "$globalContext('sim.run')", "jsonata"),
                    _set("_job", "msg", "$number($lookup(_run.sent,_module))+1", "jsonata"),
                    _set("busy", "flow", "true", "bool"),
                    _set("last_command", "flow", "topic", "msg"),
                    _set("sim.run.sent", "global", "$merge([$globalContext('sim.run').sent,{(_module):_job}])", "jsonata"),
                    _set("sim.run.command_topics", "global", "$merge([$globalContext('sim.run').command_topics,{(_module):topic}])", "jsonata"),
                    _set("_seed", "msg", "_run.config.seed", "msg"),
                    _set("_base_runtime_ms", "msg", "$lookup(_run.config.base_runtime_ms,_module)", "jsonata"),
                ],
                800, 120, [["fn-module-runtime"]], info="Busy=true | Topic merken | sent_count++",
            ),
            _function(
                "fn-module-runtime", "subflow-virtual-module", "Laufzeit berechnen",
                RUNTIME_FUNCTION, 990, 120, [["sub-module-start-status"]], FUNCTION_INFO["runtime"],
            ),
            _change(
                "sub-module-start-status", "subflow-virtual-module", "", "Laufzeit + Startstatus",
                [
                    _set("runtime_ms", "flow", "_runtime_ms", "msg"),
                    _set("sim.run.module_runtime_ms", "global", "$merge([$globalContext('sim.run').module_runtime_ms,{(_module):_runtime_ms}])", "jsonata"),
            ] + _object_rules("payload", "msg", [
                ("event", "start", "str"),
                ("module", "_module", "msg"),
                ("topic", "topic", "msg"),
                ("runtime_ms", "_runtime_ms", "msg"),
                ("sent_count", "_job", "msg"),
                ("accepted_count", "$lookup($globalContext('sim.run').accepted,_module)", "jsonata"),
                ("run_id", "$globalContext('sim.run').run_id", "jsonata"),
            ]),
                1180, 120, [["sub-module-delay"]], info="msg.delay | kompakter Startstatus",
            ),
    ]


def _module_finish_nodes() -> list[dict]:
    """Delay abschliessen oder Duplikat melden."""
    return [
            {
                "id": "sub-module-delay", "type": "delay", "z": "subflow-virtual-module",
                "name": "Teilprozess simulieren", "pauseType": "delayv", "timeout": "5",
                "timeoutUnits": "seconds", "rate": "1", "nbRateUnits": "1",
                "rateUnits": "second", "randomFirst": "1", "randomLast": "5",
                "randomUnits": "seconds", "drop": False, "allowrate": False,
                "outputs": 1, "x": 1380, "y": 120, "wires": [["sub-module-complete-active"]],
                "info": "Core-Delay | `msg.delay` | Reset per `msg.reset`",
            },
            _switch(
                "sub-module-complete-active", "subflow-virtual-module", "", "Abschluss gueltig?",
                "$globalContext('sim.run').running = true and $not($globalContext('sim.run').fault) and $flowContext('busy') = true",
                [{"t": "true"}], 1580, 120, [["sub-module-complete"]], prop_type="jsonata",
                info="Lauf aktiv | kein Fault | Modul busy",
            ),
            _change(
                "sub-module-complete", "subflow-virtual-module", "", "accepted_count++ + frei",
                [
                    _set("_run", "msg", "$globalContext('sim.run')", "jsonata"),
                    _set("_accepted", "msg", "$number($lookup(_run.accepted,_module))+1", "jsonata"),
                    _set("sim.run.accepted", "global", "$merge([_run.accepted,{(_module):_accepted}])", "jsonata"),
                    _set("busy", "flow", "false", "bool"),
            ] + _object_rules("payload", "msg", [
                ("event", "complete", "str"),
                ("module", "_module", "msg"),
                ("topic", "$flowContext('last_command')", "jsonata"),
                ("runtime_ms", "$flowContext('runtime_ms')", "jsonata"),
                ("sent_count", "$lookup(_run.sent,_module)", "jsonata"),
                ("accepted_count", "_accepted", "msg"),
                ("run_id", "_run.run_id", "msg"),
            ]),
                1790, 120, [], info="accepted_count++ | Busy=false | Abschlussstatus",
            ),
            _change(
                "sub-module-duplicate", "subflow-virtual-module", "", "Duplikatfehler",
                [_set("payload", "msg", "{'code':'duplicate_command','detail':$env('MODULE') & ' busy','module':$env('MODULE'),'topic':topic,'ts_ms':$millis()}", "jsonata")],
                800, 200, [], info="Command bei Busy | Fault-Latch",
            ),
    ]


def _module_subflow_nodes() -> list[dict]:
    """Command, Delay und Jobcounter eines Moduls."""
    return (
        [_module_definition()]
        + _module_input_nodes()
        + _module_start_nodes()
        + _module_finish_nodes()
    )


def _window_subflow_nodes() -> list[dict]:
    """Rolling Window und MQTT-Request."""
    window = {
        "id": "subflow-lstm-window",
        "type": "subflow",
        "name": "LSTM-Fenster W=10",
        "info": """### Ablauf
- Domain setzen
- Window + Bootstrap fortschreiben
- Request-Metadaten setzen
- MQTT-Request bilden

Einzige Function: keyed Rolling Window.""",
        "category": "AI-CPS",
        "in": [{"x": 40, "y": 80, "wires": [{"id": "sub-window-domain"}]}],
        "out": [{"x": 980, "y": 80, "wires": [{"id": "sub-window-request", "port": 0}]}],
        "env": [{"name": "DOMAIN", "type": "str", "value": "vgr"}],
        "meta": {},
        "color": "#C0DEED",
    }
    nodes = [window]
    nodes.extend([
        _change(
            "sub-window-domain", "subflow-lstm-window", "", "Domain setzen",
            [_set("_domain", "msg", "$env('DOMAIN')", "jsonata")],
            190, 80, [["fn-lstm-window"]], info="VGR oder HBW aus Subflow-Parameter",
        ),
        _function(
            "fn-lstm-window", "subflow-lstm-window", "LSTM-Fenster fortschreiben",
            WINDOW_FUNCTION, 410, 80, [["sub-window-request"]], FUNCTION_INFO["window"],
        ),
        _change(
            "sub-window-request", "subflow-lstm-window", "", "NN-Request bilden",
            [
                _set("_pending", "msg", "$globalContext('ai.pending')", "jsonata"),
                _set("_request_id", "msg", "_pending.cycle_id & ':' & _domain", "jsonata"),
                _set("_started_ms", "msg", "$millis()", "jsonata"),
                _set("ai.pending", "global", "$merge([_pending,{'bootstrap':$merge([_pending.bootstrap,{(_domain):_bootstrap}]),(_domain & '_request_id'):_request_id,(_domain & '_started_ms'):_started_ms,'deadline_ms':_started_ms+10000}])", "jsonata"),
                _set("topic", "msg", "'ft/nn/' & _domain & '/request'", "jsonata"),
                _set("qos", "msg", "1", "num"),
                _set("retain", "msg", "false", "bool"),
                *_object_rules("payload", "msg", [
                    ("cycle_id", "_pending.cycle_id", "msg"),
                    ("request_id", "_request_id", "msg"),
                    ("parent_request_id", "_pending.parent_request_id", "msg"),
                    ("source_id", "_pending.source_id", "msg"),
                    ("model_id", "$lookup(_pending.contracts,_domain).model_id", "jsonata"),
                    ("model_profile", "_pending.model_profile", "msg"),
                    ("sequence", "_window", "msg"),
                ]),
                _set("_request_summary", "msg", "{'domain':_domain,'cycle_id':_pending.cycle_id,'model_profile':_pending.model_profile,'window':$string(_bootstrap.time_steps) & 'x' & $string($count($lookup(_pending.contracts,_domain).feature_cols))}", "jsonata"),
            ],
            720, 80, [], info="IDs | Modellprofil | Sequenz | Kurzinfo",
        ),
    ])
    return nodes


def _response_definition() -> dict:
    """Schnittstelle des Response-Pruefbausteins."""
    return {
        "id": "subflow-model-response",
        "type": "subflow",
        "name": "NN-Response pruefen",
        "info": """### Ablauf
- Domain setzen
- Duplikat verwerfen
- Korrelation / Modell / Klasse / Command pruefen
- Diagnoseantwort markieren

Keine Function-Node: Entscheidungen sind als Switches sichtbar.""",
        "category": "AI-CPS",
        "in": [{"x": 40, "y": 100, "wires": [{"id": "sub-response-context"}]}],
        "out": [
            {"x": 1100, "y": 70, "wires": [{"id": "sub-response-valid", "port": 0}]},
            {"x": 1100, "y": 150, "wires": [{"id": "sub-response-error", "port": 0}]},
        ],
        "env": [{"name": "DOMAIN", "type": "str", "value": "vgr"}],
        "meta": {},
        "color": "#C7E9C0",
    }


def _response_subflow_nodes() -> list[dict]:
    """Response pruefen und fuer Diagnose markieren."""
    nodes = [_response_definition()]
    nodes.extend([
        _change("sub-response-context", "subflow-model-response", "", "Domain + Pending lesen", [
            _set("_domain", "msg", "$env('DOMAIN')", "jsonata"),
            _set("_response", "msg", "payload", "msg"),
            _set("_pending", "msg", "$globalContext('ai.pending')", "jsonata"),
            _set("_seen", "msg", "$globalContext('ai.seen_responses') ? $globalContext('ai.seen_responses') : []", "jsonata"),
            _set("_expected_request", "msg", "$lookup(_pending,_domain & '_request_id')", "jsonata"),
            _set("_expected_contract", "msg", "$lookup(_pending.contracts,_domain)", "jsonata"),
            _set("_correlation_ok", "msg", "$exists(_pending) and _response.request_id=_expected_request and _response.cycle_id=_pending.cycle_id", "jsonata"),
            _set("_model_ok", "msg", "$not($exists(_response.error)) and _response.model_profile=_pending.model_profile and _response.model_id=_expected_contract.model_id", "jsonata"),
            _set("_class_ok", "msg", "$number(_response.cmd) in _expected_contract.class_ids", "jsonata"),
            _set("_command_ok", "msg", "$lowercase($env('COMMAND_OUTPUT_ENABLED'))!='true' or _response.command_output.published=true", "jsonata"),
            _set("_response_valid", "msg", "_correlation_ok and _model_ok and _class_ok and _command_ok", "jsonata"),
        ], 240, 100, [["sub-response-duplicate"]], info="Domain | Response | offener Zyklus"),
        _switch("sub-response-duplicate", "subflow-model-response", "", "Schon verarbeitet?",
                "_response.request_id in _seen", [{"t": "false"}], 470, 100,
                [["sub-response-contract"]], prop_type="jsonata", info="Duplikate still verwerfen"),
        _switch("sub-response-contract", "subflow-model-response", "", "Response gueltig?",
                "_response_valid", [{"t": "true"}, {"t": "false"}], 660, 100,
                [["sub-response-valid"], ["sub-response-error"]], prop_type="jsonata",
                info="Korrelation | Modellprofil | Klasse | direkter Command"),
        _change("sub-response-valid", "subflow-model-response", "", "Response registrieren", [
            _set("_latency", "msg", "$millis()-$number($lookup(_pending,_domain & '_started_ms'))", "jsonata"),
            _set("ai.seen_responses", "global", "$append(_seen,_response.request_id)", "jsonata"),
            _set("topic", "msg", "_domain", "msg"),
            _set("payload", "msg", "$merge([_response,{'_diagnostic_latency_ms':_latency}])", "jsonata"),
            _set("parts", "msg", "{'id':_pending.cycle_id,'type':'object','key':_domain,'count':2,'index':_domain='vgr'?0:1}", "jsonata"),
        ], 900, 70, [], info="Latenz an Response | Join-Metadaten | keine gemeinsame Command-Barriere"),
        _change("sub-response-error", "subflow-model-response", "", "Responsefehler", [
            _set("payload", "msg", "{'code':'model_response_error','detail':_domain & ' response invalid','cycle_id':_pending.cycle_id,'ts_ms':$millis()}", "jsonata")
        ], 900, 150, [], info="Ein normalisierter Fault-Payload"),
    ])
    return nodes


def build_subflows() -> list[dict]:
    """Alle wiederverwendbaren Bausteine."""
    return (
        _module_subflow_nodes()
        + _window_subflow_nodes()
        + _response_subflow_nodes()
    )
