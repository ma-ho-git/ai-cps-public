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


def _object_rules(
    target: str,
    target_type: str,
    fields: list[tuple[str, str, str]],
) -> list[dict]:
    """Objekt leeren; Felder einzeln und sichtbar setzen."""
    rules = [_set(target, target_type, "{}", "json")]
    for field, value, value_type in fields:
        rules.append(
            _set(f"{target}.{field}", target_type, value, value_type)
        )
    return rules


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


