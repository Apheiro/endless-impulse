#!/usr/bin/env bash
# Compatibility entry point for existing shortcuts and external integrations.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/recorder.py" toggle "$@"
