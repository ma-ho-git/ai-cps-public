"use strict";

const path = require("node:path");

const SUMMARY_COLUMNS = [
  "row_index",
  "request_id_base",
  "cycle_id",
  "phase",
  "trace_phase",
  "attempt_repeat_idx",
  "guard_episode_idx",
  "guard_prefix_idx",
  "guard_process_step_idx",
  "guard_source_episode_id",
  "source_id",
  "trace_profile",
  "factory_seed",
  "factory_base_runtime_vgr_ms",
  "factory_base_runtime_hbw_ms",
  "factory_base_runtime_mpo_ms",
  "factory_base_runtime_sld_ms",
  "storage_model_id",
  "vgr_model_id",
  "hbw_model_id",
  "expected_empty_storage",
  "vgr_storage_pred",
  "hbw_storage_pred",
  "storage_match_vgr",
  "storage_match_hbw",
  "storage_confidence",
  "expected_label_VGR",
  "predicted_label_VGR",
  "vgr_match",
  "vgr_ready",
  "vgr_confidence",
  "vgr_latency_s",
  "expected_label_HBW",
  "predicted_label_HBW",
  "hbw_match",
  "hbw_ready",
  "hbw_confidence",
  "hbw_latency_s",
  "timeout",
  "error",
  "control_enabled",
  "control_published",
  "control_reason",
  "control_command_set_complete",
  "control_vgr_cmd",
  "control_hbw_cmd",
  "control_mpo_cmd",
  "control_sld_cmd",
  "control_vgr_topic",
  "control_hbw_topic",
  "control_mpo_topic",
  "control_sld_topic",
  "control_vgr_publisher",
  "control_hbw_publisher",
  "control_mpo_publisher",
  "control_sld_publisher",
  "control_qos",
  "control_retain",
  "bootstrap_vgr_rows",
  "bootstrap_hbw_rows",
  "module_runtime_vgr_ms",
  "module_runtime_hbw_ms",
  "module_runtime_mpo_ms",
  "module_runtime_sld_ms",
  "job_sent_vgr",
  "job_sent_hbw",
  "job_sent_mpo",
  "job_sent_sld",
  "job_accepted_vgr",
  "job_accepted_hbw",
  "job_accepted_mpo",
  "job_accepted_sld",
];

