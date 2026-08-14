"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const flows = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "flows.json"), "utf8"));
const nodes = Object.fromEntries(flows.map((node) => [node.id, node]));

function memory(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    get(key) { return values.get(key); },
    set(key, value) { values.set(key, value); },
  };
}

function runFunction(nodeId, msg, { global = memory(), flow = memory(), context = memory(), env = {} } = {}) {
  const errors = [];
  const node = { error(message) { errors.push(String(message)); } };
  const envApi = { get(key) { return env[key]; } };
  const execute = new Function(
    "msg", "node", "context", "flow", "global", "env", "Buffer",
    nodes[nodeId].func,
  );
  return { result: execute(msg, node, context, flow, global, envApi, Buffer), errors };
}

function baseRun(traceLength = 2) {
  const counts = { vgr: 1, hbw: 1, mpo: 1, sld: 1 };
  return {
    running: true,
    completed: false,
    fault: null,
    run_id: "run-1",
    trace: Array.from({ length: traceLength }, (_, index) => ({ request_id: `row-${index}` })),
    trace_index: 0,
    raw_samples: 3,
    releases: 0,
    sent: { ...counts },
    accepted: { ...counts },
    last_release_sent: { vgr: 0, hbw: 0, mpo: 0, sld: 0 },
    command_deadline_ms: Date.now() + 10000,
    module_runtime_ms: { vgr: 80, hbw: 90, mpo: 100, sld: 110 },
    command_topics: {},
    config: {
      trace_profile: "standard",
      trace_profile_name: "Normalbetrieb",
      model_profile: "deployment-current",
      model_profile_name: "Aktueller Modellstand",
      seed: 42,
      base_runtime_ms: { vgr: 100, hbw: 100, mpo: 100, sld: 100 },
    },
  };
}

test("semaphore releases each trace row once and completes after its command set", () => {
  const global = memory({ "sim.run": baseRun(2) });
  const raw = (index, final = false) => ({
    payload: { simulation_run_id: "run-1", trace_index: index, request_id: `row-${index}`, _final_wait: final },
  });

  let output = runFunction("fn-semaphore", raw(0), { global }).result;
  assert.equal(output[0].topic, "log/logging/state");
  assert.equal(global.get("sim.run").trace_index, 1);

  assert.equal(runFunction("fn-semaphore", raw(1), { global }).result, null);
  const afterFirst = global.get("sim.run");
  afterFirst.sent = { vgr: 2, hbw: 2, mpo: 2, sld: 2 };
  afterFirst.accepted = { vgr: 2, hbw: 2, mpo: 2, sld: 2 };
  global.set("sim.run", afterFirst);

  output = runFunction("fn-semaphore", raw(1), { global }).result;
  assert.equal(output[0].payload.request_id, "row-1");
  assert.equal(global.get("sim.run").trace_index, 2);

  const finalRun = global.get("sim.run");
  finalRun.sent = { vgr: 3, hbw: 3, mpo: 3, sld: 3 };
  finalRun.accepted = { vgr: 3, hbw: 3, mpo: 3, sld: 3 };
  global.set("sim.run", finalRun);
  output = runFunction("fn-semaphore", raw(1, true), { global }).result;
  assert.equal(output[1].payload.state, "completed");
  assert.deepEqual(output[1].payload.sent_counts, output[1].payload.accepted_counts);
});

test("semaphore faults on an incomplete command set after the watchdog", () => {
  const run = baseRun(1);
  run.sent.hbw = 0;
  run.accepted.hbw = 0;
  run.command_deadline_ms = Date.now() - 1;
  const global = memory({ "sim.run": run });
  const output = runFunction("fn-semaphore", {
    payload: { simulation_run_id: "run-1", trace_index: 0 },
  }, { global }).result;
  assert.equal(output[2].payload.code, "semaphore_stalled");
});

