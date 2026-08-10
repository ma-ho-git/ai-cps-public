"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const reporting = require("../lib/reporting");
const {
  DEFAULT_BASE_RUNTIME_MS,
  MODULES,
  VirtualFactory,
  normalizeBaseRuntimeMs,
  normalizeRunConfig,
} = require("../lib/virtual_factory");

const ROOT = path.resolve(__dirname, "..");
const topics = JSON.parse(fs.readFileSync(path.join(ROOT, "config/topics.json"), "utf8"));

test("virtual factory releases a state only after all four module commands complete", () => {
  let now = 1000;
  const factory = new VirtualFactory({
    topics,
    payloads: [{ request_id: "p1" }, { request_id: "p2" }],
    baseRuntimeMs: { vgr: 100, hbw: 100, mpo: 100, sld: 100 },
    now: () => now,
  });
  factory.runtimeMs = () => 100;
  const waiting = factory.handleControl({ cmd: "start" });
  assert.equal(waiting[0].payload.state, "waiting_for_orchestration");
  const bootstrap = factory.handleOrchestrationStatus({ state: "ready" });
  assert.equal(bootstrap.filter((item) => item.role?.endsWith("_command")).length, 4);

  for (const topic of ["ai/vgr/cmd0", "ai/hbw/cmd000", "ai/mpo/cmd0"]) {
    factory.handleCommand(topic);
  }
  now += 1000;
  assert.equal(factory.tick(now).filter((item) => item.role === "live_state").length, 0);
  factory.handleCommand("ai/sld/cmd0");
  assert.equal(factory.tick(now + 99).filter((item) => item.role === "live_state").length, 0);
  const released = factory.tick(now + 100);
  const liveState = released.find((item) => item.role === "live_state");
  assert.ok(liveState);
  assert.equal(liveState.payload.request_id, "p1");
  assert.equal(liveState.payload.simulation_run_id, "1000-1");
  assert.equal(liveState.payload.correlation_id, "1000-1");
  assert.deepEqual(liveState.payload.module_runtime_ms, { vgr: 100, hbw: 100, mpo: 100, sld: 100 });
  assert.deepEqual(liveState.payload.module_job_counts.sent, { vgr: 1, hbw: 1, mpo: 1, sld: 1 });
  assert.deepEqual(liveState.payload.module_job_counts.accepted, { vgr: 1, hbw: 1, mpo: 1, sld: 1 });
});

test("restarting the same trace creates a fresh correlation scope", () => {
  const factory = new VirtualFactory({
    topics,
    payloads: [{ request_id: "same-trace-request" }],
    now: () => 1000,
  });
  factory.orchestrationReady = true;

  const first = factory.handleControl({ cmd: "start" })
    .find((item) => item.role === "factory_status").payload.run_id;
  factory.handleControl({ cmd: "reset" });
  const second = factory.handleControl({ cmd: "start" })
    .find((item) => item.role === "factory_status").payload.run_id;

  assert.equal(first, "1000-1");
  assert.equal(second, "1000-2");
  assert.notEqual(first, second);
});

test("virtual modules finish independently before the semaphore releases the state", () => {
  let now = 1000;
  const runtimes = [500, 700, 900, 1100];
  const factory = new VirtualFactory({
    topics,
    payloads: [{ request_id: "p1" }],
    now: () => now,
  });
  factory.runtimeMs = () => runtimes.shift();
  factory.handleControl({ cmd: "start" });
  factory.handleOrchestrationStatus({ state: "ready" });
  for (const topic of ["ai/vgr/cmd101", "ai/hbw/cmd111", "ai/mpo/cmd0", "ai/sld/cmd0"]) {
    factory.handleCommand(topic);
  }

  now = 1500;
  const firstCompletion = factory.tick(now);
  assert.equal(firstCompletion[0].payload.state, "modules_completed");
  assert.deepEqual(firstCompletion[0].payload.modules, ["vgr"]);
  assert.equal(firstCompletion.some((item) => item.role === "live_state"), false);

  now = 2100;
  const released = factory.tick(now);
  assert.equal(released.some((item) => item.role === "live_state"), true);
  assert.deepEqual(factory.sentCounts, factory.acceptedCounts);
});

test("virtual factory defaults every module base runtime to 100 ms", () => {
  const factory = new VirtualFactory({ topics, payloads: [] });

  assert.equal(DEFAULT_BASE_RUNTIME_MS, 100);
  assert.deepEqual(
    factory.baseRuntimeMs,
    Object.fromEntries(MODULES.map((module) => [module, 100])),
  );
});

test("runtime variation stays within minus/plus 50 percent", () => {
  const factory = new VirtualFactory({ topics, payloads: [] });

  factory.random.next = () => 0;
  assert.equal(factory.runtimeMs("vgr"), 50);
  factory.random.next = () => 0.5;
  assert.equal(factory.runtimeMs("vgr"), 100);
  factory.random.next = () => 1 - Number.EPSILON;
  assert.equal(factory.runtimeMs("vgr"), 150);
});

