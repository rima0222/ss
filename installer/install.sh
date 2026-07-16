#!/bin/bash
set -e
DIR=/opt/custom-panel
bash installer/cleanup.sh
mkdir -p "$DIR"
echo "Installing Custom Panel v15"
echo "Fresh admin credentials will be generated"