test("module flow uses deterministic module-specific delay and detects duplicates", () => {
  const run = baseRun(1);
  run.sent = { vgr: 0, hbw: 0, mpo: 0, sld: 0 };
  run.accepted = { vgr: 0, hbw: 0, mpo: 0, sld: 0 };
  run.module_busy = { vgr: false, hbw: false, mpo: false, sld: false };
  const global = memory({ "sim.run": run });
  const flow = memory({ vgr_busy: false });
  const accepted = runFunction("fn-module-vgr-gate", { topic: "ai/vgr/cmd101", payload: "" }, { global, flow }).result;
  assert.equal(accepted[0]._job, 1);
  const runtimeA = runFunction("fn-module-vgr-runtime", accepted[0], { global, flow }).result;
  assert.ok(runtimeA.delay >= 50 && runtimeA.delay <= 150);

  const copyRun = baseRun(1);
  copyRun.sent = { vgr: 1, hbw: 0, mpo: 0, sld: 0 };
  copyRun.accepted = { vgr: 0, hbw: 0, mpo: 0, sld: 0 };
  copyRun.config.seed = 42;
  const duplicate = runFunction("fn-module-vgr-gate", { topic: "ai/vgr/cmd101", payload: "" }, {
    global: memory({ "sim.run": copyRun }),
    flow: memory({ vgr_busy: true }),
  }).result;
  assert.equal(duplicate[1].payload.code, "duplicate_command");
});

test("raw-state ticks repeat without advancing the trace", () => {
  const run = baseRun(2);
  run.trace_index = 1;
  const global = memory({ "sim.run": run });
  const first = runFunction("fn-raw-state", { payload: Date.now() }, { global }).result;
  const second = runFunction("fn-raw-state", { payload: Date.now() }, { global }).result;
  assert.equal(first.payload.trace_index, 1);
  assert.equal(second.payload.trace_index, 1);
  assert.equal(global.get("sim.run").trace_index, 1);
  assert.equal(global.get("sim.run").raw_samples, 5);
});

test("virtual contract gate rejects a missing model feature", () => {
  const service = (domain, features) => ({
    schema_version: "1.0",
    domain,
    model_id: `${domain}:1`,
    feature_cols: features,
    class_ids: [0],
    command_output: domain === "storage" ? undefined : {
      mode: "direct_mqtt", qos: 2, retain: false,
      topics: { 0: domain === "vgr" ? "ai/vgr/cmd0" : "ai/hbw/cmd000" },
    },
  });
  const global = memory({
    "ai.contracts": {
      storage: service("storage", ["slot"]),
      vgr: service("vgr", ["missing", "empty_storage_0"]),
      hbw: service("hbw", ["slot", "empty_storage_0"]),
    },
    "ai.statuses": {
      storage: { state: "online" }, vgr: { state: "online" }, hbw: { state: "online" },
    },
  });
  const output = runFunction("fn-contract-gate", { payload: { slot: 1 } }, { global }).result;
  assert.equal(output[1].payload.code, "invalid_payload");
  assert.match(output[1].payload.detail, /missing/);
});

