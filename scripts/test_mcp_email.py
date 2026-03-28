#!/usr/bin/env python3
"""
Test MCP email using the same code path as POST /api/email/send (shared.mcp_email_send).

Prerequisites (local):
  - Copy .env.example → .env and set at least:
      EMAIL_TRANSPORT=mcp
      EMAIL_MCP_COMMAND / EMAIL_MCP_ARGS (defaults work for Gmail MCP)
      GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
      Either ~/.gmail-mcp/credentials.json from running Gmail MCP auth locally,
      or GMAIL_MCP_CREDENTIALS_JSON in .env (full JSON string).
  - Node/npm available (npx) if EMAIL_MCP_COMMAND=npx.

Usage:
  cd /path/to/WeeklyProductPulse   # repo root containing shared/ and web/
  python scripts/test_mcp_email.py you@gmail.com

Against production (see JSON error body):
  curl -sS -X POST "https://YOUR.onrender.com/api/email/send" \\
    -H "Content-Type: application/json" \\
    -H "X-Pulse-API-Token: YOUR_TOKEN_IF_SET" \\
    -d '{"recipients":["you@gmail.com"]}' | jq .
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    recipient = sys.argv[1].strip()
    transport = (os.getenv("EMAIL_TRANSPORT") or "smtp").strip().lower()
    if transport != "mcp":
        print(
            f"ERROR: EMAIL_TRANSPORT={transport!r}. Set EMAIL_TRANSPORT=mcp in .env for this test.",
            file=sys.stderr,
        )
        sys.exit(1)

    cmd = os.getenv("EMAIL_MCP_COMMAND") or "npx"
    args = os.getenv("EMAIL_MCP_ARGS") or "-y @gongrzhe/server-gmail-autoauth-mcp"
    print("MCP launcher:", cmd, args)
    print("Recipient:", recipient)
    print("---")

    from shared.mcp_email_send import send_email_via_mcp

    try:
        send_email_via_mcp(
            to_email=recipient,
            subject="WeeklyProductPulse — MCP connectivity test",
            text_body="If you receive this, MCP email from WeeklyProductPulse works.",
            html_body="<p>If you receive this, MCP email from WeeklyProductPulse works.</p>",
        )
    except RuntimeError as e:
        print("FAILED:", e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("FAILED:", repr(e), file=sys.stderr)
        raise

    print("OK — send_email_via_mcp returned without error.")


if __name__ == "__main__":
    main()
