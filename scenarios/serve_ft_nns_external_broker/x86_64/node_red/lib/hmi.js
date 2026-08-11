"use strict";

/* Rein lesendes Anzeigemodell fuer das virtuelle FlowFuse-Dashboard. */

const MODULES = ["vgr", "hbw", "mpo", "sld"];
const MODELS = ["storage", "vgr", "hbw"];

const FACTORY_RUNNING_STATES = new Set([
  "bootstrap_commands_published",
  "modules_running",
  "modules_completed",
  "live_state_published",
]);

const ERROR_PRESENTATION = {
  inference_timeout: ["Inferenz-Timeout", "NN-Dienste und Broker pruefen; danach Reset ausfuehren."],
  command_publish_error: ["Command konnte nicht publiziert werden", "Brokerverbindung pruefen; danach Reset ausfuehren."],
  invalid_payload: ["Ungueltiger Anlagenzustand", "Pflichtfelder und JSON-Payload pruefen; danach Reset ausfuehren."],
  contract_invalid: ["Modellvertrag ungueltig", "Modellartefakte und Featurevertrag pruefen."],
  semaphore_stalled: ["Semaphor wartet auf Module", "Command- und Jobcounter der vier Module vergleichen."],
  report_write_error: ["Report konnte nicht geschrieben werden", "Reportpfad und Schreibrechte pruefen."],
  configuration_rejected: ["Startkonfiguration abgelehnt", "Trace, Seed und Modulbasiszeiten korrigieren."],
  invalid_json: ["Ungueltige MQTT-Nachricht", "JSON-Quelle und Topicbelegung pruefen."],
  fault_latched: ["Prozess verriegelt", "Fehlerursache beheben; danach Reset ausfuehren."],
  model_offline: ["NN-Dienst offline", "Betroffenen NN-Container und MQTT-Verbindung pruefen; danach Reset ausfuehren."],
  model_response_error: ["NN-Antwort konnte nicht verarbeitet werden", "Request-ID, Zyklus und NN-Logs pruefen; danach Reset ausfuehren."],
};

function presentationCode(code) {
  const value = String(code || "unknown_error");
  if (/model.*offline|offline.*model|service.*offline/i.test(value)) return "model_offline";
  if (/^(storage|vgr|hbw)_response:/.test(value)) return "model_response_error";
  return value;
}

function parsePayload(payload) {
  if (Buffer.isBuffer(payload)) {
    return JSON.parse(payload.toString("utf8"));
  }
  return typeof payload === "string" ? JSON.parse(payload) : payload;
}

function boundedPush(values, item, limit) {
  values.push(item);
  if (values.length > limit) {
    values.splice(0, values.length - limit);
  }
}

function confidence(prediction) {
  const value = prediction?.top3?.[0]?.p;
  return Number.isFinite(Number(value)) ? Math.round(Number(value) * 1000) / 10 : null;
}

function predictionLabel(domain, prediction) {
  if (!prediction) return "-";
  if (domain === "storage") return `Fach ${prediction.empty_storage ?? "-"}`;
  return `cmd ${prediction.cmd ?? "-"}`;
}

function commandFromTopic(topic) {
  const match = /\/cmd(\d+)$/.exec(String(topic || ""));
  return match ? `cmd ${Number(match[1])}` : "-";
}

function compactCycleId(cycleId) {
  const value = String(cycleId || "");
  const counter = /-([0-9]{6})$/.exec(value);
  if (counter) return `#${counter[1]}`;
  if (value.length <= 24) return value || "-";
  return `${value.slice(0, 10)}...${value.slice(-10)}`;
}

class HmiViewModel {
  constructor({ maxCycles = 30, maxErrors = 20 } = {}) {
    this.maxCycles = maxCycles;
    this.maxErrors = maxErrors;
    this.factory = {};
    this.orchestration = {};
    this.modelStatus = Object.fromEntries(MODELS.map((model) => [model, {}]));
    this.activeModelIds = {};
    this.predictions = Object.fromEntries(MODELS.map((model) => [model, null]));
    this.cycles = [];
    this.errors = [];
    this.latenciesByModel = Object.fromEntries(MODELS.map((model) => [model, []]));
    this.notification = null;
    this.notificationDirty = false;
  }

