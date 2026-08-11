"use strict";

/* Reproduzierbarer SPS-/Semaphor-Ersatz fuer den virtuellen Compose-Stack. */

const MODULES = ["vgr", "hbw", "mpo", "sld"];
const DEFAULT_BASE_RUNTIME_MS = 100;
const HMI_MIN_BASE_RUNTIME_MS = 50;
const HMI_MAX_BASE_RUNTIME_MS = 60000;
const MAX_SEED = 0xffffffff;

function mqttAction(role, topic, payload, qos, retain = false) {
  return { channel: "mqtt", role, topic, payload, qos, retain };
}

function moduleFromTopic(topic) {
  const match = /^ai\/(vgr|hbw|mpo|sld)\/cmd\d+$/.exec(String(topic));
  return match ? match[1] : null;
}

function normalizeBaseRuntimeMs(values = {}) {
  return Object.fromEntries(MODULES.map((module) => {
    const configured = values[module] ?? DEFAULT_BASE_RUNTIME_MS;
    const runtimeMs = Number(configured);
    if (!Number.isSafeInteger(runtimeMs) || runtimeMs <= 0) {
      throw new TypeError(
        `base runtime for ${module} must be a positive finite integer, got ${configured}`,
      );
    }
    return [module, runtimeMs];
  }));
}

function normalizeSeed(value = 42) {
  const seed = Number(value);
  if (!Number.isSafeInteger(seed) || seed < 0 || seed > MAX_SEED) {
    throw new TypeError(`seed must be an integer between 0 and ${MAX_SEED}, got ${value}`);
  }
  return seed;
}

function normalizeRunConfig(value = {}, { payloadCatalog, defaults = {} } = {}) {
  const catalog = payloadCatalog || {};
  const traceProfile = String(value.trace_profile ?? defaults.trace_profile ?? "standard");
  if (!Object.hasOwn(catalog, traceProfile) || !Array.isArray(catalog[traceProfile])) {
    throw new TypeError(`trace profile '${traceProfile}' is not available`);
  }
  const modelProfiles = defaults.model_profiles || {
    "deployment-current": { display_name: "deployment-current" },
  };
  const modelProfile = String(
    value.model_profile ?? defaults.model_profile ?? "deployment-current",
  );
  if (!Object.hasOwn(modelProfiles, modelProfile)) {
    throw new TypeError(`model profile '${modelProfile}' is not available`);
  }

  const seed = normalizeSeed(value.seed ?? defaults.seed ?? 42);
  const baseRuntimeMs = normalizeBaseRuntimeMs({
    ...(defaults.base_runtime_ms || {}),
    ...(value.base_runtime_ms || {}),
  });
  for (const [module, runtimeMs] of Object.entries(baseRuntimeMs)) {
    if (runtimeMs < HMI_MIN_BASE_RUNTIME_MS || runtimeMs > HMI_MAX_BASE_RUNTIME_MS) {
      throw new TypeError(
        `base runtime for ${module} must be between ${HMI_MIN_BASE_RUNTIME_MS} and ${HMI_MAX_BASE_RUNTIME_MS} ms, got ${runtimeMs}`,
      );
    }
  }

  return {
    trace_profile: traceProfile,
    model_profile: modelProfile,
    seed,
    base_runtime_ms: baseRuntimeMs,
  };
}

class SeededRandom {
  constructor(seed = 42) {
    this.state = Number(seed) >>> 0;
  }

  next() {
    this.state = (1664525 * this.state + 1013904223) >>> 0;
    return this.state / 0x100000000;
  }
}

