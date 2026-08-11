#!/bin/sh
set -eu

SOURCE_ROOT="${AI_CPS_RUNTIME_SOURCE:-/opt/ai-cps-node-red}"
RUNTIME_ROOT="${AI_CPS_RUNTIME_ROOT:-/data/ai-cps-runtime}"
MARKER="$RUNTIME_ROOT/.ai-cps-runtime-version"
RUNTIME_VERSION="${AI_CPS_RUNTIME_VERSION:-1.1.3-dashboard}"

install_runtime() {
  force="${1:-false}"
  installed_version=""
  if [ -f "$MARKER" ] && [ "$force" != "true" ]; then
    installed_version="$(cat "$MARKER")"
    if [ "$installed_version" != "$RUNTIME_VERSION" ]; then
      printf '[NODE-RED][WARN] persistent runtime %s is older than image %s; run ./tools/run_nodered_orchestration.sh flow-update after creating a backup\n' \
        "$installed_version" "$RUNTIME_VERSION" >&2
    else
      printf '[NODE-RED] Reusing persistent runtime %s\n' "$installed_version"
    fi
    return
  fi

  mkdir -p "$RUNTIME_ROOT"
  rm -rf "$RUNTIME_ROOT/config" "$RUNTIME_ROOT/lib" "$RUNTIME_ROOT/data"
  cp -R "$SOURCE_ROOT/config" "$RUNTIME_ROOT/config"
  cp -R "$SOURCE_ROOT/lib" "$RUNTIME_ROOT/lib"
  cp -R "$SOURCE_ROOT/data" "$RUNTIME_ROOT/data"
  cp "$SOURCE_ROOT/flows.json" "$RUNTIME_ROOT/flows.json"
  cp "$SOURCE_ROOT/settings.js" "$RUNTIME_ROOT/settings.js"
  cp "$SOURCE_ROOT/package.json" "$RUNTIME_ROOT/package.json"
  printf '%s\n' "$RUNTIME_VERSION" > "$MARKER"
  printf '[NODE-RED] Installed versioned runtime %s in %s\n' "$RUNTIME_VERSION" "$RUNTIME_ROOT"
}

force="${AI_CPS_FORCE_RUNTIME_UPDATE:-false}"
install_runtime "$force"

if [ "${1:-run}" = "install-only" ]; then
  exit 0
fi

exec node-red \
  --userDir /data \
  --settings "$RUNTIME_ROOT/settings.js" \
  "$RUNTIME_ROOT/flows.json"
