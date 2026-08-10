"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { createRuntime } = require("../lib/orchestration");

const ROOT = path.resolve(__dirname, "..");
const topics = JSON.parse(fs.readFileSync(path.join(ROOT, "config/topics.json"), "utf8"));

const processFeatures = [
  "IX_VGR_RefSwitchVerticalAxis_I1",
  "IX_VGR_RefSwitchHorizontalAxis_I2",
  "IX_VGR_RefSwitchRotate_I3",
  "QX_VGR_M2_HorizontalAxisBackward_Q3",
  "QX_VGR_M2_HorizontalAxisForward_Q4",
  "QX_VGR_Compressor_Q7",
  "QX_VGR_ValveVacuum_Q8",
  "VGR_vertical_position",
  "VGR_horizontal_position",
  "VGR_rotate_position",
  "IX_HBW_RefSwitchHorizontalAxis_I1",
  "IX_HBW_LightBarrierInside_I2",
  "IX_HBW_LightBarrierOutside_I3",
  "IX_HBW_RefSwitchVerticalAxis_I4",
  "IX_HBW_SwitchCantileverFront_I5",
  "IX_HBW_SwitchCantileverBack_I6",
  "HBW_vertical_position",
  "HBW_horizontal_position",
  "IX_SSC_LightBarrierStorage_I3",
];
const storageFeatures = Array.from({ length: 9 }, (_, index) => `storage_slot_${index + 1}_occupied`);
const oneHot = Array.from({ length: 10 }, (_, index) => `empty_storage_${index}`);

function contract(domain, commandOutputEnabled = true) {
  const isStorage = domain === "storage";
  const value = {
    schema_version: "1.0",
    domain,
    model_id: `${domain}:model-a`,
    model_sha256: "a".repeat(64),
    input_shape: isStorage ? [9] : [10, 29],
    time_steps: isStorage ? null : 10,
    feature_cols: isStorage ? storageFeatures : [...processFeatures, ...oneHot],
    class_ids: isStorage ? Array.from({ length: 10 }, (_, index) => index) : domain === "vgr" ? [0, 101] : [0, 111],
    request_topic: topics.model_topics[domain].request,
    response_topic: topics.model_topics[domain].response,
  };
  if (!isStorage) {
    value.command_output = {
      mode: "direct_mqtt",
      enabled: commandOutputEnabled,
      payload: "empty",
      qos: 2,
      retain: false,
      topics: topics.command_topics[domain],
    };
  }
  return value;
}

function livePayload(requestId = "live-1", sourceId = "factory-a") {
  return {
    request_id: requestId,
    source_id: sourceId,
    ...Object.fromEntries(processFeatures.map((feature) => [feature, feature.includes("RefSwitch") ? 1 : 0])),
    ...Object.fromEntries(storageFeatures.map((feature, index) => [feature, index === 0 ? 0 : 1])),
    extra_plc_field: "allowed",
    expected_empty_storage: 1,
    expected_label_VGR: 101,
    expected_label_HBW: 111,
  };
}

function readyRuntime({ commandOutputEnabled = true, now = () => 1000 } = {}) {
  const idleRow = Object.fromEntries(processFeatures.map((feature) => [feature, feature.includes("RefSwitch") ? 1 : 0]));
  const runtime = createRuntime({
    topics,
    idleSeedTemplates: { schema_version: "1.0", rows: Array.from({ length: 9 }, () => ({ ...idleRow })) },
    commandOutputEnabled,
    now,
  });
  for (const domain of ["storage", "vgr", "hbw"]) {
    runtime.handleEvent("contract", contract(domain, commandOutputEnabled), domain);
    runtime.handleEvent("status", { domain, state: "online", model_id: `${domain}:model-a` }, domain);
  }
  assert.equal(runtime.isReady(), true);
  return runtime;
}

function modelResponse(domain, requestAction, cmd, commandOutputEnabled = true) {
  return {
    cycle_id: requestAction.payload.cycle_id,
    request_id: requestAction.payload.request_id,
    cmd,
    command_output: {
      enabled: commandOutputEnabled,
      published: commandOutputEnabled,
      reason: commandOutputEnabled ? "published" : "disabled",
      topic: topics.command_topics[domain][String(cmd)],
      qos: 2,
      retain: false,
      mid: commandOutputEnabled ? 7 : null,
    },
  };
}

function action(actions, role) {
  return actions.find((item) => item.role === role);
}

