#!/usr/bin/env python3
"""Build the self-contained, modular Node-RED virtual runtime flow."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLOW_PATH = (
    ROOT
    / "scenarios"
    / "serve_ft_nns_external_broker"
    / "x86_64"
    / "node_red"
    / "flows.json"
)
NODE_RED_DIR = FLOW_PATH.parent

MODULES = ("vgr", "hbw", "mpo", "sld")
TRACE_NAMES = {
    "standard": "Normalbetrieb - Einlagerungen und Idle-Phasen (320 Zustaende)",
    "full-storage-attempt": "Vollspeicher - 20 wiederholte Einlagerungsversuche (157 Zustaende)",
    "full-storage-process-guard": "Vollspeicher - 9 vollstaendige Prozesssequenzen (308 Zustaende)",
}
MODEL_NAMES = {
    "deployment-current": "Aktueller Modellstand",
    "historical-full-storage-error": "Historischer Stand - reproduziert Vollspeicherfehler",
}


def function_node(node_id: str, tab: str, group: str, name: str, code: str,
                  x: int, y: int, wires: list[list[str]], *, outputs: int = 1,
                  info: str) -> dict:
    return {
        "id": node_id,
        "type": "function",
        "z": tab,
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


def mqtt_in(node_id: str, tab: str, group: str, name: str, topic: str,
            qos: str, x: int, y: int, wires: list[list[str]]) -> dict:
    return {
        "id": node_id, "type": "mqtt in", "z": tab, "g": group,
        "name": name, "topic": topic, "qos": qos,
        "datatype": "auto-detect", "broker": "mqtt-ai-cps",
        "nl": False, "rap": True, "rh": 0, "inputs": 0,
        "x": x, "y": y, "wires": wires,
    }


def mqtt_out(node_id: str, tab: str, group: str, name: str,
             topic: str, qos: str, retain: str, x: int, y: int) -> dict:
    return {
        "id": node_id, "type": "mqtt out", "z": tab, "g": group,
        "name": name, "topic": topic, "qos": qos, "retain": retain,
        "respTopic": "", "contentType": "", "userProps": "",
        "correl": "", "expiry": "", "broker": "mqtt-ai-cps",
        "x": x, "y": y, "wires": [],
    }


def change_node(node_id: str, tab: str, group: str, name: str,
                rules: list[dict], x: int, y: int,
                wires: list[list[str]]) -> dict:
    return {
        "id": node_id, "type": "change", "z": tab, "g": group,
        "name": name, "rules": rules, "action": "", "property": "",
        "from": "", "to": "", "reg": False, "x": x, "y": y,
        "wires": wires,
    }


def switch_node(node_id: str, tab: str, group: str, name: str,
                prop: str, rules: list[dict], x: int, y: int,
                wires: list[list[str]], *, prop_type: str = "msg") -> dict:
    return {
        "id": node_id, "type": "switch", "z": tab, "g": group,
        "name": name, "property": prop, "propertyType": prop_type,
        "rules": rules, "checkall": "true", "repair": False,
        "outputs": len(rules), "x": x, "y": y, "wires": wires,
    }


def json_node(node_id: str, tab: str, group: str, name: str,
              x: int, y: int, wires: list[list[str]], action: str = "") -> dict:
    return {
        "id": node_id, "type": "json", "z": tab, "g": group,
        "name": name, "property": "payload", "action": action,
        "pretty": False, "x": x, "y": y, "wires": wires,
    }


def comment(node_id: str, tab: str, name: str, x: int, y: int) -> dict:
    return {
        "id": node_id, "type": "comment", "z": tab, "name": name,
        "info": "", "x": x, "y": y, "wires": [],
    }


def group(node_id: str, tab: str, name: str, x: int, y: int,
          width: int, height: int) -> dict:
    return {
        "id": node_id, "type": "group", "z": tab, "name": name,
        "style": {"label": True, "stroke": "#9e9e9e", "fill": "none"},
        "nodes": [], "x": x, "y": y, "w": width, "h": height,
    }


def link_in(node_id: str, tab: str, group_id: str, name: str,
            x: int, y: int, wires: list[list[str]]) -> dict:
    return {
        "id": node_id, "type": "link in", "z": tab, "g": group_id,
        "name": name, "links": [], "x": x, "y": y, "wires": wires,
    }


def link_out(node_id: str, tab: str, group_id: str, name: str,
             links: list[str], x: int, y: int) -> dict:
    return {
        "id": node_id, "type": "link out", "z": tab, "g": group_id,
        "name": name, "mode": "link", "links": links,
        "x": x, "y": y, "wires": [],
    }


def debug_node(node_id: str, tab: str, group_id: str, name: str,
               x: int, y: int, active: bool = True) -> dict:
    return {
        "id": node_id, "type": "debug", "z": tab, "g": group_id,
        "name": name, "active": active, "tosidebar": True,
        "console": False, "tostatus": False, "complete": "payload",
        "targetType": "msg", "statusVal": "", "statusType": "auto",
        "x": x, "y": y, "wires": [],
    }


def base_tabs() -> list[dict]:
    return [
        {"id": "tab-init", "type": "tab", "label": "00 Initialisierung", "disabled": False, "info": ""},
        {"id": "tab-state", "type": "tab", "label": "10 Zustandserfassung", "disabled": False, "info": ""},
        {"id": "tab-modules", "type": "tab", "label": "20 Virtuelle Module", "disabled": False, "info": ""},
        {"id": "tab-semaphore", "type": "tab", "label": "30 Semaphor", "disabled": False, "info": ""},
        {"id": "tab-pipeline", "type": "tab", "label": "40 NN-Pipeline", "disabled": False, "info": ""},
    ]


START_VALIDATE = r"""
// Startvertrag prüfen; Trace-Datei wählen
const payload = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : (msg.payload || {});
if (payload.cmd !== 'start') return null;
const contracts = global.get('ai.contracts') || {};
const statuses = global.get('ai.statuses') || {};
const ready = ['storage','vgr','hbw'].every((d) => contracts[d] && statuses[d]?.state === 'online');
const cfg = payload.config || {};
const traces = {
  'standard': {file:'/data/ai-cps-runtime/data/live_plc_trace/payloads.jsonl', name:'Normalbetrieb - Einlagerungen und Idle-Phasen (320 Zustaende)'},
  'full-storage-attempt': {file:'/data/ai-cps-runtime/data/live_plc_full_storage_attempt/payloads.jsonl', name:'Vollspeicher - 20 wiederholte Einlagerungsversuche (157 Zustaende)'},
  'full-storage-process-guard': {file:'/data/ai-cps-runtime/data/live_plc_full_storage_process_guard/payloads.jsonl', name:'Vollspeicher - 9 vollstaendige Prozesssequenzen (308 Zustaende)'}
};
const models = {
  'deployment-current':'Aktueller Modellstand',
  'historical-full-storage-error':'Historischer Stand - reproduziert Vollspeicherfehler'
};
const traceProfile = String(cfg.trace_profile || 'standard');
const modelProfile = String(cfg.model_profile || 'deployment-current');
const seed = Number(cfg.seed ?? 42);
const base = cfg.base_runtime_ms || {};
const baseRuntime = Object.fromEntries(['vgr','hbw','mpo','sld'].map((d) => [d, Number(base[d] ?? 100)]));
let error = '';
if (!traces[traceProfile]) error = `trace profile '${traceProfile}' is not available`;
else if (!models[modelProfile]) error = `model profile '${modelProfile}' is not available`;
else if (ready && ['vgr','hbw'].some((d) => modelProfile !== 'deployment-current' && !contracts[d]?.model_profiles?.[modelProfile])) error = `model profile '${modelProfile}' is not available in all NN contracts`;
else if (!Number.isSafeInteger(seed) || seed < 0 || seed > 0xffffffff) error = 'seed must be an integer between 0 and 4294967295';
else {
  for (const [domain,value] of Object.entries(baseRuntime)) {
    if (!Number.isSafeInteger(value) || value < 50 || value > 60000) {
      error = `base runtime for ${domain} must be between 50 and 60000 ms`;
      break;
    }
  }
}
if (error) {
  msg.payload = {state:'configuration_rejected', detail:error, ts_ms:Date.now()};
  return [null,msg];
}
const run = global.get('sim.run') || {};
if (run.running || run.completed) {
  msg.payload = {state:'start_rejected', detail:run.running ? 'factory_already_running' : 'reset_required_after_completion', ts_ms:Date.now()};
  return [null,msg];
}
const config = {trace_profile:traceProfile, trace_profile_name:traces[traceProfile].name,
  model_profile:modelProfile, model_profile_name:models[modelProfile], seed, base_runtime_ms:baseRuntime};
if (!ready) {
  global.set('sim.pending_start', {cmd:'start', config});
  msg.payload = {...config, state:'waiting_for_orchestration', detail:'NN contracts/status not ready', ts_ms:Date.now()};
  return [null,msg];
}
global.set('sim.pending_start', null);
msg.filename = traces[traceProfile].file;
msg._run_config = config;
return [msg,null];
"""


TRACE_INIT = r"""
// Trace übernehmen; flüchtigen Laufzustand anlegen
if (!Array.isArray(msg.payload) || msg.payload.length === 0) {
  node.error('trace_empty_or_invalid', msg);
  return null;
}
const config = msg._run_config || global.get('sim.pending_start')?.config;
if (!config) {
  node.error('missing_run_config', msg);
  return null;
}
const now = Date.now();
const previous = global.get('sim.run') || {};
const runCounter = Number(previous.run_counter || 0) + 1;
const counts = {vgr:0,hbw:0,mpo:0,sld:0};
const run = {
  running:true, completed:false, fault:null, run_counter:runCounter,
  run_id:`${now}-${runCounter}`, trace:msg.payload, trace_index:0,
  raw_samples:0, releases:0, sent:{...counts}, accepted:{...counts},
  last_release_sent:{...counts}, command_topics:{}, module_runtime_ms:{},
  module_busy:{vgr:false,hbw:false,mpo:false,sld:false},
  command_deadline_ms:now + 10000, config
};
global.set('sim.run', run);
global.set('sim.pending_start', null);
msg.payload = {action:'start', run_id:run.run_id};
return msg;
"""


RESET_RUNTIME = r"""
// Lauf, Fenster und offene Requests zurücksetzen
const run = global.get('sim.run') || {};
const previousRunId = run.run_id || null;
global.set('sim.run', {running:false, completed:false, fault:null, run_counter:Number(run.run_counter || 0)});
global.set('sim.pending_start', null);
global.set('ai.pending', null);
global.set('ai.windows', {vgr:{},hbw:{}});
msg.payload = {action:'reset', previous_run_id:previousRunId};
return msg;
"""


RAW_STATE = r"""
// Aktuellen Tracezustand abbilden; Index unverändert
const run = global.get('sim.run');
if (!run?.running || run.fault || !Array.isArray(run.trace) || run.trace.length === 0) return null;
const index = Math.min(run.trace_index, run.trace.length - 1);
const source = run.trace[index];
run.raw_samples += 1;
global.set('sim.run', run);
msg.topic = 'ft/sim/factory/raw_state';
msg.qos = 1;
msg.retain = false;
msg.payload = {
  ...source,
  simulation_run_id:run.run_id,
  correlation_id:run.run_id,
  trace_index:index,
  trace_profile:run.config.trace_profile,
  trace_profile_name:run.config.trace_profile_name,
  model_profile:run.config.model_profile,
  model_profile_name:run.config.model_profile_name,
  factory_seed:run.config.seed,
  factory_base_runtime_ms:{...run.config.base_runtime_ms},
  module_runtime_ms:{...run.module_runtime_ms},
  module_job_counts:{sent:{...run.sent},accepted:{...run.accepted}},
  _final_wait:run.trace_index >= run.trace.length
};
return msg;
"""


MODULE_GATE = r"""
// Command annehmen; sent_count++
const module = '__MODULE__';
const run = global.get('sim.run');
if (!run?.running || run.fault) return null;
if (flow.get(`${module}_busy`) === true) {
  msg.payload = {code:'duplicate_command', detail:`${module} busy`, module, topic:msg.topic, ts_ms:Date.now()};
  return [null,msg];
}
flow.set(`${module}_busy`, true);
flow.set(`${module}_last_command`, String(msg.topic));
run.sent[module] = Number(run.sent[module] || 0) + 1;
run.command_topics[module] = String(msg.topic);
global.set('sim.run', run);
msg._module = module;
msg._job = run.sent[module];
msg._factory_state = 'module_started';
return [msg,null];
"""


MODULE_RUNTIME = r"""
// Deterministische Laufzeit: Basis ±50 %
const run = global.get('sim.run');
const module = msg._module;
let hash = (Number(run.config.seed) ^ (msg._job * 2654435761)) >>> 0;
for (const c of module) hash = (Math.imul(hash ^ c.charCodeAt(0), 1664525) + 1013904223) >>> 0;
const factor = 0.5 + (hash / 0x100000000);
msg.delay = Math.max(1, Math.round(Number(run.config.base_runtime_ms[module]) * factor));
run.module_runtime_ms[module] = msg.delay;
flow.set(`${module}_runtime_ms`, msg.delay);
global.set('sim.run', run);
msg.payload = {event:'start', module, topic:msg.topic, runtime_ms:msg.delay, sent_count:run.sent[module], accepted_count:run.accepted[module], run_id:run.run_id};
return msg;
"""


MODULE_COMPLETE = r"""
// accepted_count++; Modul freigeben
const module = '__MODULE__';
const run = global.get('sim.run');
if (!run?.running || run.fault || flow.get(`${module}_busy`) !== true) return null;
run.accepted[module] = Number(run.accepted[module] || 0) + 1;
flow.set(`${module}_busy`, false);
global.set('sim.run', run);
msg._module = module;
msg._factory_state = 'module_completed';
msg.payload = {event:'complete', module, topic:flow.get(`${module}_last_command`)||run.command_topics[module], runtime_ms:flow.get(`${module}_runtime_ms`)||run.module_runtime_ms[module], sent_count:run.sent[module], accepted_count:run.accepted[module], run_id:run.run_id};
return msg;
"""


SEMAPHORE = r"""
// Counter atomar vergleichen; genau eine Tracezeile freigeben
const modules = ['vgr','hbw','mpo','sld'];
const run = global.get('sim.run');
if (!run?.running || run.fault) return null;
const raw = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : msg.payload;
if (raw.simulation_run_id !== run.run_id) return null;
const now = Date.now();
const equal = modules.every((d) => Number(run.sent[d]) === Number(run.accepted[d]));
const completeSet = modules.every((d) => Number(run.sent[d]) > Number(run.last_release_sent[d]));
if ((!equal || !completeSet) && now >= Number(run.command_deadline_ms || 0)) {
  msg.payload = {code:'semaphore_stalled', detail:'command set incomplete', run_id:run.run_id,
    sent_counts:{...run.sent}, accepted_counts:{...run.accepted}, ts_ms:now};
  return [null,null,msg];
}
if (!equal || !completeSet) return null;
if (run.trace_index >= run.trace.length) {
  run.running = false;
  run.completed = true;
  global.set('sim.run', run);
  msg.payload = {state:'completed', run_id:run.run_id, trace_total:run.trace.length,
    payloads_sent:run.releases, raw_samples:run.raw_samples, released_states:run.releases,
    semaphore_state:'open', sent_counts:{...run.sent}, accepted_counts:{...run.accepted},
    trace_profile:run.config.trace_profile, trace_profile_name:run.config.trace_profile_name,
    model_profile:run.config.model_profile, model_profile_name:run.config.model_profile_name,
    seed:run.config.seed, base_runtime_ms:{...run.config.base_runtime_ms}, progress_percent:100, ts_ms:now};
  return [null,msg,null];
}
if (Number(raw.trace_index) !== Number(run.trace_index)) return null;
const releaseIndex = run.trace_index;
run.last_release_sent = {...run.sent};
run.trace_index += 1;
run.releases += 1;
run.command_deadline_ms = now + 10000;
global.set('sim.run', run);
delete raw._final_wait;
raw.factory_cycle = run.releases;
raw.module_runtime_ms = {...run.module_runtime_ms};
raw.module_job_counts = {sent:{...run.sent},accepted:{...run.accepted}};
msg.topic = 'log/logging/state';
msg.qos = 1;
msg.retain = false;
msg.payload = raw;
msg._factory_status = {state:'live_state_published', run_id:run.run_id, trace_total:run.trace.length,
  payloads_sent:run.releases, payload_index:releaseIndex, raw_samples:run.raw_samples,
  released_states:run.releases, semaphore_state:'open', sent_counts:{...run.sent},
  accepted_counts:{...run.accepted}, module_runtime_ms:{...run.module_runtime_ms},
  command_topics:{...run.command_topics}, trace_profile:run.config.trace_profile,
  trace_profile_name:run.config.trace_profile_name, model_profile:run.config.model_profile,
  model_profile_name:run.config.model_profile_name, seed:run.config.seed,
  base_runtime_ms:{...run.config.base_runtime_ms},
  progress_percent:Math.round((run.releases/run.trace.length)*10000)/100, ts_ms:now};