class VirtualFactory {
  constructor({
    topics,
    payloads,
    payloadCatalog,
    experimentCatalog = {},
    traceProfile = "standard",
    modelProfile = "deployment-current",
    seed = 42,
    baseRuntimeMs = {},
    now = () => Date.now(),
  }) {
    this.topics = topics;
    this.payloadCatalog = payloadCatalog || { [traceProfile]: payloads || [] };
    this.experimentCatalog = experimentCatalog;
    this.modelProfiles = experimentCatalog.model_profiles || {
      [modelProfile]: { display_name: modelProfile },
    };
    this.traceProfiles = experimentCatalog.trace_profiles || {};
    if (!Object.hasOwn(this.payloadCatalog, traceProfile)) {
      this.payloadCatalog[traceProfile] = payloads || [];
    }
    this.defaultRunConfig = {
      trace_profile: traceProfile,
      model_profile: modelProfile,
      model_profiles: this.modelProfiles,
      seed: normalizeSeed(seed),
      base_runtime_ms: normalizeBaseRuntimeMs(baseRuntimeMs),
    };
    this.activeRunConfig = { ...this.defaultRunConfig };
    this.payloads = this.payloadCatalog[traceProfile];
    this.random = new SeededRandom(this.defaultRunConfig.seed);
    this.baseRuntimeMs = { ...this.defaultRunConfig.base_runtime_ms };
    this.now = now;
    this.running = false;
    this.finished = false;
    this.startRequested = false;
    this.orchestrationReady = false;
    this.payloadIndex = 0;
    this.commandSet = {};
    this.completionDue = {};
    this.moduleRuntimeMs = {};
    this.completedModules = new Set();
    this.sentCounts = Object.fromEntries(MODULES.map((module) => [module, 0]));
    this.acceptedCounts = Object.fromEntries(MODULES.map((module) => [module, 0]));
    this.cycleCounter = 0;
    this.runCounter = 0;
    this.activeRunId = null;
    this.pendingRunConfig = null;
  }

  runConfigSnapshot() {
    return {
      trace_profile: this.activeRunConfig.trace_profile,
      trace_profile_name: this.traceProfileName(this.activeRunConfig.trace_profile),
      model_profile: this.activeRunConfig.model_profile,
      model_profile_name: this.modelProfileName(this.activeRunConfig.model_profile),
      seed: this.activeRunConfig.seed,
      base_runtime_ms: { ...this.baseRuntimeMs },
    };
  }

  statusPayload(state, values = {}) {
    const traceTotal = this.payloads.length;
    const progressPercent = traceTotal === 0
      ? 0
      : Math.round((this.payloadIndex / traceTotal) * 10000) / 100;
    return {
      state,
      trace_profile: this.activeRunConfig.trace_profile,
      trace_profile_name: this.traceProfileName(this.activeRunConfig.trace_profile),
      model_profile: this.activeRunConfig.model_profile,
      model_profile_name: this.modelProfileName(this.activeRunConfig.model_profile),
      trace_total: traceTotal,
      payloads_sent: this.payloadIndex,
      progress_percent: progressPercent,
      seed: this.activeRunConfig.seed,
      base_runtime_ms: { ...this.baseRuntimeMs },
      run_id: this.activeRunId,
      ...values,
    };
  }

  applyRunConfig(config) {
    this.activeRunConfig = {
      trace_profile: config.trace_profile,
      model_profile: config.model_profile,
      seed: config.seed,
      base_runtime_ms: { ...config.base_runtime_ms },
    };
    this.payloads = this.payloadCatalog[config.trace_profile];
    this.random = new SeededRandom(config.seed);
    this.baseRuntimeMs = { ...config.base_runtime_ms };
  }

  traceProfileName(profileId) {
    return this.traceProfiles[profileId]?.display_name || profileId;
  }

  modelProfileName(profileId) {
    return this.modelProfiles[profileId]?.display_name || profileId;
  }

  runtimeMs(module) {
    const randomFactor = 0.5 + this.random.next();
    return Math.max(1, Math.round(this.baseRuntimeMs[module] * randomFactor));
  }

