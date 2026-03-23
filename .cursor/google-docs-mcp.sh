#!/usr/bin/env bash
# Load .env from the project root (parent of .cursor/) so GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
# are set for @a-bonus/google-docs-mcp. Cursor MCP often does not inject envFile into the child process.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
fi
exec npx -y @a-bonus/google-docs-mcp "$@"
