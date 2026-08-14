"""Low-code Node-RED flow builder for the virtual AI-CPS runtime.

The generated runtime deliberately keeps process decisions in visible Core
nodes. Only four small Function nodes remain for state transitions that would
otherwise turn into opaque JSONata programs.
"""

from __future__ import annotations

import json
from typing import Iterable


MODULES = ("vgr", "hbw", "mpo", "sld")
TRACE_NAMES = {
    "standard": "Normalbetrieb - Einlagerungen und Idle-Phasen (320 Zustaende)",
    "full-storage-attempt": "Vollspeicher - 20 wiederholte Einlagerungsversuche (157 Zustaende)",
    "full-storage-process-guard": "Vollspeicher - 9 vollstaendige Prozesssequenzen (308 Zustaende)",
}
TRACE_FILES = {
    "standard": "/data/ai-cps-runtime/data/live_plc_trace/payloads.jsonl",
    "full-storage-attempt": "/data/ai-cps-runtime/data/live_plc_full_storage_attempt/payloads.jsonl",
    "full-storage-process-guard": "/data/ai-cps-runtime/data/live_plc_full_storage_process_guard/payloads.jsonl",
}
MODEL_NAMES = {
    "deployment-current": "Aktueller Modellstand",
    "historical-full-storage-error": "Historischer Stand - reproduziert Vollspeicherfehler",
}

REPORT_COLUMNS = [
    "row_index", "request_id_base", "cycle_id", "phase", "trace_phase",
    "attempt_repeat_idx", "guard_episode_idx", "guard_prefix_idx",
    "guard_process_step_idx", "guard_source_episode_id", "source_id",
    "trace_profile", "trace_profile_name", "model_profile", "model_profile_name",
    "factory_seed", "factory_base_runtime_vgr_ms", "factory_base_runtime_hbw_ms",
    "factory_base_runtime_mpo_ms", "factory_base_runtime_sld_ms",
    "storage_model_id", "vgr_model_id", "hbw_model_id", "expected_empty_storage",
    "vgr_storage_pred", "hbw_storage_pred", "storage_match_vgr", "storage_match_hbw",
    "storage_confidence", "expected_label_VGR", "predicted_label_VGR", "vgr_match",
    "vgr_ready", "vgr_confidence", "vgr_latency_s", "expected_label_HBW",
    "predicted_label_HBW", "hbw_match", "hbw_ready", "hbw_confidence",
    "hbw_latency_s", "timeout", "error", "control_enabled", "control_published",
    "control_reason", "control_command_set_complete", "control_vgr_cmd",
    "control_hbw_cmd", "control_mpo_cmd", "control_sld_cmd", "control_vgr_topic",
    "control_hbw_topic", "control_mpo_topic", "control_sld_topic",
    "control_vgr_publisher", "control_hbw_publisher", "control_mpo_publisher",
    "control_sld_publisher", "control_qos", "control_retain", "bootstrap_vgr_rows",
    "bootstrap_hbw_rows", "module_runtime_vgr_ms", "module_runtime_hbw_ms",
    "module_runtime_mpo_ms", "module_runtime_sld_ms", "job_sent_vgr", "job_sent_hbw",
    "job_sent_mpo", "job_sent_sld", "job_accepted_vgr", "job_accepted_hbw",
    "job_accepted_mpo", "job_accepted_sld",
]


def _function(
    node_id: str,
    owner: str,
    name: str,
    code: str,
    x: int,
    y: int,
    wires: list[list[str]],
    info: str,
    *,
    group: str = "",
    outputs: int = 1,
) -> dict:
    return {
        "id": node_id,
        "type": "function",
        "z": owner,
        "g": group,
        "name": name,
        "func": code.strip() + "\n",
        "outputs": outputs,
        "timeout": 0,
        "noerr": 0,
        "initialize": "",
        "finalize": "",
        "libs": [],
        "x": x,
        "y": y,
        "wires": wires,
        "info": info,
    }


def _change(
    node_id: str,
    owner: str,
    group: str,
    name: str,
    rules: list[dict],
    x: int,
    y: int,
    wires: list[list[str]],
    info: str = "",
) -> dict:
    return {
        "id": node_id,
        "type": "change",
        "z": owner,
        "g": group,
        "name": name,
        "rules": rules,
        "action": "",
        "property": "",
        "from": "",
        "to": "",
        "reg": False,
        "x": x,
        "y": y,
        "wires": wires,
        "info": info,
    }


def _switch(
    node_id: str,
    owner: str,
    group: str,
    name: str,
    prop: str,
    rules: list[dict],
    x: int,
    y: int,
    wires: list[list[str]],
    *,
    prop_type: str = "msg",
    checkall: str = "true",
    info: str = "",
) -> dict:
    return {
        "id": node_id,
        "type": "switch",
        "z": owner,
        "g": group,
        "name": name,
        "property": prop,
        "propertyType": prop_type,
        "rules": rules,
        "checkall": checkall,
        "repair": False,
        "outputs": len(rules),
        "x": x,
        "y": y,
        "wires": wires,
        "info": info,
    }


def _json(node_id: str, owner: str, group: str, name: str, x: int, y: int,
          wires: list[list[str]], action: str = "") -> dict:
    return {
        "id": node_id,
        "type": "json",
        "z": owner,
        "g": group,
        "name": name,
        "property": "payload",
        "action": action,
        "pretty": False,
        "x": x,
        "y": y,
        "wires": wires,
    }


def _mqtt_in(node_id: str, owner: str, group: str, name: str, topic: str,
             qos: str, x: int, y: int, wires: list[list[str]]) -> dict:
    return {
        "id": node_id,
        "type": "mqtt in",
        "z": owner,
        "g": group,
        "name": name,
        "topic": topic,
        "qos": qos,
        "datatype": "auto-detect",
        "broker": "mqtt-ai-cps",
        "nl": False,
        "rap": True,
        "rh": 0,
        "inputs": 0,
        "x": x,
        "y": y,
        "wires": wires,
    }


def _mqtt_out(node_id: str, owner: str, group: str, name: str, topic: str,
              qos: str, retain: str, x: int, y: int) -> dict:
    return {
        "id": node_id,
        "type": "mqtt out",
        "z": owner,
        "g": group,
        "name": name,
        "topic": topic,
        "qos": qos,
        "retain": retain,
        "respTopic": "",
        "contentType": "",
        "userProps": "",
        "correl": "",
        "expiry": "",
        "broker": "mqtt-ai-cps",
        "x": x,
        "y": y,
        "wires": [],
    }


def _group(node_id: str, tab: str, name: str, x: int, y: int,
           width: int, height: int) -> dict:
    return {
        "id": node_id,
        "type": "group",
        "z": tab,
        "name": name,
        "style": {"label": True, "stroke": "#9e9e9e", "fill": "none"},
        "nodes": [],
        "x": x,
        "y": y,
        "w": width,
        "h": height,
    }


def _comment(node_id: str, tab: str, name: str, x: int, y: int,
             info: str = "") -> dict:
    return {
        "id": node_id,
        "type": "comment",
        "z": tab,
        "name": name,
        "info": info,
        "x": x,
        "y": y,
        "wires": [],
    }


def _link_in(node_id: str, owner: str, group: str, name: str, x: int, y: int,
             wires: list[list[str]]) -> dict:
    return {
        "id": node_id,
        "type": "link in",
        "z": owner,
        "g": group,
        "name": name,
        "links": [],
        "x": x,
        "y": y,
        "wires": wires,
    }


def _link_out(node_id: str, owner: str, group: str, name: str,
              links: list[str], x: int, y: int) -> dict:
    return {
        "id": node_id,
        "type": "link out",
        "z": owner,
        "g": group,
        "name": name,
        "mode": "link",
        "links": links,
        "x": x,
        "y": y,
        "wires": [],
    }


def _debug(node_id: str, owner: str, group: str, name: str, x: int, y: int,
           complete: str = "payload") -> dict:
    return {
        "id": node_id,
        "type": "debug",
        "z": owner,
        "g": group,
        "name": name,
        "active": True,
        "tosidebar": True,
        "console": False,
        "tostatus": False,
        "complete": complete,
        "targetType": "msg",
        "statusVal": "",
        "statusType": "auto",
        "x": x,
        "y": y,
        "wires": [],
    }


def _set(prop: str, prop_type: str, value: str, value_type: str) -> dict:
    return {"t": "set", "p": prop, "pt": prop_type, "to": value, "tot": value_type}


def _delete(prop: str, prop_type: str = "msg") -> dict:
    return {"t": "delete", "p": prop, "pt": prop_type}


