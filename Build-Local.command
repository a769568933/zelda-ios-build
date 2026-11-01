#!/bin/bash
set -euo pipefail
exec /bin/bash "$(dirname "$0")/tools/build_local.sh" "$@"
