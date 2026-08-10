"use strict";

const path = require("node:path");
const bootstrap = require("./lib/bootstrap");

const baseDir = __dirname;
const tracePath = process.env.LIVE_TRACE_PAYLOADS || path.join(baseDir, "data/live_plc_trace/payloads.jsonl");
const traceProfile = process.env.TRACE_PROFILE || "standard";
const traceCatalog = {
  standard: bootstrap.loadJsonLines(path.join(baseDir, "data/live_plc_trace/payloads.jsonl")),
  "full-storage-attempt": bootstrap.loadJsonLines(
    path.join(baseDir, "data/live_plc_full_storage_attempt/payloads.jsonl"),
  ),
  "full-storage-process-guard": bootstrap.loadJsonLines(
    path.join(baseDir, "data/live_plc_full_storage_process_guard/payloads.jsonl"),
  ),
};

module.exports = {
  flowFile: path.join(baseDir, "flows.json"),
  // Dashboard 2.0 is pinned in the immutable image rather than installed in
  // the persistent /data volume. Register its package directory explicitly.
  nodesDir: process.env.NODE_RED_NODES_DIR
    || "/opt/ai-cps-dashboard/node_modules/@flowfuse/node-red-dashboard",
  uiPort: Number(process.env.PORT || 1880),
  credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET,
  contextStorage: {
    default: { module: "memory" },
  },
  functionGlobalContext: {
    aiCpsOrchestration: require("./lib/orchestration"),
    aiCpsVirtualFactory: require("./lib/virtual_factory"),
    aiCpsHmi: require("./lib/hmi"),
    aiCpsReporting: require("./lib/reporting"),
    aiCpsTopics: bootstrap.loadJson(path.join(baseDir, "config/topics.json")),
    aiCpsIdleSeedTemplates: bootstrap.loadJson(path.join(baseDir, "config/idle_seed_templates.json")),
    aiCpsTracePayloads: bootstrap.loadJsonLines(tracePath),
    aiCpsTraceCatalog: traceCatalog,
    aiCpsDefaultTraceProfile: traceProfile,
  },
  logging: {
    console: {
      level: process.env.NODE_RED_LOG_LEVEL || "info",
      metrics: false,
      audit: false,
    },
  },
  editorTheme: {
    projects: { enabled: false },
  },
};