FUNCTION_INFO = {
    "runtime": """### Aufgabe
Reproduzierbare Modulzeit berechnen.

### Eingang
Modul, Jobnummer, Seed und Basiszeit.

### Zustand
Kein eigener Zustand.

### Ausgang
`msg.delay` in Millisekunden.

### Warum Function-Node?
Die deterministische Hashrechnung besitzt keinen verstaendlichen Core-Baustein.""",
    "semaphore": """### Aufgabe
Counter atomar vergleichen und genau eine Tracezeile freigeben.

### Eingang
Aktueller virtueller Rohzustand.

### Zustand
Traceindex, Freigabecounter und Watchdog.

### Ausgang
Freigabe, Abschluss oder Fault.

### Warum Function-Node?
Counter und Traceindex muessen in einem Zustandswechsel aktualisiert werden.""",
    "contract": """### Aufgabe
Aktives Modellprofil und dynamischen Featurevertrag pruefen.

### Eingang
Freigegebener Anlagenzustand und retained Modellvertraege.

### Zustand
Nur gelesene Contract- und Dienstregistries.

### Ausgang
Ausgewaehlte Vertraege oder normalisierter Fehler.

### Warum Function-Node?
Dynamische Feature- und Klassenlisten erfordern eine gemeinsame Vertragspruefung.""",
    "window": """### Aufgabe
LSTM-Fenster je Quelle und Modell fortschreiben.

### Eingang
Domain, aktueller Zustand, One-hot-Wert und Modellvertrag.

### Zustand
Rolling Window je Quelle und Modell-ID.

### Ausgang
Vollstaendige Sequenz und Bootstrap-Metadaten.

### Warum Function-Node?
Keyed Window, Bootstrap und Abschneiden muessen gemeinsam erfolgen.""",
}


RUNTIME_FUNCTION = r"""
// Eingabe: Modul | Job | Seed | Basiszeit
const module = String(msg._module);
let hash = (Number(msg._seed) ^ (Number(msg._job) * 2654435761)) >>> 0;
// Hash: reproduzierbare Zahl 0..1
for (const char of module) {
  hash = (Math.imul(hash ^ char.charCodeAt(0), 1664525) + 1013904223) >>> 0;
}
// Faktor: 0,5..1,5
const factor = 0.5 + (hash / 0x100000000);
msg.delay = Math.max(1, Math.round(Number(msg._base_runtime_ms) * factor));
msg._runtime_ms = msg.delay;
return msg;
"""


WINDOW_FUNCTION = r"""
// Kontext: Domain | Quelle | Modell
const pending = global.get('ai.pending');
if (!pending) return null;
const domain = String(msg._domain);
const contract = pending.contracts[domain];
const steps = Number(contract.time_steps);
const key = `${pending.source_id}|${contract.model_id}`;
const windows = global.get('ai.windows') || {vgr:{},hbw:{}};
let rows = windows[domain]?.[key] || [];
// Seed: neun Idle-Zeilen bei neuer Quelle
const seed = {IX_VGR_RefSwitchVerticalAxis_I1:1,IX_VGR_RefSwitchHorizontalAxis_I2:1,IX_VGR_RefSwitchRotate_I3:1,QX_VGR_M2_HorizontalAxisBackward_Q3:0,QX_VGR_M2_HorizontalAxisForward_Q4:0,QX_VGR_Compressor_Q7:0,QX_VGR_ValveVacuum_Q8:0,VGR_vertical_position:0,VGR_horizontal_position:0,VGR_rotate_position:0,IX_HBW_RefSwitchHorizontalAxis_I1:1,IX_HBW_LightBarrierInside_I2:1,IX_HBW_LightBarrierOutside_I3:1,IX_HBW_RefSwitchVerticalAxis_I4:1,IX_HBW_SwitchCantileverFront_I5:0,IX_HBW_SwitchCantileverBack_I6:1,HBW_vertical_position:0,HBW_horizontal_position:0,IX_SSC_LightBarrierStorage_I3:1};
const vector = (state) => contract.feature_cols.map((feature) => feature.startsWith('empty_storage_') ? pending.one_hot[feature] : Number(state[feature]));
const seeded = rows.length === 0 ? steps - 1 : 0;
if (seeded) for (let index = 0; index < seeded; index += 1) rows.push(vector(seed));
// Fenster: Echtzustand anhaengen | auf W begrenzen
rows.push(vector(pending.raw_state));
rows = rows.slice(-steps);
windows[domain] = windows[domain] || {};
windows[domain][key] = rows;
global.set('ai.windows', windows);
msg._window = rows;
msg._bootstrap = {seeded_rows:seeded,time_steps:steps,template_version:'1.0'};
return msg;
"""


SEMAPHORE_FUNCTION = r"""
// Eingang: Rohzustand | zentraler Laufzustand
const run = global.get('sim.run');
if (!run?.running || run.fault || msg.payload?.simulation_run_id !== run.run_id) return null;
const modules = ['vgr','hbw','mpo','sld'];
const now = Date.now();
const balanced = modules.every((name) => Number(run.sent[name]) === Number(run.accepted[name]));
const fresh = modules.every((name) => Number(run.sent[name]) > Number(run.last_release_sent[name]));
// Blockiert: Watchdog pruefen
if (!balanced || !fresh) {
  if (now < Number(run.command_deadline_ms || 0)) return null;
  msg._semaphore = {action:'fault',run_id:run.run_id,sent:{...run.sent},accepted:{...run.accepted},ts_ms:now};
  return [null,null,msg];
}
// Trace fertig: nach letztem Command-Set abschliessen
if (run.trace_index >= run.trace.length) {
  run.running = false;
  run.completed = true;
  global.set('sim.run', run);
  msg._semaphore = {action:'completed',run_id:run.run_id,ts_ms:now};
  return [null,msg,null];
}
if (Number(msg.payload.trace_index) !== Number(run.trace_index)) return null;
// Freigabe: Counter merken | Index genau einmal erhoehen
const releaseIndex = run.trace_index;
run.last_release_sent = {...run.sent};
run.trace_index += 1;
run.releases += 1;
run.command_deadline_ms = now + 10000;
global.set('sim.run', run);
msg._semaphore = {action:'release',release_index:releaseIndex,run_id:run.run_id,ts_ms:now};
return [msg,null,null];
"""


CONTRACT_FUNCTION = r"""
// Profil: aktuellen oder historischen Vertrag waehlen
const raw = msg.payload || {};
const contracts = global.get('ai.contracts') || {};
const statuses = global.get('ai.statuses') || {};
const profile = String(raw.model_profile || 'deployment-current');
const selected = {storage:contracts.storage};
for (const domain of ['vgr','hbw']) {
  const service = contracts[domain];
  selected[domain] = service?.model_profiles ? service.model_profiles[profile] : (profile === 'deployment-current' ? service : null);
}
// Basis: Contract | Dienst | Feature- und Klassenlisten
let error = '';
for (const domain of ['storage','vgr','hbw']) {
  const contract = selected[domain];
  if (!contract || statuses[domain]?.state !== 'online') { error = `contract_or_service_missing:${domain}`; break; }
  if (!Array.isArray(contract.feature_cols) || !Array.isArray(contract.class_ids)) { error = `contract_invalid:${domain}`; break; }
}
// Commands: direkter MQTT-Vertrag unveraendert
const topics = {vgr:{0:'ai/vgr/cmd0',101:'ai/vgr/cmd101',102:'ai/vgr/cmd102',103:'ai/vgr/cmd103',104:'ai/vgr/cmd104',105:'ai/vgr/cmd105',301:'ai/vgr/cmd301'},hbw:{0:'ai/hbw/cmd000',102:'ai/hbw/cmd102',103:'ai/hbw/cmd103',104:'ai/hbw/cmd104',105:'ai/hbw/cmd105',107:'ai/hbw/cmd107',111:'ai/hbw/cmd111',116:'ai/hbw/cmd116',121:'ai/hbw/cmd121',126:'ai/hbw/cmd126',131:'ai/hbw/cmd131',136:'ai/hbw/cmd136',141:'ai/hbw/cmd141',146:'ai/hbw/cmd146',151:'ai/hbw/cmd151',156:'ai/hbw/cmd156',161:'ai/hbw/cmd161',166:'ai/hbw/cmd166',171:'ai/hbw/cmd171',176:'ai/hbw/cmd176',181:'ai/hbw/cmd181',186:'ai/hbw/cmd186',191:'ai/hbw/cmd191',196:'ai/hbw/cmd196',301:'ai/hbw/cmd301'}};
for (const domain of ['vgr','hbw']) if (!error) {
  const output = selected[domain].command_output;
  if (output?.mode !== 'direct_mqtt' || Number(output?.qos) !== 2 || output?.retain !== false) error = `contract_invalid:${domain}:command_output`;
  for (const classId of selected[domain].class_ids.map(Number)) if (!error && output?.topics?.[String(classId)] !== topics[domain][classId]) error = `contract_invalid:${domain}:class_${classId}`;
}
// Features: im aktuellen Rohzustand numerisch vorhanden
const required = new Set(selected.storage?.feature_cols || []);
for (const domain of ['vgr','hbw']) for (const feature of selected[domain]?.feature_cols || []) if (!feature.startsWith('empty_storage_')) required.add(feature);
for (const feature of required) if (!error && (!Object.hasOwn(raw, feature) || !Number.isFinite(Number(raw[feature])))) error = `invalid_payload:${feature}`;
if (error) {
  msg.payload = {code:error.split(':')[0],detail:error,cycle_id:null,ts_ms:Date.now()};
  return [null,msg];
}
msg._raw = raw;
msg._profile = profile;
msg._contracts = selected;
return [msg,null];
"""


