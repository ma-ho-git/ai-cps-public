"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { HmiViewModel, compactCycleId } = require("../lib/hmi");

test("HMI shortens technical cycle IDs without changing their stored value", () => {
  assert.equal(compactCycleId("cycle-source-run-000123"), "#000123");
  assert.equal(compactCycleId("short"), "short");
});

test("HMI combines factory, orchestration and model status without process actions", () => {
  const hmi = new HmiViewModel({ maxCycles: 2, maxErrors: 2 });

  hmi.handle("ft/nn/storage/status", {
    domain: "storage",
    state: "online",
    model_id: "storage:model-a",
  });
  hmi.handle("ft/ai/orchestration/status", {
    state: "ready",
    command_output_enabled: true,
    model_ids: { storage: "storage:model-a", vgr: "vgr:model-a", hbw: "hbw:model-a" },
  });
  const actions = hmi.handle("ft/sim/factory/status", {
    state: "modules_running",
    trace_profile: "standard",
    trace_total: 320,
    payloads_sent: 12,
    module_runtime_ms: { vgr: 75, hbw: 110, mpo: 90, sld: 130 },
    sent_counts: { vgr: 13, hbw: 13, mpo: 13, sld: 13 },
    accepted_counts: { vgr: 12, hbw: 12, mpo: 12, sld: 12 },
  });

  assert.equal(actions.some((action) => action.role === "control"), false);
  const status = actions.find((action) => action.role === "overview").payload;
  assert.equal(status.state, "running");
  assert.equal(status.progress_percent, 3.75);
  assert.equal(status.command_mode, "Commands aktiv");
  assert.equal(status.trace_profile, "standard");
  const modules = actions.find((action) => action.role === "modules").payload;
  assert.equal(modules.length, 4);
  assert.equal(modules[0].module, "VGR");
  assert.equal(modules[0].state, "Laeuft");
});

test("HMI does not imply active commands before orchestration status is known", () => {
  const hmi = new HmiViewModel();

  const actions = hmi.handle("ft/sim/factory/status", { state: "ready" });
  const status = actions.find((action) => action.role === "overview").payload;

  assert.equal(status.command_mode, "Noch nicht bekannt");
});

test("HMI exposes predictions, bounded cycle history and latency series", () => {
  const hmi = new HmiViewModel({ maxCycles: 2, maxErrors: 2 });
  for (let index = 1; index <= 3; index += 1) {
    hmi.handle("ft/ai/orchestration/cycle_result", {
      status: "completed",
      cycle_id: `cycle-${index}`,
      source_id: "source-a",
      empty_storage: 3,
      vgr_cmd: index === 3 ? 101 : 0,
      hbw_cmd: 0,
      model_predictions: {
        storage: { empty_storage: 3, top3: [{ empty_storage: 3, p: 0.99 }] },
        vgr: { cmd: index === 3 ? 101 : 0, top3: [{ cmd: index === 3 ? 101 : 0, p: 0.97 }] },
        hbw: { cmd: 0, top3: [{ cmd: 0, p: 0.96 }] },
      },
      latencies_ms: { storage: index, vgr: index + 1, hbw: index + 2 },
    });
  }

  const snapshot = hmi.snapshot();
  assert.deepEqual(snapshot.cycles.map((row) => row.cycle_id), ["cycle-2", "cycle-3"]);
  assert.deepEqual(snapshot.cycles.map((row) => row.cycle_display), ["cycle-2", "cycle-3"]);
  assert.equal(snapshot.predictions.find((row) => row.model === "VGR").prediction, "cmd 101");
  assert.equal(snapshot.latencies.length, 6);
  assert.equal(snapshot.latencies.at(-1).series, "HBW");
});

test("HMI reset clears stale cycle, prediction and module values", () => {
  const hmi = new HmiViewModel();
  hmi.handle("ft/sim/factory/status", {
    state: "completed",
    trace_profile: "standard",
    trace_total: 320,
    payloads_sent: 320,
    sent_counts: { vgr: 321, hbw: 321, mpo: 321, sld: 321 },
    accepted_counts: { vgr: 321, hbw: 321, mpo: 321, sld: 321 },
  });
  hmi.handle("ft/ai/orchestration/cycle_result", {
    status: "completed",
    cycle_id: "cycle-old",
    model_predictions: { storage: { empty_storage: 3 } },
    latencies_ms: { storage: 12 },
  });

  const actions = hmi.handle("ft/sim/factory/status", {
    state: "reset",
    trace_profile: "standard",
    trace_total: 320,
    payloads_sent: 0,
  });
  const snapshot = hmi.snapshot();

  assert.equal(snapshot.cycles.length, 0);
  assert.equal(snapshot.latencies.length, 0);
  assert.equal(snapshot.predictions[0].prediction, "-");
  assert.equal(actions.find((action) => action.role === "modules").payload[0].sent_count, 0);
});

test("HMI maps faults to concise persistent diagnostics and deduplicates them", () => {
  const hmi = new HmiViewModel({ maxCycles: 3, maxErrors: 3 });
  const fault = {
    state: "fault_latched",
    error: "inference_timeout",
    cycle_id: "cycle-7",
    detail: "vgr response missing",
  };

  hmi.handle("ft/ai/orchestration/status", fault);
  hmi.handle("ft/ai/orchestration/status", fault);
  const snapshot = hmi.snapshot();

  assert.equal(snapshot.overview.state, "fault");
  assert.equal(snapshot.errors.length, 1);
  assert.equal(snapshot.errors[0].code, "inference_timeout");
  assert.equal(snapshot.errors[0].count, 2);
  assert.match(snapshot.errors[0].recommendation, /Reset/);
  assert.equal(snapshot.notification.level, "error");
});

test("HMI classifies model-offline and response faults for operators", () => {
  const offline = new HmiViewModel();
  offline.handle("ft/nn/storage/status", { state: "offline" });
  offline.recordError({ code: "model_offline:storage", detail: "follow-up" });
  assert.equal(offline.snapshot().errors[0].title, "NN-Dienst offline");
  assert.equal(offline.snapshot().errors[0].count, 2);
  assert.equal(offline.snapshot().errors.length, 1);

  const response = new HmiViewModel();
  response.handle("ft/ai/orchestration/status", {
    state: "fault_latched",
    detail: "additional_fault_ignored",
    fault: { reason: "storage_response:storage response without pending cycle" },
  });
  const error = response.snapshot().errors[0];
  assert.equal(error.title, "NN-Antwort konnte nicht verarbeitet werden");
  assert.match(error.detail, /storage response/);
});

test("HMI tolerates malformed MQTT payloads as an observable warning", () => {
  const hmi = new HmiViewModel();
  const actions = hmi.handle("ft/sim/factory/status", "{invalid-json");
  const error = actions.find((action) => action.role === "errors").payload.at(-1);

  assert.equal(error.code, "invalid_json");
  assert.equal(error.severity, "warning");
});
