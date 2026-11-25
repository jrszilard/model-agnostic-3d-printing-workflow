#!/usr/bin/env bash
# Complete preparation only. READY means STOP; this entrypoint never invokes send.
set -euo pipefail
exec python3 "$(dirname "$(readlink -f "$0")")/prepare.py" "$@"
