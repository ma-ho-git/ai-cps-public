"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const NODE_RED_ROOT = path.resolve(__dirname, "..");
const SCENARIO_ROOT = path.resolve(NODE_RED_ROOT, "..");
const PROJECT_ROOT = path.resolve(SCENARIO_ROOT, "../../..");

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(PROJECT_ROOT, relativePath), "utf8"));
}

function readJsonLines(relativePath) {
  return fs.readFileSync(path.join(PROJECT_ROOT, relativePath), "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

const flows = readJson(
  "scenarios/serve_ft_nns_external_broker/x86_64/node_red/flows.json",
);
const nodes = Object.fromEntries(flows.map((node) => [node.id, node]));
const topics = readJson(
  "scenarios/serve_ft_nns_external_broker/x86_64/node_red/config/topics.json",
);

function mqttNode(nodeId, topic, qos, retain) {
  const node = nodes[nodeId];
  assert.ok(node, `Node fehlt: ${nodeId}`);
  assert.equal(node.topic, topic);
  assert.equal(node.qos, qos);
  assert.equal(node.retain, retain);
}

function assertModelValue(payload, feature, label) {
  const valueType = typeof payload[feature];
  assert.ok(
    valueType === "number" || valueType === "boolean",
    `${label} fehlt: ${feature}`,
  );
}

test("aktiver Flow behaelt die MQTT-Grenzvertraege", () => {
  mqttNode("out-live-release", "log/logging/state", "1", "false");
  mqttNode("out-storage-request", "ft/nn/storage/request", "1", "false");
  mqttNode("out-vgr-request", "ft/nn/vgr/request", "1", "false");
  mqttNode("out-hbw-request", "ft/nn/hbw/request", "1", "false");
  mqttNode("out-cycle-result", "ft/ai/orchestration/cycle_result", "1", "false");

  assert.equal(topics.command_topics.vgr[0], "ai/vgr/cmd0");
  assert.equal(topics.command_topics.hbw[0], "ai/hbw/cmd000");
  assert.equal(topics.command_topics.mpo[0], "ai/mpo/cmd0");
  assert.equal(topics.command_topics.sld[0], "ai/sld/cmd0");
});

test("vier getrennte Modulpfade besitzen Idle, Command und Diagnose", () => {
  for (const domain of ["vgr", "hbw", "mpo", "sld"]) {
    assert.equal(nodes[`in-module-${domain}-command`].type, "mqtt in");
    assert.equal(nodes[`out-module-${domain}-idle`].type, "mqtt out");
    assert.equal(nodes[`debug-module-${domain}`].type, "debug");
  }
  assert.equal(
    flows.filter((node) => node.type === "subflow:subflow-virtual-module").length,
    4,
  );
});

test("Fehlerpfade und MQTT-Status sind auf jedem Funktionstab sichtbar", () => {
  const catchNodes = flows.filter((node) => node.type === "catch");
  const statusNodes = flows.filter((node) => node.type === "status");
  const debugNames = new Set(
    flows.filter((node) => node.type === "debug").map((node) => node.name),
  );

  assert.ok(catchNodes.length >= 5);
  assert.ok(statusNodes.length >= 4);
  for (const name of [
    "Initialisierung abgeschlossen",
    "Semaphorfreigabe",
    "Storage-Ergebnis",
    "VGR-Request Kurzinfo",
    "HBW-Request Kurzinfo",
    "Fault-Latch",
  ]) {
    assert.ok(debugNames.has(name), `Debug fehlt: ${name}`);
  }
});

test("HMI beobachtet Status und steuert nur das vorhandene Control-Topic", () => {
  assert.equal(nodes["ui-hmi-run-form"].type, "ui-form");
  assert.equal(nodes["ui-hmi-reset-button"].type, "ui-button");
  assert.equal(nodes["in-hmi-model-status"].topic, "ft/nn/+/status");
  assert.equal(nodes["in-hmi-ai-status"].topic, "ft/ai/orchestration/status");
  assert.equal(nodes["in-hmi-factory-status"].topic, "ft/sim/factory/status");
  assert.equal(nodes["in-hmi-cycle-result"].topic, "ft/ai/orchestration/cycle_result");
  assert.equal(nodes["out-hmi-control"].type, "mqtt out");
});

test("Reporting verwendet weiterhin die drei vereinbarten Dateien", () => {
  assert.equal(nodes["file-report-append-inline"].overwriteFile, "false");
  assert.equal(nodes["file-report-replace-inline"].overwriteFile, "true");
  const serialized = JSON.stringify(flows);
  assert.match(serialized, /events\.jsonl/);
  assert.match(serialized, /summary\.csv/);
  assert.match(serialized, /run_summary\.json/);
});

test("Standardtrace besitzt 320 gueltige Modellzustaende", () => {
  const payloads = readJsonLines(
    "scenarios/serve_ft_nns_external_broker/x86_64/test_payloads/live_plc_trace/payloads.jsonl",
  );
  const storage = readJson("model_registry/storage/latest/activation.json");
  const vgr = readJson("model_registry/vgr/latest/activation.json");
  const hbw = readJson("model_registry/hbw/latest/activation.json");

  assert.equal(payloads.length, 320);
  for (const payload of payloads) {
    assert.ok(payload.request_id);
    assert.ok(payload.source_id);
    for (const feature of storage.feature_cols) {
      assertModelValue(payload, feature, "Storage-Feature");
    }
    for (const feature of [...vgr.feature_cols, ...hbw.feature_cols]) {
      if (!feature.startsWith("empty_storage_")) {
        assertModelValue(payload, feature, "Rohfeature");
      }
    }
  }
});