return [msg,null,null];
"""


FACTORY_STATUS = r"""
// Fabrikstatus kompakt vereinheitlichen
const run = global.get('sim.run') || {};
const input = msg._factory_status || msg.payload || {};
msg.topic = 'ft/sim/factory/status';
msg.qos = 1;
msg.retain = true;
msg.payload = {
  state:input.state || msg._factory_state || 'running', detail:input.detail || '',
  run_id:input.run_id ?? run.run_id ?? null,
  trace_profile:input.trace_profile ?? run.config?.trace_profile ?? 'standard',
  trace_profile_name:input.trace_profile_name ?? run.config?.trace_profile_name ?? 'standard',
  model_profile:input.model_profile ?? run.config?.model_profile ?? 'deployment-current',
  model_profile_name:input.model_profile_name ?? run.config?.model_profile_name ?? 'Aktueller Modellstand',
  trace_total:input.trace_total ?? run.trace?.length ?? 0,
  payloads_sent:input.payloads_sent ?? run.releases ?? 0,
  raw_samples:input.raw_samples ?? run.raw_samples ?? 0,
  released_states:input.released_states ?? run.releases ?? 0,
  progress_percent:input.progress_percent ?? (run.trace?.length ? Math.round(((run.releases||0)/run.trace.length)*10000)/100 : 0),
  semaphore_state:input.semaphore_state ?? (run.fault ? 'fault' : 'blocked'),
  sent_counts:input.sent_counts ?? {...(run.sent||{})},
  accepted_counts:input.accepted_counts ?? {...(run.accepted||{})},
  module_runtime_ms:input.module_runtime_ms ?? {...(run.module_runtime_ms||{})},
  command_topics:input.command_topics ?? {...(run.command_topics||{})},
  seed:input.seed ?? run.config?.seed ?? 42,
  base_runtime_ms:input.base_runtime_ms ?? {...(run.config?.base_runtime_ms||{})},
  ts_ms:input.ts_ms || Date.now()
};
return msg;
"""


FAULT_LATCH = r"""
// Ersten Fehler verriegeln; Folgefehler nur melden
const input = msg.payload || {};
const run = global.get('sim.run') || {};
if (input.code === 'mqtt_disconnected' && !run.running) return null;
const fault = run.fault || {reason:String(input.code || input.error || 'runtime_error'), detail:String(input.detail || ''),
  module:input.module || null, cycle_id:input.cycle_id || null, ts_ms:Date.now()};
run.fault = fault;
run.running = false;
global.set('sim.run', run);
msg.payload = {schema_version:'1.0', state:'fault_latched', detail:fault.reason,
  error:fault.reason, fault, run_id:run.run_id || null, cycle_id:fault.cycle_id,
  command_output_enabled:true, fault_latched:true, ts_ms:Date.now()};
return msg;
"""


CONTRACT_REGISTER = r"""
// Retained Contract speichern; Topicvertrag prüfen
const match = /^ft\/nn\/(storage|vgr|hbw)\/contract$/.exec(String(msg.topic));
if (!match) return null;
const domain = match[1];
const value = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : msg.payload;
const expected = {storage:['ft/nn/storage/request','ft/nn/response/storage'],vgr:['ft/nn/vgr/request','ft/nn/response/vgr'],hbw:['ft/nn/hbw/request','ft/nn/response/hbw']}[domain];
if (!value || value.schema_version !== '1.0' || value.domain !== domain || !Array.isArray(value.feature_cols)
    || !Array.isArray(value.class_ids) || value.request_topic !== expected[0] || value.response_topic !== expected[1]) {
  node.error(`contract_invalid:${domain}`, msg);
  return null;
}
const contracts = global.get('ai.contracts') || {};
if (contracts[domain]?.model_id && contracts[domain].model_id !== value.model_id) {
  if (global.get('sim.run')?.running || global.get('ai.pending')) {
    node.error(`model_changed_during_cycle:${domain}`, msg);
    return null;
  }
  global.set('ai.windows', {vgr:{},hbw:{}});
}
contracts[domain] = value;
global.set('ai.contracts', contracts);
return msg;
"""


STATUS_REGISTER = r"""
// Retained Dienststatus speichern
const match = /^ft\/nn\/(storage|vgr|hbw)\/status$/.exec(String(msg.topic));
if (!match) return null;
const statuses = global.get('ai.statuses') || {};
const value = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : msg.payload;
if (value?.state !== 'online' && global.get('sim.run')?.running) {
  node.error(`model_offline:${match[1]}`, msg);
  return null;
}
statuses[match[1]] = value;
global.set('ai.statuses', statuses);
return msg;
"""


READINESS = r"""
// Drei Dienste gemeinsam bewerten
const contracts = global.get('ai.contracts') || {};
const statuses = global.get('ai.statuses') || {};
const domains = ['storage','vgr','hbw'];
const ready = domains.every((d) => contracts[d] && statuses[d]?.state === 'online' && statuses[d]?.model_id === contracts[d]?.model_id);
msg.topic = 'ft/ai/orchestration/status';
msg.qos = 1;
msg.retain = true;
msg.payload = {schema_version:'1.0', state:ready ? 'ready':'waiting_for_models',
  detail:ready ? 'contracts_and_status_ready':'contracts_or_status_missing',
  command_output_enabled:String(env.get('COMMAND_OUTPUT_ENABLED') || 'false').toLowerCase() === 'true',
  fault_latched:Boolean(global.get('sim.run')?.fault),
  model_ids:Object.fromEntries(domains.filter((d)=>contracts[d]).map((d)=>[d,contracts[d].model_id])), ts_ms:Date.now()};
return msg;
"""


AI_RESET = r"""
// Offene NN-Anfragen und LSTM-Fenster zuruecksetzen
const value = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : (msg.payload || {});
if (value.cmd !== 'reset') return null;
global.set('ai.pending', null);
global.set('ai.windows', {vgr:{},hbw:{}});
global.set('ai.seen_responses', []);
return msg;
"""


CONTRACT_GATE = r"""
// Virtueller Feature-/Profilvertrag vor Storage prüfen
const raw = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : msg.payload;
const contracts = global.get('ai.contracts') || {};
const statuses = global.get('ai.statuses') || {};
const profile = String(raw.model_profile || 'deployment-current');
const selected = {storage:contracts.storage};
for (const domain of ['vgr','hbw']) {
  const service = contracts[domain];
  selected[domain] = service?.model_profiles ? service.model_profiles[profile] : (profile === 'deployment-current' ? service : null);
}
let error = '';
for (const domain of ['storage','vgr','hbw']) {
  const c = selected[domain];
  if (!c || statuses[domain]?.state !== 'online') { error = `contract_or_service_missing:${domain}`; break; }
  if (!Array.isArray(c.feature_cols) || !Array.isArray(c.class_ids)) { error = `contract_invalid:${domain}`; break; }
}
if (!error) {
  const commandTopics = {
    vgr:{0:'ai/vgr/cmd0',101:'ai/vgr/cmd101',102:'ai/vgr/cmd102',103:'ai/vgr/cmd103',104:'ai/vgr/cmd104',105:'ai/vgr/cmd105',301:'ai/vgr/cmd301'},
    hbw:{0:'ai/hbw/cmd000',102:'ai/hbw/cmd102',103:'ai/hbw/cmd103',104:'ai/hbw/cmd104',105:'ai/hbw/cmd105',107:'ai/hbw/cmd107',111:'ai/hbw/cmd111',116:'ai/hbw/cmd116',121:'ai/hbw/cmd121',126:'ai/hbw/cmd126',131:'ai/hbw/cmd131',136:'ai/hbw/cmd136',141:'ai/hbw/cmd141',146:'ai/hbw/cmd146',151:'ai/hbw/cmd151',156:'ai/hbw/cmd156',161:'ai/hbw/cmd161',166:'ai/hbw/cmd166',171:'ai/hbw/cmd171',176:'ai/hbw/cmd176',181:'ai/hbw/cmd181',186:'ai/hbw/cmd186',191:'ai/hbw/cmd191',196:'ai/hbw/cmd196',301:'ai/hbw/cmd301'}
  };
  for (const domain of ['vgr','hbw']) {
    const output = selected[domain].command_output;
    if (output?.mode !== 'direct_mqtt' || Number(output?.qos) !== 2 || Boolean(output?.retain) !== false) { error=`contract_invalid:${domain}:command_output`; break; }
    for (const classId of selected[domain].class_ids.map(Number)) {
      if (output?.topics?.[String(classId)] !== commandTopics[domain][classId]) { error=`contract_invalid:${domain}:class_${classId}`; break; }
    }
    if (error) break;
  }
}
if (!error) {
  const required = new Set(selected.storage.feature_cols);
  for (const domain of ['vgr','hbw']) for (const f of selected[domain].feature_cols) if (!f.startsWith('empty_storage_')) required.add(f);
  for (const f of required) if (!Object.hasOwn(raw,f) || !Number.isFinite(Number(raw[f]))) { error = `invalid_payload:${f}`; break; }
}
if (error) {
  msg.payload = {code:error.split(':')[0], detail:error, cycle_id:null, ts_ms:Date.now()};
  return [null,msg];
}
msg._raw = raw;
msg._profile = profile;
msg._contracts = selected;
return [msg,null];
"""


STORAGE_REQUEST = r"""
// Storage-Request erzeugen; einen Zyklus öffnen
if (global.get('ai.pending')) {
  msg.payload = {code:'invalid_payload',detail:'new live state while cycle pending',ts_ms:Date.now()};
  return [null,msg];
}
const raw = msg._raw;
const contract = msg._contracts.storage;
const cycleNo = Number(global.get('ai.cycle_counter') || 0) + 1;
global.set('ai.cycle_counter', cycleNo);
const sourceId = String(raw.source_id || 'plc_live');
const parent = String(raw.request_id || `live-${Date.now()}-${cycleNo}`);
const correlation = String(raw.correlation_id || parent);
const cycleId = `cycle-${sourceId}-${correlation}-${String(cycleNo).padStart(6,'0')}`;
const pending = {cycle_id:cycleId,parent_request_id:parent,source_id:sourceId,raw_state:raw,
  model_profile:msg._profile,model_profile_name:String(raw.model_profile_name || msg._profile),
  contracts:msg._contracts,storage_request_id:`${cycleId}:storage`,storage_started_ms:Date.now(),
  deadline_ms:Date.now()+10000,responses:{},bootstrap:{},issued_commands:{}};
global.set('ai.pending', pending);
msg.topic = contract.request_topic;
msg.qos = 1;
msg.retain = false;
msg.payload = {cycle_id:cycleId,request_id:pending.storage_request_id,parent_request_id:parent,
  source_id:sourceId,model_id:contract.model_id,
  features:Object.fromEntries(contract.feature_cols.map((f)=>[f,Number(raw[f])]))};
