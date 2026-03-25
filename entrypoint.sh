#!/bin/sh
set -e

# Gmail MCP: write OAuth keys file from env vars
if [ -n "$GOOGLE_CLIENT_ID" ] && [ -n "$GOOGLE_CLIENT_SECRET" ]; then
  mkdir -p /root/.gmail-mcp
  cat > /root/.gmail-mcp/gcp-oauth.keys.json <<EOF
{
  "installed": {
    "client_id": "$GOOGLE_CLIENT_ID",
    "project_id": "weekly-product-pulse",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "$GOOGLE_CLIENT_SECRET",
    "redirect_uris": ["http://localhost"]
  }
}
EOF
  echo "Wrote /root/.gmail-mcp/gcp-oauth.keys.json"
fi

# Gmail MCP: write OAuth credentials/token from env var
if [ -n "$GMAIL_MCP_CREDENTIALS_JSON" ]; then
  mkdir -p /root/.gmail-mcp
  echo "$GMAIL_MCP_CREDENTIALS_JSON" > /root/.gmail-mcp/credentials.json
  echo "Wrote /root/.gmail-mcp/credentials.json"
fi

# Google Docs MCP: write OAuth token from env var
if [ -n "$GOOGLE_DOCS_MCP_TOKEN_JSON" ]; then
  mkdir -p /root/.config/google-docs-mcp
  echo "$GOOGLE_DOCS_MCP_TOKEN_JSON" > /root/.config/google-docs-mcp/token.json
  echo "Wrote /root/.config/google-docs-mcp/token.json"
fi

exec uvicorn web.main:app --host 0.0.0.0 --port "${PORT:-8000}"
