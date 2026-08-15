"use strict";

const path = require("node:path");

const baseDir = __dirname;

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
  // Fachlogik und kleine Kataloge liegen direkt in begrenzten Flow-Nodes.
  // Extern gelesen werden zur Laufzeit nur die drei versionierten Traces.
  functionGlobalContext: {},
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
