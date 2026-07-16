#!/usr/bin/env bash
set -Eeuo pipefail

FILE="/etc/custom-panel/admin-credentials.txt"

if [[ ! -f "$FILE" ]]; then
  echo "Credentials file not found: $FILE"
  echo "The panel may not be installed yet."
  exit 1
fi

cat "$FILE"
