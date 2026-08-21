#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JAR="$SCRIPT_DIR/TailViewer.jar"

if [[ ! -f "$JAR" ]]; then
  echo "$JAR not found alongside script." >&2
  exit 1
fi

exec java -jar "$JAR" "$@"