test("modular reporting stays running until the correlated factory completion", () => {
  const flow = memory();
  const cycle = {
    payload: {
      request_id: "request-1", cycle_id: "cycle-1", source_id: "source-1",
      status: "completed", empty_storage: 1, vgr_cmd: 0, hbw_cmd: 0,
      command_output_enabled: true, command_set_complete: true,
      model_ids: { storage: "storage:1", vgr: "vgr:1", hbw: "hbw:1" },
      commands: {
        vgr: { cmd: 0, topic: "ai/vgr/cmd0", publisher: "vgr_nn" },
        hbw: { cmd: 0, topic: "ai/hbw/cmd000", publisher: "hbw_nn" },
        mpo: { cmd: 0, topic: "ai/mpo/cmd0", publisher: "ai_flow" },
        sld: { cmd: 0, topic: "ai/sld/cmd0", publisher: "ai_flow" },
      },
      input_metadata: {
        simulation_run_id: "factory-1", trace_profile: "standard",
        trace_profile_name: "Normalbetrieb", model_profile: "deployment-current",
        model_profile_name: "Aktueller Modellstand", factory_seed: 42,
        factory_base_runtime_ms: { vgr: 100, hbw: 100, mpo: 100, sld: 100 },
      },
    },
  };
  const rowMessage = runFunction("fn-report-row", cycle, { flow }).result;
  const stateOutput = runFunction("fn-report-state", rowMessage, {
    flow, env: { REPORT_ROOT: "/tmp/reports" },
  }).result;
  const running = runFunction("fn-report-summary", stateOutput[0], { flow }).result;
  const runningSummary = JSON.parse(running.payload);
  assert.equal(runningSummary.completed, false);
  assert.equal(runningSummary.stop_reason, "running");
  assert.equal(runningSummary.rows_completed, 1);

  const foreign = runFunction("fn-report-state", {
    _report_event: "factory_status", payload: { state: "completed", run_id: "foreign" },
  }, { flow }).result;
  assert.equal(foreign, null);
  const finalOutput = runFunction("fn-report-state", {
    _report_event: "factory_status", payload: {
      state: "completed", run_id: "factory-1", trace_total: 1, payloads_sent: 1,
      sent_counts: { vgr: 2, hbw: 2, mpo: 2, sld: 2 },
      accepted_counts: { vgr: 2, hbw: 2, mpo: 2, sld: 2 },
    },
  }, { flow }).result;
  const completed = runFunction("fn-report-summary", finalOutput[1], { flow }).result;
  const completedSummary = JSON.parse(completed.payload);
  assert.equal(completedSummary.completed, true);
  assert.equal(completedSummary.stop_reason, "completed");
  assert.equal(completedSummary.factory_status.run_id, "factory-1");
});

test("HMI source adapters build one bounded shared widget snapshot", () => {
  const flow = memory();
  runFunction("fn-hmi-ai-status", {
    topic: "ft/ai/orchestration/status",
    payload: { state: "ready", command_output_enabled: true },
  }, { flow });
  runFunction("fn-hmi-factory-status", {
    topic: "ft/sim/factory/status",
    payload: {
      state: "module_started", trace_total: 320, payloads_sent: 7,
      semaphore_state: "blocked", raw_samples: 22, released_states: 7,
      sent_counts: { vgr: 8, hbw: 8, mpo: 8, sld: 8 },
      accepted_counts: { vgr: 7, hbw: 7, mpo: 7, sld: 7 },
    },
  }, { flow });
  const snapshot = runFunction("fn-hmi-snapshot", { payload: {} }, { flow }).result.payload;
  const actions = Object.fromEntries(snapshot.map((entry) => [entry.role, entry.payload]));
  assert.equal(actions.overview.label, "Simulation laeuft");
  assert.equal(actions.overview.raw_samples, 22);
  assert.equal(actions.overview.released_states, 7);
  assert.equal(actions.modules.length, 4);
  assert.equal(actions.modules[0].summary, "Laeuft | 7/8 | -");
});

test("AI reset clears response deduplication as a list", () => {
  const global = memory({
    "ai.pending": { request_id: "old" },
    "ai.windows": { vgr: { source: [1] }, hbw: { source: [1] } },
    "ai.seen_responses": ["old"],
  });
  const reset = runFunction("fn-ai-reset", { payload: { cmd: "reset" } }, { global });
  assert.ok(reset.result);
  assert.equal(global.get("ai.pending"), null);
  assert.deepEqual(global.get("ai.windows"), { vgr: {}, hbw: {} });
  assert.deepEqual(global.get("ai.seen_responses"), []);
});

test("ready start clears pending marker before asynchronous trace loading", () => {
  const global = memory({
    "ai.contracts": { storage: {}, vgr: {}, hbw: {} },
    "ai.statuses": {
      storage: { state: "online" }, vgr: { state: "online" }, hbw: { state: "online" },
    },
    "sim.run": { running: false, completed: false },
    "sim.pending_start": { cmd: "start", config: { trace_profile: "standard" } },
  });
  const output = runFunction("fn-start-validate", {
    payload: { cmd: "start", config: { trace_profile: "standard", model_profile: "deployment-current" } },
  }, { global }).result;
  assert.ok(output[0].filename.endsWith("/live_plc_trace/payloads.jsonl"));
  assert.equal(global.get("sim.pending_start"), null);
});