def build_subflows() -> list[dict]:
    """Return the reusable low-code building blocks."""
    module = {
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
    nodes = [module]
    nodes.extend([
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
                _set("payload", "msg", "{'event':'start','module':_module,'topic':topic,'runtime_ms':_runtime_ms,'sent_count':_job,'accepted_count':$lookup($globalContext('sim.run').accepted,_module),'run_id':$globalContext('sim.run').run_id}", "jsonata"),
            ],
            1180, 120, [["sub-module-delay"]], info="msg.delay | kompakter Startstatus",
        ),
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
                _set("payload", "msg", "{'event':'complete','module':_module,'topic':$flowContext('last_command'),'runtime_ms':$flowContext('runtime_ms'),'sent_count':$lookup(_run.sent,_module),'accepted_count':_accepted,'run_id':_run.run_id}", "jsonata"),
            ],
            1790, 120, [], info="accepted_count++ | Busy=false | Abschlussstatus",
        ),
        _change(
            "sub-module-duplicate", "subflow-virtual-module", "", "Duplikatfehler",
            [_set("payload", "msg", "{'code':'duplicate_command','detail':$env('MODULE') & ' busy','module':$env('MODULE'),'topic':topic,'ts_ms':$millis()}", "jsonata")],
            800, 200, [], info="Command bei Busy | Fault-Latch",
        ),
    ])

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
    nodes.append(window)
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
                _set("payload", "msg", "{'cycle_id':_pending.cycle_id,'request_id':_request_id,'parent_request_id':_pending.parent_request_id,'source_id':_pending.source_id,'model_id':$lookup(_pending.contracts,_domain).model_id,'model_profile':_pending.model_profile,'sequence':_window}", "jsonata"),
                _set("_request_summary", "msg", "{'domain':_domain,'cycle_id':_pending.cycle_id,'model_profile':_pending.model_profile,'window':$string(_bootstrap.time_steps) & 'x' & $string($count($lookup(_pending.contracts,_domain).feature_cols))}", "jsonata"),
            ],
            720, 80, [], info="IDs | Modellprofil | Sequenz | Kurzinfo",
        ),
    ])

    response = {
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
    nodes.append(response)
    response_valid = (
        "$exists(_pending) and _response.request_id=$lookup(_pending,_domain & '_request_id') and "
        "_response.cycle_id=_pending.cycle_id and $not($exists(_response.error)) and "
        "_response.model_profile=_pending.model_profile and "
        "_response.model_id=$lookup(_pending.contracts,_domain).model_id and "
        "$number(_response.cmd) in $lookup(_pending.contracts,_domain).class_ids and "
        "($lowercase($env('COMMAND_OUTPUT_ENABLED'))!='true' or _response.command_output.published=true)"
    )
    nodes.extend([
        _change("sub-response-context", "subflow-model-response", "", "Domain + Pending lesen", [
            _set("_domain", "msg", "$env('DOMAIN')", "jsonata"),
            _set("_response", "msg", "payload", "msg"),
            _set("_pending", "msg", "$globalContext('ai.pending')", "jsonata"),
            _set("_seen", "msg", "$globalContext('ai.seen_responses') ? $globalContext('ai.seen_responses') : []", "jsonata"),
        ], 240, 100, [["sub-response-duplicate"]], info="Domain | Response | offener Zyklus"),
        _switch("sub-response-duplicate", "subflow-model-response", "", "Schon verarbeitet?",
                "_response.request_id in _seen", [{"t": "false"}], 470, 100,
                [["sub-response-contract"]], prop_type="jsonata", info="Duplikate still verwerfen"),
        _switch("sub-response-contract", "subflow-model-response", "", "Response gueltig?",
                response_valid, [{"t": "true"}, {"t": "false"}], 660, 100,
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


def _tabs() -> list[dict]:
    return [
        {"id": "tab-init", "type": "tab", "label": "00 Initialisierung", "disabled": False, "info": ""},
        {"id": "tab-state", "type": "tab", "label": "10 Zustandserfassung", "disabled": False, "info": ""},
        {"id": "tab-modules", "type": "tab", "label": "20 Virtuelle Module", "disabled": False, "info": ""},
        {"id": "tab-semaphore", "type": "tab", "label": "30 Semaphor", "disabled": False, "info": ""},
        {"id": "tab-pipeline", "type": "tab", "label": "40 NN-Pipeline", "disabled": False, "info": ""},
    ]


def build_init_nodes() -> list[dict]:
    tab = "tab-init"
    start_config = (
        "{'trace_profile':$string(payload.config.trace_profile ? payload.config.trace_profile : 'standard'),"
        "'model_profile':$string(payload.config.model_profile ? payload.config.model_profile : 'deployment-current'),"
        "'seed':$number($exists(payload.config.seed) ? payload.config.seed : 42),"
        "'base_runtime_ms':{"
        "'vgr':$number($exists(payload.config.base_runtime_ms.vgr) ? payload.config.base_runtime_ms.vgr : 100),"
        "'hbw':$number($exists(payload.config.base_runtime_ms.hbw) ? payload.config.base_runtime_ms.hbw : 100),"
        "'mpo':$number($exists(payload.config.base_runtime_ms.mpo) ? payload.config.base_runtime_ms.mpo : 100),"
        "'sld':$number($exists(payload.config.base_runtime_ms.sld) ? payload.config.base_runtime_ms.sld : 100)}}"
    )
    valid_numbers = (
        "$type(_config.seed)='number' and $floor(_config.seed)=_config.seed and _config.seed>=0 and _config.seed<=4294967295 and "
        "$reduce(['vgr','hbw','mpo','sld'],function($ok,$name){$ok and $type($lookup(_config.base_runtime_ms,$name))='number' and "
        "$floor($lookup(_config.base_runtime_ms,$name))=$lookup(_config.base_runtime_ms,$name) and "
        "$lookup(_config.base_runtime_ms,$name)>=50 and $lookup(_config.base_runtime_ms,$name)<=60000},true)"
    )
    ready = (
        "$exists($globalContext('ai.contracts').storage) and $exists($globalContext('ai.contracts').vgr) and "
        "$exists($globalContext('ai.contracts').hbw) and $globalContext('ai.statuses').storage.state='online' and "
        "$globalContext('ai.statuses').vgr.state='online' and $globalContext('ai.statuses').hbw.state='online'"
    )
    profile_ready = (
        "_config.model_profile='deployment-current' or "
        "($exists($lookup($globalContext('ai.contracts').vgr.model_profiles,'historical-full-storage-error')) and "
        "$exists($lookup($globalContext('ai.contracts').hbw.model_profiles,'historical-full-storage-error')))"
    )
    run_expression = (
        "{'running':true,'completed':false,'fault':null,'run_counter':_run_counter,'run_id':_run_id,'trace':payload,'trace_index':0,"
        "'raw_samples':0,'releases':0,'sent':{'vgr':0,'hbw':0,'mpo':0,'sld':0},'accepted':{'vgr':0,'hbw':0,'mpo':0,'sld':0},"
        "'last_release_sent':{'vgr':0,'hbw':0,'mpo':0,'sld':0},'command_topics':{},'module_runtime_ms':{},"
        "'command_deadline_ms':$millis()+10000,'config':_config}"
    )
    nodes = [
        _group("group-init-control", tab, "Start und Trace", 20, 20, 1800, 390),
        _group("group-init-status", tab, "Status und Fault-Latch", 20, 430, 1800, 280),
        _comment("comment-init", tab, "Start | Parameter einzeln pruefen | Trace laden | vier Idle-Commands", 340, 45),
        _mqtt_in("in-init-control", tab, "group-init-control", "Start / Reset", "ft/sim/factory/control", "1", 120, 100, [["json-init-control"]]),
        _json("json-init-control", tab, "group-init-control", "Control JSON", 300, 100, [["switch-init-control"]], "obj"),
        _switch("switch-init-control", tab, "group-init-control", "Start oder Reset", "payload.cmd",
                [{"t":"eq","v":"start","vt":"str"},{"t":"eq","v":"reset","vt":"str"}],
                490, 100, [["change-start-defaults"],["change-reset-runtime"]], info="Start | Reset"),
        _change("change-start-defaults", tab, "group-init-control", "Defaults uebernehmen",
                [_set("_config", "msg", start_config, "jsonata")], 700, 80, [["switch-trace-profile"]],
                info="Fehlende Werte: Standardprofil | aktuelles Modell | Seed 42 | 100 ms"),
        _switch("switch-trace-profile", tab, "group-init-control", "Testszenario vorhanden?", "_config.trace_profile",
                [{"t":"eq","v":"standard","vt":"str"},{"t":"eq","v":"full-storage-attempt","vt":"str"},
                 {"t":"eq","v":"full-storage-process-guard","vt":"str"},{"t":"else"}],
                920, 80,
                [["change-trace-standard"],["change-trace-attempt"],["change-trace-process"],["change-config-rejected"]],
                info="Drei versionierte Testszenarien | sonst ablehnen"),
    ]
    for index, profile in enumerate(TRACE_NAMES):
        suffix = {"standard":"standard","full-storage-attempt":"attempt","full-storage-process-guard":"process"}[profile]
        nodes.append(_change(
            f"change-trace-{suffix}", tab, "group-init-control", f"Szenario: {profile}",
            [_set("filename", "msg", TRACE_FILES[profile], "str"),
             _set("_config.trace_profile_name", "msg", TRACE_NAMES[profile], "str")],
            1160, 45 + index * 40, [["switch-model-profile"]], info="Dateipfad | Anzeigename",
        ))
    nodes.extend([
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
        _switch("switch-start-numbers", tab, "group-init-control", "Seed + Laufzeiten gueltig?", valid_numbers,
                [{"t":"true"},{"t":"false"}], 1580, 180,
                [["switch-run-available"],["change-config-rejected"]], prop_type="jsonata",
                info="Seed: 0..2^32-1 | Laufzeiten: 50..60000 ms"),
        _switch("switch-run-available", tab, "group-init-control", "Neuer Lauf erlaubt?",
                "$not($exists($globalContext('sim.run'))) or "
                "($not($globalContext('sim.run').running) and $not($globalContext('sim.run').completed))",
                [{"t":"true"},{"t":"false"}], 1360, 230,
                [["switch-ai-ready"],["change-start-rejected"]], prop_type="jsonata",
                info="Kein laufender Lauf | nach Abschluss zuerst Reset"),
        _switch("switch-model-available", tab, "group-init-control", "Profil in Contracts?", profile_ready,
                [{"t":"true"},{"t":"false"}], 1150, 230,
                [["change-start-ready"],["change-config-rejected"]], prop_type="jsonata",
                info="Historisches Profil in VGR- und HBW-Contract"),
        _switch("switch-ai-ready", tab, "group-init-control", "Alle NN bereit?", ready,
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
                [_set("sim.run", "global", run_expression, "jsonata"),
                 _delete("sim.pending_start", "global"),
                 _set("payload", "msg", "{'action':'start','run_id':_run_id}", "jsonata")],
                1580, 290, [["link-init-vgr","link-init-hbw","link-init-mpo","link-init-sld","change-init-status","debug-init"]],
                info="Trace | Run-ID | Counter 0 | Semaphor blockiert"),
        _debug("debug-init", tab, "group-init-control", "Initialisierung abgeschlossen", 1720, 350),
        _change("change-init-status", tab, "group-init-control", "Init-Status",
                [_set("payload", "msg", "{'state':'bootstrap_commands_published','semaphore_state':'blocked'}", "jsonata")],
                1580, 350, [["link-factory-status-out-init"]]),
    ])
    for module, y in zip(MODULES, (210, 240, 270, 300)):
        nodes.append(_link_out(f"link-init-{module}", tab, "group-init-control", f"{module.upper()} initialisieren", [f"link-module-{module}-init"], 1710, y))
    nodes.extend([
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
        _link_in("link-fault-central", tab, "group-init-status", "Flowfehler", 80, 570, [["switch-fault-relevant"]]),
        _switch("switch-fault-relevant", tab, "group-init-status", "Fehler relevant?",
                "$not(payload.code='mqtt_disconnected' and $not($globalContext('sim.run').running))",
                [{"t":"true"}], 260, 570, [["switch-fault-first"]], prop_type="jsonata"),
        _switch("switch-fault-first", tab, "group-init-status", "Erster Fehler?",
                "$type($globalContext('sim.run').fault)='object'", [{"t":"false"},{"t":"true"}],
                440, 570, [["change-fault-first"],["change-fault-existing"]], prop_type="jsonata"),
        _change("change-fault-first", tab, "group-init-status", "Fault speichern",
                [_set("_fault", "msg", "{'reason':$string(payload.code ? payload.code : (payload.error ? payload.error : 'runtime_error')),'detail':$string(payload.detail ? payload.detail : ''),'module':payload.module,'cycle_id':payload.cycle_id,'ts_ms':$millis()}", "jsonata"),
                 _set("sim.run.fault", "global", "_fault", "msg"),
                 _set("sim.run.running", "global", "false", "bool")],
                640, 550, [["change-fault-payload"]]),
        _change("change-fault-existing", tab, "group-init-status", "Ersten Fault behalten",
                [_set("_fault", "msg", "$globalContext('sim.run').fault", "jsonata")],
                640, 600, [["change-fault-payload"]]),
        _change("change-fault-payload", tab, "group-init-status", "Faultstatus bilden",
                [_set("payload", "msg", "{'schema_version':'1.0','state':'fault_latched','detail':_fault.reason,'error':_fault.reason,'fault':_fault,'run_id':$globalContext('sim.run').run_id,'cycle_id':_fault.cycle_id,'command_output_enabled':true,'fault_latched':true,'ts_ms':$millis()}", "jsonata")],
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
    ])
    return nodes


def build_state_nodes() -> list[dict]:
    """Build the periodic raw-state publisher entirely from Core nodes."""
    tab = "tab-state"
    group = "group-state-publisher"
    active = (
        "$globalContext('sim.run').running = true and "
        "$not($globalContext('sim.run').fault) and "
        "$count($globalContext('sim.run').trace) > 0"
    )
    raw_state = (
        "$merge([_run.trace[$$._trace_index],{"
        "'simulation_run_id':_run.run_id,'correlation_id':_run.run_id,"
        "'trace_index':_trace_index,'trace_profile':_run.config.trace_profile,"
        "'trace_profile_name':_run.config.trace_profile_name,"
        "'model_profile':_run.config.model_profile,"
        "'model_profile_name':_run.config.model_profile_name,"
        "'factory_seed':_run.config.seed,'factory_base_runtime_ms':_run.config.base_runtime_ms,"
        "'module_runtime_ms':_run.module_runtime_ms,"
        "'module_job_counts':{'sent':_run.sent,'accepted':_run.accepted},"
        "'_final_wait':_run.trace_index >= $count(_run.trace)}])"
    )
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
        _switch("switch-raw-active", tab, group, "Simulation aktiv?", active,
                [{"t": "true"}], 350, 110, [["change-raw-context"]],
                prop_type="jsonata", info="Lauf aktiv | Trace geladen | kein Fault"),
        _change("change-raw-context", tab, group, "Lauf + Index lesen", [
            _set("_run", "msg", "$globalContext('sim.run')", "jsonata"),
            _set("_trace_index", "msg", "$min([$number(_run.trace_index),$count(_run.trace)-1])", "jsonata"),
            _set("sim.run.raw_samples", "global", "$number(_run.raw_samples)+1", "jsonata"),
        ], 560, 110, [["change-raw-payload"]], info="Run lesen | raw_samples++ | Traceindex nicht erhoehen"),
        _change("change-raw-payload", tab, group, "Rohzustand abbilden", [
            _set("payload", "msg", raw_state, "jsonata"),
            _set("topic", "msg", "ft/sim/factory/raw_state", "str"),
            _set("qos", "msg", "1", "num"),
            _set("retain", "msg", "false", "bool"),
        ], 790, 110, [["json-raw-state"]], info="Tracezeile + Laufmetadaten | kein Indexwechsel"),
        _json("json-raw-state", tab, group, "Rohzustand JSON", 1010, 110, [["out-raw-state"]]),
        _mqtt_out("out-raw-state", tab, group, "Virtueller Rohzustand",
                  "ft/sim/factory/raw_state", "1", "false", 1230, 110),
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


def build_module_nodes() -> list[dict]:
    """Instantiate one visible low-code module block per factory component."""
    tab = "tab-modules"
    nodes: list[dict] = [
        _comment("comment-modules", tab, "Vier unabhaengige Module | gleicher Subflow | eigene Counter", 390, 30)
    ]
    for index, module in enumerate(MODULES):
        y = 60 + index * 260
        group = f"group-module-{module}"
        instance = f"subflow-module-{module}"
        nodes.extend([
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
        ])
    scope = [f"subflow-module-{module}" for module in MODULES]
    nodes.extend([
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
    ])
    return nodes


def build_semaphore_nodes() -> list[dict]:
    """Build the atomic four-counter semaphore around one retained Function."""
    tab = "tab-semaphore"
    group = "group-semaphore"
    status_release = (
        "{'state':'live_state_published','run_id':_run.run_id,'trace_total':$count(_run.trace),"
        "'payloads_sent':_run.releases,'payload_index':_semaphore.release_index,'raw_samples':_run.raw_samples,"
        "'released_states':_run.releases,'semaphore_state':'open','sent_counts':_run.sent,"
        "'accepted_counts':_run.accepted,'module_runtime_ms':_run.module_runtime_ms,"
        "'command_topics':_run.command_topics,'trace_profile':_run.config.trace_profile,"
        "'trace_profile_name':_run.config.trace_profile_name,'model_profile':_run.config.model_profile,"
        "'model_profile_name':_run.config.model_profile_name,'seed':_run.config.seed,"
        "'base_runtime_ms':_run.config.base_runtime_ms,"
        "'progress_percent':$round((_run.releases/$count(_run.trace))*10000)/100,'ts_ms':$millis()}"
    )
    completed = (
        "{'state':'completed','run_id':_run.run_id,'trace_total':$count(_run.trace),"
        "'payloads_sent':_run.releases,'raw_samples':_run.raw_samples,'released_states':_run.releases,"
        "'semaphore_state':'open','sent_counts':_run.sent,'accepted_counts':_run.accepted,"
        "'trace_profile':_run.config.trace_profile,'trace_profile_name':_run.config.trace_profile_name,"
        "'model_profile':_run.config.model_profile,'model_profile_name':_run.config.model_profile_name,"
        "'seed':_run.config.seed,'base_runtime_ms':_run.config.base_runtime_ms,"
        "'progress_percent':100,'ts_ms':$millis()}"
    )
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
            _set("_factory_status", "msg", status_release, "jsonata"),
        ], 810, 90, [["change-live-topic", "change-semaphore-debug", "link-semaphore-status"]],
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
            _set("_factory_status", "msg", completed, "jsonata"),
        ], 820, 225, [["link-semaphore-completed-status"]]),
        _link_out("link-semaphore-completed-status", tab, group, "Status bilden",
                  ["link-factory-status"], 1070, 225),
        _change("change-semaphore-fault", tab, group, "Semaphorfehler", [
            _set("payload", "msg", "{'code':'semaphore_stalled','detail':'command set incomplete','run_id':_semaphore.run_id,'sent_counts':_semaphore.sent,'accepted_counts':_semaphore.accepted,'ts_ms':_semaphore.ts_ms}", "jsonata")
        ], 820, 290, [["link-fault-semaphore"]]),
        _link_out("link-fault-semaphore", tab, group, "Zum Fault-Latch", ["link-fault-central"], 1060, 290),
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


def build_pipeline_nodes() -> list[dict]:
    """Build the MQTT inference pipeline with Core nodes and two retained Functions."""
    tab = "tab-pipeline"
    ready_expr = (
        "$exists($globalContext('ai.contracts').storage) and $exists($globalContext('ai.contracts').vgr) and "
        "$exists($globalContext('ai.contracts').hbw) and $globalContext('ai.statuses').storage.state='online' and "
        "$globalContext('ai.statuses').vgr.state='online' and $globalContext('ai.statuses').hbw.state='online' and "
        "$globalContext('ai.statuses').storage.model_id=$globalContext('ai.contracts').storage.model_id and "
        "$globalContext('ai.statuses').vgr.model_id=$globalContext('ai.contracts').vgr.model_id and "
        "$globalContext('ai.statuses').hbw.model_id=$globalContext('ai.contracts').hbw.model_id"
    )
    expected_request = "'ft/nn/' & _domain & '/request'"
    expected_response = "'ft/nn/response/' & _domain"
    valid_contract = (
        "payload.schema_version='1.0' and payload.domain=_domain and $type(payload.feature_cols)='array' and "
        "$type(payload.class_ids)='array' and payload.request_topic=" + expected_request + " and "
        "payload.response_topic=" + expected_response
    )
    cycle_result = (
        "{'schema_version':'1.0','cycle_id':_pending.cycle_id,'request_id':_pending.parent_request_id,"
        "'source_id':_pending.source_id,'status':'completed','model_profile':_pending.model_profile,"
        "'model_profile_name':_pending.model_profile_name,"
        "'model_ids':{'storage':_storage.model_id,'vgr':_vgr.model_id,'hbw':_hbw.model_id},"
        "'model_contracts':_pending.contracts,'empty_storage':_pending.empty_storage,"
        "'vgr_cmd':$number(_vgr.cmd),'hbw_cmd':$number(_hbw.cmd),"
        "'model_predictions':{'storage':{'empty_storage':_storage.empty_storage,'top3':_storage.top3 ? _storage.top3 : []},"
        "'vgr':{'cmd':$number(_vgr.cmd),'name':_vgr.name,'top3':_vgr.top3 ? _vgr.top3 : []},"
        "'hbw':{'cmd':$number(_hbw.cmd),'name':_hbw.name,'top3':_hbw.top3 ? _hbw.top3 : []}},"
        "'commands':{'vgr':{'cmd':$number(_vgr.cmd),'topic':_vgr.command_output.topic,'publisher':'model_service','published':_vgr.command_output.published=true,'mid':_vgr.command_output.mid},"
        "'hbw':{'cmd':$number(_hbw.cmd),'topic':_hbw.command_output.topic,'publisher':'model_service','published':_hbw.command_output.published=true,'mid':_hbw.command_output.mid},"
        "'mpo':{'cmd':0,'topic':'ai/mpo/cmd0','publisher':'ai_flow','published':_enabled},"
        "'sld':{'cmd':0,'topic':'ai/sld/cmd0','publisher':'ai_flow','published':_enabled}},"
        "'command_output_enabled':_enabled,'command_set_complete':"
        "((_vgr.command_output.published=true)=_enabled and (_hbw.command_output.published=true)=_enabled),"
        "'bootstrap':_pending.bootstrap,'storage_latency_ms':_pending.storage_latency_ms,"
        "'vgr_latency_ms':_vgr._diagnostic_latency_ms,'hbw_latency_ms':_hbw._diagnostic_latency_ms,"
        "'duration_ms':_finished-_pending.storage_started_ms,'input_metadata':_pending.raw_state,"
        "'qos':2,'retain':false,'ts_ms':_finished}"
    )
    nodes: list[dict] = [
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
    for index, domain in enumerate(("storage", "vgr", "hbw")):
        nodes.append(_change(
            f"change-contract-{domain}", tab, "group-contracts", f"{domain.upper()} markieren",
            [_set("_domain", "msg", domain, "str")], 690, 60 + index * 40,
            [["switch-contract-shape"]], info="Domain explizit setzen",
        ))
    nodes.extend([
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
    ])
    for index, domain in enumerate(("storage", "vgr", "hbw")):
        nodes.append(_change(
            f"change-status-{domain}", tab, "group-contracts", f"{domain.upper()} Status",
            [_set("_domain", "msg", domain, "str")], 690, 160 + index * 35,
            [["switch-status-offline"]], info="Domain explizit setzen",
        ))
    nodes.extend([
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
            _set("_ready", "msg", ready_expr, "jsonata"),
            _set("payload", "msg", "{'schema_version':'1.0','state':_ready?'ready':'waiting_for_models','detail':_ready?'contracts_and_status_ready':'contracts_or_status_missing','command_output_enabled':$lowercase($env('COMMAND_OUTPUT_ENABLED'))='true','fault_latched':$type($globalContext('sim.run').fault)='object','model_ids':{'storage':$globalContext('ai.contracts').storage.model_id,'vgr':$globalContext('ai.contracts').vgr.model_id,'hbw':$globalContext('ai.contracts').hbw.model_id},'ts_ms':$millis()}", "jsonata"),
        ], 1550, 185, [["json-ai-ready"]], info="Drei Contracts + drei Online-Status gemeinsam anzeigen"),
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
            _set("ai.pending", "global", "{'cycle_id':_cycle_id,'parent_request_id':_parent_id,'source_id':_source_id,'raw_state':_raw,'model_profile':_profile,'model_profile_name':_raw.model_profile_name ? _raw.model_profile_name : _profile,'contracts':_contracts,'storage_request_id':_cycle_id & ':storage','storage_started_ms':_started,'deadline_ms':_started+10000,'responses':{},'bootstrap':{},'issued_commands':{}}", "jsonata"),
        ], 1030, 340, [["change-storage-request"]], info="Cycle-ID | Quelle | Profil | Deadline gemeinsam setzen"),
        _change("change-storage-request", tab, "group-storage", "Storage-Request bilden", [
            _set("_pending", "msg", "$globalContext('ai.pending')", "jsonata"),
            _set("topic", "msg", "_pending.contracts.storage.request_topic", "msg"),
            _set("qos", "msg", "1", "num"),
            _set("retain", "msg", "false", "bool"),
            _set("payload", "msg", "{'cycle_id':_pending.cycle_id,'request_id':_pending.storage_request_id,'parent_request_id':_pending.parent_request_id,'source_id':_pending.source_id,'model_id':_pending.contracts.storage.model_id,'features':$merge($map(_pending.contracts.storage.feature_cols,function($feature){{($feature):$number($lookup(_pending.raw_state,$feature))}}))}", "jsonata"),
        ], 1260, 340, [["json-storage-request", "change-timeout-arm"]],
            info="Features in Contract-Reihenfolge | MQTT-Metadaten"),
        _json("json-storage-request", tab, "group-storage", "Storage JSON", 1490, 330,
              [["out-storage-request"]]),
        _mqtt_out("out-storage-request", tab, "group-storage", "Storage-Request",
                  "ft/nn/storage/request", "1", "false", 1700, 330),

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
    ])
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
    nodes.extend([
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
            _set("payload", "msg", cycle_result, "jsonata"),
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
    ])
    nodes.extend(build_reporting_nodes())
    nodes.extend([
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
    ])
    return nodes