test("first live state creates one storage call and two complete seeded LSTM windows", () => {
  const runtime = readyRuntime();
  const storageActions = runtime.handleEvent("live_state", livePayload());
  const storageRequest = action(storageActions, "storage_request");
  assert.ok(storageRequest);
  assert.equal(storageRequest.topic, "ft/nn/storage/request");
  assert.equal(Object.keys(storageRequest.payload.features).length, 9);

  const cycleId = storageRequest.payload.cycle_id;
  const modelActions = runtime.handleEvent("storage_response", {
    cycle_id: cycleId,
    request_id: storageRequest.payload.request_id,
    source_id: "factory-a",
    empty_storage: 1,
  });
  assert.deepEqual(modelActions.map((item) => item.role).sort(), [
    "hbw_request",
    "mpo_command",
    "sld_command",
    "vgr_request",
  ]);
  for (const modelAction of modelActions.filter((item) => item.role.endsWith("_request"))) {
    assert.equal(modelAction.payload.sequence.length, 10);
    assert.equal(modelAction.payload.sequence[0].length, 29);
    assert.equal(modelAction.payload.sequence[0][20], 1);
    assert.equal(modelAction.payload.sequence[0][19], 0);
  }

  const vgr = action(modelActions, "vgr_request");
  const hbw = action(modelActions, "hbw_request");
  assert.deepEqual(runtime.handleEvent("vgr_response", modelResponse("vgr", vgr, 101)), []);
  const completed = runtime.handleEvent("hbw_response", modelResponse("hbw", hbw, 111));
  const commands = completed.filter((item) => item.role.endsWith("_command"));
  assert.equal(commands.length, 0);
  const result = action(completed, "cycle_result").payload;
  assert.equal(result.commands.vgr.publisher, "model_service");
  assert.equal(result.commands.hbw.publisher, "model_service");
  assert.equal(result.commands.mpo.publisher, "ai_flow");
  assert.equal(result.command_set_complete, true);
  assert.equal(result.bootstrap.vgr.seeded_rows, 9);
  assert.equal(result.bootstrap.hbw.seeded_rows, 9);
});

test("virtual run correlation keeps repeated trace requests unique across flow restarts", () => {
  const firstPayload = { ...livePayload("same-request", "factory-a"), correlation_id: "run-1:same-request" };
  const secondPayload = { ...livePayload("same-request", "factory-a"), correlation_id: "run-2:same-request" };

  const firstRequest = action(readyRuntime().handleEvent("live_state", firstPayload), "storage_request");
  const secondRequest = action(readyRuntime().handleEvent("live_state", secondPayload), "storage_request");

  assert.notEqual(firstRequest.payload.cycle_id, secondRequest.payload.cycle_id);
  assert.notEqual(firstRequest.payload.request_id, secondRequest.payload.request_id);
  assert.equal(firstRequest.payload.parent_request_id, "same-request");
  assert.equal(secondRequest.payload.parent_request_id, "same-request");
});

test("one startup live state waits for model readiness and then starts exactly one cycle", () => {
  const idleRow = Object.fromEntries(processFeatures.map((feature) => [feature, feature.includes("RefSwitch") ? 1 : 0]));
  const runtime = createRuntime({
    topics,
    idleSeedTemplates: { schema_version: "1.0", rows: Array.from({ length: 9 }, () => ({ ...idleRow })) },
    commandOutputEnabled: true,
    now: () => 1000,
  });

  const queued = runtime.handleEvent("live_state", livePayload("startup-live"));
  assert.equal(action(queued, "orchestration_status").payload.detail, "startup_live_state_queued");
  assert.equal(action(queued, "storage_request"), undefined);

  let finalRegistration = [];
  for (const domain of ["storage", "vgr", "hbw"]) {
    runtime.handleEvent("contract", contract(domain), domain);
    finalRegistration = runtime.handleEvent(
      "status",
      { domain, state: "online", model_id: `${domain}:model-a` },
      domain,
    );
  }

  assert.equal(runtime.isReady(), true);
  assert.ok(action(finalRegistration, "storage_request"));
  assert.equal(finalRegistration.filter((item) => item.role === "storage_request").length, 1);
  assert.equal(runtime.queuedLiveState, null);
});

test("stale retained pre-migration contract waits for the fresh service contract", () => {
  const idleRow = Object.fromEntries(processFeatures.map((feature) => [feature, 0]));
  const runtime = createRuntime({
    topics,
    idleSeedTemplates: { schema_version: "1.0", rows: Array.from({ length: 9 }, () => ({ ...idleRow })) },
    commandOutputEnabled: true,
    now: () => 1000,
  });
  const stale = contract("vgr");
  delete stale.command_output;

  const waiting = runtime.handleEvent("contract", stale, "vgr");

  assert.equal(runtime.fault, null);
  assert.equal(action(waiting, "orchestration_status").payload.state, "waiting_for_models");
  assert.equal(runtime.contracts.vgr, undefined);
  runtime.handleEvent("contract", contract("vgr"), "vgr");
  assert.equal(runtime.contracts.vgr.model_id, "vgr:model-a");
});

