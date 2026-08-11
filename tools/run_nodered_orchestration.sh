#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCENARIO_DIR="$REPO_ROOT/scenarios/serve_ft_nns_external_broker/x86_64"
BASE_COMPOSE="$SCENARIO_DIR/docker-compose.yml"
VIRTUAL_COMPOSE="$SCENARIO_DIR/docker-compose.virtual.yml"
ENV_FILE_DEFAULT="$REPO_ROOT/.env"

usage() {
  cat <<'EOF'
Usage: ./tools/run_nodered_orchestration.sh <command> [options]

Commands:
  physical-up     Startet Storage, VGR und HBW und wartet auf MQTT-Bereitschaft.
  virtual-up      Startet Mosquitto, Node-RED und die drei NN-Container.
  virtual-hmi     Startet den virtuellen Stack, wartet auf `ready` und oeffnet keinen Lauf.
  virtual-run     Startet/resetet den virtuellen Stack, wartet auf frisches `ready` und zuendet einmal.
  physical-preflight Prueft nur den physischen Drei-NN-Pfad und den externen Broker.
  virtual-preflight  Prueft den vollstaendigen virtuellen Stack.
  physical-status Zeigt den Compose-Status der drei physischen NN-Dienste.
  virtual-status  Zeigt den Compose-Status des virtuellen Stacks.
  physical-down   Stoppt nur die drei physischen NN-Dienste.
  virtual-down    Stoppt den virtuellen Stack; persistente Volumes bleiben erhalten.
  start           Publiziert {"cmd":"start"} an ft/sim/factory/control.
  reset           Setzt virtuelle Fabrik und verriegelte KI-Orchestrierung zurueck.
  status          Rueckwaertskompatibler Alias fuer virtual-status.
  monitor         Beobachtet Live-, Status-, Ergebnis- und Command-Topics.
  preflight       Rueckwaertskompatibler Alias fuer virtual-preflight.
  flow-update     Aktualisiert den persistenten virtuellen Flow bewusst.
  down            Rueckwaertskompatibler Alias fuer virtual-down.

Options:
  --no-build      Vorhandene Images verwenden.
  --images        Gepinnte Runtime-Images aus GHCR statt lokaler Builds verwenden.
  --diagnosis     Command-Output deaktivieren (nur fuer virtual-up/virtual-hmi/virtual-run).
  --command-output-enabled
                  Direkte VGR-/HBW-Commands im physischen Betrieb bewusst freigeben.
  --trace-profile NAME
                  Virtueller Trace: standard, full-storage-attempt oder
                  full-storage-process-guard.
  --model-profile NAME
                  Virtuelles Modellprofil: deployment-current oder
                  historical-full-storage-error.
  --env-file PATH Andere Umgebungsdatei statt .env verwenden.
  --skip-preflight Preflight bewusst ueberspringen.

Model selection (.env):
  STORAGE_MODEL_DIR, VGR_MODEL_DIR, HBW_MODEL_DIR
                  Optionaler Pfad unter /model_registry; leer bedeutet den
                  versionierten Standard /model_registry/<domain>/latest.
  STORAGE_IMAGE, VGR_IMAGE, HBW_IMAGE
                  Vollstaendige Referenz eines MQTT-kompatiblen Ersatzimages;
                  nur zusammen mit --images verwenden.
  NODE_RED_IMAGE  Optionale vollstaendige Referenz des virtuellen
                  Node-RED-/Dashboard-Images.

Virtual factory runtimes (.env, milliseconds):
  FACTORY_VGR_BASE_RUNTIME_MS, FACTORY_HBW_BASE_RUNTIME_MS,
  FACTORY_MPO_BASE_RUNTIME_MS, FACTORY_SLD_BASE_RUNTIME_MS
                  Positive Ganzzahlen; Standard jeweils 100. Pro Command
                  reproduzierbare Variation von -50 bis +50 Prozent.

Virtual HMI:
  Nach `virtual-hmi` ist die Bedienseite unter
  http://localhost:1880/dashboard/betrieb erreichbar.

Portable release setup:
  python3 tools/setup_portable_runtime.py init --mode virtual \
    --release runtime-v1.2.0
  Danach mit `virtual-hmi --images` starten. COMPOSE_PROJECT_NAME trennt
  mehrere lokale Standortinstallationen voneinander.

Safe model change:
  Stack stoppen, Kandidat mit tools/manage_model_candidates.py add/select
  waehlen, virtual-run ausfuehren und Reports mit compare_model_runs.py
  vergleichen. Kein Hot-Swap waehrend eines Zyklus.

Examples:
  MQTT_HOST=192.168.0.5 ./tools/run_nodered_orchestration.sh physical-up
  MQTT_HOST=192.168.0.5 ./tools/run_nodered_orchestration.sh physical-up --command-output-enabled
  ./tools/run_nodered_orchestration.sh physical-status
  ./tools/run_nodered_orchestration.sh virtual-run
  ./tools/run_nodered_orchestration.sh virtual-hmi
  FACTORY_VGR_BASE_RUNTIME_MS=200 ./tools/run_nodered_orchestration.sh virtual-run
  ./tools/run_nodered_orchestration.sh virtual-run --diagnosis
  ./tools/run_nodered_orchestration.sh virtual-run --trace-profile full-storage-attempt
  ./tools/run_nodered_orchestration.sh virtual-run --trace-profile full-storage-process-guard
  ./tools/run_nodered_orchestration.sh virtual-run \
    --trace-profile full-storage-attempt \
    --model-profile historical-full-storage-error

Testszenarien im Dashboard:
  standard                   Normalbetrieb - Einlagerungen und Idle-Phasen (320 Zustaende)
  full-storage-attempt       Vollspeicher - 20 wiederholte Einlagerungsversuche (157 Zustaende)
  full-storage-process-guard Vollspeicher - 9 vollstaendige Prozesssequenzen (308 Zustaende)
  python3 tools/manage_model_candidates.py status
  ./tools/run_nodered_orchestration.sh monitor
  ./tools/run_nodered_orchestration.sh virtual-down
EOF
}