test("module-specific base runtimes are applied independently", () => {
  const factory = new VirtualFactory({
    topics,
    payloads: [],
    baseRuntimeMs: { vgr: 100, hbw: 200, mpo: 300, sld: 400 },
  });
  factory.random.next = () => 0.5;

  assert.deepEqual(
    Object.fromEntries(MODULES.map((module) => [module, factory.runtimeMs(module)])),
    { vgr: 100, hbw: 200, mpo: 300, sld: 400 },
  );
});

test("same seed and command order produce identical module runtimes", () => {
  const createFactory = () => new VirtualFactory({
    topics,
    payloads: [],
    seed: 1234,
    baseRuntimeMs: { vgr: 80, hbw: 100, mpo: 120, sld: 140 },
  });
  const first = createFactory();
  const second = createFactory();
  const commandTopics = ["ai/vgr/cmd101", "ai/hbw/cmd111", "ai/mpo/cmd0", "ai/sld/cmd0"];

  first.running = true;
  second.running = true;
  for (const topic of commandTopics) {
    first.handleCommand(topic);
    second.handleCommand(topic);
  }

  assert.deepEqual(first.moduleRuntimeMs, second.moduleRuntimeMs);
});

test("invalid module base runtimes are rejected", () => {
  for (const invalid of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, "invalid"]) {
    assert.throws(
      () => normalizeBaseRuntimeMs({ vgr: invalid }),
      /positive finite integer/,
    );
  }
});

test("start accepts an atomic dashboard run configuration", () => {
  const factory = new VirtualFactory({
    topics,
    payloads: [{ request_id: "default" }],
    payloadCatalog: {
      standard: [{ request_id: "standard" }],
      "full-storage-attempt": [{ request_id: "guard-1" }, { request_id: "guard-2" }],
    },
    traceProfile: "standard",
  });
  factory.orchestrationReady = true;

  const actions = factory.handleControl({
    cmd: "start",
    config: {
      trace_profile: "full-storage-attempt",
      seed: 123,
      base_runtime_ms: { vgr: 200, hbw: 300, mpo: 400, sld: 500 },
    },
  });

  const status = actions.find((action) => action.role === "factory_status");
  assert.equal(status.payload.state, "bootstrap_commands_published");
  assert.equal(status.payload.trace_profile, "full-storage-attempt");
  assert.equal(status.payload.trace_total, 2);
  assert.equal(status.payload.seed, 123);
  assert.deepEqual(status.payload.base_runtime_ms, { vgr: 200, hbw: 300, mpo: 400, sld: 500 });
});

test("bare start keeps the environment-compatible default configuration", () => {
  const factory = new VirtualFactory({
    topics,
    payloads: [{ request_id: "default" }],
    traceProfile: "standard",
    seed: 77,
    baseRuntimeMs: { vgr: 110, hbw: 120, mpo: 130, sld: 140 },
  });
  factory.orchestrationReady = true;

  const status = factory.handleControl({ cmd: "start" })
    .find((action) => action.role === "factory_status").payload;

  assert.equal(status.trace_profile, "standard");
  assert.equal(status.seed, 77);
  assert.deepEqual(status.base_runtime_ms, { vgr: 110, hbw: 120, mpo: 130, sld: 140 });
});

test("invalid or active dashboard configuration is rejected without changing a run", () => {
  const factory = new VirtualFactory({
    topics,
    payloads: [{ request_id: "default" }],
    payloadCatalog: { standard: [{ request_id: "standard" }] },
  });

  const invalid = factory.handleControl({
    cmd: "start",
    config: {
      trace_profile: "unknown",
      seed: 42,
      base_runtime_ms: { vgr: 100, hbw: 100, mpo: 100, sld: 100 },
    },
  });
  assert.equal(invalid[0].payload.state, "configuration_rejected");
  assert.match(invalid[0].payload.detail, /trace profile/);
  assert.equal(factory.startRequested, false);

  factory.orchestrationReady = true;
  factory.handleControl({ cmd: "start" });
  const active = factory.handleControl({ cmd: "start" });
  assert.equal(active[0].payload.state, "start_rejected");
  assert.equal(active[0].payload.detail, "factory_already_running");
});

test("dashboard run config validates seed and HMI runtime bounds", () => {
  const catalog = { standard: [] };
  assert.deepEqual(
    normalizeRunConfig({
      trace_profile: "standard",
      seed: 0,
      base_runtime_ms: { vgr: 50, hbw: 100, mpo: 1000, sld: 60000 },
    }, { payloadCatalog: catalog }),
    {
      trace_profile: "standard",
      seed: 0,
      base_runtime_ms: { vgr: 50, hbw: 100, mpo: 1000, sld: 60000 },
    },
  );
  for (const seed of [-1, 1.5, 0x100000000, "invalid"]) {
    assert.throws(
      () => normalizeRunConfig({ trace_profile: "standard", seed }, { payloadCatalog: catalog }),
      /seed/,
    );
  }
  for (const runtime of [49, 60001]) {
    assert.throws(
      () => normalizeRunConfig({
        trace_profile: "standard",
        base_runtime_ms: { vgr: runtime, hbw: 100, mpo: 100, sld: 100 },
      }, { payloadCatalog: catalog }),
      /between 50 and 60000/,
    );
  }
});