function csvValue(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function optionalMatch(actual, expected) {
  if (actual === null || actual === undefined || expected === null || expected === undefined) return "";
  return Number(actual) === Number(expected);
}

function selectedProbability(prediction, key, value) {
  const top3 = prediction?.top3;
  if (!Array.isArray(top3)) return "";
  const selected = top3.find((candidate) => Number(candidate?.[key]) === Number(value));
  return selected?.p === undefined ? "" : Number(selected.p);
}

function makeRunId(nowMs = Date.now()) {
  return new Date(nowMs).toISOString().replace(/[-:TZ.]/g, "").slice(0, 18) + "_nodered";
}

function createReportState(reportRoot, nowMs = Date.now()) {
  const runId = makeRunId(nowMs);
  return {
    run_id: runId,
    run_dir: path.join(reportRoot, runId),
    started_at: new Date(nowMs).toISOString(),
    rows: 0,
    matches: { storage: 0, vgr: 0, hbw: 0 },
    faults: 0,
    command_rows: 0,
    idle_fallback_rows: 0,
    factory_run_id: null,
    last_cycle_status: null,
    model_ids: {},
    run_config: {},
  };
}

function summaryRow(result, rowIndex) {
  const meta = result.input_metadata || {};
  const expectedStorage = meta.expected_empty_storage;
  const expectedVgr = meta.expected_label_VGR;
  const expectedHbw = meta.expected_label_HBW;
  const completed = result.status === "completed";
  const commands = result.commands || {};
  return {
    row_index: rowIndex,
    request_id_base: result.request_id || "",
    cycle_id: result.cycle_id || "",
    phase: meta.phase || "live_state",
    trace_phase: meta.trace_phase || "",
    attempt_repeat_idx: meta.attempt_repeat_idx,
    guard_episode_idx: meta.guard_episode_idx,
    guard_prefix_idx: meta.guard_prefix_idx,
    guard_process_step_idx: meta.guard_process_step_idx,
    guard_source_episode_id: meta.guard_source_episode_id,
    source_id: result.source_id || "",
    trace_profile: meta.trace_profile || "",
    factory_seed: meta.factory_seed,
    factory_base_runtime_vgr_ms: meta.factory_base_runtime_ms?.vgr,
    factory_base_runtime_hbw_ms: meta.factory_base_runtime_ms?.hbw,
    factory_base_runtime_mpo_ms: meta.factory_base_runtime_ms?.mpo,
    factory_base_runtime_sld_ms: meta.factory_base_runtime_ms?.sld,
    storage_model_id: result.model_ids?.storage || "",
    vgr_model_id: result.model_ids?.vgr || "",
    hbw_model_id: result.model_ids?.hbw || "",
    expected_empty_storage: expectedStorage,
    vgr_storage_pred: result.empty_storage,
    hbw_storage_pred: result.empty_storage,
    storage_match_vgr: optionalMatch(result.empty_storage, expectedStorage),
    storage_match_hbw: optionalMatch(result.empty_storage, expectedStorage),
    storage_confidence: selectedProbability(
      result.model_predictions?.storage,
      "empty_storage",
      result.empty_storage,
    ),
    expected_label_VGR: expectedVgr,
    predicted_label_VGR: result.vgr_cmd,
    vgr_match: optionalMatch(result.vgr_cmd, expectedVgr),
    vgr_ready: completed,
    vgr_confidence: selectedProbability(result.model_predictions?.vgr, "cmd", result.vgr_cmd),
    vgr_latency_s: result.vgr_latency_ms === undefined ? "" : Number(result.vgr_latency_ms) / 1000,
    expected_label_HBW: expectedHbw,
    predicted_label_HBW: result.hbw_cmd,
    hbw_match: optionalMatch(result.hbw_cmd, expectedHbw),
    hbw_ready: completed,
    hbw_confidence: selectedProbability(result.model_predictions?.hbw, "cmd", result.hbw_cmd),
    hbw_latency_s: result.hbw_latency_ms === undefined ? "" : Number(result.hbw_latency_ms) / 1000,
    timeout: String(result.error || "").includes("timeout"),
    error: result.error || "",
    control_enabled: Boolean(result.command_output_enabled),
    control_published: Boolean(
      result.command_output_enabled
      && completed
      && result.command_set_complete,
    ),
    control_reason: completed
      ? (result.command_output_enabled ? "published_independently" : "disabled")
      : result.status,
    control_command_set_complete: Boolean(result.command_set_complete),
    control_vgr_cmd: commands.vgr?.cmd,
    control_hbw_cmd: commands.hbw?.cmd,
    control_mpo_cmd: commands.mpo?.cmd,
    control_sld_cmd: commands.sld?.cmd,
    control_vgr_topic: commands.vgr?.topic,
    control_hbw_topic: commands.hbw?.topic,
    control_mpo_topic: commands.mpo?.topic,
    control_sld_topic: commands.sld?.topic,
    control_vgr_publisher: commands.vgr?.publisher,
    control_hbw_publisher: commands.hbw?.publisher,
    control_mpo_publisher: commands.mpo?.publisher,
    control_sld_publisher: commands.sld?.publisher,
    control_qos: result.qos,
    control_retain: result.retain,
    bootstrap_vgr_rows: result.bootstrap?.vgr?.seeded_rows,
    bootstrap_hbw_rows: result.bootstrap?.hbw?.seeded_rows,
    module_runtime_vgr_ms: meta.module_runtime_ms?.vgr,
    module_runtime_hbw_ms: meta.module_runtime_ms?.hbw,
    module_runtime_mpo_ms: meta.module_runtime_ms?.mpo,
    module_runtime_sld_ms: meta.module_runtime_ms?.sld,
    job_sent_vgr: meta.module_job_counts?.sent?.vgr,
    job_sent_hbw: meta.module_job_counts?.sent?.hbw,
    job_sent_mpo: meta.module_job_counts?.sent?.mpo,
    job_sent_sld: meta.module_job_counts?.sent?.sld,
    job_accepted_vgr: meta.module_job_counts?.accepted?.vgr,
    job_accepted_hbw: meta.module_job_counts?.accepted?.hbw,
    job_accepted_mpo: meta.module_job_counts?.accepted?.mpo,
    job_accepted_sld: meta.module_job_counts?.accepted?.sld,
  };
}

function recordCycle(state, result, nowMs = Date.now()) {
  const row = summaryRow(result, state.rows);
  state.rows += 1;
  if (row.storage_match_vgr === true) state.matches.storage += 1;
  if (row.vgr_match === true) state.matches.vgr += 1;
  if (row.hbw_match === true) state.matches.hbw += 1;
  if (result.status === "fault_latched") state.faults += 1;
  if (row.control_published) state.command_rows += 1;
  if (result.idle_set_published) state.idle_fallback_rows += 1;
  state.factory_run_id = state.factory_run_id
    || result.input_metadata?.simulation_run_id
    || result.input_metadata?.correlation_id
    || null;
  state.last_cycle_status = result.status || null;
  state.model_ids = result.model_ids || state.model_ids;
  state.run_config = {
    trace_profile: row.trace_profile,
    seed: row.factory_seed,
    base_runtime_ms: {
      vgr: row.factory_base_runtime_vgr_ms,
      hbw: row.factory_base_runtime_hbw_ms,
      mpo: row.factory_base_runtime_mpo_ms,
      sld: row.factory_base_runtime_sld_ms,
    },
  };

  const header = SUMMARY_COLUMNS.join(",") + "\n";
  const csv = SUMMARY_COLUMNS.map((column) => csvValue(row[column])).join(",") + "\n";
  const runSummary = buildRunSummary(state, {
    completed: false,
    stopped: result.status === "fault_latched",
    stopReason: result.status === "fault_latched" ? "fault_latched" : "running",
    nowMs,
  });
  return {
    state,
    files: [
      { role: "events", filename: path.join(state.run_dir, "events.jsonl"), payload: JSON.stringify(result) + "\n", append: true },
      { role: "summary", filename: path.join(state.run_dir, "summary.csv"), payload: (state.rows === 1 ? header : "") + csv, append: true },
      runSummaryFile(state, runSummary),
    ],
    row,
    run_summary: runSummary,
  };
}

function buildRunSummary(
  state,
  {
    completed = false,
    stopped = false,
    stopReason = "running",
    factoryStatus = null,
    nowMs = Date.now(),
  } = {},
) {
  const summary = {
    mode: "live_mqtt_nodered",
    completed,
    stopped,
    stop_reason: stopReason,
    last_cycle_status: state.last_cycle_status,
    rows_completed: state.rows,
    control_published_rows: state.command_rows,
    control_published_commands: state.command_rows * 4,
    control_idle_fallback_rows: state.idle_fallback_rows,
    faults: state.faults,
    storage_matches_vgr: state.matches.storage,
    storage_matches_hbw: state.matches.storage,
    vgr_matches: state.matches.vgr,
    hbw_matches: state.matches.hbw,
    model_ids: state.model_ids,
    run_config: state.run_config,
    started_at: state.started_at,
    updated_at: new Date(nowMs).toISOString(),
    events_path: path.join(state.run_dir, "events.jsonl"),
    summary_path: path.join(state.run_dir, "summary.csv"),
  };
  if (factoryStatus) {
    summary.factory_status = {
      run_id: factoryStatus.run_id,
      trace_total: factoryStatus.trace_total,
      payloads_sent: factoryStatus.payloads_sent,
      progress_percent: factoryStatus.progress_percent,
      sent_counts: factoryStatus.sent_counts,
      accepted_counts: factoryStatus.accepted_counts,
    };
  }
  return summary;
}

function runSummaryFile(state, runSummary) {
  return {
    role: "run_summary",
    filename: path.join(state.run_dir, "run_summary.json"),
    payload: JSON.stringify(runSummary, null, 2) + "\n",
    append: false,
  };
}

function finalizeRun(state, factoryStatus, nowMs = Date.now()) {
  if (!state || !factoryStatus || !["completed", "reset"].includes(factoryStatus.state)) {
    return null;
  }
  if (
    !state.factory_run_id
    || !factoryStatus.run_id
    || String(factoryStatus.run_id) !== String(state.factory_run_id)
  ) {
    return null;
  }
  const completed = factoryStatus.state === "completed";
  const runSummary = buildRunSummary(state, {
    completed,
    stopped: !completed,
    stopReason: completed ? "completed" : "reset",
    factoryStatus,
    nowMs,
  });
  return {
    state,
    files: [runSummaryFile(state, runSummary)],
    run_summary: runSummary,
  };
}

module.exports = {
  SUMMARY_COLUMNS,
  buildRunSummary,
  createReportState,
  finalizeRun,
  makeRunId,
  recordCycle,
  summaryRow,
};