die() {
  printf '[NODE-RED][ERROR] %s\n' "$*" >&2
  exit 1
}

info() {
  printf '[NODE-RED] %s\n' "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Command fehlt: $1"
}

require_docker() {
  require_command docker
  docker compose version >/dev/null 2>&1 || die "Docker Compose ist nicht verfuegbar."
  docker info >/dev/null 2>&1 || die "Docker-Daemon ist nicht erreichbar."
}

load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS='=' read -r raw_key raw_value; do
    local key value
    key="${raw_key//[[:space:]]/}"
    [[ -n "$key" && "$key" != \#* ]] || continue
    value="${raw_value%$'\r'}"
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"
    if [[ -z "${!key+x}" ]]; then
      printf -v "$key" '%s' "$value"
      export "$key"
    fi
  done < "$file"
}

ensure_no_conflicting_nn_consumers() {
  local conflicts current_project
  current_project="${COMPOSE_PROJECT_NAME:-ai-cps-nn-runtime}"
  conflicts="$(docker ps --format '{{.Names}} {{.Label "com.docker.compose.project"}} {{.Label "com.docker.compose.service"}}' \
    | awk -v project="$current_project" '$3 ~ /^(storage_infer|vgr_infer|hbw_infer)$/ && $2 != project {print}')"
  if [[ -n "$conflicts" ]]; then
    printf '[NODE-RED][ERROR] Fremde NN-Consumer abonnieren dieselben ft/nn/*/request-Topics:\n%s\n' "$conflicts" >&2
    die "Stoppe den Legacy-Stack oder verwende fuer Shadow-Tests getrennte Broker/Topic-Namespaces."
  fi
}

base_compose() {
  local env_args=()
  [[ -f "$ENV_FILE" ]] && env_args=(--env-file "$ENV_FILE")
  docker compose "${env_args[@]}" -f "$BASE_COMPOSE" "$@"
}

virtual_compose() {
  local env_args=()
  [[ -f "$ENV_FILE" ]] && env_args=(--env-file "$ENV_FILE")
  docker compose "${env_args[@]}" -f "$BASE_COMPOSE" -f "$VIRTUAL_COMPOSE" "$@"
}

preserve_running_node_red_configuration() {
  local container_id env_line key value
  container_id="$(virtual_compose ps -q node_red 2>/dev/null || true)"
  [[ -n "$container_id" ]] || return 0

  while IFS= read -r env_line; do
    key="${env_line%%=*}"
    value="${env_line#*=}"
    case "$key" in
      COMMAND_OUTPUT_ENABLED|TRACE_PROFILE|MODEL_PROFILE|LIVE_TRACE_PAYLOADS|FACTORY_SEED|\
      FACTORY_VGR_BASE_RUNTIME_MS|FACTORY_HBW_BASE_RUNTIME_MS|\
      FACTORY_MPO_BASE_RUNTIME_MS|FACTORY_SLD_BASE_RUNTIME_MS)
        printf -v "$key" '%s' "$value"
        export "$key"
        ;;
    esac
  done < <(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container_id")

  info "Uebernehme die aktive virtuelle Laufkonfiguration fuer den erneuerten Node-RED-Container."
}

parse_options() {
  BUILD=1
  USE_IMAGES=0
  DIAGNOSIS=0
  FORCE_COMMAND_OUTPUT=0
  SKIP_PREFLIGHT=0
  ENV_FILE="$ENV_FILE_DEFAULT"
  TRACE_PROFILE_CLI=""
  TRACE_PROFILE_EXPLICIT=0
  MODEL_PROFILE_CLI=""
  MODEL_PROFILE_EXPLICIT=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-build) BUILD=0 ;;
      --images) USE_IMAGES=1; BUILD=0 ;;
      --diagnosis) DIAGNOSIS=1 ;;
      --command-output-enabled) FORCE_COMMAND_OUTPUT=1 ;;
      --skip-preflight) SKIP_PREFLIGHT=1 ;;
      --trace-profile)
        shift
        [[ $# -gt 0 ]] || die "--trace-profile benoetigt einen Namen."
        TRACE_PROFILE_CLI="$1"
        TRACE_PROFILE_EXPLICIT=1
        ;;
      --model-profile)
        shift
        [[ $# -gt 0 ]] || die "--model-profile benoetigt einen Namen."
        MODEL_PROFILE_CLI="$1"
        MODEL_PROFILE_EXPLICIT=1
        ;;
      --env-file)
        shift
        [[ $# -gt 0 ]] || die "--env-file benoetigt einen Pfad."
        ENV_FILE="$1"
        ;;
      *) die "Unbekannte Option: $1" ;;
    esac
    shift
  done
  load_env_file "$ENV_FILE"
  TRACE_PROFILE="${TRACE_PROFILE_CLI:-${TRACE_PROFILE:-standard}}"
  case "$TRACE_PROFILE" in
    standard)
      LIVE_TRACE_PAYLOADS="/opt/ai-cps-node-red/data/live_plc_trace/payloads.jsonl"
      ;;
    full-storage-attempt)
      LIVE_TRACE_PAYLOADS="/opt/ai-cps-node-red/data/live_plc_full_storage_attempt/payloads.jsonl"
      ;;
    full-storage-process-guard)
      LIVE_TRACE_PAYLOADS="/opt/ai-cps-node-red/data/live_plc_full_storage_process_guard/payloads.jsonl"
      ;;
    *) die "Unbekanntes Trace-Profil: $TRACE_PROFILE (erlaubt: standard, full-storage-attempt, full-storage-process-guard)" ;;
  esac
  export TRACE_PROFILE LIVE_TRACE_PAYLOADS
  MODEL_PROFILE="${MODEL_PROFILE_CLI:-${MODEL_PROFILE:-deployment-current}}"
  case "$MODEL_PROFILE" in
    deployment-current|historical-full-storage-error) ;;
    *) die "Unbekanntes Modellprofil: $MODEL_PROFILE (erlaubt: deployment-current, historical-full-storage-error)" ;;
  esac
  export MODEL_PROFILE
  MQTT_HOST="${MQTT_HOST:-localhost}"
  MQTT_PORT="${MQTT_PORT:-1883}"
  MQTT_CLI_HOST="${VIRTUAL_MQTT_HOST:-localhost}"
  READY_TIMEOUT_S="${READY_TIMEOUT_S:-180}"
  COMMAND_OUTPUT_ENABLED="${COMMAND_OUTPUT_ENABLED:-false}"
  if [[ "$FORCE_COMMAND_OUTPUT" == "1" ]]; then
    COMMAND_OUTPUT_ENABLED=true
    export COMMAND_OUTPUT_ENABLED
  fi
}

