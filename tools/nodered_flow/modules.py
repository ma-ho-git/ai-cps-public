"""Vier unabhaengige virtuelle Modulpfade."""

from .common import (
    MODULES,
    _change,
    _comment,
    _debug,
    _group,
    _link_in,
    _link_out,
    _mqtt_in,
    _mqtt_out,
    _set,
    _switch,
)


def _module_nodes(module: str, index: int) -> list[dict]:
    """Ein Modul: Eingang, Delay-Subflow und Ausgaenge."""
    tab = "tab-modules"
    y = 60 + index * 260
    group = f"group-module-{module}"
    instance = f"subflow-module-{module}"
    return [
                _group(group, tab, f"{module.upper()}: Command -> Delay -> Abschluss", 20, y, 1740, 230),
                _comment(f"comment-module-{module}", tab,
                         f"{module.upper()} | sent_count++ | 100 ms +/-50 % | accepted_count++", 350, y + 25),
                _link_in(f"link-module-{module}-init", tab, group, "Initialisierung", 70, y + 75,
                         [[f"change-module-{module}-init"]]),
                _change(f"change-module-{module}-init", tab, group, "Init / Reset markieren", [
                    _set("_event", "msg", "payload.action='start'?'init':'reset'", "jsonata")
                ], 240, y + 75, [[instance]], info="action=start -> init | action=reset -> reset"),
                _mqtt_in(f"in-module-{module}-command", tab, group, "Command empfangen",
                         f"ai/{module}/+", "2", 120, y + 145, [[f"change-module-{module}-command"]]),
                _change(f"change-module-{module}-command", tab, group, "Command markieren", [
                    _set("_event", "msg", "command", "str")
                ], 330, y + 145, [[instance]], info="Bestehendes Command-Topic | Payload leer"),
                {
                    "id": instance, "type": "subflow:subflow-virtual-module", "z": tab, "g": group,
                    "name": f"{module.upper()} simulieren", "env": [{"name": "MODULE", "value": module, "type": "str"}],
                    "x": 590, "y": y + 110,
                    "wires": [[f"change-module-{module}-status"], [f"link-fault-module-{module}"], [f"out-module-{module}-idle"]],
                },
                _change(f"change-module-{module}-status", tab, group, "Status kurz", [
                    _set("_factory_status", "msg", "{'state':payload.event='start'?'module_started':'module_completed','detail':payload.module,'ts_ms':$millis()}", "jsonata")
                ], 820, y + 90, [[f"debug-module-{module}", f"link-module-{module}-status"]]),
                _debug(f"debug-module-{module}", tab, group, f"{module.upper()} Start / Abschluss", 1060, y + 70),
                _link_out(f"link-module-{module}-status", tab, group, "Status bilden",
                          ["link-factory-status"], 1070, y + 115),
                _link_out(f"link-fault-module-{module}", tab, group, "Zum Fault-Latch",
                          ["link-fault-central"], 830, y + 145),
                _mqtt_out(f"out-module-{module}-idle", tab, group, "Initiales Idle",
                          "", "2", "false", 830, y + 195),
    ]


def _diagnostic_nodes() -> list[dict]:
    """Gemeinsame Flow- und MQTT-Fehlerpfade."""
    tab = "tab-modules"
    scope = [f"subflow-module-{module}" for module in MODULES]
    return [
            {"id": "catch-modules", "type": "catch", "z": tab, "name": "Modulfehler",
             "scope": scope, "uncaught": False, "x": 1400, "y": 45, "wires": [["change-catch-modules"]]},
            _change("change-catch-modules", tab, "", "Fehler normalisieren", [
                _set("payload", "msg", "{'code':'runtime_error','detail':error.message,'source':error.source.name}", "jsonata")
            ], 1580, 45, [["link-fault-modules"]]),
            _link_out("link-fault-modules", tab, "", "Zum Fault-Latch", ["link-fault-central"], 1740, 45),
            {"id": "status-mqtt-modules", "type": "status", "z": tab, "name": "MQTT-Zustand",
             "scope": [f"in-module-{module}-command" for module in MODULES]
                      + [f"out-module-{module}-idle" for module in MODULES],
             "x": 1400, "y": 90, "wires": [["switch-mqtt-modules"]]},
            _switch("switch-mqtt-modules", tab, "", "MQTT getrennt?", "status.text",
                    [{"t": "regex", "v": "disconnected|error", "vt": "str", "case": False}],
                    1570, 90, [["change-mqtt-modules"]]),
            _change("change-mqtt-modules", tab, "", "MQTT-Fehler", [
                _set("payload", "msg", "{'code':'mqtt_disconnected','detail':status.text,'source':'virtual_modules'}", "jsonata")
            ], 1730, 90, [["link-fault-modules"]]),
    ]


def build_module_nodes() -> list[dict]:
    """Vier sichtbare Instanzen des Modul-Subflows."""
    nodes = [
        _comment(
            "comment-modules",
            "tab-modules",
            "Vier unabhaengige Module | gleicher Subflow | eigene Counter",
            390,
            30,
        )
    ]
    for index, module in enumerate(MODULES):
        nodes.extend(_module_nodes(module, index))
    return nodes + _diagnostic_nodes()

