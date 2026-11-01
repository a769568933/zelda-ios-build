#!/bin/bash
# Compatibility entry; no network calls or automatic cloud dispatch.
set -euo pipefail
exec /bin/bash "$(dirname "$0")/build_local.sh" "$@"
