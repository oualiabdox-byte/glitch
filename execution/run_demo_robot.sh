#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f config/demo_profile.env ]]; then
  echo 'Missing config/demo_profile.env; copy config/demo_profile.env.example and review it.' >&2
  exit 1
fi
set -a
source config/demo_profile.env
set +a
export PYTHONPATH="${PYTHONPATH:-.}"
exec .venv/bin/python -m execution.demo_runner