configure_image_mode() {
  if [[ "$USE_IMAGES" == "1" ]]; then
    local owner="${GHCR_OWNER:-ma-ho-git}"
    local domain image_key repository_key
    for domain in STORAGE VGR HBW; do
      image_key="${domain}_IMAGE"
      repository_key="${domain}_IMAGE_REPOSITORY"
      if [[ -z "${!image_key:-}" ]]; then
        [[ -n "${IMAGE_TAG:-}" && "${IMAGE_TAG:-}" != "local" ]] \
          || die "--images benoetigt ${image_key}=<vollstaendiges-image> oder IMAGE_TAG=<release- oder sha-Tag>."
        printf -v "$repository_key" 'ghcr.io/%s/ai-cps-runtime-%s-infer' "$owner" "${domain,,}"
        export "$repository_key"
      fi
    done
    if [[ -z "${NODE_RED_IMAGE:-}" && -n "${IMAGE_TAG:-}" && "${IMAGE_TAG:-}" != "local" ]]; then
      NODE_RED_IMAGE_REPOSITORY="ghcr.io/${owner}/ai-cps-runtime-node-red"
      export NODE_RED_IMAGE_REPOSITORY
    fi
  elif [[ -n "${STORAGE_IMAGE:-}${VGR_IMAGE:-}${HBW_IMAGE:-}${NODE_RED_IMAGE:-}" ]]; then
    die "Vollstaendige *_IMAGE-Referenzen werden nur mit --images verwendet; so wird kein fremdes Image versehentlich lokal ueberschrieben."
  fi
}