return [msg,null];
"""


STORAGE_RESPONSE = r"""
// Storage-Antwort korrelieren; One-hot erzeugen
const response = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : msg.payload;
let seen = global.get('ai.seen_responses') || [];
if (seen.includes(response.request_id)) return null;
const pending = global.get('ai.pending');
if (!pending || response.request_id !== pending.storage_request_id || response.cycle_id !== pending.cycle_id || response.error) {
  msg.payload = {code:'model_response_error',detail:'storage correlation or inference error',cycle_id:pending?.cycle_id,ts_ms:Date.now()};
  return [null,msg];
}
const value = Number(response.empty_storage);
if (!pending.contracts.storage.class_ids.map(Number).includes(value)) {
  msg.payload = {code:'model_response_error',detail:`storage class ${value} unknown`,cycle_id:pending.cycle_id,ts_ms:Date.now()};
  return [null,msg];
}
pending.responses.storage = response;
seen.push(response.request_id); seen = seen.slice(-5000); global.set('ai.seen_responses', seen);
pending.empty_storage = value;
pending.storage_latency_ms = Date.now()-pending.storage_started_ms;
pending.one_hot = Object.fromEntries(Array.from({length:10},(_,i)=>[`empty_storage_${i}`,i===value?1:0]));
global.set('ai.pending', pending);
msg.payload = {cycle_id:pending.cycle_id,empty_storage:value,model_id:response.model_id,top3:response.top3||[]};
return [msg,null];
"""


WINDOW_REQUEST = r"""
// __DOMAIN__-Fenster W=10 aktualisieren
const domain = '__DOMAIN__';
const pending = global.get('ai.pending');
if (!pending) return null;
const contract = pending.contracts[domain];
const steps = Number(contract.time_steps);
const key = `${pending.source_id}|${contract.model_id}`;
const windows = global.get('ai.windows') || {vgr:{},hbw:{}};
let rows = windows[domain]?.[key] || [];
let seeded = 0;
const seed = {
  IX_VGR_RefSwitchVerticalAxis_I1:1,IX_VGR_RefSwitchHorizontalAxis_I2:1,IX_VGR_RefSwitchRotate_I3:1,
  QX_VGR_M2_HorizontalAxisBackward_Q3:0,QX_VGR_M2_HorizontalAxisForward_Q4:0,QX_VGR_Compressor_Q7:0,QX_VGR_ValveVacuum_Q8:0,
  VGR_vertical_position:0,VGR_horizontal_position:0,VGR_rotate_position:0,
  IX_HBW_RefSwitchHorizontalAxis_I1:1,IX_HBW_LightBarrierInside_I2:1,IX_HBW_LightBarrierOutside_I3:1,
  IX_HBW_RefSwitchVerticalAxis_I4:1,IX_HBW_SwitchCantileverFront_I5:0,IX_HBW_SwitchCantileverBack_I6:1,
  HBW_vertical_position:0,HBW_horizontal_position:0,IX_SSC_LightBarrierStorage_I3:1
};
const vector = (state) => contract.feature_cols.map((f) => f.startsWith('empty_storage_') ? pending.one_hot[f] : Number(state[f]));
if (rows.length === 0) {
  for (let i=0;i<steps-1;i+=1) rows.push(vector(seed));
  seeded = steps-1;
}
rows.push(vector(pending.raw_state));
rows = rows.slice(-steps);
windows[domain] = windows[domain] || {};
windows[domain][key] = rows;
global.set('ai.windows', windows);
pending.bootstrap[domain] = {seeded_rows:seeded,time_steps:steps,template_version:'1.0'};
pending[`${domain}_request_id`] = `${pending.cycle_id}:${domain}`;
pending[`${domain}_started_ms`] = Date.now();
pending.deadline_ms = Date.now()+10000;
global.set('ai.pending', pending);
msg.topic = domain === 'vgr' ? 'ft/nn/vgr/request':'ft/nn/hbw/request';
msg.qos = 1; msg.retain = false;
msg.payload = {cycle_id:pending.cycle_id,request_id:pending[`${domain}_request_id`],parent_request_id:pending.parent_request_id,
  source_id:pending.source_id,model_id:contract.model_id,model_profile:pending.model_profile,sequence:rows};
msg._request_summary = {domain,cycle_id:pending.cycle_id,model_profile:pending.model_profile,window:`${steps}x${contract.feature_cols.length}`};
return msg;
"""


MODEL_RESPONSE = r"""
// __DOMAIN__-Antwort validieren; nur Reporting freigeben
const domain = '__DOMAIN__';
const response = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : msg.payload;
let seen = global.get('ai.seen_responses') || [];
if (seen.includes(response.request_id)) return null;
const pending = global.get('ai.pending');
const contract = pending?.contracts?.[domain];
let error = '';
if (!pending || response.request_id !== pending?.[`${domain}_request_id`] || response.cycle_id !== pending?.cycle_id) error = `${domain} correlation mismatch`;
else if (response.error) error = `${domain} inference error: ${response.error}`;
else if (response.model_profile !== pending.model_profile || response.model_id !== contract.model_id) error = `${domain} model mismatch`;
else if (!contract.class_ids.map(Number).includes(Number(response.cmd))) error = `${domain} class unknown`;
else if (String(env.get('COMMAND_OUTPUT_ENABLED') || 'false').toLowerCase() === 'true' && response.command_output?.published !== true) error = `${domain} command not published`;
if (error) {
  msg.payload = {code:'model_response_error',detail:error,cycle_id:pending?.cycle_id,ts_ms:Date.now()};
  return [null,msg];
}
pending.responses[domain] = response;
seen.push(response.request_id); seen = seen.slice(-5000); global.set('ai.seen_responses', seen);
pending[`${domain}_latency_ms`] = Date.now()-pending[`${domain}_started_ms`];
pending.issued_commands[domain] = {cmd:Number(response.cmd),topic:response.command_output?.topic,
  publisher:'model_service',published:Boolean(response.command_output?.published),mid:response.command_output?.mid ?? null};
global.set('ai.pending', pending);
msg.topic = domain;
msg.payload = response;
msg.parts = {id:pending.cycle_id,type:'object',key:domain,count:2,index:domain==='vgr'?0:1};
return [msg,null];
"""


CYCLE_RESULT = r"""
// Zwei Diagnoseantworten zu einem Reportdatensatz verbinden
const pending = global.get('ai.pending');
if (!pending || !msg.payload?.vgr || !msg.payload?.hbw) return null;
const finished = Date.now();
const vgr = msg.payload.vgr, hbw = msg.payload.hbw, storage = pending.responses.storage;
const enabled = String(env.get('COMMAND_OUTPUT_ENABLED') || 'false').toLowerCase() === 'true';
const commands = {
  vgr:pending.issued_commands.vgr,hbw:pending.issued_commands.hbw,
  mpo:{cmd:0,topic:'ai/mpo/cmd0',publisher:'ai_flow',published:enabled},
  sld:{cmd:0,topic:'ai/sld/cmd0',publisher:'ai_flow',published:enabled}
};
msg.topic = 'ft/ai/orchestration/cycle_result'; msg.qos=1; msg.retain=false;
msg.payload = {schema_version:'1.0',cycle_id:pending.cycle_id,request_id:pending.parent_request_id,
  source_id:pending.source_id,status:'completed',model_profile:pending.model_profile,
  model_profile_name:pending.model_profile_name,model_ids:{storage:storage.model_id,vgr:vgr.model_id,hbw:hbw.model_id},
  model_contracts:pending.contracts,empty_storage:pending.empty_storage,vgr_cmd:Number(vgr.cmd),hbw_cmd:Number(hbw.cmd),
  model_predictions:{storage:{empty_storage:storage.empty_storage,top3:storage.top3||[]},
    vgr:{cmd:Number(vgr.cmd),name:vgr.name,top3:vgr.top3||[]},hbw:{cmd:Number(hbw.cmd),name:hbw.name,top3:hbw.top3||[]}},
  commands,command_output_enabled:enabled,command_set_complete:Object.values(commands).every((c)=>c.published===enabled),
  bootstrap:pending.bootstrap,storage_latency_ms:pending.storage_latency_ms,vgr_latency_ms:pending.vgr_latency_ms,
  hbw_latency_ms:pending.hbw_latency_ms,duration_ms:finished-pending.storage_started_ms,input_metadata:pending.raw_state,
  qos:2,retain:false,ts_ms:finished};