test("reporting preserves the established filenames and key summary columns", () => {
  const state = reporting.createReportState("/reports/orchestration_simulation", 0);
  const recorded = reporting.recordCycle(state, {
    status: "completed",
    cycle_id: "c1",
    request_id: "r1",
    source_id: "s1",
    empty_storage: 1,
    vgr_cmd: 101,
    hbw_cmd: 111,
    model_predictions: {
      storage: { empty_storage: 1, top3: [{ empty_storage: 1, p: 0.999 }] },
      vgr: { cmd: 101, top3: [{ cmd: 101, p: 0.998 }] },
      hbw: { cmd: 111, top3: [{ cmd: 111, p: 0.997 }] },
    },
    model_ids: { storage: "storage:a", vgr: "vgr:a", hbw: "hbw:a" },
    model_contracts: { storage: { model_id: "storage:a" } },
    command_output_enabled: true,
    command_set_complete: true,
    commands: {
      vgr: { cmd: 101, topic: "ai/vgr/cmd101", publisher: "model_service", published: true },
      hbw: { cmd: 111, topic: "ai/hbw/cmd111", publisher: "model_service", published: true },
      mpo: { cmd: 0, topic: "ai/mpo/cmd0", publisher: "ai_flow", published: true },
      sld: { cmd: 0, topic: "ai/sld/cmd0", publisher: "ai_flow", published: true },
    },
    bootstrap: { vgr: { seeded_rows: 9 }, hbw: { seeded_rows: 9 } },
    input_metadata: {
      phase: "live_state",
      trace_profile: "standard",
      factory_seed: 42,
      factory_base_runtime_ms: { vgr: 100, hbw: 100, mpo: 100, sld: 100 },
      expected_empty_storage: 1,
      expected_label_VGR: 101,
      expected_label_HBW: 111,
      guard_episode_idx: 2,
      guard_process_step_idx: 3,
      guard_source_episode_id: "source-episode",
      module_runtime_ms: { vgr: 800, hbw: 900, mpo: 600, sld: 700 },
      module_job_counts: {
        sent: { vgr: 1, hbw: 1, mpo: 1, sld: 1 },
        accepted: { vgr: 1, hbw: 1, mpo: 1, sld: 1 },
      },
    },
    qos: 2,
    retain: false,
  }, 1000);

  assert.deepEqual(recorded.files.map((item) => path.basename(item.filename)), [
    "events.jsonl",
    "summary.csv",
    "run_summary.json",
  ]);
  assert.match(recorded.files[1].payload, /predicted_label_VGR/);
  assert.equal(recorded.row.vgr_match, true);
  assert.equal(recorded.row.hbw_match, true);
  assert.equal(recorded.row.storage_model_id, "storage:a");
  assert.equal(recorded.row.module_runtime_hbw_ms, 900);
  assert.equal(recorded.run_summary.model_ids.vgr, "vgr:a");
  assert.equal(recorded.run_summary.control_published_rows, 1);
  assert.equal(recorded.run_summary.control_published_commands, 4);
  assert.equal(recorded.row.control_vgr_publisher, "model_service");
  assert.equal(recorded.row.job_accepted_hbw, 1);
  assert.equal(recorded.row.storage_confidence, 0.999);
  assert.equal(recorded.row.vgr_confidence, 0.998);
  assert.equal(recorded.row.hbw_confidence, 0.997);
  assert.equal(recorded.row.guard_episode_idx, 2);
  assert.equal(recorded.row.guard_process_step_idx, 3);
  assert.equal(recorded.row.guard_source_episode_id, "source-episode");
  assert.equal(recorded.row.trace_profile, "standard");
  assert.equal(recorded.row.factory_seed, 42);
  assert.equal(recorded.run_summary.run_config.base_runtime_ms.vgr, 100);
});

test("reporting does not count a fault as a replacement idle command set", () => {
  const state = reporting.createReportState("/reports/orchestration_simulation", 0);
  const recorded = reporting.recordCycle(state, {
    status: "fault_latched",
    error: "inference_timeout",
    command_output_enabled: true,
    command_set_complete: false,
    idle_set_published: false,
    commands: {
      mpo: { cmd: 0, topic: "ai/mpo/cmd0", publisher: "ai_flow", published: true },
      sld: { cmd: 0, topic: "ai/sld/cmd0", publisher: "ai_flow", published: true },
    },
    qos: 2,
    retain: false,
  }, 1000);

  assert.equal(recorded.row.control_published, false);
  assert.equal(recorded.row.control_reason, "fault_latched");
  assert.equal(recorded.run_summary.control_published_rows, 0);
  assert.equal(recorded.run_summary.control_idle_fallback_rows, 0);
});