command_uses_runtime_images() {
  case "$1" in
    physical-up|virtual-up|virtual-hmi|virtual-run|physical-preflight|virtual-preflight|preflight)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

run_preflight() {
  local mode="$1"
  [[ "$SKIP_PREFLIGHT" == "1" ]] && return 0
  local options=(--mode "$mode" --env-file "$ENV_FILE")
  [[ "$USE_IMAGES" == "1" ]] && options+=(--images)
  local python_bin="$REPO_ROOT/.venv/bin/python"
  [[ -x "$python_bin" ]] || python_bin="$(command -v python3 || true)"
  [[ -n "$python_bin" ]] || die "Python 3 fehlt fuer den Deployment-Preflight."
  "$python_bin" "$REPO_ROOT/tools/check_deployment_readiness.py" "${options[@]}"
}

ensure_report_root() {
  local configured="${REPORT_ROOT_HOST:-../../../reports}"
  if [[ "$configured" = /* ]]; then
    mkdir -p "$configured"
  else
    mkdir -p "$SCENARIO_DIR/$configured"
  fi
}

pull_nn_images() {
  info "Lade NN-Images mit Tag ${IMAGE_TAG}."
  base_compose pull storage_infer vgr_infer hbw_infer
}

pull_virtual_images() {
  local owner="${GHCR_OWNER:-ma-ho-git}"
  if [[ -z "${NODE_RED_IMAGE:-}" ]]; then
    [[ -n "${IMAGE_TAG:-}" && "${IMAGE_TAG:-}" != "local" ]] \
      || die "--images im virtuellen Modus benoetigt NODE_RED_IMAGE=<vollstaendiges-image> oder einen unveraenderlichen IMAGE_TAG."
    NODE_RED_IMAGE_REPOSITORY="ghcr.io/${owner}/ai-cps-runtime-node-red"
    export NODE_RED_IMAGE_REPOSITORY
  fi
  info "Lade NN- und Node-RED-Images mit Tag ${IMAGE_TAG:-vollstaendige Referenz}."
  virtual_compose pull storage_infer vgr_infer hbw_infer node_red
}

physical_nn_instance_map() {
  local domain service container_id instance_id
  for domain in storage vgr hbw; do
    service="${domain}_infer"
    container_id="$(base_compose ps -q "$service" 2>/dev/null || true)"
    [[ -n "$container_id" ]] || return 1
    instance_id="$(docker inspect --format '{{.Config.Hostname}}' "$container_id" 2>/dev/null || true)"
    [[ -n "$instance_id" ]] || return 1
    printf '%s=%s\n' "$domain" "$instance_id"
  done
}

physical_nn_statuses_match() {
  local payload_lines="$1"
  local expected_instances="$2"
  local python_bin="$REPO_ROOT/.venv/bin/python"
  [[ -x "$python_bin" ]] || python_bin="$(command -v python3 || true)"
  [[ -n "$python_bin" ]] || return 1

  PHYSICAL_NN_STATUS_LINES="$payload_lines" EXPECTED_NN_INSTANCES="$expected_instances" \
    "$python_bin" -c '
import json
import os
import sys

expected = {}
for line in os.environ["EXPECTED_NN_INSTANCES"].splitlines():
    domain, separator, instance_id = line.partition("=")
    if separator and domain and instance_id:
        expected[domain] = instance_id

ready = set()
for line in os.environ["PHYSICAL_NN_STATUS_LINES"].splitlines():
    topic, separator, raw_payload = line.partition(" ")
    if not separator:
        continue
    parts = topic.split("/")
    if len(parts) != 4 or parts[:2] != ["ft", "nn"] or parts[3] != "status":
        continue
    domain = parts[2]
    try:
        status = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        continue
    if (
        domain in expected
        and status.get("state") == "online"
        and status.get("detail") == "model_loaded"
        and str(status.get("instance_id", "")) == expected[domain]
    ):
        ready.add(domain)

sys.exit(0 if ready == set(expected) == {"storage", "vgr", "hbw"} else 1)
' >/dev/null 2>&1
}

read_physical_nn_statuses() {
  mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" "${MQTT_AUTH_ARGS[@]}" -v \
    -t 'ft/nn/+/status' -C 3 -W 2 2>/dev/null || true
}

wait_physical_nn_ready() {
  local expected_instances="$1"
  local first_payload second_payload
  require_command mosquitto_sub
  info "Warte auf Storage, VGR und HBW: aktuelle Containerinstanz, Modell geladen und MQTT online."
  local deadline=$((SECONDS + READY_TIMEOUT_S))
  while (( SECONDS < deadline )); do
    first_payload="$(read_physical_nn_statuses)"
    if physical_nn_statuses_match "$first_payload" "$expected_instances"; then
      # runtime-v1.2.0 publiziert den Online-Status unmittelbar vor subscribe().
      # Eine zweite identische Sicht nach kurzer Stabilisierung schliesst diese
      # kleine Start-Race auch fuer bereits veroeffentlichte Images praktisch aus.
      sleep 1
      second_payload="$(read_physical_nn_statuses)"
      if physical_nn_statuses_match "$second_payload" "$expected_instances"; then
        return 0
      fi
    fi
    sleep 1
  done
  die "NN-Dienste wurden innerhalb von ${READY_TIMEOUT_S}s nicht MQTT-ready. Pruefe: docker compose logs storage_infer vgr_infer hbw_infer"
}

physical_up() {
  require_docker
  if [[ "$USE_IMAGES" == "1" ]]; then
    pull_nn_images
  fi
  run_preflight physical
  ensure_no_conflicting_nn_consumers
  local options=(-d)
  if [[ "$USE_IMAGES" == "1" ]]; then
    options+=(--no-build)
  elif [[ "$BUILD" == "1" ]]; then
    options+=(--build)
  else
    options+=(--no-build)
  fi
  info "Starte ausschliesslich die drei NN-Anwendungscontainer gegen ${MQTT_HOST}:${MQTT_PORT} (Command-Output=${COMMAND_OUTPUT_ENABLED})."
  MQTT_HOST="$MQTT_HOST" MQTT_PORT="$MQTT_PORT" COMMAND_OUTPUT_ENABLED="$COMMAND_OUTPUT_ENABLED" \
    base_compose up "${options[@]}"
  local expected_instances
  if ! expected_instances="$(physical_nn_instance_map)"; then
    die "Die drei gestarteten NN-Containerinstanzen konnten nicht eindeutig bestimmt werden."
  fi
  wait_physical_nn_ready "$expected_instances"
  if [[ "${COMMAND_OUTPUT_ENABLED,,}" == "true" ]]; then
    info "[BEREIT] Storage, VGR und HBW sind MQTT-ready; Command-Ausgabe ist aktiv. Die Anlage kann jetzt eingeschaltet werden."
  else
    info "[BEREIT] Storage, VGR und HBW sind MQTT-ready. Diagnosebetrieb: VGR-/HBW-Commands bleiben deaktiviert."
  fi
}

physical_status() {
  require_docker
  base_compose ps
}

virtual_status() {
  require_docker
  virtual_compose ps
}

physical_down() {
  require_docker
  base_compose down
}

virtual_down() {
  require_docker
  virtual_compose down
}

virtual_up() {
  require_docker
  if [[ "$USE_IMAGES" == "1" ]]; then
    pull_virtual_images
  fi
  run_preflight virtual
  ensure_no_conflicting_nn_consumers
  local options=(-d)
  if [[ "$USE_IMAGES" == "1" ]]; then
    options+=(--no-build)
  elif [[ "$BUILD" == "1" ]]; then
    options+=(--build)
  else
    options+=(--no-build)
  fi
  local output=true
  [[ "$DIAGNOSIS" == "1" ]] && output=false
  ensure_report_root
  info "Starte persistenten Mosquitto-/Node-RED-Teststack (Command-Output=${output}, Testszenario=${TRACE_PROFILE}, Modellprofil=${MODEL_PROFILE})."
  COMMAND_OUTPUT_ENABLED="$output" virtual_compose up "${options[@]}"
}

status_is_fresh_ready() {
  local payload="$1"
  local not_before_ms="$2"
  local python_bin="$REPO_ROOT/.venv/bin/python"
  [[ -x "$python_bin" ]] || python_bin="$(command -v python3 || true)"
  [[ -n "$python_bin" ]] || return 1

  READY_PAYLOAD="$payload" READY_NOT_BEFORE_MS="$not_before_ms" "$python_bin" -c '
import json
import os
import sys

try:
    status = json.loads(os.environ["READY_PAYLOAD"])
    is_fresh = (
        status.get("state") == "ready"
        and int(status.get("ts_ms", -1)) >= int(os.environ["READY_NOT_BEFORE_MS"])
    )
except (TypeError, ValueError, json.JSONDecodeError):
    is_fresh = False
sys.exit(0 if is_fresh else 1)
' >/dev/null 2>&1
}

request_virtual_reset() {
  # Die beiden Resets machen virtual-run auch bei einem bereits laufenden,
  # persistenten Stack reproduzierbar. Fehler sind waehrend des Brokerstarts
  # erwartbar; wait_ready versucht es bis zum Timeout erneut.
  mosquitto_pub -h "$MQTT_CLI_HOST" -p "$MQTT_PORT" "${MQTT_AUTH_ARGS[@]}" \
    -q 1 -t 'ft/sim/factory/control' -m '{"cmd":"reset"}' >/dev/null 2>&1 || true
  mosquitto_pub -h "$MQTT_CLI_HOST" -p "$MQTT_PORT" "${MQTT_AUTH_ARGS[@]}" \
    -q 1 -t 'ft/ai/orchestration/control' -m '{"cmd":"reset"}' >/dev/null 2>&1 || true
}

wait_ready() {
  local not_before_ms="${1:-0}"
  local reset_before_start="${2:-0}"
  require_command mosquitto_sub
  [[ "$reset_before_start" == "1" ]] && require_command mosquitto_pub
  info "Warte auf einen frischen retained ready-Status (ts_ms >= ${not_before_ms})."
  local deadline=$((SECONDS + READY_TIMEOUT_S))
  while (( SECONDS < deadline )); do
    local payload
    if [[ "$reset_before_start" == "1" ]]; then
      request_virtual_reset
    fi
    payload="$(mosquitto_sub -h "$MQTT_CLI_HOST" -p "$MQTT_PORT" "${MQTT_AUTH_ARGS[@]}" -t 'ft/ai/orchestration/status' -C 1 -W 2 2>/dev/null || true)"
    if status_is_fresh_ready "$payload" "$not_before_ms"; then
      return 0
    fi
    sleep 1
  done
  die "Orchestrierung wurde innerhalb von ${READY_TIMEOUT_S}s nicht ready. Pruefe: virtual_compose logs node_red storage_infer vgr_infer hbw_infer"
}

wait_hmi_ready() {
  require_command curl
  local timeout_s="${HMI_READY_TIMEOUT_S:-60}"
  local deadline=$((SECONDS + timeout_s))
  local url="http://localhost:${NODE_RED_PORT:-1880}/dashboard/betrieb"

  while (( SECONDS < deadline )); do
    if curl --fail --silent --show-error --output /dev/null "$url"; then
      return 0
    fi
    sleep 1
  done

  die "Dashboard-Route ist unter $url nicht erreichbar. Bei einem bestehenden Node-RED-Volume zuerst ein Backup erstellen und danach ./tools/run_nodered_orchestration.sh flow-update ausfuehren."
}

factory_start() {
  require_command mosquitto_pub
  local payload
  printf -v payload '{"cmd":"start","config":{"model_profile":"%s","trace_profile":"%s","seed":%s,"base_runtime_ms":{"vgr":%s,"hbw":%s,"mpo":%s,"sld":%s}}}' \
    "$MODEL_PROFILE" "$TRACE_PROFILE" "${FACTORY_SEED:-42}" \
    "${FACTORY_VGR_BASE_RUNTIME_MS:-100}" "${FACTORY_HBW_BASE_RUNTIME_MS:-100}" \
    "${FACTORY_MPO_BASE_RUNTIME_MS:-100}" "${FACTORY_SLD_BASE_RUNTIME_MS:-100}"
  info "Publiziere die einmalige Initialzuendung auf ft/sim/factory/control (Testszenario=${TRACE_PROFILE}, Modellprofil=${MODEL_PROFILE})."
  mosquitto_pub -h "$MQTT_CLI_HOST" -p "$MQTT_PORT" "${MQTT_AUTH_ARGS[@]}" -q 1 -t 'ft/sim/factory/control' -m "$payload"
}

reset_all() {
  require_command mosquitto_pub
  mosquitto_pub -h "$MQTT_CLI_HOST" -p "$MQTT_PORT" "${MQTT_AUTH_ARGS[@]}" -q 1 -t 'ft/sim/factory/control' -m '{"cmd":"reset"}'
  mosquitto_pub -h "$MQTT_CLI_HOST" -p "$MQTT_PORT" "${MQTT_AUTH_ARGS[@]}" -q 1 -t 'ft/ai/orchestration/control' -m '{"cmd":"reset"}'
  info "Fabrikemulator und KI-Buffer wurden zurueckgesetzt."
}

main() {
  local command="${1:-help}"
  [[ $# -gt 0 ]] && shift

  # Hilfe muss auch mit einer unvollstaendigen oder release-gepinnten .env
  # erreichbar bleiben. Sie liest deshalb bewusst keine Standortkonfiguration.
  if [[ "$command" == "help" || "$command" == "-h" || "$command" == "--help" ]]; then
    usage
    return 0
  fi

  parse_options "$@"
  if [[ "$DIAGNOSIS" == "1" && "$FORCE_COMMAND_OUTPUT" == "1" ]]; then
    die "--diagnosis und --command-output-enabled duerfen nicht gemeinsam verwendet werden."
  fi
  if [[ "$DIAGNOSIS" == "1" && "$command" != "virtual-up" && "$command" != "virtual-hmi" && "$command" != "virtual-run" ]]; then
    die "--diagnosis gilt nur fuer virtual-up/virtual-hmi/virtual-run. physical-up ist ohne --command-output-enabled bereits Diagnosebetrieb."
  fi
  if [[ "$FORCE_COMMAND_OUTPUT" == "1" && "$command" != "physical-up" ]]; then
    die "--command-output-enabled gilt nur fuer physical-up; virtual-up/virtual-run sind ohne --diagnosis bereits freigegeben."
  fi
  if [[ "$TRACE_PROFILE_EXPLICIT" == "1" && "$command" != "virtual-up" && "$command" != "virtual-hmi" && "$command" != "virtual-run" ]]; then
    die "--trace-profile gilt nur fuer virtual-up/virtual-hmi/virtual-run."
  fi
  if [[ "$MODEL_PROFILE_EXPLICIT" == "1" && "$command" != "virtual-up" && "$command" != "virtual-hmi" && "$command" != "virtual-run" ]]; then
    die "--model-profile gilt nur fuer virtual-up/virtual-hmi/virtual-run."
  fi
  if command_uses_runtime_images "$command"; then
    configure_image_mode
  fi
  MQTT_AUTH_ARGS=()
  if [[ -n "${MQTT_USER:-}" ]]; then
    MQTT_AUTH_ARGS=(-u "$MQTT_USER")
    [[ -n "${MQTT_PASS:-}" ]] && MQTT_AUTH_ARGS+=(-P "$MQTT_PASS")
  fi
  case "$command" in
    physical-up) physical_up ;;
    virtual-up) virtual_up ;;
    virtual-hmi)
      local ready_not_before_ms
      virtual_up
      ready_not_before_ms="$(date +%s%3N)"
      wait_ready "$ready_not_before_ms" 1
      wait_hmi_ready
      info "Dashboard bereit: http://localhost:${NODE_RED_PORT:-1880}/dashboard/betrieb"
      info "Modellprofil, Testszenario, Seed und Modulbasiszeiten werden vor dem Start im HMI gewaehlt."
      ;;
    virtual-run)
      local ready_not_before_ms
      virtual_up
      ready_not_before_ms="$(date +%s%3N)"
      wait_ready "$ready_not_before_ms" 1
      factory_start
      info "Der Semaphor-Regelkreis laeuft jetzt selbststaendig bis zum Trace-Ende oder Reset."
      ;;
    physical-preflight) run_preflight physical ;;
    virtual-preflight|preflight) run_preflight virtual ;;
    physical-status) physical_status ;;
    virtual-status|status) virtual_status ;;
    physical-down) physical_down ;;
    virtual-down|down) virtual_down ;;
    start) factory_start ;;
    reset) reset_all ;;
    monitor)
      require_command mosquitto_sub
      mosquitto_sub -h "$MQTT_CLI_HOST" -p "$MQTT_PORT" "${MQTT_AUTH_ARGS[@]}" -v \
        -t 'log/logging/state' \
        -t 'ft/nn/+/contract' \
        -t 'ft/nn/+/status' \
        -t 'ft/ai/orchestration/#' \
        -t 'ft/sim/factory/#' \
        -t 'ai/+/+'
      ;;
    flow-update)
      require_docker
      preserve_running_node_red_configuration
      info "Stoppe Node-RED und ersetze den persistenten Runtime-Stand explizit."
      virtual_compose stop node_red
      virtual_compose run --rm --no-deps \
        -e AI_CPS_FORCE_RUNTIME_UPDATE=true node_red install-only
      virtual_compose up -d --no-deps node_red
      ;;
    *)
      usage
      die "Unbekanntes Command: $command"
      ;;
  esac
}

main "$@"
