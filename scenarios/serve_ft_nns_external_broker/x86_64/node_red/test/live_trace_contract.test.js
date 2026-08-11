"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { createRuntime } = require("../lib/orchestration");
const bootstrap = require("../lib/bootstrap");

const SCENARIO_ROOT = path.resolve(__dirname, "../..");
const PROJECT_ROOT = path.resolve(SCENARIO_ROOT, "../../..");
const topics = bootstrap.loadJson(path.join(SCENARIO_ROOT, "node_red/config/topics.json"));
const idleSeeds = bootstrap.loadJson(path.join(SCENARIO_ROOT, "node_red/config/idle_seed_templates.json"));
const payloads = bootstrap.loadJsonLines(path.join(SCENARIO_ROOT, "test_payloads/live_plc_trace/payloads.jsonl"));

function activation(domain) {
  return bootstrap.loadJson(path.join(PROJECT_ROOT, `model_registry/${domain}/latest/activation.json`));
}

function modelContract(domain) {
  const current = activation(domain);
  const timeSteps = current.time_steps === undefined ? null : Number(current.time_steps);
  const inputShape = current.input_shape || current.architecture?.input_shape || [current.feature_cols.length];
  const contract = {
    schema_version: "1.0",
    domain,
    model_id: `${domain}:${current.trained_at || "latest"}:offline-contract-test`,
    model_sha256: "b".repeat(64),
    input_shape: inputShape,
    time_steps: timeSteps,
    feature_cols: current.feature_cols,
    class_ids: current.class_ids,
    request_topic: topics.model_topics[domain].request,
    response_topic: topics.model_topics[domain].response,
  };
  if (domain !== "storage") {
    contract.command_output = {
      mode: "direct_mqtt",
      enabled: true,
      payload: "empty",
      qos: 2,
      retain: false,
      topics: topics.command_topics[domain],
    };
  }
  return contract;
}

function one(actions, role) {
  const matches = actions.filter((item) => item.role === role);
  assert.equal(matches.length, 1, `expected one ${role}, got ${matches.length}`);
  return matches[0];
}

function response(domain, request, cmd) {
  return {
    cycle_id: request.payload.cycle_id,
    request_id: request.payload.request_id,
    source_id: request.payload.source_id,
    model_id: request.payload.model_id,
    model_profile: request.payload.model_profile,
    cmd,
    command_output: {
      enabled: true,
      published: true,
      reason: "published",
      topic: topics.command_topics[domain][String(cmd)],
      qos: 2,
      retain: false,
      mid: 1,
    },
  };
}

test("all 320 live-trace states satisfy the current Node-RED/model contracts", () => {
  let now = 1000;
  const runtime = createRuntime({
    topics,
    idleSeedTemplates: idleSeeds,
    commandOutputEnabled: true,
    now: () => now,
  });
  for (const domain of ["storage", "vgr", "hbw"]) {
    const contract = modelContract(domain);
    runtime.handleEvent("contract", contract, domain);
    runtime.handleEvent("status", { domain, model_id: contract.model_id, state: "online" }, domain);
  }
  assert.equal(runtime.isReady(), true);
  assert.equal(payloads.length, 320);

  const seenSources = new Set();
  let storageRequests = 0;
  let vgrRequests = 0;
  let hbwRequests = 0;
  let commands = 0;
  let seededRows = 0;

  for (const payload of payloads) {
    now += 10;
    const storageRequest = one(runtime.handleEvent("live_state", payload), "storage_request");
    storageRequests += 1;
    const modelActions = runtime.handleEvent("storage_response", {
      cycle_id: storageRequest.payload.cycle_id,
      request_id: storageRequest.payload.request_id,
      source_id: payload.source_id,
      empty_storage: payload.expected_empty_storage,
    });
    const vgrRequest = one(modelActions, "vgr_request");
    const hbwRequest = one(modelActions, "hbw_request");
    vgrRequests += 1;
    hbwRequests += 1;
    assert.deepEqual([vgrRequest.payload.sequence.length, vgrRequest.payload.sequence[0].length], [10, 29]);
    assert.deepEqual([hbwRequest.payload.sequence.length, hbwRequest.payload.sequence[0].length], [10, 29]);

    runtime.handleEvent(
      "vgr_response",
      response("vgr", vgrRequest, payload.expected_label_VGR),
    );
    const completed = runtime.handleEvent(
      "hbw_response",
      response("hbw", hbwRequest, payload.expected_label_HBW),
    );
    const result = one(completed, "cycle_result").payload;
    commands += Object.values(result.commands).filter((item) => item.published).length;
    seededRows += result.bootstrap.vgr.seeded_rows + result.bootstrap.hbw.seeded_rows;
    if (seenSources.has(payload.source_id)) {
      assert.equal(result.bootstrap.vgr.seeded_rows, 0);
      assert.equal(result.bootstrap.hbw.seeded_rows, 0);
    } else {
      assert.equal(result.bootstrap.vgr.seeded_rows, 9);
      assert.equal(result.bootstrap.hbw.seeded_rows, 9);
      seenSources.add(payload.source_id);
    }
  }

  assert.equal(seenSources.size, 3);
  assert.equal(storageRequests, 320);
  assert.equal(vgrRequests, 320);
  assert.equal(hbwRequests, 320);
  assert.equal(commands, 1280);
  assert.equal(seededRows, 3 * 9 * 2);
  assert.equal(runtime.fault, null);
});
