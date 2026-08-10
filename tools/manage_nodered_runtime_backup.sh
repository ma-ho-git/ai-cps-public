#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="$(command -v python3)"
MIGRATION_TOOL="$REPO_ROOT/tools/manage_runtime_migration.py"

usage() {
  cat <<'EOF'
Compatibility wrapper for the checksummed runtime site bundle.

Usage:
  ./tools/manage_nodered_runtime_backup.sh backup OUTPUT_DIR
  ./tools/manage_nodered_runtime_backup.sh restore BUNDLE_OR_DIR --force

`backup` now creates OUTPUT_DIR/ai-cps-site-backup.tar.gz and includes the
complete .env, runtime volumes, configured reports and selected model state.
The stack must be stopped. The bundle is plaintext and intended for the local
isolated test environment.
EOF
}

case "${1:-}" in
  backup)
    [[ $# -eq 2 ]] || { usage; exit 2; }
    mkdir -p "$2"
    exec "$PYTHON_BIN" "$MIGRATION_TOOL" export \
      --output "$2/ai-cps-site-backup.tar.gz"
    ;;
  restore)
    [[ $# -eq 3 && "$3" == "--force" ]] || { usage; exit 2; }
    bundle="$2"
    [[ -d "$bundle" ]] && bundle="$bundle/ai-cps-site-backup.tar.gz"
    exec "$PYTHON_BIN" "$MIGRATION_TOOL" import "$bundle" --force
    ;;
  *) usage; exit 2 ;;
esac