def build_reporting_nodes() -> list[dict]:
    """Build stable JSONL/CSV/summary reporting from Core transformation nodes."""
    tab = "tab-pipeline"
    group = "group-responses"
    row = (
        "{'row_index':_row_index,'request_id_base':_result.request_id,'cycle_id':_result.cycle_id,"
        "'phase':_meta.phase ? _meta.phase : 'live_state','trace_phase':_meta.trace_phase,"
        "'attempt_repeat_idx':_meta.attempt_repeat_idx,'guard_episode_idx':_meta.guard_episode_idx,"
        "'guard_prefix_idx':_meta.guard_prefix_idx,'guard_process_step_idx':_meta.guard_process_step_idx,"
        "'guard_source_episode_id':_meta.guard_source_episode_id,'source_id':_result.source_id,"
        "'trace_profile':_meta.trace_profile,'trace_profile_name':_meta.trace_profile_name,"
        "'model_profile':_result.model_profile,'model_profile_name':_result.model_profile_name,"
        "'factory_seed':_meta.factory_seed,'factory_base_runtime_vgr_ms':_meta.factory_base_runtime_ms.vgr,"
        "'factory_base_runtime_hbw_ms':_meta.factory_base_runtime_ms.hbw,"
        "'factory_base_runtime_mpo_ms':_meta.factory_base_runtime_ms.mpo,"
        "'factory_base_runtime_sld_ms':_meta.factory_base_runtime_ms.sld,"
        "'storage_model_id':_result.model_ids.storage,'vgr_model_id':_result.model_ids.vgr,"
        "'hbw_model_id':_result.model_ids.hbw,'expected_empty_storage':_meta.expected_empty_storage,"
        "'vgr_storage_pred':_result.empty_storage,'hbw_storage_pred':_result.empty_storage,"
        "'storage_match_vgr':$exists(_meta.expected_empty_storage)?$number(_result.empty_storage)=$number(_meta.expected_empty_storage):'',"
        "'storage_match_hbw':$exists(_meta.expected_empty_storage)?$number(_result.empty_storage)=$number(_meta.expected_empty_storage):'',"
        "'storage_confidence':_result.model_predictions.storage.top3[0].p,"
        "'expected_label_VGR':_meta.expected_label_VGR,'predicted_label_VGR':_result.vgr_cmd,"
        "'vgr_match':$exists(_meta.expected_label_VGR)?$number(_result.vgr_cmd)=$number(_meta.expected_label_VGR):'',"
        "'vgr_ready':_result.status='completed','vgr_confidence':_result.model_predictions.vgr.top3[0].p,"
        "'vgr_latency_s':$number(_result.vgr_latency_ms)/1000,"
        "'expected_label_HBW':_meta.expected_label_HBW,'predicted_label_HBW':_result.hbw_cmd,"
        "'hbw_match':$exists(_meta.expected_label_HBW)?$number(_result.hbw_cmd)=$number(_meta.expected_label_HBW):'',"
        "'hbw_ready':_result.status='completed','hbw_confidence':_result.model_predictions.hbw.top3[0].p,"
        "'hbw_latency_s':$number(_result.hbw_latency_ms)/1000,'timeout':$contains($string(_result.error),'timeout'),"
        "'error':_result.error,'control_enabled':_result.command_output_enabled,"
        "'control_published':_result.command_output_enabled and _result.status='completed' and _result.command_set_complete,"
        "'control_reason':_result.status='completed'?(_result.command_output_enabled?'published_independently':'disabled'):_result.status,"
        "'control_command_set_complete':_result.command_set_complete,"
        "'control_vgr_cmd':_result.commands.vgr.cmd,'control_hbw_cmd':_result.commands.hbw.cmd,"
        "'control_mpo_cmd':_result.commands.mpo.cmd,'control_sld_cmd':_result.commands.sld.cmd,"
        "'control_vgr_topic':_result.commands.vgr.topic,'control_hbw_topic':_result.commands.hbw.topic,"
        "'control_mpo_topic':_result.commands.mpo.topic,'control_sld_topic':_result.commands.sld.topic,"
        "'control_vgr_publisher':_result.commands.vgr.publisher,'control_hbw_publisher':_result.commands.hbw.publisher,"
        "'control_mpo_publisher':_result.commands.mpo.publisher,'control_sld_publisher':_result.commands.sld.publisher,"
        "'control_qos':_result.qos,'control_retain':_result.retain,"
        "'bootstrap_vgr_rows':_result.bootstrap.vgr.seeded_rows,'bootstrap_hbw_rows':_result.bootstrap.hbw.seeded_rows,"
        "'module_runtime_vgr_ms':_meta.module_runtime_ms.vgr,'module_runtime_hbw_ms':_meta.module_runtime_ms.hbw,"
        "'module_runtime_mpo_ms':_meta.module_runtime_ms.mpo,'module_runtime_sld_ms':_meta.module_runtime_ms.sld,"
        "'job_sent_vgr':_meta.module_job_counts.sent.vgr,'job_sent_hbw':_meta.module_job_counts.sent.hbw,"
        "'job_sent_mpo':_meta.module_job_counts.sent.mpo,'job_sent_sld':_meta.module_job_counts.sent.sld,"
        "'job_accepted_vgr':_meta.module_job_counts.accepted.vgr,"
        "'job_accepted_hbw':_meta.module_job_counts.accepted.hbw,"
        "'job_accepted_mpo':_meta.module_job_counts.accepted.mpo,"
        "'job_accepted_sld':_meta.module_job_counts.accepted.sld}"
    )
    summary = (
        "{'mode':'live_mqtt_nodered','completed':_completed,'stopped':_stopped,"
        "'stop_reason':_stop_reason,'last_cycle_status':_report_state.last_cycle_status,"
        "'rows_completed':_report_state.rows,'control_published_rows':_report_state.command_rows,"
        "'control_published_commands':_report_state.command_rows*4,"
        "'control_idle_fallback_rows':_report_state.idle_fallback_rows,'faults':_report_state.faults,"
        "'storage_matches_vgr':_report_state.matches.storage,'storage_matches_hbw':_report_state.matches.storage,"
        "'vgr_matches':_report_state.matches.vgr,'hbw_matches':_report_state.matches.hbw,"
        "'model_ids':_report_state.model_ids,'run_config':_report_state.run_config,"
        "'started_at':_report_state.started_at,'updated_at':$fromMillis($millis()),"
        "'events_path':_report_state.run_dir & '/events.jsonl',"
        "'summary_path':_report_state.run_dir & '/summary.csv',"
        "'factory_status':_factory_status?{'run_id':_factory_status.run_id,'trace_total':_factory_status.trace_total,"
        "'payloads_sent':_factory_status.payloads_sent,'progress_percent':_factory_status.progress_percent,"
        "'sent_counts':_factory_status.sent_counts,'accepted_counts':_factory_status.accepted_counts}:undefined}"
    )
    state_update = (
        "$merge([_state,{'rows':_state.rows+1,"
        "'matches':{'storage':_state.matches.storage+(_row.storage_match_vgr=true?1:0),"
        "'vgr':_state.matches.vgr+(_row.vgr_match=true?1:0),'hbw':_state.matches.hbw+(_row.hbw_match=true?1:0)},"
        "'faults':_state.faults+(_result.status='fault_latched'?1:0),"
        "'command_rows':_state.command_rows+(_row.control_published=true?1:0),"
        "'factory_run_id':_state.factory_run_id?_state.factory_run_id:(_meta.simulation_run_id?_meta.simulation_run_id:_meta.correlation_id),"
        "'last_cycle_status':_result.status,'model_ids':_result.model_ids,"
        "'run_config':{'trace_profile':_row.trace_profile,'trace_profile_name':_row.trace_profile_name,"
        "'model_profile':_row.model_profile,'model_profile_name':_row.model_profile_name,'seed':_row.factory_seed,"
        "'base_runtime_ms':{'vgr':_row.factory_base_runtime_vgr_ms,'hbw':_row.factory_base_runtime_hbw_ms,"
        "'mpo':_row.factory_base_runtime_mpo_ms,'sld':_row.factory_base_runtime_sld_ms}}}])"
    )
    columns = ",".join(REPORT_COLUMNS)
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
            _set("report.state", "flow", r"{'run_id':_report_id,'run_dir':$replace($env('REPORT_ROOT'),/\/$/,'') & '/' & _report_id,'started_at':$fromMillis($millis()),'rows':0,'matches':{'storage':0,'vgr':0,'hbw':0},'faults':0,'command_rows':0,'idle_fallback_rows':0,'factory_run_id':null,'last_cycle_status':null,'model_ids':{},'run_config':{}}", "jsonata"),
        ], 1840, 985, [["change-report-state-read"]], info="Neuer Ordner je Lauf | Flow-Context"),
        _change("change-report-state-read", tab, group, "Reportzaehler lesen", [
            _set("_state", "msg", "$flowContext('report.state')", "jsonata"),
            _set("_row_index", "msg", "$flowContext('report.state').rows", "jsonata"),
        ], 1840, 930, [["change-report-row-map"]]),
        _change("change-report-row-map", tab, group, "Tabellenzeile bilden", [
            _set("_row", "msg", row, "jsonata"),
        ], 1840, 890, [["change-report-state-update"]]),
        _change("change-report-state-update", tab, group, "Reportzaehler aktualisieren", [
            _set("_report_state", "msg", state_update, "jsonata"),
            _set("report.state", "flow", "_report_state", "msg"),
        ], 1640, 890, [["change-report-event", "switch-report-first-row", "change-report-summary-running"]],
            info="Zeile | Matches | Commands | Modell-IDs"),
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
            _set("payload", "msg", summary, "jsonata"),
        ], 1620, 1220, [["json-report-summary"]], info="Running | Completed | Reset"),
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


