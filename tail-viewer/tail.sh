#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JAR="$SCRIPT_DIR/TailViewer.jar"

if [[ ! -f "$JAR" ]]; then
  echo "$JAR not found alongside script." >&2
  exit 1
fi

has_cli=false
for arg in "$@"; do
  if [[ "$arg" == "--cli" ]]; then
    has_cli=true
    break
  fi
done

if [[ "$has_cli" == false ]]; then
  exec java -jar "$JAR" --cli "$@"
else
  exec java -jar "$JAR" "$@"
fi

