#!/usr/bin/env bash

if [[ -n ${1:-} ]]; then
  exec >> "$1"
fi

while true; do
  printf '%(%Y-%m-%d %H:%M:%S)T INFO demo.logger.App:42 Random log entry: %d\n' -1 "$RANDOM"
  sleep 3
done
