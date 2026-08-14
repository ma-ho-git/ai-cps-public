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

test("flow contains exactly the four documented Function exceptions", () => {
  const functions = flows.filter((node) => node.type === "function");
  assert.deepEqual(
    new Set(functions.map((node) => node.id)),
    new Set(["fn-module-runtime", "fn-semaphore", "fn-contract-gate", "fn-lstm-window"]),
  );
  for (const node of functions) {
    for (const heading of ["### Aufgabe", "### Eingang", "### Zustand", "### Ausgang", "### Warum Function-Node?"]) {
      assert.match(node.info, new RegExp(heading.replace("?", "\\?")));
    }
  }
});

test("deterministic runtime stays module-specific and within plus/minus 50 percent", () => {
  const input = { _module: "vgr", _seed: 42, _job: 1, _base_runtime_ms: 100 };
  const first = runFunction("fn-module-runtime", { ...input }).result;
  const second = runFunction("fn-module-runtime", { ...input }).result;
  assert.equal(first.delay, second.delay);
  assert.ok(first.delay >= 50 && first.delay <= 150);
  const hbw = runFunction("fn-module-runtime", { ...input, _module: "hbw" }).result;
  assert.notEqual(first.delay, hbw.delay);
});

test("semaphore releases once, blocks stale raw states, and completes after final commands", () => {
  const global = memory({ "sim.run": baseRun(2) });
  const raw = (index) => ({ payload: { simulation_run_id: "run-1", trace_index: index } });

  let output = runFunction("fn-semaphore", raw(0), { global }).result;
  assert.equal(output[0]._semaphore.action, "release");
  assert.equal(global.get("sim.run").trace_index, 1);
  assert.equal(runFunction("fn-semaphore", raw(1), { global }).result, null);

  const second = global.get("sim.run");
  second.sent = { vgr: 2, hbw: 2, mpo: 2, sld: 2 };
  second.accepted = { vgr: 2, hbw: 2, mpo: 2, sld: 2 };
  global.set("sim.run", second);
  output = runFunction("fn-semaphore", raw(1), { global }).result;
  assert.equal(output[0]._semaphore.release_index, 1);

  const finalRun = global.get("sim.run");
  finalRun.sent = { vgr: 3, hbw: 3, mpo: 3, sld: 3 };
  finalRun.accepted = { vgr: 3, hbw: 3, mpo: 3, sld: 3 };
  global.set("sim.run", finalRun);
  output = runFunction("fn-semaphore", raw(1), { global }).result;
  assert.equal(output[1]._semaphore.action, "completed");
  assert.equal(global.get("sim.run").completed, true);
});

test("semaphore emits a compact fault decision after its watchdog", () => {
  const run = baseRun(1);
  run.sent.hbw = 0;
  run.accepted.hbw = 0;
  run.command_deadline_ms = Date.now() - 1;
  const output = runFunction("fn-semaphore", {
    payload: { simulation_run_id: "run-1", trace_index: 0 },
  }, { global: memory({ "sim.run": run }) }).result;
  assert.equal(output[2]._semaphore.action, "fault");
  assert.equal(output[2]._semaphore.sent.hbw, 0);
});

test("virtual contract gate accepts current contracts and rejects a missing feature", () => {
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
  const contracts = {
    storage: service("storage", ["slot"]),
    vgr: service("vgr", ["slot", "empty_storage_0"]),
    hbw: service("hbw", ["slot", "empty_storage_0"]),
  };
  const statuses = {
    storage: { state: "online" }, vgr: { state: "online" }, hbw: { state: "online" },
  };
  const global = memory({ "ai.contracts": contracts, "ai.statuses": statuses });
  let output = runFunction("fn-contract-gate", { payload: { slot: 1 } }, { global }).result;
  assert.equal(output[0]._profile, "deployment-current");

  contracts.vgr.feature_cols = ["missing", "empty_storage_0"];
  output = runFunction("fn-contract-gate", { payload: { slot: 1 } }, { global }).result;
  assert.equal(output[1].payload.code, "invalid_payload");
  assert.match(output[1].payload.detail, /missing/);
});

test("LSTM window performs nine-row bootstrap and then rolls by model and source", () => {
  const features = ["IX_SSC_LightBarrierStorage_I3", "empty_storage_0"];
  const pending = {
    source_id: "source-1",
    raw_state: { IX_SSC_LightBarrierStorage_I3: 0 },
    one_hot: { empty_storage_0: 1 },
    contracts: { vgr: { model_id: "vgr:1", time_steps: 10, feature_cols: features } },
  };
  const global = memory({ "ai.pending": pending, "ai.windows": { vgr: {}, hbw: {} } });
  let output = runFunction("fn-lstm-window", { _domain: "vgr" }, { global }).result;
  assert.equal(output._bootstrap.seeded_rows, 9);
  assert.equal(output._window.length, 10);
  assert.deepEqual(output._window.at(-1), [0, 1]);

  pending.raw_state.IX_SSC_LightBarrierStorage_I3 = 1;
  global.set("ai.pending", pending);
  output = runFunction("fn-lstm-window", { _domain: "vgr" }, { global }).result;
  assert.equal(output._bootstrap.seeded_rows, 0);
  assert.equal(output._window.length, 10);
  assert.deepEqual(output._window.at(-1), [1, 1]);
});

test("module and window behavior is represented by documented subflows", () => {
  assert.equal(nodes["sub-module-delay"].type, "delay");
  assert.equal(nodes["sub-module-delay"].pauseType, "delayv");
  assert.equal(nodes["sub-module-active"].type, "switch");
  assert.equal(nodes["sub-module-accept"].type, "change");
  assert.equal(nodes["sub-response-contract"].type, "switch");
  assert.equal(nodes["trigger-ai-timeout"].type, "trigger");
  assert.equal(flows.filter((node) => node.type === "subflow:subflow-virtual-module").length, 4);
  assert.equal(flows.filter((node) => node.type === "subflow:subflow-lstm-window").length, 2);
});
