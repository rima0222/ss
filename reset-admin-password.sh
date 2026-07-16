#!/bin/bash
set -e
if [ -z "$1" ]; then
 PASS=$(openssl rand -hex 16)
else
 PASS="$1"
fi

sed -i "s/^Password:.*/Password: $PASS/" /etc/custom-panel/admin-credentials.txt

echo "New password:"
cat /etc/custom-panel/admin-credentials.txt
