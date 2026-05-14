#!/usr/bin/env bash
# Idempotent bootstrap for Cursor Cloud Agents (see .cursor/environment.json "install").
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

git submodule sync --recursive
git submodule update --init --recursive

MANIFEST="${ROOT}/feather-flash-quiz/scripts/generate-location-birds-manifest.js"
if [[ ! -f "${MANIFEST}" ]]; then
  echo "error: missing ${MANIFEST} (submodule not populated?)" >&2
  exit 1
fi

python3 -m pip install --user -r "${ROOT}/requirements.txt"

npm ci --prefix "${ROOT}/feather-flash-quiz"

echo "cloud_agent_install: ok"
