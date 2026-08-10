"use strict";

/*
 * Zustandskern des Node-RED-KI-Subflows.
 *
 * Der Kern kennt keine SPS und keinen OPC-UA-Client. Er verarbeitet nur
 * MQTT-Ereignisse, erzeugt MQTT-Aktionen und haelt die nichtpersistenten
 * Rolling Windows. Nach einem Prozessneustart beginnt er deshalb immer mit
 * einem kontrollierten Idle-Bootstrap.
 */

const DOMAINS = ["storage", "vgr", "hbw"];
const LSTM_DOMAINS = ["vgr", "hbw"];
const EMPTY_STORAGE_PREFIX = "empty_storage_";

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function asObject(value, label) {
  if (value === null || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label} must be a JSON object`);
  }
  return value;
}

function asPayload(value) {
  if (Buffer.isBuffer(value)) {
    return JSON.parse(value.toString("utf8"));
  }
  if (typeof value === "string") {
    return JSON.parse(value);
  }
  return asObject(value, "payload");
}

function mqttAction(role, topic, payload, qos, retain = false) {
  return { channel: "mqtt", role, topic, payload, qos, retain };
}

function oneHotEmptyStorage(emptyStorage) {
  const value = Number(emptyStorage);
  if (!Number.isInteger(value) || value < 0 || value > 9) {
    throw new Error(`empty_storage must be an integer in 0..9, got ${emptyStorage}`);
  }
  const result = {};
  for (let slot = 0; slot <= 9; slot += 1) {
    result[`${EMPTY_STORAGE_PREFIX}${slot}`] = slot === value ? 1.0 : 0.0;
  }
  return result;
}

function validateContract(domain, contract, topics) {
  asObject(contract, `${domain} contract`);
  if (contract.schema_version !== "1.0") {
    throw new Error(`${domain} contract schema_version must be 1.0`);
  }
  if (contract.domain !== domain) {
    throw new Error(`${domain} contract domain mismatch: ${contract.domain}`);
  }
  for (const key of ["model_id", "model_sha256", "request_topic", "response_topic"]) {
    if (typeof contract[key] !== "string" || contract[key].length === 0) {
      throw new Error(`${domain} contract is missing ${key}`);
    }
  }
  if (!Array.isArray(contract.feature_cols) || contract.feature_cols.length === 0) {
    throw new Error(`${domain} contract feature_cols must be a non-empty array`);
  }
  if (!Array.isArray(contract.class_ids) || contract.class_ids.length === 0) {
    throw new Error(`${domain} contract class_ids must be a non-empty array`);
  }
  if (contract.request_topic !== topics.model_topics[domain].request) {
    throw new Error(`${domain} request topic differs from the frozen model interface`);
  }
  if (contract.response_topic !== topics.model_topics[domain].response) {
    throw new Error(`${domain} response topic differs from the frozen model interface`);
  }
  if (domain === "storage") {
    if (contract.time_steps !== null && contract.time_steps !== undefined) {
      throw new Error("storage contract must not define time_steps");
    }
  } else {
    if (!Number.isInteger(Number(contract.time_steps)) || Number(contract.time_steps) < 1) {
      throw new Error(`${domain} contract requires a positive time_steps value`);
    }
    const commandOutput = asObject(contract.command_output, `${domain} command_output`);
    if (commandOutput.mode !== "direct_mqtt") {
      throw new Error(`${domain} contract must declare direct_mqtt command output`);
    }
    if (Number(commandOutput.qos) !== Number(topics.mqtt.command_qos)) {
      throw new Error(`${domain} command QoS differs from the frozen physical interface`);
    }
    if (Boolean(commandOutput.retain) !== Boolean(topics.mqtt.command_retain)) {
      throw new Error(`${domain} command retain flag differs from the frozen physical interface`);
    }
    const mappedTopics = asObject(commandOutput.topics, `${domain} command_output topics`);
    for (const classId of contract.class_ids.map(Number)) {
      if (mappedTopics[String(classId)] !== topics.command_topics[domain][String(classId)]) {
        throw new Error(`${domain} command topic mismatch for class ${classId}`);
      }
    }
  }
}

function buildFeatureVector(featureCols, rawState, emptyStorage) {
  const oneHot = oneHotEmptyStorage(emptyStorage);
  return featureCols.map((feature) => {
    if (Object.prototype.hasOwnProperty.call(oneHot, feature)) {
      return oneHot[feature];
    }
    if (!Object.prototype.hasOwnProperty.call(rawState, feature)) {
      throw new Error(`live state cannot provide model feature ${feature}`);
    }
    const value = Number(rawState[feature]);
    if (!Number.isFinite(value)) {
      throw new Error(`feature ${feature} is not numeric`);
    }
    return value;
  });
}

class OrchestrationRuntime {
  constructor({ topics, idleSeedTemplates, commandOutputEnabled = false, now = () => Date.now() }) {
    this.topics = clone(topics);
    this.idleSeedTemplates = clone(idleSeedTemplates);
    this.commandOutputEnabled = Boolean(commandOutputEnabled);
    this.now = now;
    this.contracts = {};
    this.statuses = {};
    this.buffers = { vgr: new Map(), hbw: new Map() };
    this.pending = null;
    this.queuedLiveState = null;
    this.fault = null;
    this.hasBeenReady = false;
    this.cycleCounter = 0;
    this.completedRequestIds = new Set();
    // QoS 1 darf Modellantworten erneut zustellen. Bereits verarbeitete
    // Response-IDs werden deshalb begrenzt gespeichert und idempotent ignoriert.
    this.seenResponseIds = new Set();
    this.lastStatus = null;
  }

  orchestrationStatus(state, detail = "", extra = {}) {
    this.lastStatus = state;
    return mqttAction(
      "orchestration_status",
      this.topics.status_topic,
      {
        schema_version: "1.0",
        state,
        detail,
        command_output_enabled: this.commandOutputEnabled,
        fault_latched: this.fault !== null,
        ts_ms: this.now(),
        ...extra,
      },
      1,
      true,
    );
  }

  isModelReady(domain) {
    return Boolean(
      this.contracts[domain]
      && this.statuses[domain]?.state === "online"
      && this.statuses[domain]?.model_id === this.contracts[domain].model_id,
    );
  }

  isReady() {
    return DOMAINS.every((domain) => this.isModelReady(domain)) && this.fault === null;
  }

  statusAndResume(detail) {
    const ready = this.isReady();
    if (ready) {
      this.hasBeenReady = true;
    }
    const actions = [
      this.orchestrationStatus(
        ready ? "ready" : "waiting_for_models",
        detail,
        { model_ids: this.modelIds() },
      ),
    ];
    if (!ready || !this.queuedLiveState || this.pending || this.fault) {
      return actions;
    }
    const queued = this.queuedLiveState;
    this.queuedLiveState = null;
    return [...actions, ...this.handleLiveState(queued)];
  }

  registerContract(domain, payload) {
    if (!DOMAINS.includes(domain)) {
      return this.enterFault(`unknown_contract_domain:${domain}`);
    }
    try {
      const contract = asPayload(payload);
      validateContract(domain, contract, this.topics);
      if (
        LSTM_DOMAINS.includes(domain)
        && Boolean(contract.command_output.enabled) !== this.commandOutputEnabled
      ) {
        throw new Error(
          `${domain} command output mode differs from Node-RED; restart the stack with one shared setting`,
        );
      }
      const previousModelId = this.contracts[domain]?.model_id;
      if (previousModelId && previousModelId !== contract.model_id) {
        if (this.pending) {
          return this.enterFault(`model_changed_during_cycle:${domain}`);
        }
        this.clearBuffers();
      }
      this.contracts[domain] = clone(contract);
      return this.statusAndResume(`contract_registered:${domain}`);
    } catch (error) {
      if (!this.hasBeenReady && !this.pending) {
        delete this.contracts[domain];
        return [
          this.orchestrationStatus(
            "waiting_for_models",
            `invalid_startup_contract:${domain}:${error.message}`,
          ),
        ];
      }
      return this.enterFault(`invalid_contract:${domain}:${error.message}`);
    }
  }

  registerStatus(domain, payload) {
    if (!DOMAINS.includes(domain)) {
      return this.enterFault(`unknown_status_domain:${domain}`);
    }
    try {
      const status = asPayload(payload);
      this.statuses[domain] = clone(status);
      if (status.state !== "online" && (this.pending || this.hasBeenReady)) {
        return this.enterFault(`model_offline:${domain}`);
      }
      return this.statusAndResume(`status_registered:${domain}:${status.state}`);
    } catch (error) {
      return this.enterFault(`invalid_status:${domain}:${error.message}`);
    }
  }

  modelIds() {
    return Object.fromEntries(
      DOMAINS.filter((domain) => this.contracts[domain]).map((domain) => [domain, this.contracts[domain].model_id]),
    );
  }

  clearBuffers() {
    this.buffers.vgr.clear();
    this.buffers.hbw.clear();
  }

  reset() {
    this.pending = null;
    this.queuedLiveState = null;
    this.fault = null;
    this.clearBuffers();
    this.completedRequestIds.clear();
    return [this.orchestrationStatus(this.isReady() ? "ready" : "waiting_for_models", "manual_reset")];
  }

  handleControl(payload) {
    try {
      const control = asPayload(payload);
      if (control.cmd === "reset") {
        return this.reset();
      }
      if (control.cmd === "command_output") {
        const requested = Boolean(control.enabled);
        const detail = requested === this.commandOutputEnabled
          ? "command_output_unchanged"
          : "command_output_restart_required";
        return [this.orchestrationStatus(this.isReady() ? "ready" : "waiting_for_models", detail)];
      }
      return [this.orchestrationStatus(this.lastStatus || "waiting_for_models", `ignored_control:${control.cmd}`)];
    } catch (error) {
      return this.enterFault(`invalid_control:${error.message}`);
    }
  }

  normalizeLivePayload(payload) {
    const raw = asPayload(payload);
    const state = raw.state && typeof raw.state === "object" && !Array.isArray(raw.state) ? raw.state : raw;
    const required = new Set(this.contracts.storage.feature_cols);
    for (const domain of LSTM_DOMAINS) {
      for (const feature of this.contracts[domain].feature_cols) {
        if (!feature.startsWith(EMPTY_STORAGE_PREFIX)) {
          required.add(feature);
        }
      }
    }
    const missing = [...required].filter((feature) => !Object.prototype.hasOwnProperty.call(state, feature));
    if (missing.length > 0) {
      throw new Error(`missing live fields: ${missing.join(",")}`);
    }
    const normalized = {};
    for (const feature of required) {
      const value = Number(state[feature]);
      if (!Number.isFinite(value)) {
        throw new Error(`live field ${feature} is not numeric`);
      }
      normalized[feature] = value;
    }
    return { raw, state: normalized };
  }

  handleLiveState(payload) {
    if (this.fault) {
      return [this.orchestrationStatus("fault_latched", "live_state_ignored", { fault: this.fault })];
    }
    if (!this.isReady()) {
      if (this.hasBeenReady) {
        return this.enterFault("models_not_ready");
      }
      try {
        const queued = asPayload(payload);
        const queuedRequestId = this.queuedLiveState?.request_id;
        if (this.queuedLiveState && queuedRequestId && queued.request_id === queuedRequestId) {
          return [this.orchestrationStatus("waiting_for_models", "duplicate_startup_live_state_ignored")];
        }
        if (this.queuedLiveState) {
          return this.enterFault("multiple_live_states_while_waiting_models");
        }
        this.queuedLiveState = clone(queued);
        return [this.orchestrationStatus("waiting_for_models", "startup_live_state_queued")];
      } catch (error) {
        return this.enterFault(`invalid_live_payload:${error.message}`);
      }
    }
    if (this.pending) {
      return this.enterFault("new_live_state_while_cycle_pending");
    }

    try {
      const { raw, state } = this.normalizeLivePayload(payload);
      const parentRequestId = String(raw.request_id || `live-${this.now()}-${this.cycleCounter + 1}`);
      if (this.completedRequestIds.has(parentRequestId)) {
        return [this.orchestrationStatus("ready", "duplicate_live_state_ignored")];
      }
      const sourceId = String(raw.source_id || "plc_live");
      const correlationId = String(raw.correlation_id || parentRequestId);
      this.cycleCounter += 1;
      const cycleId = `cycle-${sourceId}-${correlationId}-${String(this.cycleCounter).padStart(6, "0")}`;
      const requestId = `${cycleId}:storage`;
      this.pending = {
        cycle_id: cycleId,
        parent_request_id: parentRequestId,
        source_id: sourceId,
        raw_state: state,
        input_metadata: clone(raw),
        storage_request_id: requestId,
        storage_started_ms: this.now(),
        deadline_ms: this.now() + Number(this.topics.request_timeout_ms),
        responses: {},
        bootstrap: {},
        issued_commands: {},
      };
      const features = Object.fromEntries(
        this.contracts.storage.feature_cols.map((feature) => [feature, state[feature]]),
      );
      return [
        this.orchestrationStatus("running", "storage_request", { cycle_id: cycleId }),
        mqttAction(
          "storage_request",
          this.contracts.storage.request_topic,
          {
            cycle_id: cycleId,
            request_id: requestId,
            parent_request_id: parentRequestId,
            source_id: sourceId,
            model_id: this.contracts.storage.model_id,
            features,
          },
          Number(this.topics.mqtt.model_qos),
          false,
        ),
      ];
    } catch (error) {
      return this.enterFault(`invalid_live_payload:${error.message}`);
    }
  }

  assertMatchingResponse(response, expectedRequestId, domain) {
    if (!this.pending) {
      throw new Error(`${domain} response without pending cycle`);
    }
    if (response.cycle_id !== this.pending.cycle_id) {
      throw new Error(`${domain} cycle_id mismatch`);
    }
    if (response.request_id !== expectedRequestId) {
      throw new Error(`${domain} request_id mismatch`);
    }
    if (response.error) {
      throw new Error(`${domain} inference error: ${response.error}`);
    }
  }

  responseWasSeen(response) {
    return typeof response?.request_id === "string" && this.seenResponseIds.has(response.request_id);
  }

  rememberResponse(response) {
    if (typeof response?.request_id !== "string" || response.request_id.length === 0) {
      throw new Error("model response is missing request_id");
    }
    this.seenResponseIds.add(response.request_id);
    while (this.seenResponseIds.size > 5000) {
      this.seenResponseIds.delete(this.seenResponseIds.values().next().value);
    }
  }

  seedAndAppend(domain, emptyStorage) {
    const contract = this.contracts[domain];
    const timeSteps = Number(contract.time_steps);
    const sourceId = this.pending.source_id;
    let entry = this.buffers[domain].get(sourceId);
    let seededRows = 0;

    if (!entry || entry.model_id !== contract.model_id) {
      const requiredSeedRows = timeSteps - 1;
      if (this.idleSeedTemplates.rows.length < requiredSeedRows) {
        throw new Error(`${domain} needs ${requiredSeedRows} idle seed rows, only ${this.idleSeedTemplates.rows.length} exist`);
      }
      entry = { model_id: contract.model_id, rows: [] };
      for (const seedState of this.idleSeedTemplates.rows.slice(0, requiredSeedRows)) {
        entry.rows.push(buildFeatureVector(contract.feature_cols, seedState, emptyStorage));
      }
      seededRows = requiredSeedRows;
    }

    entry.rows.push(buildFeatureVector(contract.feature_cols, this.pending.raw_state, emptyStorage));
    entry.rows = entry.rows.slice(-timeSteps);
    if (entry.rows.length !== timeSteps) {
      throw new Error(`${domain} window has ${entry.rows.length} rows, expected ${timeSteps}`);
    }
    this.buffers[domain].set(sourceId, entry);
    this.pending.bootstrap[domain] = {
      seeded_rows: seededRows,
      time_steps: timeSteps,
      template_version: this.idleSeedTemplates.schema_version,
    };
    return clone(entry.rows);
  }

  handleStorageResponse(payload) {
    try {
      const response = asPayload(payload);
      if (this.responseWasSeen(response)) {
        return [];
      }
      this.assertMatchingResponse(response, this.pending?.storage_request_id, "storage");
      const emptyStorage = Number(response.empty_storage);
      if (!this.contracts.storage.class_ids.map(Number).includes(emptyStorage)) {
        throw new Error(`storage returned unknown class ${response.empty_storage}`);
      }
      this.pending.responses.storage = clone(response);
      this.rememberResponse(response);
      this.pending.empty_storage = emptyStorage;
      this.pending.storage_latency_ms = this.now() - this.pending.storage_started_ms;
      const actions = [];
      for (const domain of LSTM_DOMAINS) {
        const sequence = this.seedAndAppend(domain, emptyStorage);
        const requestId = `${this.pending.cycle_id}:${domain}`;
        this.pending[`${domain}_request_id`] = requestId;
        this.pending[`${domain}_started_ms`] = this.now();
        actions.push(
          mqttAction(
            `${domain}_request`,
            this.contracts[domain].request_topic,
            {
              cycle_id: this.pending.cycle_id,
              request_id: requestId,
              parent_request_id: this.pending.parent_request_id,
              source_id: this.pending.source_id,
              model_id: this.contracts[domain].model_id,
              sequence,
            },
            Number(this.topics.mqtt.model_qos),
            false,
          ),
        );
      }
      for (const module of ["mpo", "sld"]) {
        const topic = this.topics.command_topics[module]["0"];
        this.pending.issued_commands[module] = {
          cmd: 0,
          topic,
          publisher: "ai_flow",
          published: this.commandOutputEnabled,
        };
        if (this.commandOutputEnabled) {
          actions.push(
            mqttAction(
              `${module}_command`,
              topic,
              "",
              Number(this.topics.mqtt.command_qos),
              Boolean(this.topics.mqtt.command_retain),
            ),
          );
        }
      }
      this.pending.deadline_ms = this.now() + Number(this.topics.request_timeout_ms);
      return actions;
    } catch (error) {
      return this.enterFault(`storage_response:${error.message}`);
    }
  }

  handleModelResponse(domain, payload) {
    if (!LSTM_DOMAINS.includes(domain)) {
      return this.enterFault(`unknown_model_response_domain:${domain}`);
    }
    try {
      const response = asPayload(payload);
      if (this.responseWasSeen(response)) {
        return [];
      }
      this.assertMatchingResponse(response, this.pending?.[`${domain}_request_id`], domain);
      const cmd = Number(response.cmd);
      if (!this.contracts[domain].class_ids.map(Number).includes(cmd)) {
        throw new Error(`${domain} returned unknown model class ${response.cmd}`);
      }
      if (!this.topics.command_topics[domain][String(cmd)]) {
        throw new Error(`${domain} command ${cmd} has no physical topic mapping`);
      }
      const expectedTopic = this.topics.command_topics[domain][String(cmd)];
      const output = response.command_output;
      if (this.commandOutputEnabled) {
        asObject(output, `${domain} command_output`);
        if (output.published !== true) {
          throw new Error(`${domain} did not publish its predicted command`);
        }
        if (output.topic !== expectedTopic) {
          throw new Error(`${domain} published ${output.topic}, expected ${expectedTopic}`);
        }
        if (
          Number(output.qos) !== Number(this.topics.mqtt.command_qos)
          || Boolean(output.retain) !== Boolean(this.topics.mqtt.command_retain)
        ) {
          throw new Error(`${domain} command delivery flags differ from the frozen interface`);
        }
      } else if (output?.published === true) {
        throw new Error(`${domain} published a command while diagnosis mode is active`);
      }
      this.pending.responses[domain] = clone(response);
      this.pending.issued_commands[domain] = {
        cmd,
        topic: expectedTopic,
        publisher: "model_service",
        published: this.commandOutputEnabled,
        mid: output?.mid ?? null,
      };
      this.rememberResponse(response);
      this.pending[`${domain}_latency_ms`] = this.now() - this.pending[`${domain}_started_ms`];
      if (!this.pending.responses.vgr || !this.pending.responses.hbw) {
        return [];
      }
      return this.completeCycle();
    } catch (error) {
      return this.enterFault(`${domain}_response:${error.message}`);
    }
  }

  commandSet(vgrCmd, hbwCmd) {
    return [
      ["vgr", Number(vgrCmd), this.topics.command_topics.vgr[String(vgrCmd)]],
      ["hbw", Number(hbwCmd), this.topics.command_topics.hbw[String(hbwCmd)]],
      ["mpo", 0, this.topics.command_topics.mpo["0"]],
      ["sld", 0, this.topics.command_topics.sld["0"]],
    ];
  }

  completeCycle() {
    const finished = this.now();
    const cycle = this.pending;
    const vgrCmd = Number(cycle.responses.vgr.cmd);
    const hbwCmd = Number(cycle.responses.hbw.cmd);
    const commands = this.commandSet(vgrCmd, hbwCmd);
    const commandDetails = Object.fromEntries(
      commands.map(([module, cmd, topic]) => [
        module,
        this.pending.issued_commands[module] || {
          cmd,
          topic,
          publisher: module === "vgr" || module === "hbw" ? "model_service" : "ai_flow",
          published: false,
        },
      ]),
    );
    const result = {
      schema_version: "1.0",
      cycle_id: cycle.cycle_id,
      request_id: cycle.parent_request_id,
      source_id: cycle.source_id,
      status: "completed",
      model_ids: this.modelIds(),
      model_contracts: clone(this.contracts),
      empty_storage: cycle.empty_storage,
      vgr_cmd: vgrCmd,
      hbw_cmd: hbwCmd,
      model_predictions: {
        storage: {
          empty_storage: cycle.responses.storage.empty_storage,
          top3: clone(cycle.responses.storage.top3 || []),
        },
        vgr: {
          cmd: vgrCmd,
          name: cycle.responses.vgr.name,
          top3: clone(cycle.responses.vgr.top3 || []),
        },
        hbw: {
          cmd: hbwCmd,
          name: cycle.responses.hbw.name,
          top3: clone(cycle.responses.hbw.top3 || []),
        },
      },
      commands: commandDetails,
      command_output_enabled: this.commandOutputEnabled,
      command_set_complete: Object.values(commandDetails).every(
        (command) => command.published === this.commandOutputEnabled,
      ),
      bootstrap: clone(cycle.bootstrap),
      storage_latency_ms: cycle.storage_latency_ms,
      vgr_latency_ms: cycle.vgr_latency_ms,
      hbw_latency_ms: cycle.hbw_latency_ms,
      duration_ms: finished - cycle.storage_started_ms,
      input_metadata: cycle.input_metadata,
      qos: Number(this.topics.mqtt.command_qos),
      retain: Boolean(this.topics.mqtt.command_retain),
      ts_ms: finished,
    };
    const actions = [
      mqttAction("cycle_result", this.topics.cycle_result_topic, result, 1, false),
      this.orchestrationStatus("ready", "cycle_completed", { cycle_id: cycle.cycle_id }),
    ];
    this.completedRequestIds.add(cycle.parent_request_id);
    this.pending = null;
    return actions;
  }

  enterFault(reason) {
    if (this.fault) {
      return [this.orchestrationStatus("fault_latched", "additional_fault_ignored", { fault: this.fault })];
    }
    const cycle = this.pending;
    this.fault = { reason: String(reason), cycle_id: cycle?.cycle_id || null, ts_ms: this.now() };
    this.queuedLiveState = null;
    const issuedCommands = clone(cycle?.issued_commands || {});
    const actions = [
      mqttAction(
        "cycle_result",
        this.topics.cycle_result_topic,
        {
          schema_version: "1.0",
          cycle_id: cycle?.cycle_id || null,
          request_id: cycle?.parent_request_id || null,
          source_id: cycle?.source_id || null,
          status: "fault_latched",
          error: String(reason),
          model_ids: this.modelIds(),
          model_contracts: clone(this.contracts),
          commands: issuedCommands,
          command_output_enabled: this.commandOutputEnabled,
          command_set_complete: false,
          idle_set_published: false,
          bootstrap: clone(cycle?.bootstrap || {}),
          input_metadata: clone(cycle?.input_metadata || {}),
          qos: Number(this.topics.mqtt.command_qos),
          retain: Boolean(this.topics.mqtt.command_retain),
          ts_ms: this.now(),
        },
        1,
        false,
      ),
      this.orchestrationStatus("fault_latched", String(reason), { fault: this.fault }),
    ];
    this.pending = null;
    return actions;
  }

  tick(nowMs = this.now()) {
    if (this.pending && Number(nowMs) >= Number(this.pending.deadline_ms)) {
      return this.enterFault("inference_timeout");
    }
    return [];
  }

  handleEvent(event, payload, domain = null) {
    switch (event) {
      case "contract":
        return this.registerContract(domain, payload);
      case "status":
        return this.registerStatus(domain, payload);
      case "live_state":
        return this.handleLiveState(payload);
      case "storage_response":
        return this.handleStorageResponse(payload);
      case "vgr_response":
        return this.handleModelResponse("vgr", payload);
      case "hbw_response":
        return this.handleModelResponse("hbw", payload);
      case "control":
        return this.handleControl(payload);
      case "tick":
        return this.tick();
      default:
        return this.enterFault(`unknown_event:${event}`);
    }
  }
}

function createRuntime(options) {
  return new OrchestrationRuntime(options);
}

module.exports = {
  OrchestrationRuntime,
  buildFeatureVector,
  createRuntime,
  oneHotEmptyStorage,
  validateContract,
};
