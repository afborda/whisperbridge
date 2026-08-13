#!/usr/bin/env bash
# Equivalente Linux do Instalar.bat
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/doctor.sh" --menu
