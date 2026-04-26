#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8787}"

read -rsp "Enter password: " PASSWORD
echo

if [[ -z "$PASSWORD" ]]; then
  echo "ERROR: Password cannot be empty"
  exit 1
fi

RESPONSE=$(curl -fsS "$BASE_URL/api/auth/verify" \
  -X POST \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"$PASSWORD\"}")

TOKEN=$(printf '%s' "$RESPONSE" | jq -r '.token')

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "ERROR: Failed to get token"
  echo "$RESPONSE"
  exit 1
fi

echo ""
echo "Token: $TOKEN"