global.set('ai.pending', null);
return msg;
"""


TIMEOUT_CHECK = r"""
// Offenen Inferenzzyklus auf Timeout prüfen
const pending = global.get('ai.pending');
if (!pending || Date.now() < Number(pending.deadline_ms)) return null;
global.set('ai.pending', null);
msg.payload = {code:'inference_timeout',detail:'model response deadline exceeded',cycle_id:pending.cycle_id,ts_ms:Date.now()};
return msg;
"""


HMI_MODEL_STATUS = r"""
// Einen NN-Dienststatus in das rein lesende HMI-Modell uebernehmen
const value = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : (msg.payload || {});
const domain = /^ft\/nn\/(storage|vgr|hbw)\/status$/.exec(String(msg.topic))?.[1];
if (!domain) return null;
const state = flow.get('hmi.state') || {factory:{},orchestration:{},modelStatus:{},activeModelIds:{},predictions:{},cycles:[],errors:[],latencies:[]};
state.modelStatus[domain] = {...value};
if (value.state === 'offline') {
  const entry = {timestamp:new Date().toISOString(),severity:'warning',code:`model_service_offline:${domain}`,title:'NN-Dienst offline',detail:`${domain} meldet offline`,recommendation:'Container und MQTT pruefen; danach Reset',count:1};
  state.errors.push(entry); state.notification=entry;
}
state.errors=state.errors.slice(-20);
flow.set('hmi.state',state);
return msg;
"""

HMI_AI_STATUS = r"""
// Orchestrierungsstatus und einen moeglichen Fault in das HMI uebernehmen
const value = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : (msg.payload || {});
const state = flow.get('hmi.state') || {factory:{},orchestration:{},modelStatus:{},activeModelIds:{},predictions:{},cycles:[],errors:[],latencies:[]};
state.orchestration={...value};
if (value.state === 'fault_latched') {
  const code=value.error||value.fault?.reason||value.detail||'fault_latched';
  const entry={timestamp:new Date().toISOString(),severity:'error',code,title:'Prozess verriegelt',detail:value.fault?.detail||value.detail||'',recommendation:'Ursache beheben; danach Reset',count:1};
  const previous=state.errors.at(-1);
  if (previous?.code===entry.code && previous?.detail===entry.detail) previous.count=Number(previous.count||1)+1;
  else state.errors.push(entry);
  state.notification=entry;
}
state.errors=state.errors.slice(-20);
flow.set('hmi.state',state);
return msg;
"""

HMI_FACTORY_STATUS = r"""
// Fabrikstatus, Fortschritt und Startfehler in das HMI uebernehmen
const value = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : (msg.payload || {});
let state = flow.get('hmi.state') || {factory:{},orchestration:{},modelStatus:{},activeModelIds:{},predictions:{},cycles:[],errors:[],latencies:[]};
if (value.state === 'reset') state={factory:{...value},orchestration:state.orchestration,modelStatus:state.modelStatus,activeModelIds:{},predictions:{},cycles:[],errors:[],latencies:[]};
else state.factory={...state.factory,...value};
if (['configuration_rejected','start_rejected'].includes(value.state)) {
  const entry={timestamp:new Date().toISOString(),severity:'warning',code:value.state,title:'Start abgelehnt',detail:value.detail||'',recommendation:'Konfiguration pruefen',count:1};
  state.errors.push(entry); state.notification=entry;
}
state.errors=state.errors.slice(-20);
flow.set('hmi.state',state);
return msg;
"""

HMI_CYCLE_RESULT = r"""
// Vorhersagen, Modell-IDs und begrenzte Diagnosehistorie aktualisieren
const value = typeof msg.payload === 'string' ? JSON.parse(msg.payload) : (msg.payload || {});
const models=['storage','vgr','hbw'];
const state = flow.get('hmi.state') || {factory:{},orchestration:{},modelStatus:{},activeModelIds:{},predictions:{},cycles:[],errors:[],latencies:[]};
state.predictions={...state.predictions,...(value.model_predictions||{})};
state.activeModelIds={...state.activeModelIds,...(value.model_ids||{})};
state.cycles.push({timestamp:new Date(value.ts_ms||Date.now()).toISOString(),cycle_id:value.cycle_id||'-',source_id:value.source_id||'-',status:value.status||'unknown',empty_storage:value.empty_storage??'-',vgr_cmd:value.vgr_cmd??'-',hbw_cmd:value.hbw_cmd??'-',duration_ms:value.duration_ms??'-'});
for (const model of models) {
  const latency=Number(value[`${model}_latency_ms`]);
  if (Number.isFinite(latency)) state.latencies.push({x:value.ts_ms||Date.now(),y:latency,series:model==='storage'?'Storage':model.toUpperCase()});
}
if (value.status === 'fault_latched') {
  const entry={timestamp:new Date().toISOString(),severity:'error',code:value.error||'fault_latched',title:'Zyklusfehler',detail:value.detail||'',recommendation:'Diagnose pruefen; danach Reset',count:1};
  state.errors.push(entry); state.notification=entry;
}
state.cycles=state.cycles.slice(-30); state.errors=state.errors.slice(-20); state.latencies=state.latencies.slice(-90);
flow.set('hmi.state',state);
return msg;
"""

HMI_SNAPSHOT = r"""
// Gemeinsamen HMI-Zustand in acht begrenzte Widgetrollen abbilden
const modules=['vgr','hbw','mpo','sld'], models=['storage','vgr','hbw'];
const state=flow.get('hmi.state') || {factory:{},orchestration:{},modelStatus:{},activeModelIds:{},predictions:{},cycles:[],errors:[],latencies:[]};
const f=state.factory||{}, o=state.orchestration||{}, total=Number(f.trace_total||0), sent=Number(f.payloads_sent||0);
const running=['bootstrap_commands_published','module_started','module_completed','live_state_published'].includes(f.state);
const label=o.state==='fault_latched'?'Verriegelt':f.state==='completed'?'Abgeschlossen':running?'Simulation laeuft':o.state==='ready'?'Bereit':'Warte auf Systemstatus';
const overview={label,trace_profile_name:f.trace_profile_name||f.trace_profile||'-',model_profile_name:f.model_profile_name||f.model_profile||'Aktueller Modellstand',trace_total:total,payloads_sent:sent,progress_percent:total?Math.round((sent/total)*10000)/100:0,command_mode:o.command_output_enabled===true?'Commands aktiv':o.command_output_enabled===false?'Diagnose (keine Commands)':'Noch nicht bekannt',semaphore_state:f.semaphore_state||'unbekannt',raw_samples:Number(f.raw_samples||0),released_states:Number(f.released_states||0)};
const moduleRows=modules.map((d)=>{const sent=Number(f.sent_counts?.[d]||0), accepted=Number(f.accepted_counts?.[d]||0), runtime=f.module_runtime_ms?.[d]??'-'; return {module:d.toUpperCase(),command:(/\/cmd(\d+)$/.exec(String(f.command_topics?.[d]||''))?.[1]||'-'),summary:`${sent>accepted?'Laeuft':'Bereit'} | ${accepted}/${sent} | ${runtime}`};});
const predictionRows=models.map((d)=>{const p=state.predictions?.[d], series=d==='storage'?'Storage':d.toUpperCase(), confidence=Number.isFinite(Number(p?.top3?.[0]?.p))?Math.round(Number(p.top3[0].p)*1000)/10:'-', latency=state.latencies.filter((x)=>x.series===series).at(-1)?.y??'-'; return {model:series,prediction:d==='storage'?`Fach ${p?.empty_storage??'-'}`:`cmd ${p?.cmd??'-'}`,quality:`${confidence} | ${latency}`};});
const modelRows=models.map((d)=>({model:d==='storage'?'Storage':d.toUpperCase(),state:state.modelStatus?.[d]?.state||'unbekannt',model_id:state.activeModelIds?.[d]||state.modelStatus?.[d]?.model_id||o.model_ids?.[d]||'-'}));
const shortTime=(value)=>String(value||'').slice(11,19)||'-';
const cycleRows=(state.cycles||[]).map((item)=>({timestamp:shortTime(item.timestamp),summary:`${item.cycle_id}: ${item.status} | Fach ${item.empty_storage} | VGR ${item.vgr_cmd} | HBW ${item.hbw_cmd} | ${item.duration_ms} ms`}));
const errorRows=(state.errors||[]).map((item)=>({timestamp:shortTime(item.timestamp),summary:`${item.title}: ${item.detail||'-'} | x${item.count||1} | ${item.recommendation||'-'}`}));
const notification=state.notification||null; delete state.notification; flow.set('hmi.state',state);
msg.payload=[{role:'overview',payload:overview},{role:'modules',payload:moduleRows},{role:'predictions',payload:predictionRows},{role:'models',payload:modelRows},{role:'cycles',payload:cycleRows},{role:'errors',payload:errorRows},{role:'latencies',payload:state.latencies||[]},{role:'notification',payload:notification}];
return msg;
"""


REPORT_ROW = r"""
// Zyklusergebnis auf den stabilen CSV-Vertrag abbilden
const result=msg.payload||{}, meta=result.input_metadata||{}, commands=result.commands||{};
const match=(a,b)=>a===null||a===undefined||b===null||b===undefined?'':Number(a)===Number(b);
const probability=(prediction,key,value)=>{const found=(prediction?.top3||[]).find((item)=>Number(item?.[key])===Number(value)); return found?.p===undefined?'':Number(found.p);};
const report=flow.get('report.state')||{rows:0};
msg._report_result=result;
msg._report_row={
 row_index:Number(report.rows||0),request_id_base:result.request_id||'',cycle_id:result.cycle_id||'',phase:meta.phase||'live_state',trace_phase:meta.trace_phase||'',attempt_repeat_idx:meta.attempt_repeat_idx,
 guard_episode_idx:meta.guard_episode_idx,guard_prefix_idx:meta.guard_prefix_idx,guard_process_step_idx:meta.guard_process_step_idx,guard_source_episode_id:meta.guard_source_episode_id,source_id:result.source_id||'',
 trace_profile:meta.trace_profile||'',trace_profile_name:meta.trace_profile_name||'',model_profile:result.model_profile||meta.model_profile||'deployment-current',model_profile_name:result.model_profile_name||meta.model_profile_name||'',factory_seed:meta.factory_seed,
 factory_base_runtime_vgr_ms:meta.factory_base_runtime_ms?.vgr,factory_base_runtime_hbw_ms:meta.factory_base_runtime_ms?.hbw,factory_base_runtime_mpo_ms:meta.factory_base_runtime_ms?.mpo,factory_base_runtime_sld_ms:meta.factory_base_runtime_ms?.sld,
 storage_model_id:result.model_ids?.storage||'',vgr_model_id:result.model_ids?.vgr||'',hbw_model_id:result.model_ids?.hbw||'',expected_empty_storage:meta.expected_empty_storage,
 vgr_storage_pred:result.empty_storage,hbw_storage_pred:result.empty_storage,storage_match_vgr:match(result.empty_storage,meta.expected_empty_storage),storage_match_hbw:match(result.empty_storage,meta.expected_empty_storage),storage_confidence:probability(result.model_predictions?.storage,'empty_storage',result.empty_storage),
 expected_label_VGR:meta.expected_label_VGR,predicted_label_VGR:result.vgr_cmd,vgr_match:match(result.vgr_cmd,meta.expected_label_VGR),vgr_ready:result.status==='completed',vgr_confidence:probability(result.model_predictions?.vgr,'cmd',result.vgr_cmd),vgr_latency_s:result.vgr_latency_ms===undefined?'':Number(result.vgr_latency_ms)/1000,
 expected_label_HBW:meta.expected_label_HBW,predicted_label_HBW:result.hbw_cmd,hbw_match:match(result.hbw_cmd,meta.expected_label_HBW),hbw_ready:result.status==='completed',hbw_confidence:probability(result.model_predictions?.hbw,'cmd',result.hbw_cmd),hbw_latency_s:result.hbw_latency_ms===undefined?'':Number(result.hbw_latency_ms)/1000,
 timeout:String(result.error||'').includes('timeout'),error:result.error||'',control_enabled:Boolean(result.command_output_enabled),control_published:Boolean(result.command_output_enabled&&result.status==='completed'&&result.command_set_complete),control_reason:result.status==='completed'?(result.command_output_enabled?'published_independently':'disabled'):result.status,
 control_command_set_complete:Boolean(result.command_set_complete),control_vgr_cmd:commands.vgr?.cmd,control_hbw_cmd:commands.hbw?.cmd,control_mpo_cmd:commands.mpo?.cmd,control_sld_cmd:commands.sld?.cmd,
 control_vgr_topic:commands.vgr?.topic,control_hbw_topic:commands.hbw?.topic,control_mpo_topic:commands.mpo?.topic,control_sld_topic:commands.sld?.topic,control_vgr_publisher:commands.vgr?.publisher,control_hbw_publisher:commands.hbw?.publisher,control_mpo_publisher:commands.mpo?.publisher,control_sld_publisher:commands.sld?.publisher,
 control_qos:result.qos,control_retain:result.retain,bootstrap_vgr_rows:result.bootstrap?.vgr?.seeded_rows,bootstrap_hbw_rows:result.bootstrap?.hbw?.seeded_rows,
 module_runtime_vgr_ms:meta.module_runtime_ms?.vgr,module_runtime_hbw_ms:meta.module_runtime_ms?.hbw,module_runtime_mpo_ms:meta.module_runtime_ms?.mpo,module_runtime_sld_ms:meta.module_runtime_ms?.sld,
 job_sent_vgr:meta.module_job_counts?.sent?.vgr,job_sent_hbw:meta.module_job_counts?.sent?.hbw,job_sent_mpo:meta.module_job_counts?.sent?.mpo,job_sent_sld:meta.module_job_counts?.sent?.sld,
 job_accepted_vgr:meta.module_job_counts?.accepted?.vgr,job_accepted_hbw:meta.module_job_counts?.accepted?.hbw,job_accepted_mpo:meta.module_job_counts?.accepted?.mpo,job_accepted_sld:meta.module_job_counts?.accepted?.sld
};
return msg;
"""

REPORT_STATE = r"""
// Einen Zyklus zaehlen oder einen korrelierten Laufabschluss erkennen
let state=flow.get('report.state');
if (msg._report_event==='factory_status') {
  if (!state || !state.factory_run_id || String(msg.payload?.run_id||'')!==String(state.factory_run_id)) return null;
  if (!['completed','reset'].includes(msg.payload?.state)) return null;
  msg._report_state=state; msg._factory_status=msg.payload;
  flow.set('report.state',null);
  return [null,msg];
}
const now=Date.now(), result=msg._report_result||{}, row=msg._report_row||{};
if (!state) {
  const runId=new Date(now).toISOString().replace(/[-:TZ.]/g,'').slice(0,18)+'_nodered';
  const root=String(env.get('REPORT_ROOT')||'/reports/orchestration_simulation').replace(/\/$/,'');
  state={run_id:runId,run_dir:`${root}/${runId}`,started_at:new Date(now).toISOString(),rows:0,matches:{storage:0,vgr:0,hbw:0},faults:0,command_rows:0,idle_fallback_rows:0,factory_run_id:null,last_cycle_status:null,model_ids:{},run_config:{}};
}
state.rows+=1;
if (row.storage_match_vgr===true) state.matches.storage+=1;
if (row.vgr_match===true) state.matches.vgr+=1;
if (row.hbw_match===true) state.matches.hbw+=1;
if (result.status==='fault_latched') state.faults+=1;
if (row.control_published) state.command_rows+=1;
if (result.idle_set_published) state.idle_fallback_rows+=1;
state.factory_run_id=state.factory_run_id||result.input_metadata?.simulation_run_id||result.input_metadata?.correlation_id||null;
state.last_cycle_status=result.status||null; state.model_ids=result.model_ids||state.model_ids;
state.run_config={trace_profile:row.trace_profile,trace_profile_name:row.trace_profile_name,model_profile:row.model_profile,model_profile_name:row.model_profile_name,seed:row.factory_seed,base_runtime_ms:{vgr:row.factory_base_runtime_vgr_ms,hbw:row.factory_base_runtime_hbw_ms,mpo:row.factory_base_runtime_mpo_ms,sld:row.factory_base_runtime_sld_ms}};
flow.set('report.state',state); msg._report_state=state;
return [msg,null];
"""

REPORT_CSV = r"""
// Genau eine CSV-Zeile mit stabilem Spaltenvertrag bilden
const columns=['row_index','request_id_base','cycle_id','phase','trace_phase','attempt_repeat_idx','guard_episode_idx','guard_prefix_idx','guard_process_step_idx','guard_source_episode_id','source_id','trace_profile','trace_profile_name','model_profile','model_profile_name','factory_seed','factory_base_runtime_vgr_ms','factory_base_runtime_hbw_ms','factory_base_runtime_mpo_ms','factory_base_runtime_sld_ms','storage_model_id','vgr_model_id','hbw_model_id','expected_empty_storage','vgr_storage_pred','hbw_storage_pred','storage_match_vgr','storage_match_hbw','storage_confidence','expected_label_VGR','predicted_label_VGR','vgr_match','vgr_ready','vgr_confidence','vgr_latency_s','expected_label_HBW','predicted_label_HBW','hbw_match','hbw_ready','hbw_confidence','hbw_latency_s','timeout','error','control_enabled','control_published','control_reason','control_command_set_complete','control_vgr_cmd','control_hbw_cmd','control_mpo_cmd','control_sld_cmd','control_vgr_topic','control_hbw_topic','control_mpo_topic','control_sld_topic','control_vgr_publisher','control_hbw_publisher','control_mpo_publisher','control_sld_publisher','control_qos','control_retain','bootstrap_vgr_rows','bootstrap_hbw_rows','module_runtime_vgr_ms','module_runtime_hbw_ms','module_runtime_mpo_ms','module_runtime_sld_ms','job_sent_vgr','job_sent_hbw','job_sent_mpo','job_sent_sld','job_accepted_vgr','job_accepted_hbw','job_accepted_mpo','job_accepted_sld'];
const csv=(value)=>{if(value===null||value===undefined)return '';const text=String(value);return /[",\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text;};
const row=msg._report_row||{};
msg.filename=`${msg._report_state.run_dir}/summary.csv`;
msg.payload=(Number(row.row_index)===0?columns.join(',')+'\n':'')+columns.map((key)=>csv(row[key])).join(',')+'\n';
return msg;
"""

REPORT_SUMMARY = r"""
// Laufende oder finale run_summary.json aus einem konsistenten Zaehlerstand bilden
const state=msg._report_state, factory=msg._factory_status||null, completed=factory?.state==='completed', stopped=factory?.state==='reset'||state.last_cycle_status==='fault_latched';
const summary={mode:'live_mqtt_nodered',completed,stopped,stop_reason:factory?(completed?'completed':'reset'):(stopped?'fault_latched':'running'),last_cycle_status:state.last_cycle_status,rows_completed:state.rows,control_published_rows:state.command_rows,control_published_commands:state.command_rows*4,control_idle_fallback_rows:state.idle_fallback_rows,faults:state.faults,storage_matches_vgr:state.matches.storage,storage_matches_hbw:state.matches.storage,vgr_matches:state.matches.vgr,hbw_matches:state.matches.hbw,model_ids:state.model_ids,run_config:state.run_config,started_at:state.started_at,updated_at:new Date().toISOString(),events_path:`${state.run_dir}/events.jsonl`,summary_path:`${state.run_dir}/summary.csv`};
if (factory) summary.factory_status={run_id:factory.run_id,trace_total:factory.trace_total,payloads_sent:factory.payloads_sent,progress_percent:factory.progress_percent,sent_counts:factory.sent_counts,accepted_counts:factory.accepted_counts};
msg.filename=`${state.run_dir}/run_summary.json`; msg.payload=JSON.stringify(summary,null,2)+'\n';
return msg;
"""


def build_runtime_nodes() -> list[dict]:
    nodes: list[dict] = []
    nodes.extend(base_tabs())
    nodes.extend(build_init_nodes())
    nodes.extend(build_state_nodes())
    nodes.extend(build_module_nodes())
    nodes.extend(build_semaphore_nodes())
    nodes.extend(build_pipeline_nodes())
    return nodes


def build_init_nodes() -> list[dict]:
    tab = "tab-init"
    nodes = [
        group("group-init-control", tab, "Start und Trace", 20, 20, 1600, 300),
        group("group-init-errors", tab, "Fehler und Status", 20, 350, 1600, 210),
        comment("comment-init", tab, "Start pruefen | Trace laden | vier Idle-Commands", 220, 45),
        mqtt_in("in-init-control", tab, "group-init-control", "Start / Reset", "ft/sim/factory/control", "1", 130, 100, [["json-init-control"]]),
        json_node("json-init-control", tab, "group-init-control", "Control JSON", 330, 100, [["switch-init-control"]], "obj"),
        switch_node("switch-init-control", tab, "group-init-control", "Start oder Reset", "payload.cmd", [
            {"t":"eq","v":"start","vt":"str"},{"t":"eq","v":"reset","vt":"str"}], 530, 100,
            [["fn-start-validate"],["fn-reset-runtime"]]),
        function_node("fn-start-validate", tab, "group-init-control", "Start pruefen", START_VALIDATE, 740, 80,
                      [["file-trace"],["fn-factory-status"]], outputs=2,
                      info="### Aufgabe\nStartparameter und NN-Bereitschaft pruefen.\n\n### Eingang\n`ft/sim/factory/control`.\n\n### Zustand\nNur ausstehende Startkonfiguration.\n\n### Ausgang\nTrace-Dateipfad oder normalisierter Status.\n\n### Warum Function-Node?\nDie Konfiguration muss atomar validiert werden."),
        {"id":"file-trace","type":"file in","z":tab,"g":"group-init-control","name":"Testszenario lesen","filename":"filename","filenameType":"msg","format":"utf8","chunk":False,"sendError":True,"encoding":"none","allProps":True,"x":940,"y":80,"wires":[["change-trim-trace"]]},
        change_node("change-trim-trace",tab,"group-init-control","Abschlusszeile entfernen",[
            {"t":"change","p":"payload","pt":"msg","from":"\\s+$","fromt":"re","to":"","tot":"str"}],1110,55,[["split-trace-lines"]]),
        {"id":"split-trace-lines","type":"split","z":tab,"g":"group-init-control","name":"JSONL zerlegen","splt":"\n","spltType":"str","arraySplt":1,"arraySpltType":"len","stream":False,"addname":"","property":"payload","x":1130,"y":80,"wires":[["switch-trace-line"]]},
        switch_node("switch-trace-line", tab, "group-init-control", "Leerzeilen verwerfen", "payload", [{"t":"nempty"}], 1320, 80, [["json-trace-line"]]),
        json_node("json-trace-line", tab, "group-init-control", "Tracezeile JSON", 1500, 80, [["change-trace-parts"]], "obj"),
        change_node("change-trace-parts",tab,"group-init-control","Als Datensatzliste sammeln",[
            {"t":"set","p":"parts.type","pt":"msg","to":"array","tot":"str"},
            {"t":"delete","p":"parts.ch","pt":"msg"}],1500,105,[["join-trace"]]),
        {"id":"join-trace","type":"join","z":tab,"g":"group-init-control","name":"Trace sammeln","mode":"auto","build":"array","property":"payload","propertyType":"msg","key":"topic","joiner":"\\n","joinerType":"str","accumulate":False,"timeout":"","count":"","reduceRight":False,"reduceExp":"","reduceInit":"","reduceInitType":"","reduceFixup":"","x":1500,"y":130,"wires":[["fn-trace-init"]]},
        function_node("fn-trace-init", tab, "group-init-control", "Lauf initialisieren", TRACE_INIT, 1280, 170,
                      [["link-init-vgr","link-init-hbw","link-init-mpo","link-init-sld","change-init-status","debug-init"]],
                      info="### Aufgabe\nGeladenen Trace und fluechtigen Laufzustand gemeinsam initialisieren.\n\n### Eingang\nVollstaendige Tracezeilen und validierte Konfiguration.\n\n### Ausgang\nStartsignal an vier getrennte Modulzweige.\n\n### Warum Function-Node?\nRun-ID, Index und acht Counter muessen konsistent beginnen."),
        link_out("link-init-vgr",tab,"group-init-control","VGR initialisieren",["link-module-vgr-init"],1120,210),
        link_out("link-init-hbw",tab,"group-init-control","HBW initialisieren",["link-module-hbw-init"],1120,235),
        link_out("link-init-mpo",tab,"group-init-control","MPO initialisieren",["link-module-mpo-init"],1120,260),
        link_out("link-init-sld",tab,"group-init-control","SLD initialisieren",["link-module-sld-init"],1120,285),
        change_node("change-init-status",tab,"group-init-control","Init-Status",[
            {"t":"set","p":"payload","pt":"msg","to":"{'state':'bootstrap_commands_published','semaphore_state':'blocked'}","tot":"jsonata"}],1040,170,[["fn-factory-status"]]),
        debug_node("debug-init",tab,"group-init-control","Initialisierung abgeschlossen",1480,210),
        function_node("fn-reset-runtime",tab,"group-init-control","Lauf zuruecksetzen",RESET_RUNTIME,760,240,
                      [["link-init-vgr","link-init-hbw","link-init-mpo","link-init-sld","change-reset-status"]],
                      info="### Aufgabe\nLaufzustand, Fenster und offene Requests gemeinsam leeren.\n\n### Eingang\nReset-Control.\n\n### Ausgang\nReset an Module und Statuspfad.\n\n### Warum Function-Node?\nDer Reset muss atomar sein."),
        change_node("change-reset-status",tab,"group-init-control","Reset-Status",[
            {"t":"set","p":"payload","pt":"msg","to":"{'state':'reset','run_id':payload.previous_run_id,'semaphore_state':'blocked'}","tot":"jsonata"}],1040,240,[["fn-factory-status"]]),
        mqtt_in("in-init-ai-ready",tab,"group-init-control","KI bereit?","ft/ai/orchestration/status","1",130,285,[["switch-init-ai-ready"]]),
        switch_node("switch-init-ai-ready",tab,"group-init-control","Pending Start?","payload.state",[
            {"t":"eq","v":"ready","vt":"str"}],350,285,[["fn-resume-start"]]),
        function_node("fn-resume-start",tab,"group-init-control","Start fortsetzen",r"""
// Ausstehenden Start nach NN-Bereitschaft erneut einreichen
const pending = global.get('sim.pending_start');
if (!pending) return null;
msg.payload = pending;
return msg;
""",560,285,[["fn-start-validate"]],
                      info="### Aufgabe\nAusstehenden Start nach eingetroffener NN-Bereitschaft erneut einreichen.\n\n### Eingang\nRetained Ready-Status.\n\n### Zustand\nNur die validierte Pending-Konfiguration.\n\n### Ausgang\nErneute Startpruefung.\n\n### Warum Function-Node?\nPending Start wird atomar gelesen."),
        function_node("fn-factory-status",tab,"group-init-errors","Fabrikstatus bilden",FACTORY_STATUS,1050,410,
                      [["json-factory-status"]],info="### Aufgabe\nFabrikstatus aus dem zentralen Laufzustand bilden.\n\n### Eingang\nStatusereignis.\n\n### Ausgang\nRetained Fabrikstatus.\n\n### Warum Function-Node?\nEin konsistentes Statusbild wird atomar gelesen."),
        json_node("json-factory-status",tab,"group-init-errors","Status JSON",1250,410,[["out-factory-status"]]),
        mqtt_out("out-factory-status",tab,"group-init-errors","Fabrikstatus retained","ft/sim/factory/status","1","true",1460,410),
        link_in("link-factory-status",tab,"group-init-errors","Statusereignisse",1020,460,[["fn-factory-status"]]),
        link_in("link-fault-central",tab,"group-init-errors","Flowfehler",130,410,[["fn-fault-latch"]]),
        function_node("fn-fault-latch",tab,"group-init-errors","Fault verriegeln",FAULT_LATCH,350,410,
                      [["json-ai-fault","change-fault-factory","debug-fault"]],
                      info="### Aufgabe\nDen ersten normalisierten Flowfehler verriegeln.\n\n### Eingang\nFehlercode und Kurzdetail.\n\n### Ausgang\nOrchestrierungs- und Fabrikstatus.\n\n### Warum Function-Node?\nFault-Latch darf nur einmal atomar gesetzt werden."),
        json_node("json-ai-fault",tab,"group-init-errors","Fault JSON",560,390,[["out-ai-fault"]]),
        mqtt_out("out-ai-fault",tab,"group-init-errors","Orchestrierungsfehler","ft/ai/orchestration/status","1","true",790,390),
        change_node("change-fault-factory",tab,"group-init-errors","Fabrikfehler",[
            {"t":"set","p":"payload","pt":"msg","to":"{'state':'fault_latched','detail':payload.error,'semaphore_state':'fault'}","tot":"jsonata"}],560,440,[["fn-factory-status"]]),
        debug_node("debug-fault",tab,"group-init-errors","Fault-Latch",770,480),
        {"id":"catch-init","type":"catch","z":tab,"g":"group-init-errors","name":"Initialisierungsfehler","scope":["fn-start-validate","file-trace","json-trace-line","fn-trace-init","fn-reset-runtime","fn-factory-status"],"uncaught":False,"x":140,"y":480,"wires":[["change-catch-init"]]},
        change_node("change-catch-init",tab,"group-init-errors","Fehler normalisieren",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'runtime_error','detail':error.message,'source':error.source.name}","tot":"jsonata"}],380,480,[["link-fault-out-init"]]),
        link_out("link-fault-out-init",tab,"group-init-errors","Zum Fault-Latch",["link-fault-central"],570,480),
    ]
    return nodes


def build_state_nodes() -> list[dict]:
    tab="tab-state"; group_id="group-state"
    return [
        group(group_id,tab,"50-ms-Rohzustand",20,20,1280,260),
        comment("comment-state",tab,"50 ms tick | Index halten | virtuelles Rohzustandstopic",230,45),
        {"id":"inject-raw-state","type":"inject","z":tab,"g":group_id,"name":"Zustand alle 50 ms","props":[{"p":"payload"},{"p":"topic","vt":"str"}],"repeat":"0.05","crontab":"","once":True,"onceDelay":0.1,"topic":"","payload":"","payloadType":"date","x":180,"y":110,"wires":[["fn-raw-state"]]},
        function_node("fn-raw-state",tab,group_id,"Rohzustand bilden",RAW_STATE,410,110,[["json-raw-state"]],
                      info="### Aufgabe\nDen aktuellen Tracezustand abbilden, ohne den Index zu erhoehen.\n\n### Eingang\n50-ms-Tick.\n\n### Ausgang\nEin virtueller Rohzustand.\n\n### Warum Function-Node?\nTraceindex und Rohsamplezaehler muessen konsistent gelesen werden."),
        json_node("json-raw-state",tab,group_id,"Rohzustand JSON",620,110,[["out-raw-state"]]),
        mqtt_out("out-raw-state",tab,group_id,"Virtueller Rohzustand","ft/sim/factory/raw_state","1","false",840,110),
        {"id":"catch-state","type":"catch","z":tab,"g":group_id,"name":"Zustandsfehler","scope":["fn-raw-state","json-raw-state"],"uncaught":False,"x":180,"y":200,"wires":[["change-catch-state"]]},
        change_node("change-catch-state",tab,group_id,"Fehler normalisieren",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'invalid_payload','detail':error.message,'source':error.source.name}","tot":"jsonata"}],430,200,[["link-fault-out-state"]]),
        link_out("link-fault-out-state",tab,group_id,"Zum Fault-Latch",["link-fault-central"],650,200),
        {"id":"status-mqtt-state","type":"status","z":tab,"g":group_id,"name":"MQTT-Zustand","scope":["out-raw-state"],"x":870,"y":190,"wires":[["switch-mqtt-state"]]},
        switch_node("switch-mqtt-state",tab,group_id,"MQTT getrennt?","status.text",[
            {"t":"regex","v":"disconnected|error","vt":"str","case":False}],1060,190,[["change-mqtt-state"]]),
        change_node("change-mqtt-state",tab,group_id,"MQTT-Fehler",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'mqtt_disconnected','detail':status.text,'source':'Zustandserfassung'}","tot":"jsonata"}],1080,230,[["link-fault-out-state"]]),
    ]


def build_module_nodes() -> list[dict]:
    tab="tab-modules"; nodes=[]
    y_positions={"vgr":20,"hbw":250,"mpo":480,"sld":710}
    idle_topics={"vgr":"ai/vgr/cmd0","hbw":"ai/hbw/cmd000","mpo":"ai/mpo/cmd0","sld":"ai/sld/cmd0"}
    for module,y in y_positions.items():
        gid=f"group-module-{module}"; upper=module.upper()
        nodes.extend([
            group(gid,tab,f"{upper}: Command -> Laufzeit -> Abschluss",20,y,1780,205),
            comment(f"comment-module-{module}",tab,f"{upper} | sent_count++ | Delay | accepted_count++",230,y+25),
            link_in(f"link-module-{module}-init",tab,gid,"Initialisierung",100,y+70,[[f"switch-module-{module}-init"]]),
            switch_node(f"switch-module-{module}-init",tab,gid,"Start oder Reset","payload.action",[
                {"t":"eq","v":"start","vt":"str"},{"t":"eq","v":"reset","vt":"str"}],270,y+70,
                [[f"change-module-{module}-init"],[f"change-module-{module}-reset"]]),
            change_node(f"change-module-{module}-init",tab,gid,"Variablen + Idle",[
                {"t":"set","p":f"{module}_busy","pt":"flow","to":"false","tot":"bool"},
                {"t":"set","p":f"{module}_last_command","pt":"flow","to":"","tot":"str"},
                {"t":"set","p":f"{module}_runtime_ms","pt":"flow","to":"0","tot":"num"},
                {"t":"set","p":"topic","pt":"msg","to":idle_topics[module],"tot":"str"},
                {"t":"set","p":"payload","pt":"msg","to":"","tot":"str"},
                {"t":"set","p":"qos","pt":"msg","to":"2","tot":"num"},
                {"t":"set","p":"retain","pt":"msg","to":"false","tot":"bool"}],500,y+55,[[f"out-module-{module}-idle"]]),
            mqtt_out(f"out-module-{module}-idle",tab,gid,"Initiales Idle",idle_topics[module],"2","false",750,y+55),
            change_node(f"change-module-{module}-reset",tab,gid,"Delay leeren",[
                {"t":"set","p":f"{module}_busy","pt":"flow","to":"false","tot":"bool"},
                {"t":"set","p":f"{module}_last_command","pt":"flow","to":"","tot":"str"},
                {"t":"set","p":f"{module}_runtime_ms","pt":"flow","to":"0","tot":"num"},
                {"t":"set","p":"reset","pt":"msg","to":"true","tot":"bool"}],500,y+95,[[f"delay-module-{module}"]]),
            mqtt_in(f"in-module-{module}-command",tab,gid,"Command empfangen",f"ai/{module}/+","2",120,y+140,[[f"fn-module-{module}-gate"]]),
            function_node(f"fn-module-{module}-gate",tab,gid,"Command pruefen",MODULE_GATE.replace('__MODULE__',module),370,y+140,
                          [[f"fn-module-{module}-runtime"],[f"link-fault-module-{module}"]],outputs=2,
                          info=f"### Aufgabe\n{upper}-Command atomar annehmen und `sent_count` erhoehen.\n\n### Eingang\nBestehendes Command-Topic.\n\n### Zustand\nBusy und Jobcounter.\n\n### Ausgang\nAngenommener Command oder Duplikatfehler.\n\n### Warum Function-Node?\nBusy-Pruefung und Counterupdate duerfen nicht getrennt werden."),
            function_node(f"fn-module-{module}-runtime",tab,gid,"Laufzeit bestimmen",MODULE_RUNTIME,620,y+140,
                          [[f"delay-module-{module}",f"debug-module-{module}-start",f"link-status-module-{module}-start"]],
                          info="### Aufgabe\nReproduzierbare Modulzeit aus Seed, Modul und Jobnummer berechnen.\n\n### Eingang\nAngenommener Command.\n\n### Ausgang\n`msg.delay` fuer den Core-Delay.\n\n### Warum Function-Node?\nDie deterministische Hashberechnung ist eine atomare Rechenoperation."),
            {"id":f"delay-module-{module}","type":"delay","z":tab,"g":gid,"name":"Teilprozess simulieren","pauseType":"delayv","timeout":"5","timeoutUnits":"seconds","rate":"1","nbRateUnits":"1","rateUnits":"second","randomFirst":"1","randomLast":"5","randomUnits":"seconds","drop":False,"allowrate":False,"outputs":1,"x":880,"y":140,"wires":[[f"fn-module-{module}-complete"]]},
            function_node(f"fn-module-{module}-complete",tab,gid,"Abschluss registrieren",MODULE_COMPLETE.replace('__MODULE__',module),1130,y+140,
                          [[f"debug-module-{module}-complete",f"link-status-module-{module}-complete"]],
                          info=f"### Aufgabe\n{upper}-Abschluss atomar registrieren und `accepted_count` erhoehen.\n\n### Eingang\nAbgelaufener Delay.\n\n### Ausgang\nKompakter Modulabschluss.\n\n### Warum Function-Node?\nCounter und Busy-Zustand muessen gemeinsam wechseln."),
            debug_node(f"debug-module-{module}-start",tab,gid,f"{upper} Start",900,y+95),
            debug_node(f"debug-module-{module}-complete",tab,gid,f"{upper} Abschluss",1400,y+140),
            link_out(f"link-status-module-{module}-start",tab,gid,"Status Start",["link-factory-status"],1020,y+95),
            link_out(f"link-status-module-{module}-complete",tab,gid,"Status Abschluss",["link-factory-status"],1500,y+175),
            link_out(f"link-fault-module-{module}",tab,gid,"Zum Fault-Latch",["link-fault-central"],630,y+175),
        ])
    all_mqtt=[f"in-module-{d}-command" for d in MODULES]+[f"out-module-{d}-idle" for d in MODULES]
    nodes.extend([
        {"id":"catch-modules","type":"catch","z":tab,"name":"Modulfehler","scope":[n["id"] for n in nodes if n.get("type")=="function"],"uncaught":False,"x":1550,"y":30,"wires":[["change-catch-modules"]]},
        change_node("change-catch-modules",tab,"","Fehler normalisieren",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'runtime_error','detail':error.message,'source':error.source.name}","tot":"jsonata"}],1570,70,[["link-fault-out-modules"]]),
        link_out("link-fault-out-modules",tab,"","Zum Fault-Latch",["link-fault-central"],1760,70),
        {"id":"status-mqtt-modules","type":"status","z":tab,"name":"MQTT-Zustand","scope":all_mqtt,"x":1570,"y":110,"wires":[["switch-mqtt-modules"]]},
        switch_node("switch-mqtt-modules",tab,"","MQTT getrennt?","status.text",[{"t":"regex","v":"disconnected|error","vt":"str","case":False}],1570,150,[["change-mqtt-modules"]]),
        change_node("change-mqtt-modules",tab,"","MQTT-Fehler",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'mqtt_disconnected','detail':status.text,'source':'Virtuelle Module'}","tot":"jsonata"}],1570,190,[["link-fault-out-modules"]]),
    ])
    return nodes


def build_semaphore_nodes() -> list[dict]:
    tab="tab-semaphore"; gid="group-semaphore"
    return [
        group(gid,tab,"Jobcounter-Semaphor",20,20,1660,360),
        comment("comment-semaphore",tab,"Rohzustand | 4 Counterpaare | genau eine Freigabe",250,45),
        mqtt_in("in-raw-semaphore",tab,gid,"Rohzustand empfangen","ft/sim/factory/raw_state","1",150,110,[["fn-semaphore"]]),
        function_node("fn-semaphore",tab,gid,"Semaphor pruefen",SEMAPHORE,390,110,
                      [["json-live-release","change-semaphore-status","change-debug-semaphore"],["fn-factory-status-semaphore"],["link-fault-semaphore"]],outputs=3,
                      info="### Aufgabe\nVier `sent_count`-/`accepted_count`-Paare und Commandgeneration atomar vergleichen.\n\n### Eingang\nVirtueller Rohzustand.\n\n### Zustand\nLetzte Freigabecounter, Traceindex und Watchdog.\n\n### Ausgang\nGenau eine Live-Freigabe, Abschluss oder Fault.\n\n### Warum Function-Node?\nCountervergleich und Traceindex duerfen nicht zwischen Nachrichten auseinanderfallen."),
        json_node("json-live-release",tab,gid,"Anlagenzustand JSON",650,90,[["out-live-release"]]),
        mqtt_out("out-live-release",tab,gid,"Freigegebener Anlagenzustand","log/logging/state","1","false",900,90),
        change_node("change-semaphore-status",tab,gid,"Freigabestatus",[
            {"t":"set","p":"payload","pt":"msg","to":"_factory_status","tot":"msg"}],650,140,[["fn-factory-status-semaphore"]]),
        function_node("fn-factory-status-semaphore",tab,gid,"Fabrikstatus bilden",FACTORY_STATUS,900,180,[["json-semaphore-status"]],
                      info="### Aufgabe\nSemaphorereignis als konsistenten Fabrikstatus darstellen.\n\n### Eingang\nFreigabe oder Abschluss.\n\n### Ausgang\nRetained Status.\n\n### Warum Function-Node?\nAlle Counter werden aus demselben Snapshot gelesen."),
        json_node("json-semaphore-status",tab,gid,"Status JSON",1110,180,[["out-semaphore-status"]]),
        mqtt_out("out-semaphore-status",tab,gid,"Fabrikstatus","ft/sim/factory/status","1","true",1320,180),
        debug_node("debug-semaphore",tab,gid,"Semaphorfreigabe",900,130),
        change_node("change-debug-semaphore",tab,gid,"Freigabe Kurzinfo",[
            {"t":"set","p":"payload","pt":"msg","to":"{'run_id':payload.simulation_run_id,'request_id':payload.request_id,'trace_index':payload.trace_index,'sent':payload.module_job_counts.sent,'accepted':payload.module_job_counts.accepted}","tot":"jsonata"}],650,130,[["debug-semaphore"]]),
        link_out("link-fault-semaphore",tab,gid,"Zum Fault-Latch",["link-fault-central"],650,240),
        {"id":"catch-semaphore","type":"catch","z":tab,"g":gid,"name":"Semaphorfehler","scope":["fn-semaphore","fn-factory-status-semaphore"],"uncaught":False,"x":160,"y":290,"wires":[["change-catch-semaphore"]]},
        change_node("change-catch-semaphore",tab,gid,"Fehler normalisieren",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'runtime_error','detail':error.message,'source':error.source.name}","tot":"jsonata"}],410,290,[["link-fault-out-semaphore"]]),
        link_out("link-fault-out-semaphore",tab,gid,"Zum Fault-Latch",["link-fault-central"],620,290),
        {"id":"status-mqtt-semaphore","type":"status","z":tab,"g":gid,"name":"MQTT-Zustand","scope":["in-raw-semaphore","out-live-release","out-semaphore-status"],"x":900,"y":290,"wires":[["switch-mqtt-semaphore"]]},
        switch_node("switch-mqtt-semaphore",tab,gid,"MQTT getrennt?","status.text",[{"t":"regex","v":"disconnected|error","vt":"str","case":False}],1110,290,[["change-mqtt-semaphore"]]),
        change_node("change-mqtt-semaphore",tab,gid,"MQTT-Fehler",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'mqtt_disconnected','detail':status.text,'source':'Semaphor'}","tot":"jsonata"}],1320,290,[["link-fault-out-semaphore"]]),
    ]


def build_pipeline_nodes() -> list[dict]:
    tab="tab-pipeline"; nodes=[]
    nodes.extend([
        group("group-contracts",tab,"Contracts und Status",20,20,1660,210),
        group("group-storage",tab,"Storage",20,250,1660,210),
        group("group-window",tab,"Windowing und parallele Requests",20,480,1660,250),
        group("group-responses",tab,"Responses und Reporting",20,750,1660,300),
        comment("comment-pipeline",tab,"Contract Gate | Storage | VGR/HBW parallel | Responses nur Reporting",340,45),
        mqtt_in("in-contracts",tab,"group-contracts","Modellvertraege","ft/nn/+/contract","1",130,90,[["fn-contract-register"]]),
        function_node("fn-contract-register",tab,"group-contracts","Contract registrieren",CONTRACT_REGISTER,370,90,[["fn-readiness"]],
                      info="### Aufgabe\nEinen retained Modellvertrag gegen Domain und Topics pruefen und speichern.\n\n### Eingang\n`ft/nn/+/contract`.\n\n### Ausgang\nRegistry-Aktualisierung.\n\n### Warum Function-Node?\nEin Vertrag wird atomar validiert und ersetzt."),
        mqtt_in("in-model-statuses",tab,"group-contracts","Modellstatus","ft/nn/+/status","1",130,150,[["fn-status-register"]]),
        function_node("fn-status-register",tab,"group-contracts","Status registrieren",STATUS_REGISTER,370,150,[["fn-readiness"]],
                      info="### Aufgabe\nEinen retained Dienststatus domainbezogen speichern.\n\n### Eingang\n`ft/nn/+/status`.\n\n### Ausgang\nRegistry-Aktualisierung.\n\n### Warum Function-Node?\nWildcard-Topic und Domain werden gemeinsam ausgewertet."),
        function_node("fn-readiness",tab,"group-contracts","Bereitschaft pruefen",READINESS,620,120,[["json-ai-ready"]],
                      info="### Aufgabe\nDrei Contracts und Online-Status gemeinsam bewerten.\n\n### Eingang\nRegistry-Aktualisierung.\n\n### Ausgang\nRetained Orchestrierungsstatus.\n\n### Warum Function-Node?\nDie Bereitschaft ist ein atomarer Gesamtsnapshot."),
        json_node("json-ai-ready",tab,"group-contracts","Status JSON",830,120,[["out-ai-ready"]]),
        mqtt_out("out-ai-ready",tab,"group-contracts","Orchestrierungsstatus","ft/ai/orchestration/status","1","true",1050,120),
        mqtt_in("in-ai-control",tab,"group-contracts","KI Reset","ft/ai/orchestration/control","1",1180,90,[["fn-ai-reset"]]),
        function_node("fn-ai-reset",tab,"group-contracts","KI-Zustand leeren",AI_RESET,1380,90,[["fn-readiness"]],
                      info="### Aufgabe\nOffene Requests, Antwort-Deduplizierung und LSTM-Fenster leeren.\n\n### Eingang\n`ft/ai/orchestration/control` mit `cmd=reset`.\n\n### Ausgang\nImpuls zur erneuten Bereitschaftspruefung.\n\n### Warum Function-Node?\nDie drei fluechtigen KI-Zustaende muessen gemeinsam zurueckgesetzt werden."),
        mqtt_in("in-live-pipeline",tab,"group-storage","Freigegebener Anlagenzustand","log/logging/state","1",150,320,[["fn-contract-gate"]]),
        function_node("fn-contract-gate",tab,"group-storage","Contract pruefen",CONTRACT_GATE,390,320,
                      [["fn-storage-request"],["link-fault-pipeline"]],outputs=2,
                      info="### Aufgabe\nVirtuell verfuegbare Features, Profil, Klassen und Dienststatus vor Storage pruefen.\n\n### Eingang\nFreigegebener Anlagenzustand.\n\n### Ausgang\nValidierter Zykluskontext oder Fault.\n\n### Warum Function-Node?\nDer virtuelle Contract-Gate muss einen konsistenten Snapshot pruefen."),
        function_node("fn-storage-request",tab,"group-storage","Storage-Request bilden",STORAGE_REQUEST,650,320,
                      [["json-storage-request"],["link-fault-pipeline"]],outputs=2,
                      info="### Aufgabe\nGenau einen Storage-Request und Korrelationszustand erzeugen.\n\n### Eingang\nValidierter Live-Zustand.\n\n### Ausgang\nStorage-Request oder Pending-Fehler.\n\n### Warum Function-Node?\nCycle-ID und Pending-Zustand muessen gemeinsam entstehen."),
        json_node("json-storage-request",tab,"group-storage","Storage JSON",870,320,[["out-storage-request"]]),
        mqtt_out("out-storage-request",tab,"group-storage","Storage-Request","ft/nn/storage/request","1","false",1090,320),
        mqtt_in("in-storage-result",tab,"group-storage","Storage-Ergebnis","ft/nn/response/storage","1",150,400,[["fn-storage-response"]]),
        function_node("fn-storage-response",tab,"group-storage","Storage-Ergebnis pruefen",STORAGE_RESPONSE,410,400,
                      [["fn-window-vgr","fn-window-hbw","change-idle-modules","debug-storage"],["link-fault-pipeline"]],outputs=2,
                      info="### Aufgabe\nStorage-Antwort korrelieren, Klasse pruefen und One-hot bilden.\n\n### Eingang\nStorage-Response.\n\n### Ausgang\nKlasse fuer zwei Window-Zweige und Idle-Zweig.\n\n### Warum Function-Node?\nKorrelation und One-hot muessen denselben Pending-Zyklus verwenden."),
        debug_node("debug-storage",tab,"group-storage","Storage-Ergebnis",700,440),
        function_node("fn-window-vgr",tab,"group-window","VGR W=10 bilden",WINDOW_REQUEST.replace('__DOMAIN__','vgr'),390,550,[["json-vgr-request","change-debug-request-vgr"]],
                      info="### Aufgabe\nVGR-Rolling-Window aktualisieren und Request bilden.\n\n### Eingang\nStorage-Klasse und aktueller Zustand.\n\n### Zustand\nNur VGR-Fenster je Quelle und Modell-ID.\n\n### Ausgang\nVGR-Request `(10,29)`.\n\n### Warum Function-Node?\nWindowupdate und Bootstrap muessen atomar sein."),
        function_node("fn-window-hbw",tab,"group-window","HBW W=10 bilden",WINDOW_REQUEST.replace('__DOMAIN__','hbw'),390,620,[["json-hbw-request","change-debug-request-hbw"]],
                      info="### Aufgabe\nHBW-Rolling-Window aktualisieren und Request bilden.\n\n### Eingang\nStorage-Klasse und aktueller Zustand.\n\n### Zustand\nNur HBW-Fenster je Quelle und Modell-ID.\n\n### Ausgang\nHBW-Request `(10,29)`.\n\n### Warum Function-Node?\nWindowupdate und Bootstrap muessen atomar sein."),
        json_node("json-vgr-request",tab,"group-window","VGR JSON",650,550,[["out-vgr-request"]]),
        mqtt_out("out-vgr-request",tab,"group-window","VGR-Request","ft/nn/vgr/request","1","false",860,550),
        json_node("json-hbw-request",tab,"group-window","HBW JSON",650,620,[["out-hbw-request"]]),
        mqtt_out("out-hbw-request",tab,"group-window","HBW-Request","ft/nn/hbw/request","1","false",860,620),
        debug_node("debug-request-vgr",tab,"group-window","VGR-Request Kurzinfo",650,520),
        debug_node("debug-request-hbw",tab,"group-window","HBW-Request Kurzinfo",650,670),
        change_node("change-debug-request-vgr",tab,"group-window","VGR Kurzinfo",[
            {"t":"set","p":"payload","pt":"msg","to":"_request_summary","tot":"msg"}],520,520,[["debug-request-vgr"]]),
        change_node("change-debug-request-hbw",tab,"group-window","HBW Kurzinfo",[
            {"t":"set","p":"payload","pt":"msg","to":"_request_summary","tot":"msg"}],520,670,[["debug-request-hbw"]]),
        change_node("change-idle-modules",tab,"group-window","MPO / SLD Idle",[
            {"t":"set","p":"payload","pt":"msg","to":json.dumps([
                {"topic":"ai/mpo/cmd0","payload":"","qos":2,"retain":False},
                {"topic":"ai/sld/cmd0","payload":"","qos":2,"retain":False},
            ], separators=(",", ":")),"tot":"json"}],1080,585,[["split-idle-modules"]]),
        {"id":"split-idle-modules","type":"split","z":tab,"g":"group-window","name":"Idle-Commands trennen","splt":"\\n","spltType":"str","arraySplt":1,"arraySpltType":"len","stream":False,"addname":"","property":"payload","x":1300,"y":585,"wires":[["change-idle-command"]]},
        change_node("change-idle-command",tab,"group-window","MQTT-Felder",[
            {"t":"set","p":"topic","pt":"msg","to":"payload.topic","tot":"msg"},{"t":"set","p":"qos","pt":"msg","to":"payload.qos","tot":"msg"},{"t":"set","p":"retain","pt":"msg","to":"payload.retain","tot":"msg"},{"t":"set","p":"payload","pt":"msg","to":"","tot":"str"}],1510,585,[["out-idle-modules"]]),
        mqtt_out("out-idle-modules",tab,"group-window","MPO / SLD Idle","","","",1630,585),
        mqtt_in("in-vgr-response",tab,"group-responses","VGR-Response","ft/nn/response/vgr","1",140,820,[["fn-vgr-response"]]),
        function_node("fn-vgr-response",tab,"group-responses","VGR-Response pruefen",MODEL_RESPONSE.replace('__DOMAIN__','vgr'),390,820,
                      [["join-model-responses"],["link-fault-pipeline"]],outputs=2,
                      info="### Aufgabe\nVGR-Response korrelieren und fuer Reporting markieren.\n\n### Eingang\nVGR-Response.\n\n### Ausgang\nValidierte Diagnoseantwort.\n\n### Warum Function-Node?\nKorrelation und Command-Nachweis gehoeren zu einer Antwort."),
        mqtt_in("in-hbw-response",tab,"group-responses","HBW-Response","ft/nn/response/hbw","1",140,880,[["fn-hbw-response"]]),
        function_node("fn-hbw-response",tab,"group-responses","HBW-Response pruefen",MODEL_RESPONSE.replace('__DOMAIN__','hbw'),390,880,
                      [["join-model-responses"],["link-fault-pipeline"]],outputs=2,
                      info="### Aufgabe\nHBW-Response korrelieren und fuer Reporting markieren.\n\n### Eingang\nHBW-Response.\n\n### Ausgang\nValidierte Diagnoseantwort.\n\n### Warum Function-Node?\nKorrelation und Command-Nachweis gehoeren zu einer Antwort."),
        {"id":"join-model-responses","type":"join","z":tab,"g":"group-responses","name":"Responses fuer Report","mode":"auto","build":"object","property":"payload","propertyType":"msg","key":"topic","joiner":"\\n","joinerType":"str","accumulate":False,"timeout":"10","count":"2","reduceRight":False,"reduceExp":"","reduceInit":"","reduceInitType":"","reduceFixup":"","x":680,"y":850,"wires":[["fn-cycle-result"]]},
        function_node("fn-cycle-result",tab,"group-responses","Zyklusergebnis bilden",CYCLE_RESULT,920,850,[["json-cycle-result","fn-report-row"]],
                      info="### Aufgabe\nZwei bereits unabhaengig publizierte NN-Ergebnisse zu einem Diagnosebericht verbinden.\n\n### Eingang\nVGR- und HBW-Response.\n\n### Ausgang\nZyklusergebnis.\n\n### Warum Function-Node?\nDer Report braucht einen konsistenten Pending-Snapshot; er ist keine Command-Barriere."),
        json_node("json-cycle-result",tab,"group-responses","Zyklus JSON",1140,820,[["out-cycle-result"]]),
        mqtt_out("out-cycle-result",tab,"group-responses","Zyklusergebnis","ft/ai/orchestration/cycle_result","1","false",1370,820),
        {"id":"inject-ai-timeout","type":"inject","z":tab,"g":"group-responses","name":"Timeout alle 250 ms","props":[{"p":"payload"}],"repeat":"0.25","crontab":"","once":False,"onceDelay":0.1,"payload":"","payloadType":"date","x":170,"y":960,"wires":[["fn-timeout-check"]]},
        function_node("fn-timeout-check",tab,"group-responses","Timeout pruefen",TIMEOUT_CHECK,410,960,[["link-fault-pipeline"]],
                      info="### Aufgabe\nDeadline eines offenen Inferenzzyklus pruefen.\n\n### Eingang\n250-ms-Tick.\n\n### Ausgang\nNur bei Timeout ein Fault.\n\n### Warum Function-Node?\nDeadline und Pending-Zyklus werden atomar gelesen."),
        link_out("link-fault-pipeline",tab,"group-responses","Zum Fault-Latch",["link-fault-central"],650,960),
    ])
    nodes.extend([
        mqtt_in("in-report-factory-status",tab,"group-responses","Fabrikabschluss","ft/sim/factory/status","1",920,930,[["switch-report-factory-status"]]),
        switch_node("switch-report-factory-status",tab,"group-responses","Abschluss oder Reset","payload.state",[
            {"t":"eq","v":"completed","vt":"str"},{"t":"eq","v":"reset","vt":"str"}],1140,930,
            [["change-report-factory-status"],["change-report-factory-status"]]),
        change_node("change-report-factory-status",tab,"group-responses","Reportabschluss markieren",[
            {"t":"set","p":"_report_event","pt":"msg","to":"factory_status","tot":"str"}],1360,930,[["fn-report-state"]]),
        function_node("fn-report-row",tab,"group-responses","CSV-Zeile abbilden",REPORT_ROW,1110,850,[["fn-report-state"]],
                      info="### Aufgabe\nEin Zyklusergebnis auf den stabilen CSV-Spaltenvertrag abbilden.\n\n### Eingang\nFertiges Zyklusergebnis.\n\n### Zustand\nKein eigener Zustand.\n\n### Ausgang\nOriginalereignis und normalisierte Tabellenzeile.\n\n### Warum Function-Node?\nOptionale Metriken und Sollwerte werden typisiert zusammengefuehrt."),
        function_node("fn-report-state",tab,"group-responses","Reportzaehler aktualisieren",REPORT_STATE,1280,850,
                      [["change-report-event","fn-report-csv","fn-report-summary"],["fn-report-summary"]],outputs=2,
                      info="### Aufgabe\nEinen Zyklus zaehlen oder einen korrelierten Laufabschluss erkennen.\n\n### Eingang\nNormalisierte Zykluszeile oder finaler Fabrikstatus.\n\n### Zustand\nNur Reportzaehler, Pfad und Run-ID.\n\n### Ausgang\nLaufende oder finale Reportdaten.\n\n### Warum Function-Node?\nZaehler und Abschlusskorrelation muessen atomar bleiben."),
        change_node("change-report-event",tab,"group-responses","Eventdatei waehlen",[
            {"t":"set","p":"filename","pt":"msg","to":"_report_state.run_dir & '/events.jsonl'","tot":"jsonata"},{"t":"set","p":"payload","pt":"msg","to":"_report_result","tot":"msg"}],1450,790,[["json-report-event"]]),
        {"id":"json-report-event","type":"json","z":tab,"g":"group-responses","name":"Event JSONL","property":"payload","action":"str","pretty":False,"x":1580,"y":790,"wires":[["change-report-event-newline"]]},
        change_node("change-report-event-newline",tab,"group-responses","Zeilenabschluss",[
            {"t":"set","p":"payload","pt":"msg","to":"payload & '\\n'","tot":"jsonata"}],1580,820,[["file-report-append-inline"]]),
        function_node("fn-report-csv",tab,"group-responses","CSV formatieren",REPORT_CSV,1450,850,[["file-report-append-inline"]],
                      info="### Aufgabe\nGenau eine CSV-Zeile in stabiler Spaltenreihenfolge formatieren.\n\n### Eingang\nNormalisierte Tabellenzeile.\n\n### Zustand\nKein eigener Zustand.\n\n### Ausgang\nDateiname und CSV-Text.\n\n### Warum Function-Node?\nHeader und CSV-Escaping muessen je Reportlauf konsistent sein."),
        function_node("fn-report-summary",tab,"group-responses","Run Summary bilden",REPORT_SUMMARY,1450,900,[["file-report-replace-inline"]],
                      info="### Aufgabe\nLaufende oder finale run_summary.json aus demselben Zaehlerstand bilden.\n\n### Eingang\nReportzustand und optional korrelierter Fabrikabschluss.\n\n### Zustand\nKein eigener Zustand.\n\n### Ausgang\nDateiname und JSON-Text.\n\n### Warum Function-Node?\nAbschlussflags und finale Zaehler gehoeren in einen Snapshot."),
        {"id":"file-report-append-inline","type":"file","z":tab,"g":"group-responses","name":"Events / CSV","filename":"filename","filenameType":"msg","appendNewline":False,"createDir":True,"overwriteFile":"false","encoding":"none","x":1600,"y":960,"wires":[[]]},
        {"id":"file-report-replace-inline","type":"file","z":tab,"g":"group-responses","name":"Run Summary","filename":"filename","filenameType":"msg","appendNewline":False,"createDir":True,"overwriteFile":"true","encoding":"none","x":1600,"y":1000,"wires":[[]]},
        {"id":"catch-report","type":"catch","z":tab,"g":"group-responses","name":"Reportfehler","scope":["file-report-append-inline","file-report-replace-inline"],"uncaught":False,"x":920,"y":1010,"wires":[["change-catch-report"]]},
        change_node("change-catch-report",tab,"group-responses","Reportfehler normalisieren",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'report_write_error','detail':error.message,'source':error.source.name}","tot":"jsonata"}],1150,1010,[["link-fault-pipeline"]]),
        {"id":"catch-pipeline","type":"catch","z":tab,"name":"Pipelinefehler","scope":[n["id"] for n in nodes if n.get("type")=="function"]+["fn-report-row","fn-report-state","fn-report-csv","fn-report-summary"],"uncaught":False,"x":1150,"y":1000,"wires":[["change-catch-pipeline"]]},
        change_node("change-catch-pipeline",tab,"","Fehler normalisieren",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'runtime_error','detail':error.message,'source':error.source.name}","tot":"jsonata"}],1360,1000,[["link-fault-pipeline"]]),
        {"id":"status-mqtt-pipeline","type":"status","z":tab,"name":"MQTT-Zustand","scope":["in-contracts","in-model-statuses","in-live-pipeline","out-storage-request","out-vgr-request","out-hbw-request","out-idle-modules"],"x":1150,"y":1040,"wires":[["switch-mqtt-pipeline"]]},
        switch_node("switch-mqtt-pipeline",tab,"","MQTT getrennt?","status.text",[{"t":"regex","v":"disconnected|error","vt":"str","case":False}],1360,1040,[["change-mqtt-pipeline"]]),
        change_node("change-mqtt-pipeline",tab,"","MQTT-Fehler",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'mqtt_disconnected','detail':status.text,'source':'NN-Pipeline'}","tot":"jsonata"}],1530,1040,[["link-fault-pipeline"]]),
    ])
    return nodes


def update_hmi(existing: list[dict]) -> list[dict]:
    generated_ids = {
        "change-hmi-semaphore", "change-hmi-raw-count", "change-hmi-release-count",
        "ui-hmi-semaphore", "ui-hmi-raw-count", "ui-hmi-release-count",
        "fn-hmi-model-status", "fn-hmi-ai-status", "fn-hmi-factory-status",
        "fn-hmi-cycle-result", "fn-hmi-snapshot", "catch-hmi", "change-catch-hmi",
        "status-mqtt-hmi", "switch-mqtt-hmi", "change-mqtt-hmi", "link-fault-hmi",
    }
    hmi = [
        dict(node) for node in existing
        if (node.get("id") == "tab-virtual-hmi" or node.get("z") == "tab-virtual-hmi")
        and node.get("id") not in generated_ids
    ]
    by_id = {node["id"]: node for node in hmi}
    hmi = [node for node in hmi if node.get("id") != "fn-hmi-view-model"]
    by_id = {node["id"]: node for node in hmi}
    hmi_functions = [
        ("fn-hmi-model-status", "NN-Status merken", HMI_MODEL_STATUS, 520, 100,
         "Einen NN-Dienststatus in das gemeinsame, rein lesende HMI-Modell uebernehmen."),
        ("fn-hmi-ai-status", "KI-Status merken", HMI_AI_STATUS, 520, 140,
         "Orchestrierungsstatus und einen moeglichen Fault fuer die Anzeige merken."),
        ("fn-hmi-factory-status", "Fabrikstatus merken", HMI_FACTORY_STATUS, 520, 180,
         "Fabrikstatus, Fortschritt und Startfehler fuer die Anzeige merken."),
        ("fn-hmi-cycle-result", "Zyklusdiagnose merken", HMI_CYCLE_RESULT, 520, 220,
         "Vorhersagen, Modell-IDs und eine begrenzte Diagnosehistorie aktualisieren."),
    ]
    input_targets = {
        "in-hmi-model-status": "fn-hmi-model-status",
        "in-hmi-ai-status": "fn-hmi-ai-status",
        "in-hmi-factory-status": "fn-hmi-factory-status",
        "in-hmi-cycle-result": "fn-hmi-cycle-result",
    }
    for input_id, target in input_targets.items():
        by_id[input_id]["wires"] = [[target]]
    for node_id, name, code, x, y, task in hmi_functions:
        hmi.append(function_node(
            node_id, "tab-virtual-hmi", "group-hmi-core", name, code, x, y,
            [["fn-hmi-snapshot"]],
            info=f"### Aufgabe\n{task}\n\n### Eingang\nGenau eine MQTT-Nachrichtenart.\n\n### Zustand\nBegrenzter Anzeigezustand im Flow-Context.\n\n### Ausgang\nImpuls zur Snapshotbildung.\n\n### Warum Function-Node?\nDie Aktualisierung eines asynchronen Teilzustands muss atomar sein.",
        ))
    hmi.append(function_node(
        "fn-hmi-snapshot", "tab-virtual-hmi", "group-hmi-core", "Widgetdaten bilden",
        HMI_SNAPSHOT, 750, 160, [["split-hmi-actions"]],
        info="### Aufgabe\nGemeinsamen Anzeigezustand in acht begrenzte Widgetrollen abbilden.\n\n### Eingang\nImpuls nach einer Teilaktualisierung.\n\n### Zustand\nNur lesender HMI-Flow-Context.\n\n### Ausgang\nUebersicht, Tabellen, Chart und Meldung.\n\n### Warum Function-Node?\nAlle Widgets muessen denselben Snapshot erhalten.",
    ))
    overview_wires = [wire for wire in by_id["switch-hmi-role"]["wires"][0] if wire not in generated_ids]
    by_id["switch-hmi-role"]["wires"][0] = overview_wires
    overview_wires.extend(["change-hmi-semaphore","change-hmi-raw-count","change-hmi-release-count"])
    new_nodes = [
        change_node("change-hmi-semaphore","tab-virtual-hmi","group-hmi-widgets","Semaphorstatus",[
            {"t":"set","p":"payload","pt":"msg","to":"payload.semaphore_state","tot":"msg"}],1180,230,[["ui-hmi-semaphore"]]),
        change_node("change-hmi-raw-count","tab-virtual-hmi","group-hmi-widgets","Rohsamplezaehler",[
            {"t":"set","p":"payload","pt":"msg","to":"payload.raw_samples","tot":"msg"}],1180,260,[["ui-hmi-raw-count"]]),
        change_node("change-hmi-release-count","tab-virtual-hmi","group-hmi-widgets","Freigabezaehler",[
            {"t":"set","p":"payload","pt":"msg","to":"payload.released_states","tot":"msg"}],1180,290,[["ui-hmi-release-count"]]),
        {"id":"catch-hmi","type":"catch","z":"tab-virtual-hmi","g":"group-hmi-core","name":"HMI-Fehler","scope":[item[0] for item in hmi_functions]+["fn-hmi-snapshot"],"uncaught":False,"x":750,"y":260,"wires":[["change-catch-hmi"]]},
        change_node("change-catch-hmi","tab-virtual-hmi","group-hmi-core","HMI-Fehler normalisieren",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'hmi_runtime_error','detail':error.message,'source':error.source.name}","tot":"jsonata"}],980,260,[["link-fault-hmi"]]),
        {"id":"status-mqtt-hmi","type":"status","z":"tab-virtual-hmi","g":"group-hmi-inputs","name":"MQTT-Zustand","scope":list(input_targets),"x":310,"y":260,"wires":[["switch-mqtt-hmi"]]},
        switch_node("switch-mqtt-hmi","tab-virtual-hmi","group-hmi-inputs","MQTT getrennt?","status.text",[{"t":"regex","v":"disconnected|error","vt":"str","case":False}],520,260,[["change-mqtt-hmi"]]),
        change_node("change-mqtt-hmi","tab-virtual-hmi","group-hmi-inputs","MQTT-Fehler",[
            {"t":"set","p":"payload","pt":"msg","to":"{'code':'mqtt_disconnected','detail':status.text,'source':'Virtual HMI'}","tot":"jsonata"}],750,300,[["link-fault-hmi"]]),
        link_out("link-fault-hmi","tab-virtual-hmi","group-hmi-core","Zum Fault-Latch",["link-fault-central"],1200,280),
    ]
    for node_id,name,label,order in [
        ("ui-hmi-semaphore","Semaphorstatus","Semaphor",5),
        ("ui-hmi-raw-count","Rohsamples","Rohsamples",6),
        ("ui-hmi-release-count","Freigaben","Freigaben",7),
    ]:
        new_nodes.append({"id":node_id,"type":"ui-text","z":"tab-virtual-hmi","g":"group-hmi-widgets","group":"ui-hmi-group-status","order":order,"width":3,"height":2,"name":name,"label":label,"format":"{{msg.payload}}","layout":"col-center","style":False,"font":"Helvetica","fontSize":16,"color":"#263238","wrapText":True,"className":"","value":"payload","valueType":"msg","x":1600,"y":220+order*25,"wires":[]})
    source = by_id.get("ui-hmi-source-meta")
    if source:
        source["format"] = str(source.get("format", "")).replace("runtime-v1.2.0", "runtime-v1.3.0-rc.1")
    trace_summary = by_id.get("ui-hmi-trace")
    if trace_summary:
        trace_summary["className"] = "hmi-run-summary"
    styles = by_id.get("ui-hmi-table-layout-style")
    if styles and "hmi-run-summary" not in str(styles.get("format", "")):
        styles["format"] = str(styles.get("format", "")) + """

/* Lange Szenario-/Modellnamen auf schmalen Displays vollstaendig zeigen. */
@media (max-width: 600px) {
  .hmi-run-summary {
    grid-row-end: span 3 !important;
    grid-template-rows: repeat(3, var(--widget-row-height)) !important;
  }
  .hmi-run-summary .nrdb-ui-text-value {
    font-size: 14px;
    line-height: 1.25;
    overflow-wrap: anywhere;
    padding-inline: 6px;
  }
}

.hmi-model-table td {
  overflow-wrap: anywhere;
  word-break: break-all;
}

.hmi-diagnosis-table td {
  overflow-wrap: anywhere;
  word-break: normal;
  white-space: normal;
}
"""
    predictions = by_id.get("ui-hmi-predictions")
    if predictions:
        predictions["columns"] = [
            {"title":"Modell","key":"model","keyType":"key","type":"text","width":"20%","align":"start"},
            {"title":"Vorhersage","key":"prediction","keyType":"key","type":"text","width":"30%","align":"start"},
            {"title":"Konf.% | ms","key":"quality","keyType":"key","type":"text","width":"50%","align":"end"},
        ]
    modules = by_id.get("ui-hmi-modules")
    if modules:
        modules["columns"] = [
            {"title":"Modul","key":"module","keyType":"key","type":"text","width":"20%","align":"start"},
            {"title":"Cmd","key":"command","keyType":"key","type":"text","width":"20%","align":"start"},
            {"title":"Status | fertig/ges. | ms","key":"summary","keyType":"key","type":"text","width":"60%","align":"end"},
        ]
    models = by_id.get("ui-hmi-models")
    if models:
        models["className"] = "hmi-model-table"
        models["columns"] = [
            {"title":"Dienst","key":"model","keyType":"key","type":"text","width":"18%","align":"start"},
            {"title":"Status","key":"state","keyType":"key","type":"text","width":"18%","align":"start"},
            {"title":"Modell-ID","key":"model_id","keyType":"key","type":"text","width":"64%","align":"start"},
        ]
    cycles = by_id.get("ui-hmi-cycles")
    if cycles:
        cycles["className"] = "hmi-diagnosis-table"
        cycles["columns"] = [
            {"title":"Zeit","key":"timestamp","keyType":"key","type":"text","width":"20%","align":"start"},
            {"title":"Zyklus und Ergebnis","key":"summary","keyType":"key","type":"text","width":"80%","align":"start"},
        ]
    errors = by_id.get("ui-hmi-errors")
    if errors:
        errors["className"] = "hmi-diagnosis-table"
        errors["columns"] = [
            {"title":"Zeit","key":"timestamp","keyType":"key","type":"text","width":"20%","align":"start"},
            {"title":"Fehler | Details | Anzahl | Aktion","key":"summary","keyType":"key","type":"text","width":"80%","align":"start"},
        ]
    return hmi + new_nodes


def assign_groups(nodes: list[dict]) -> None:
    memberships: dict[str, list[str]] = {}
    for node in nodes:
        gid = node.get("g")
        if gid:
            memberships.setdefault(gid, []).append(node["id"])
    for node in nodes:
        if node.get("type") == "group":
            node["nodes"] = memberships.get(node["id"], [])
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        if node.get("type") != "link out":
            continue
        for target_id in node.get("links", []):
            target = by_id.get(target_id)
            if target and target.get("type") == "link in":
                target.setdefault("links", []).append(node["id"])


def main() -> None:
    existing = json.loads(FLOW_PATH.read_text(encoding="utf-8"))
    config_nodes = [
        dict(node) for node in existing
        if not node.get("z") and node.get("type") not in {"tab", "group"}
    ]
    nodes = build_runtime_nodes() + update_hmi(existing) + config_nodes
    assign_groups(nodes)
    FLOW_PATH.write_text(json.dumps(nodes, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