test("second state for the same source reuses the rolling windows without reseeding", () => {
  const runtime = readyRuntime();

  function runCycle(requestId) {
    const storageRequest = action(runtime.handleEvent("live_state", livePayload(requestId)), "storage_request");
    const models = runtime.handleEvent("storage_response", {
      cycle_id: storageRequest.payload.cycle_id,
      request_id: storageRequest.payload.request_id,
      empty_storage: 1,
    });
    const vgr = action(models, "vgr_request");
    const hbw = action(models, "hbw_request");
    runtime.handleEvent("vgr_response", modelResponse("vgr", vgr, 101));
    return runtime.handleEvent("hbw_response", modelResponse("hbw", hbw, 111));
  }

  assert.equal(action(runCycle("live-1"), "cycle_result").payload.bootstrap.vgr.seeded_rows, 9);
  assert.equal(action(runCycle("live-2"), "cycle_result").payload.bootstrap.vgr.seeded_rows, 0);
});

test("duplicate QoS 1 model responses are idempotent and never start duplicate requests", () => {
  const runtime = readyRuntime();
  const storageRequest = action(runtime.handleEvent("live_state", livePayload()), "storage_request");
  const storageResponse = {
    cycle_id: storageRequest.payload.cycle_id,
    request_id: storageRequest.payload.request_id,
    empty_storage: 1,
  };
  const models = runtime.handleEvent("storage_response", storageResponse);
  assert.deepEqual(runtime.handleEvent("storage_response", storageResponse), []);

  const vgr = action(models, "vgr_request");
  const hbw = action(models, "hbw_request");
  const vgrResponse = modelResponse("vgr", vgr, 101);
  const hbwResponse = modelResponse("hbw", hbw, 111);
  assert.deepEqual(runtime.handleEvent("vgr_response", vgrResponse), []);
  const completed = runtime.handleEvent("hbw_response", hbwResponse);
  assert.equal(action(completed, "cycle_result").payload.status, "completed");

  assert.deepEqual(runtime.handleEvent("vgr_response", vgrResponse), []);
  assert.deepEqual(runtime.handleEvent("hbw_response", hbwResponse), []);
  assert.equal(runtime.fault, null);
});

test("full storage remains a normal LSTM input and can publish four idle commands", () => {
  const runtime = readyRuntime();
  const storageRequest = action(runtime.handleEvent("live_state", livePayload()), "storage_request");
  const models = runtime.handleEvent("storage_response", {
    cycle_id: storageRequest.payload.cycle_id,
    request_id: storageRequest.payload.request_id,
    empty_storage: 0,
  });
  const vgr = action(models, "vgr_request");
  const hbw = action(models, "hbw_request");
  assert.equal(vgr.payload.sequence[0][19], 1);
  runtime.handleEvent("vgr_response", modelResponse("vgr", vgr, 0));
  const completed = runtime.handleEvent("hbw_response", modelResponse("hbw", hbw, 0));
  assert.equal(completed.filter((item) => item.role.endsWith("_command")).length, 0);
  assert.equal(action(completed, "cycle_result").payload.commands.vgr.topic, "ai/vgr/cmd0");
  assert.equal(action(completed, "cycle_result").payload.commands.hbw.topic, "ai/hbw/cmd000");
  assert.equal(action(completed, "cycle_result").payload.status, "completed");
});

test("inference error latches immediately without publishing a replacement idle set", () => {
  const runtime = readyRuntime();
  const storageRequest = action(runtime.handleEvent("live_state", livePayload()), "storage_request");
  const fault = runtime.handleEvent("storage_response", {
    cycle_id: storageRequest.payload.cycle_id,
    request_id: storageRequest.payload.request_id,
    error: "model failed",
  });
  assert.equal(fault.filter((item) => item.role.endsWith("_command")).length, 0);
  const faultResult = action(fault, "cycle_result").payload;
  assert.equal(faultResult.status, "fault_latched");
  assert.equal(faultResult.idle_set_published, false);
  assert.deepEqual(faultResult.commands, {});
  assert.equal(faultResult.qos, 2);
  assert.equal(faultResult.retain, false);

  const ignored = runtime.handleEvent("live_state", livePayload("live-2"));
  assert.equal(ignored.filter((item) => item.role.endsWith("_command")).length, 0);
  assert.equal(action(ignored, "orchestration_status").payload.state, "fault_latched");

  runtime.handleEvent("control", { cmd: "reset" });
  assert.equal(runtime.isReady(), true);
  assert.ok(action(runtime.handleEvent("live_state", livePayload("live-3")), "storage_request"));
});