  start(config = this.pendingRunConfig || this.defaultRunConfig) {
    this.applyRunConfig(config);
    this.runCounter += 1;
    this.activeRunId = `${Math.trunc(this.now())}-${this.runCounter}`;
    this.running = true;
    this.startRequested = false;
    this.pendingRunConfig = null;
    this.payloadIndex = 0;
    this.cycleCounter = 0;
    this.commandSet = {};
    this.completionDue = {};
    this.moduleRuntimeMs = {};
    this.completedModules.clear();
    this.sentCounts = Object.fromEntries(MODULES.map((module) => [module, 0]));
    this.acceptedCounts = Object.fromEntries(MODULES.map((module) => [module, 0]));
    return [
      mqttAction("vgr_command", this.topics.command_topics.vgr["0"], "", 2, false),
      mqttAction("hbw_command", this.topics.command_topics.hbw["0"], "", 2, false),
      mqttAction("mpo_command", this.topics.command_topics.mpo["0"], "", 2, false),
      mqttAction("sld_command", this.topics.command_topics.sld["0"], "", 2, false),
      {
        channel: "status",
        role: "factory_status",
        payload: this.statusPayload("bootstrap_commands_published"),
      },
    ];
  }

  handleControl(payload) {
    let value;
    try {
      value = typeof payload === "string" ? JSON.parse(payload) : payload;
    } catch (error) {
      return [{
        channel: "status",
        role: "factory_status",
        payload: this.statusPayload("configuration_rejected", { detail: `invalid_json: ${error.message}` }),
      }];
    }
    if (value?.cmd === "start") {
      if (this.running || this.finished) {
        return [{
          channel: "status",
          role: "factory_status",
          payload: this.statusPayload("start_rejected", {
            detail: this.running ? "factory_already_running" : "reset_required_after_completion",
          }),
        }];
      }
      try {
        this.pendingRunConfig = value.config
          ? normalizeRunConfig(value.config, {
            payloadCatalog: this.payloadCatalog,
            defaults: this.defaultRunConfig,
          })
          : {
            ...this.defaultRunConfig,
            base_runtime_ms: { ...this.defaultRunConfig.base_runtime_ms },
          };
      } catch (error) {
        this.pendingRunConfig = null;
        return [{
          channel: "status",
          role: "factory_status",
          payload: this.statusPayload("configuration_rejected", { detail: error.message }),
        }];
      }
      this.startRequested = true;
      if (this.orchestrationReady) {
        return this.start(this.pendingRunConfig);
      }
      const pending = this.pendingRunConfig;
      return [{
        channel: "status",
        role: "factory_status",
        payload: {
          ...this.statusPayload("waiting_for_orchestration"),
          trace_profile: pending.trace_profile,
          trace_profile_name: this.traceProfileName(pending.trace_profile),
          model_profile: pending.model_profile,
          model_profile_name: this.modelProfileName(pending.model_profile),
          trace_total: this.payloadCatalog[pending.trace_profile].length,
          seed: pending.seed,
          base_runtime_ms: { ...pending.base_runtime_ms },
        },
      }];
    }
    if (value?.cmd === "reset") {
      const previousRunId = this.activeRunId;
      this.running = false;
      this.finished = false;
      this.startRequested = false;
      this.payloadIndex = 0;
      this.commandSet = {};
      this.completionDue = {};
      this.moduleRuntimeMs = {};
      this.completedModules.clear();
      this.sentCounts = Object.fromEntries(MODULES.map((module) => [module, 0]));
      this.acceptedCounts = Object.fromEntries(MODULES.map((module) => [module, 0]));
      this.cycleCounter = 0;
      this.activeRunId = null;
      this.pendingRunConfig = null;
      this.applyRunConfig(this.defaultRunConfig);
      return [{
        channel: "status",
        role: "factory_status",
        payload: this.statusPayload("reset", { run_id: previousRunId }),
      }];
    }
    return [];
  }

  handleOrchestrationStatus(payload) {
    const value = typeof payload === "string" ? JSON.parse(payload) : payload;
    this.orchestrationReady = value?.state === "ready";
    if (this.startRequested && this.orchestrationReady && !this.running && !this.finished) {
      return this.start(this.pendingRunConfig || this.defaultRunConfig);
    }
    return [];
  }

