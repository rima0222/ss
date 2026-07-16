#!/bin/bash
PASS=${1:-$(openssl rand -hex 16)}
sed -i "s/^Password:.*/Password: $PASS/" /etc/custom-panel/admin-credentials.txt
cat /etc/custom-panel/admin-credentials.txt