test("partial LSTM failure preserves already issued commands and adds no replacement", () => {
  const runtime = readyRuntime();
  const storageRequest = action(runtime.handleEvent("live_state", livePayload()), "storage_request");
  const models = runtime.handleEvent("storage_response", {
    cycle_id: storageRequest.payload.cycle_id,
    request_id: storageRequest.payload.request_id,
    empty_storage: 1,
  });
  const vgr = action(models, "vgr_request");
  const hbw = action(models, "hbw_request");

  runtime.handleEvent("vgr_response", modelResponse("vgr", vgr, 101));
  const fault = runtime.handleEvent("hbw_response", {
    cycle_id: hbw.payload.cycle_id,
    request_id: hbw.payload.request_id,
    error: "hbw failed",
  });

  assert.equal(fault.filter((item) => item.role.endsWith("_command")).length, 0);
  const result = action(fault, "cycle_result").payload;
  assert.deepEqual(Object.keys(result.commands).sort(), ["mpo", "sld", "vgr"]);
  assert.equal(result.commands.vgr.topic, "ai/vgr/cmd101");
  assert.equal(result.command_set_complete, false);
  assert.equal(runtime.fault.reason.includes("hbw inference error"), true);
});

test("diagnosis mode never publishes physical command topics", () => {
  const runtime = readyRuntime({ commandOutputEnabled: false });
  const storageRequest = action(runtime.handleEvent("live_state", livePayload()), "storage_request");
  const models = runtime.handleEvent("storage_response", {
    cycle_id: storageRequest.payload.cycle_id,
    request_id: storageRequest.payload.request_id,
    empty_storage: 1,
  });
  const vgr = action(models, "vgr_request");
  const hbw = action(models, "hbw_request");
  runtime.handleEvent("vgr_response", modelResponse("vgr", vgr, 101, false));
  const completed = runtime.handleEvent("hbw_response", modelResponse("hbw", hbw, 111, false));
  assert.equal(completed.filter((item) => item.role.endsWith("_command")).length, 0);
  assert.equal(action(completed, "cycle_result").payload.command_output_enabled, false);
});

test("command output mode can only change through a coordinated stack restart", () => {
  const runtime = readyRuntime({ commandOutputEnabled: false });

  const status = action(
    runtime.handleEvent("control", { cmd: "command_output", enabled: true }),
    "orchestration_status",
  );

  assert.equal(status.payload.detail, "command_output_restart_required");
  assert.equal(runtime.commandOutputEnabled, false);
});

test("timeout latches without adding commands to the incomplete semaphore cycle", () => {
  let now = 1000;
  const runtime = readyRuntime({ now: () => now });
  runtime.handleEvent("live_state", livePayload());
  now += topics.request_timeout_ms + 1;
  const fault = runtime.tick(now);
  assert.equal(fault.filter((item) => item.role.endsWith("_command")).length, 0);
  assert.equal(action(fault, "cycle_result").payload.error, "inference_timeout");
  assert.equal(runtime.fault.reason, "inference_timeout");
});

test("a model change requires matching online status and an offline model latches the runtime", () => {
  const runtime = readyRuntime();
  const changedContract = { ...contract("vgr"), model_id: "vgr:model-b", model_sha256: "b".repeat(64) };

  const waiting = runtime.handleEvent("contract", changedContract, "vgr");
  assert.equal(runtime.isReady(), false);
  assert.equal(action(waiting, "orchestration_status").payload.state, "waiting_for_models");

  runtime.handleEvent("status", { domain: "vgr", state: "online", model_id: "vgr:model-a" }, "vgr");
  assert.equal(runtime.isReady(), false);

  const ready = runtime.handleEvent("status", { domain: "vgr", state: "online", model_id: "vgr:model-b" }, "vgr");
  assert.equal(runtime.isReady(), true);
  assert.equal(action(ready, "orchestration_status").payload.state, "ready");

  const fault = runtime.handleEvent("status", { domain: "vgr", state: "offline", model_id: "vgr:model-b" }, "vgr");
  assert.equal(runtime.isReady(), false);
  assert.equal(runtime.fault.reason, "model_offline:vgr");
  assert.equal(fault.filter((item) => item.role.endsWith("_command")).length, 0);
  assert.equal(action(fault, "cycle_result").payload.status, "fault_latched");
});

test("multiple startup states before model readiness latch instead of overwriting the first state", () => {
  const idleRow = Object.fromEntries(processFeatures.map((feature) => [feature, feature.includes("RefSwitch") ? 1 : 0]));
  const runtime = createRuntime({
    topics,
    idleSeedTemplates: { schema_version: "1.0", rows: Array.from({ length: 9 }, () => ({ ...idleRow })) },
    commandOutputEnabled: true,
    now: () => 1000,
  });

  runtime.handleEvent("live_state", livePayload("startup-live-1"));
  const fault = runtime.handleEvent("live_state", livePayload("startup-live-2"));

  assert.equal(runtime.fault.reason, "multiple_live_states_while_waiting_models");
  assert.equal(fault.filter((item) => item.role.endsWith("_command")).length, 0);
  assert.equal(action(fault, "cycle_result").payload.status, "fault_latched");
});
