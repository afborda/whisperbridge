#!/usr/bin/env bash
# Equivalente Linux do Instalar.bat — menu do doctor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec bash "$ROOT/scripts/linux/doctor.sh" --menu