  handleCommand(topic) {
    if (!this.running || this.finished) {
      return [];
    }
    const module = moduleFromTopic(topic);
    if (!module) {
      return [];
    }
    if (this.commandSet[module]) {
      return [{
        channel: "status",
        role: "factory_status",
        payload: this.statusPayload("duplicate_command_ignored", {
          module,
          topic: String(topic),
          sent_counts: { ...this.sentCounts },
          accepted_counts: { ...this.acceptedCounts },
        }),
      }];
    }
    this.commandSet[module] = String(topic);
    this.sentCounts[module] += 1;
    this.moduleRuntimeMs[module] = this.runtimeMs(module);
    this.completionDue[module] = this.now() + this.moduleRuntimeMs[module];
    if (Object.keys(this.commandSet).length === MODULES.length) {
      this.cycleCounter += 1;
      return [{
        channel: "status",
        role: "factory_status",
        payload: this.statusPayload("modules_running", {
          factory_cycle: this.cycleCounter,
          command_topics: { ...this.commandSet },
          module_runtime_ms: { ...this.moduleRuntimeMs },
          completion_due_ms: { ...this.completionDue },
          sent_counts: { ...this.sentCounts },
          accepted_counts: { ...this.acceptedCounts },
        }),
      }];
    }
    return [];
  }

  tick(nowMs = this.now()) {
    if (!this.running || this.finished || Object.keys(this.commandSet).length !== MODULES.length) {
      return [];
    }
    const newlyCompleted = [];
    for (const module of MODULES) {
      if (
        !this.completedModules.has(module)
        && Number(nowMs) >= Number(this.completionDue[module])
      ) {
        this.completedModules.add(module);
        this.acceptedCounts[module] += 1;
        newlyCompleted.push(module);
      }
    }
    const semaphoreFree = MODULES.every(
      (module) => this.sentCounts[module] === this.acceptedCounts[module],
    );
    if (this.completedModules.size !== MODULES.length || !semaphoreFree) {
      if (newlyCompleted.length === 0) {
        return [];
      }
      return [{
        channel: "status",
        role: "factory_status",
        payload: this.statusPayload("modules_completed", {
          modules: newlyCompleted,
          sent_counts: { ...this.sentCounts },
          accepted_counts: { ...this.acceptedCounts },
        }),
      }];
    }
    if (this.payloadIndex >= this.payloads.length) {
      this.finished = true;
      this.running = false;
      return [{
        channel: "status",
        role: "factory_status",
        payload: this.statusPayload("completed", {
          sent_counts: { ...this.sentCounts },
          accepted_counts: { ...this.acceptedCounts },
        }),
      }];
    }

    const payload = this.payloads[this.payloadIndex];
    this.payloadIndex += 1;
    const livePayload = {
      ...payload,
      simulation_run_id: this.activeRunId,
      correlation_id: this.activeRunId,
      factory_cycle: this.cycleCounter,
      trace_profile: this.activeRunConfig.trace_profile,
      trace_profile_name: this.traceProfileName(this.activeRunConfig.trace_profile),
      model_profile: this.activeRunConfig.model_profile,
      model_profile_name: this.modelProfileName(this.activeRunConfig.model_profile),
      factory_seed: this.activeRunConfig.seed,
      factory_base_runtime_ms: { ...this.baseRuntimeMs },
      module_runtime_ms: { ...this.moduleRuntimeMs },
      module_job_counts: {
        sent: { ...this.sentCounts },
        accepted: { ...this.acceptedCounts },
      },
    };
    const action = mqttAction("live_state", this.topics.live_state_topic, livePayload, 1, false);
    this.commandSet = {};
    this.completionDue = {};
    this.moduleRuntimeMs = {};
    this.completedModules.clear();
    return [
      action,
      {
        channel: "status",
        role: "factory_status",
        payload: this.statusPayload("live_state_published", {
          factory_cycle: this.cycleCounter,
          payload_index: this.payloadIndex - 1,
          request_id: livePayload.request_id,
          module_runtime_ms: livePayload.module_runtime_ms,
          sent_counts: { ...this.sentCounts },
          accepted_counts: { ...this.acceptedCounts },
        }),
      },
    ];
  }
}

module.exports = {
  DEFAULT_BASE_RUNTIME_MS,
  MODULES,
  SeededRandom,
  VirtualFactory,
  moduleFromTopic,
  normalizeBaseRuntimeMs,
  normalizeRunConfig,
  normalizeSeed,
};
