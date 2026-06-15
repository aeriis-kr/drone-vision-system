#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper for classroom use:
#   scripts/stream-to-rx.sh <receiver-ip>
# is equivalent to:
#   STREAM_HOST=<receiver-ip> scripts/run-pi.sh

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${STREAM_HOST:-}" && $# -gt 0 && "$1" != -* ]]; then
	STREAM_HOST="$1"
	export STREAM_HOST
	shift
fi

exec "$ROOT/scripts/run-pi.sh" "$@"