  recordError({ code, detail = "", cycleId = "", severity = "error" }) {
    const normalizedCode = String(code || "unknown_error");
    const classifiedCode = presentationCode(normalizedCode);
    const modelDomain = /(?:^|:)(storage|vgr|hbw)(?:$|:)/.exec(normalizedCode)?.[1] || "";
    const key = classifiedCode === "model_offline"
      ? `${classifiedCode}|${modelDomain}|${cycleId}`
      : `${normalizedCode}|${cycleId}|${detail}`;
    const existing = this.errors.find((entry) => entry.key === key);
    if (existing) {
      existing.count += 1;
      existing.timestamp = new Date().toISOString();
      this.notification = existing;
      this.notificationDirty = true;
      return;
    }
    const [title, recommendation] = ERROR_PRESENTATION[classifiedCode]
      || ["Technischer Fehler", "Details und Containerlogs pruefen; bei Verriegelung Reset ausfuehren."];
    const entry = {
      key,
      timestamp: new Date().toISOString(),
      severity,
      code: normalizedCode,
      title,
      detail: String(detail || ""),
      cycle_id: String(cycleId || ""),
      cycle_display: compactCycleId(cycleId),
      recommendation,
      count: 1,
    };
    boundedPush(this.errors, entry, this.maxErrors);
    this.notification = entry;
    this.notificationDirty = true;
  }

  resetRunDisplay(factoryStatus) {
    this.factory = { ...factoryStatus };
    this.activeModelIds = {};
    this.predictions = Object.fromEntries(MODELS.map((model) => [model, null]));
    this.cycles = [];
    this.errors = [];
    this.latenciesByModel = Object.fromEntries(MODELS.map((model) => [model, []]));
    this.notification = null;
    this.notificationDirty = false;
  }

  handle(topic, payload) {
    let value;
    try {
      value = parsePayload(payload) || {};
    } catch (error) {
      this.recordError({ code: "invalid_json", detail: error.message, severity: "warning" });
      return this.actions();
    }

    const modelMatch = /^ft\/nn\/(storage|vgr|hbw)\/status$/.exec(String(topic));
    if (modelMatch) {
      this.modelStatus[modelMatch[1]] = { ...value };
      if (value.state === "offline") {
        this.recordError({
          code: `model_service_offline:${modelMatch[1]}`,
          detail: `${modelMatch[1]} service reported offline`,
          severity: "warning",
        });
      }
    } else if (topic === "ft/ai/orchestration/status") {
      this.orchestration = { ...value };
      if (value.state === "fault_latched") {
        const reason = value.error || value.fault?.reason || "fault_latched";
        this.recordError({
          code: reason,
          detail: value.fault?.detail
            || (value.detail === "additional_fault_ignored" ? reason : value.detail)
            || "",
          cycleId: value.cycle_id || value.fault?.cycle_id || "",
        });
      }
    } else if (topic === "ft/sim/factory/status") {
      if (value.state === "reset") {
        this.resetRunDisplay(value);
      } else {
        this.factory = { ...this.factory, ...value };
      }
      if (value.state === "configuration_rejected" || value.state === "start_rejected") {
        this.recordError({
          code: value.state === "configuration_rejected" ? value.state : "configuration_rejected",
          detail: value.detail || "",
          severity: "warning",
        });
      }
    } else if (topic === "ft/ai/orchestration/cycle_result") {
      this.recordCycle(value);
    }
    return this.actions();
  }

  recordCycle(cycle) {
    if (cycle.status === "fault_latched") {
      this.recordError({
        code: cycle.error || "fault_latched",
        detail: cycle.detail || "",
        cycleId: cycle.cycle_id || "",
      });
    }
    const predictions = cycle.model_predictions || {};
    this.activeModelIds = { ...this.activeModelIds, ...(cycle.model_ids || {}) };
    for (const model of MODELS) {
      if (predictions[model]) this.predictions[model] = { ...predictions[model] };
    }
    boundedPush(this.cycles, {
      timestamp: new Date(cycle.ts_ms || Date.now()).toISOString(),
      cycle_id: cycle.cycle_id || "-",
      cycle_display: compactCycleId(cycle.cycle_id),
      source_id: cycle.source_id || "-",
      status: cycle.status || "unknown",
      empty_storage: cycle.empty_storage ?? "-",
      vgr_cmd: cycle.vgr_cmd ?? "-",
      hbw_cmd: cycle.hbw_cmd ?? "-",
      duration_ms: cycle.duration_ms ?? "-",
    }, this.maxCycles);

    const legacyLatencies = cycle.latencies_ms || {};
    for (const model of MODELS) {
      const latency = cycle[`${model}_latency_ms`] ?? legacyLatencies[model];
      if (!Number.isFinite(Number(latency))) continue;
      boundedPush(this.latenciesByModel[model], {
        x: cycle.ts_ms || Date.now(),
        y: Number(latency),
        series: model === "storage" ? "Storage" : model.toUpperCase(),
      }, this.maxCycles);
    }
  }

