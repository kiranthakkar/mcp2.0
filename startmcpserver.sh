#!/usr/bin/env bash
# Start the OCI Object Storage MCP server for local development.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing .env. Create it with: cp .env.example .env" >&2
  exit 1
fi

# The .env file contains shell-style KEY=value entries. Keep it local and out
# of source control because it contains OAuth client credentials.
set -a
# shellcheck disable=SC1090
if ! source "${ENV_FILE}"; then
  echo "Could not load .env. Use shell-compatible KEY=value entries; quote values containing spaces." >&2
  exit 1
fi
set +a

export MCP_HOST="${MCP_HOST:-127.0.0.1}"
export MCP_PORT="${MCP_PORT:-8000}"
export MCP_PUBLIC_URL="${MCP_PUBLIC_URL:-http://localhost:${MCP_PORT}}"

required=(
  OCI_CONFIG_URL
  MCP_OAUTH_SIGNING_KEY
)

for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]] || [[ "${!name}" == *'<'*'>'* ]]; then
    echo "Set ${name} in .env before starting the server." >&2
    exit 1
  fi
done

PYTHON="${PROJECT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
if [[ -z "${PYTHON}" ]]; then
  echo "Python 3 was not found. Create .venv and install dependencies first." >&2
  exit 1
fi

echo "Starting MCP server at ${MCP_PUBLIC_URL}/mcp"
cd "${PROJECT_DIR}"
exec "${PYTHON}" -m oci_object_storage_mcp.server_cimd