def update_low_code_hmi(existing: list[dict]) -> list[dict]:
    """Keep the Dashboard widgets and replace all HMI Functions with Core nodes."""
    tab = "tab-virtual-hmi"
    keep = {
        tab, "group-hmi-inputs", "group-hmi-core", "group-hmi-widgets", "group-hmi-controls",
        "in-hmi-model-status", "in-hmi-ai-status", "in-hmi-factory-status", "in-hmi-cycle-result",
        "change-hmi-status", "change-hmi-trace", "change-hmi-progress", "change-hmi-mode",
        "change-hmi-semaphore", "change-hmi-raw-count", "change-hmi-release-count",
        "switch-hmi-notification", "change-hmi-notification",
        "ui-hmi-status", "ui-hmi-trace", "ui-hmi-progress", "ui-hmi-mode", "ui-hmi-source-meta",
        "ui-hmi-modules", "ui-hmi-predictions", "ui-hmi-models", "ui-hmi-cycles",
        "ui-hmi-errors", "ui-hmi-latencies", "ui-hmi-notification", "ui-hmi-table-layout-style",
        "ui-hmi-semaphore", "ui-hmi-raw-count", "ui-hmi-release-count",
        "ui-hmi-run-form", "change-hmi-start", "ui-hmi-reset-button", "change-hmi-reset-prompt",
        "ui-hmi-reset-confirm", "change-hmi-reset-factory", "change-hmi-reset-ai",
        "json-hmi-control", "out-hmi-control",
    }
    hmi = [
        dict(node) for node in existing
        if node.get("id") in keep
    ]
    by_id = {node["id"]: node for node in hmi}
    input_wires = {
        "in-hmi-model-status": [["json-hmi-model-status"]],
        "in-hmi-ai-status": [["json-hmi-ai-status"]],
        "in-hmi-factory-status": [["json-hmi-factory-status"]],
        "in-hmi-cycle-result": [["json-hmi-cycle-result"]],
    }
    for node_id, wires in input_wires.items():
        by_id[node_id]["wires"] = wires
    footer = by_id.get("ui-hmi-source-meta")
    if footer:
        footer["format"] = str(footer.get("format", "")).replace(
            "runtime-v1.3.0-rc.1", "runtime-v1.3.0-rc.2"
        )
    trace = by_id.get("ui-hmi-trace")
    if trace:
        trace["className"] = "hmi-run-summary"
    widget_group = by_id.get("group-hmi-widgets")
    if widget_group:
        widget_group.update({"x": 1084, "y": 39, "w": 900, "h": 720})
    widget_positions = {
        "ui-hmi-status": (1740, 120), "ui-hmi-trace": (1740, 160),
        "ui-hmi-progress": (1740, 200), "ui-hmi-mode": (1740, 240),
        "ui-hmi-semaphore": (1740, 280), "ui-hmi-raw-count": (1740, 320),
        "ui-hmi-release-count": (1740, 360), "ui-hmi-source-meta": (1740, 80),
        "ui-hmi-modules": (1660, 420), "ui-hmi-predictions": (1660, 460),
        "ui-hmi-models": (1660, 500), "ui-hmi-cycles": (1660, 540),
        "ui-hmi-errors": (1660, 580), "ui-hmi-latencies": (1660, 620),
        "ui-hmi-notification": (1740, 660), "ui-hmi-table-layout-style": (1740, 700),
    }
    for node_id, (x, y) in widget_positions.items():
        if node_id in by_id:
            by_id[node_id].update({"x": x, "y": y})
    mapper_positions = {
        "change-hmi-status": (1430, 120), "change-hmi-trace": (1430, 160),
        "change-hmi-progress": (1430, 200), "change-hmi-mode": (1430, 240),
        "change-hmi-semaphore": (1430, 280), "change-hmi-raw-count": (1430, 320),
        "change-hmi-release-count": (1430, 360),
        "switch-hmi-notification": (1490, 660), "change-hmi-notification": (1660, 660),
    }
    for node_id, (x, y) in mapper_positions.items():
        if node_id in by_id:
            by_id[node_id].update({"x": x, "y": y})

    overview = (
        "{'label':$flowContext('hmi.orchestration').state='fault_latched'?'Verriegelt':"
        "_factory.state='completed'?'Abgeschlossen':"
        "(_factory.state in ['bootstrap_commands_published','module_started','module_completed','live_state_published'])?"
        "'Simulation laeuft':$flowContext('hmi.orchestration').state='ready'?'Bereit':'Warte auf Systemstatus',"
        "'trace_profile_name':_factory.trace_profile_name?_factory.trace_profile_name:_factory.trace_profile,"
        "'model_profile_name':_factory.model_profile_name?_factory.model_profile_name:'Aktueller Modellstand',"
        "'trace_total':$number(_factory.trace_total?_factory.trace_total:0),"
        "'payloads_sent':$number(_factory.payloads_sent?_factory.payloads_sent:0),"
        "'progress_percent':$number(_factory.progress_percent?_factory.progress_percent:0),"
        "'command_mode':$flowContext('hmi.orchestration').command_output_enabled=true?'Commands aktiv':"
        "$flowContext('hmi.orchestration').command_output_enabled=false?'Diagnose (keine Commands)':'Noch nicht bekannt',"
        "'semaphore_state':_factory.semaphore_state?_factory.semaphore_state:'unbekannt',"
        "'raw_samples':$number(_factory.raw_samples?_factory.raw_samples:0),"
        "'released_states':$number(_factory.released_states?_factory.released_states:0)}"
    )
    modules = (
        "[{'module':'VGR','command':$replace($string(_factory.command_topics.vgr),/^.*cmd/,'')?_factory.command_topics.vgr:'-',"
        "'summary':($number(_factory.sent_counts.vgr)>$number(_factory.accepted_counts.vgr)?'Laeuft':'Bereit') & ' | ' & "
        "$string(_factory.accepted_counts.vgr?_factory.accepted_counts.vgr:0) & '/' & $string(_factory.sent_counts.vgr?_factory.sent_counts.vgr:0) & ' | ' & $string(_factory.module_runtime_ms.vgr?_factory.module_runtime_ms.vgr:'-')},"
        "{'module':'HBW','command':_factory.command_topics.hbw?_factory.command_topics.hbw:'-',"
        "'summary':($number(_factory.sent_counts.hbw)>$number(_factory.accepted_counts.hbw)?'Laeuft':'Bereit') & ' | ' & $string(_factory.accepted_counts.hbw?_factory.accepted_counts.hbw:0) & '/' & $string(_factory.sent_counts.hbw?_factory.sent_counts.hbw:0) & ' | ' & $string(_factory.module_runtime_ms.hbw?_factory.module_runtime_ms.hbw:'-')},"
        "{'module':'MPO','command':_factory.command_topics.mpo?_factory.command_topics.mpo:'-',"
        "'summary':($number(_factory.sent_counts.mpo)>$number(_factory.accepted_counts.mpo)?'Laeuft':'Bereit') & ' | ' & $string(_factory.accepted_counts.mpo?_factory.accepted_counts.mpo:0) & '/' & $string(_factory.sent_counts.mpo?_factory.sent_counts.mpo:0) & ' | ' & $string(_factory.module_runtime_ms.mpo?_factory.module_runtime_ms.mpo:'-')},"
        "{'module':'SLD','command':_factory.command_topics.sld?_factory.command_topics.sld:'-',"
        "'summary':($number(_factory.sent_counts.sld)>$number(_factory.accepted_counts.sld)?'Laeuft':'Bereit') & ' | ' & $string(_factory.accepted_counts.sld?_factory.accepted_counts.sld:0) & '/' & $string(_factory.sent_counts.sld?_factory.sent_counts.sld:0) & ' | ' & $string(_factory.module_runtime_ms.sld?_factory.module_runtime_ms.sld:'-')}]"
    )
    predictions = (
        "[{'model':'Storage','prediction':'Fach ' & $string($flowContext('hmi.predictions').storage.empty_storage?$flowContext('hmi.predictions').storage.empty_storage:'-'),"
        "'quality':$string($round($number($flowContext('hmi.predictions').storage.top3[0].p)*1000)/10) & ' | ' & $string($flowContext('hmi.last_latency').storage?$flowContext('hmi.last_latency').storage:'-')},"
        "{'model':'VGR','prediction':'cmd ' & $string($flowContext('hmi.predictions').vgr.cmd?$flowContext('hmi.predictions').vgr.cmd:'-'),"
        "'quality':$string($round($number($flowContext('hmi.predictions').vgr.top3[0].p)*1000)/10) & ' | ' & $string($flowContext('hmi.last_latency').vgr?$flowContext('hmi.last_latency').vgr:'-')},"
        "{'model':'HBW','prediction':'cmd ' & $string($flowContext('hmi.predictions').hbw.cmd?$flowContext('hmi.predictions').hbw.cmd:'-'),"
        "'quality':$string($round($number($flowContext('hmi.predictions').hbw.top3[0].p)*1000)/10) & ' | ' & $string($flowContext('hmi.last_latency').hbw?$flowContext('hmi.last_latency').hbw:'-')}]"
    )
    models = (
        "[{'model':'Storage','state':$flowContext('hmi.models').storage.state?$flowContext('hmi.models').storage.state:'unbekannt','model_id':$flowContext('hmi.model_ids').storage?$flowContext('hmi.model_ids').storage:'-'},"
        "{'model':'VGR','state':$flowContext('hmi.models').vgr.state?$flowContext('hmi.models').vgr.state:'unbekannt','model_id':$flowContext('hmi.model_ids').vgr?$flowContext('hmi.model_ids').vgr:'-'},"
        "{'model':'HBW','state':$flowContext('hmi.models').hbw.state?$flowContext('hmi.models').hbw.state:'unbekannt','model_id':$flowContext('hmi.model_ids').hbw?$flowContext('hmi.model_ids').hbw:'-'}]"
    )
    hmi.extend([
        _json("json-hmi-model-status", tab, "group-hmi-inputs", "Status JSON", 310, 100,
              [["switch-hmi-model-topic"]], "obj"),
        _switch("switch-hmi-model-topic", tab, "group-hmi-inputs", "Modelldomain", "topic", [
            {"t": "eq", "v": "ft/nn/storage/status", "vt": "str"},
            {"t": "eq", "v": "ft/nn/vgr/status", "vt": "str"},
            {"t": "eq", "v": "ft/nn/hbw/status", "vt": "str"},
        ], 500, 100, [["change-hmi-model-storage"], ["change-hmi-model-vgr"], ["change-hmi-model-hbw"]]),
    ])
    for domain, y in zip(("storage", "vgr", "hbw"), (70, 105, 140)):
        hmi.append(_change(
            f"change-hmi-model-{domain}", tab, "group-hmi-core", f"{domain.upper()} merken", [
                _set(f"hmi.models.{domain}", "flow", "payload", "msg"),
                _set(f"hmi.model_ids.{domain}", "flow", "payload.model_id", "msg"),
                _set("_hmi_domain", "msg", domain, "str"),
            ], 710, y, [["switch-hmi-model-offline"]], info="Nur Anzeigezustand",
        ))
    hmi.extend([
        _switch("switch-hmi-model-offline", tab, "group-hmi-core", "NN offline?", "payload.state",
                [{"t": "eq", "v": "offline", "vt": "str"}, {"t": "else"}], 920, 105,
                [["change-hmi-model-warning"], ["link-hmi-refresh-out"]]),
        _change("change-hmi-model-warning", tab, "group-hmi-core", "Offline-Warnung", [
            _set("_hmi_error", "msg", "{'timestamp':$fromMillis($millis()),'severity':'warning','code':'model_service_offline:' & _hmi_domain,'title':'NN-Dienst offline','detail':_hmi_domain & ' meldet offline','recommendation':'Container und MQTT pruefen; danach Reset','count':1}", "jsonata"),
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
            _set("_hmi_error", "msg", "{'timestamp':$fromMillis($millis()),'severity':'error','code':payload.error?payload.error:'fault_latched','title':'Prozess verriegelt','detail':payload.fault.detail?payload.fault.detail:payload.detail,'recommendation':'Ursache beheben; danach Reset','count':1}", "jsonata"),
            _set("hmi.errors", "flow", "$filter($append($flowContext('hmi.errors')?$flowContext('hmi.errors'):[],_hmi_error),function($value,$index,$array){$index >= $count($array)-20})", "jsonata"),
            _set("hmi.notification", "flow", "_hmi_error", "msg"),
        ], 950, 170, [["link-hmi-refresh-out"]]),
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
            _set("_cycle_row", "msg", "{'timestamp':$substring($fromMillis(payload.ts_ms?$number(payload.ts_ms):$millis()),11,8),'summary':payload.cycle_id & ': ' & payload.status & ' | Fach ' & $string(payload.empty_storage) & ' | VGR ' & $string(payload.vgr_cmd) & ' | HBW ' & $string(payload.hbw_cmd) & ' | ' & $string(payload.duration_ms) & ' ms'}", "jsonata"),
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
            _set("_factory", "msg", "$flowContext('hmi.factory')?$flowContext('hmi.factory'):{}", "jsonata"),
            _set("payload", "msg", overview, "jsonata"),
        ], 1280, 80, [["link-hmi-overview-out"]]),
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
        _change("change-hmi-modules-table", tab, "group-hmi-widgets", "Modultabelle", [
            _set("_factory", "msg", "$flowContext('hmi.factory')?$flowContext('hmi.factory'):{}", "jsonata"),
            _set("payload", "msg", modules, "jsonata"),
        ], 1320, 420, [["ui-hmi-modules"]]),
        _change("change-hmi-predictions-table", tab, "group-hmi-widgets", "Vorhersagetabelle", [
            _set("payload", "msg", predictions, "jsonata")
        ], 1320, 460, [["ui-hmi-predictions"]]),
        _change("change-hmi-models-table", tab, "group-hmi-widgets", "Modelltabelle", [
            _set("payload", "msg", models, "jsonata")
        ], 1320, 500, [["ui-hmi-models"]]),
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
         "scope": list(input_wires), "x": 310, "y": 330, "wires": [["switch-mqtt-hmi"]]},
        _switch("switch-mqtt-hmi", tab, "group-hmi-inputs", "MQTT getrennt?", "status.text",
                [{"t": "regex", "v": "disconnected|error", "vt": "str", "case": False}],
                520, 330, [["change-mqtt-hmi"]]),
        _change("change-mqtt-hmi", tab, "group-hmi-inputs", "MQTT-Fehler", [
            _set("payload", "msg", "{'code':'mqtt_disconnected','detail':status.text,'source':'Virtual HMI'}", "jsonata")
        ], 730, 330, [["link-fault-hmi"]]),
    ])
    return hmi


def build_low_code_flow(existing: list[dict]) -> list[dict]:
    """Return the complete RC.2 flow while retaining Dashboard/config nodes."""
    config_nodes = [
        dict(node) for node in existing
        if not node.get("z") and node.get("type") not in {"tab", "subflow"}
    ]
    return (
        _tabs()
        + build_subflows()
        + build_init_nodes()
        + build_state_nodes()
        + build_module_nodes()
        + build_semaphore_nodes()
        + build_pipeline_nodes()
        + update_low_code_hmi(existing)
        + config_nodes
    )