  overview() {
    const orchestrationFault = this.orchestration.state === "fault_latched";
    let state = "waiting";
    let label = "Warte auf Systemstatus";
    if (orchestrationFault) {
      state = "fault";
      label = "Verriegelt";
    } else if (this.factory.state === "completed") {
      state = "completed";
      label = "Abgeschlossen";
    } else if (FACTORY_RUNNING_STATES.has(this.factory.state)) {
      state = "running";
      label = "Simulation laeuft";
    } else if (this.orchestration.state === "ready") {
      state = "ready";
      label = "Bereit";
    }
    const total = Number(this.factory.trace_total || 0);
    const sent = Number(this.factory.payloads_sent || 0);
    return {
      state,
      label,
      trace_profile: this.factory.trace_profile || "-",
      trace_profile_name: this.factory.trace_profile_name || this.factory.trace_profile || "-",
      model_profile: this.factory.model_profile || "deployment-current",
      model_profile_name: this.factory.model_profile_name
        || this.factory.model_profile
        || "Aktueller Modellstand",
      trace_total: total,
      payloads_sent: sent,
      progress_percent: total > 0 ? Math.round((sent / total) * 10000) / 100 : 0,
      command_mode: this.orchestration.command_output_enabled === true
        ? "Commands aktiv"
        : this.orchestration.command_output_enabled === false
          ? "Diagnose (keine Commands)"
          : "Noch nicht bekannt",
      cycle_id: this.orchestration.cycle_id || "-",
    };
  }

  moduleRows() {
    const sent = this.factory.sent_counts || {};
    const accepted = this.factory.accepted_counts || {};
    const runtimes = this.factory.module_runtime_ms || {};
    const topics = this.factory.command_topics || {};
    return MODULES.map((module) => {
      const sentCount = Number(sent[module] || 0);
      const acceptedCount = Number(accepted[module] || 0);
      return {
        module: module.toUpperCase(),
        command: commandFromTopic(topics[module]),
        runtime_ms: runtimes[module] ?? "-",
        sent_count: sentCount,
        accepted_count: acceptedCount,
        state: sentCount > acceptedCount ? "Laeuft" : "Bereit",
      };
    });
  }

  modelRows() {
    return MODELS.map((model) => ({
      model: model === "storage" ? "Storage" : model.toUpperCase(),
      state: this.modelStatus[model].state || "unbekannt",
      model_id: this.activeModelIds[model]
        || this.modelStatus[model].model_id
        || this.orchestration.model_ids?.[model]
        || "-",
    }));
  }

  predictionRows() {
    return MODELS.map((model) => ({
      model: model === "storage" ? "Storage" : model.toUpperCase(),
      prediction: predictionLabel(model, this.predictions[model]),
      confidence_percent: confidence(this.predictions[model]) ?? "-",
      latency_ms: this.latenciesByModel[model].at(-1)?.y ?? "-",
    }));
  }

  snapshot() {
    return {
      overview: this.overview(),
      modules: this.moduleRows(),
      models: this.modelRows(),
      predictions: this.predictionRows(),
      cycles: this.cycles.map((entry) => ({ ...entry })),
      errors: this.errors.map(({ key, ...entry }) => ({ ...entry })),
      latencies: MODELS.flatMap((model) => this.latenciesByModel[model].map((entry) => ({ ...entry }))),
      notification: this.notification ? { level: this.notification.severity, ...this.notification } : null,
    };
  }

  actions() {
    const snapshot = this.snapshot();
    const notification = this.notificationDirty ? snapshot.notification : null;
    this.notificationDirty = false;
    return [
      { role: "overview", payload: snapshot.overview },
      { role: "modules", payload: snapshot.modules },
      { role: "models", payload: snapshot.models },
      { role: "predictions", payload: snapshot.predictions },
      { role: "cycles", payload: snapshot.cycles },
      { role: "errors", payload: snapshot.errors },
      { role: "latencies", payload: snapshot.latencies },
      { role: "notification", payload: notification },
    ];
  }
}

module.exports = { HmiViewModel, compactCycleId };
