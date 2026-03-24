"""
Send email via an MCP server over stdio.

This module is intentionally provider-agnostic so different MCP email servers can be used
by environment configuration (command/args/tool name).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from typing import Any

logger = logging.getLogger("weekly_pulse")

MCP_EMAIL_TIMEOUT_SEC = 120


def _pick_send_email_tool(tool_list: list[Any], forced_tool: str | None = None) -> str | None:
    names = [getattr(t, "name", "") for t in tool_list]
    if forced_tool:
        return forced_tool if forced_tool in names else None

    preferred = (
        "send_email",
        "sendEmail",
        "gmail_send_email",
        "gmail_send",
        "sendGmail",
    )
    for p in preferred:
        if p in names:
            return p
    for n in names:
        lower = n.lower()
        if "send" in lower and "mail" in lower:
            return n
    return None


async def _send_email_async(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    command: str,
    args: list[str],
    tool_name: str | None,
) -> bool:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=dict(os.environ),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            picked_tool = _pick_send_email_tool(listed.tools, tool_name)
            if not picked_tool:
                raise RuntimeError(
                    f"No compatible email tool found on MCP server. Available: {[t.name for t in listed.tools]}"
                )

            # Include common argument aliases to maximize compatibility across MCP email servers.
            arguments = {
                "to": to_email,
                "to_email": to_email,
                "subject": subject,
                "body": text_body,
                "text": text_body,
                "html": html_body,
            }
            result = await session.call_tool(picked_tool, arguments=arguments)

            if getattr(result, "isError", False):
                err_text = ""
                for block in result.content or []:
                    if getattr(block, "type", None) == "text":
                        err_text += getattr(block, "text", "") or ""
                raise RuntimeError(err_text or "MCP email tool returned isError")

            logger.info(
                "mcp_email_sent",
                extra={
                    "phase": "mcp_email_send",
                    "data": {"to": to_email, "tool": picked_tool},
                },
            )
            return True


def send_email_via_mcp(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> bool:
    """
    Send one email via MCP.

    Env config:
    - EMAIL_MCP_COMMAND: default "npx"
    - EMAIL_MCP_ARGS: default "-y @gongrzhe/server-gmail-autoauth-mcp"
    - EMAIL_MCP_TOOL: optional explicit tool name
    """
    if not to_email.strip():
        return False

    command = (os.getenv("EMAIL_MCP_COMMAND") or "npx").strip()
    args_raw = (os.getenv("EMAIL_MCP_ARGS") or "-y @gongrzhe/server-gmail-autoauth-mcp").strip()
    args = shlex.split(args_raw)
    forced_tool = (os.getenv("EMAIL_MCP_TOOL") or "").strip() or None

    try:
        asyncio.run(
            asyncio.wait_for(
                _send_email_async(
                    to_email=to_email,
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                    command=command,
                    args=args,
                    tool_name=forced_tool,
                ),
                timeout=MCP_EMAIL_TIMEOUT_SEC,
            )
        )
        return True
    except TimeoutError:
        logger.error("MCP email send timed out", extra={"phase": "mcp_email_send"})
        return False
    except Exception as e:
        logger.error(f"MCP email send failed: {e}", exc_info=True)
        return False
