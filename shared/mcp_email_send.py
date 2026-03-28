"""
Send email via an MCP server over stdio.

This module is intentionally provider-agnostic so different MCP email servers can be used
by environment configuration (command/args/tool name).

By default the mailer uses **one MCP subprocess per recipient** (most Gmail MCP servers
fail on a second ``call_tool`` in the same session). Set **`EMAIL_MCP_BATCH=1`** to try
one session for all recipients (faster when your server supports it).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from typing import Any

logger = logging.getLogger("weekly_pulse")


def _describe_exception(exc: BaseException) -> str:
    """
    Human-readable error text. Unwraps ExceptionGroup / TaskGroup so logs and 502 detail
    show the real failure (e.g. MCP stdio or Gmail tool) instead of only "1 sub-exception".
    """
    if isinstance(exc, BaseExceptionGroup):
        lines = [f"{type(exc).__name__}: {exc}"]
        for i, sub in enumerate(exc.exceptions, 1):
            lines.append(f"  [{i}] {_describe_exception(sub)}")
        return "\n".join(lines)
    return f"{type(exc).__name__}: {exc}"


# Single-message cap (legacy callers).
MCP_EMAIL_TIMEOUT_SEC = 120
# Batch: one npx + handshake, then one tool call per recipient — scale with count.
MCP_EMAIL_BATCH_TIMEOUT_BASE_SEC = 90
MCP_EMAIL_BATCH_TIMEOUT_PER_MSG_SEC = 45
MCP_EMAIL_BATCH_TIMEOUT_MAX_SEC = 600


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


def _validate_tool_result(result: Any, to_email: str, picked_tool: str) -> None:
    response_text = ""
    for block in result.content or []:
        if getattr(block, "type", None) == "text":
            response_text += (getattr(block, "text", "") or "").strip()

    lowered = response_text.lower()
    if getattr(result, "isError", False) or lowered.startswith("error:") or "invalid_type" in lowered:
        raise RuntimeError(response_text or "MCP email tool returned an error response")

    logger.info(
        "mcp_email_sent",
        extra={
            "phase": "mcp_email_send",
            "data": {"to": to_email, "tool": picked_tool},
        },
    )


async def _send_emails_batch_async(
    messages: list[tuple[str, str, str, str]],
    command: str,
    args: list[str],
    tool_name: str | None,
) -> None:
    """
    Send one or more emails through a **single** MCP stdio session.

    Each tuple is (to_email, subject, text_body, html_body).
    """
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    if not messages:
        return

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

            for to_email, subject, text_body, html_body in messages:
                arguments = {
                    "to": [to_email],
                    "subject": subject,
                    "body": text_body,
                    "htmlBody": html_body,
                    "mimeType": "multipart/alternative",
                }
                result = await session.call_tool(picked_tool, arguments=arguments)
                _validate_tool_result(result, to_email, picked_tool)


def _mcp_env() -> tuple[str, list[str], str | None]:
    command = (os.getenv("EMAIL_MCP_COMMAND") or "npx").strip()
    args_raw = (os.getenv("EMAIL_MCP_ARGS") or "-y @gongrzhe/server-gmail-autoauth-mcp").strip()
    args = shlex.split(args_raw)
    forced_tool = (os.getenv("EMAIL_MCP_TOOL") or "").strip() or None
    return command, args, forced_tool


def _batch_timeout_sec(n: int) -> float:
    if n <= 0:
        return float(MCP_EMAIL_TIMEOUT_SEC)
    return float(
        min(
            MCP_EMAIL_BATCH_TIMEOUT_MAX_SEC,
            MCP_EMAIL_BATCH_TIMEOUT_BASE_SEC + MCP_EMAIL_BATCH_TIMEOUT_PER_MSG_SEC * n,
        )
    )


def send_emails_via_mcp_batch(
    messages: list[tuple[str, str, str, str]],
) -> None:
    """
    Send one or more emails via one MCP subprocess + session.

    Each tuple is (to_email, subject, text_body, html_body).
    Raises ``RuntimeError`` on timeout; propagates other failures from the MCP tool.
    """
    if not messages:
        return

    command, args, forced_tool = _mcp_env()
    timeout = _batch_timeout_sec(len(messages))

    try:
        asyncio.run(
            asyncio.wait_for(
                _send_emails_batch_async(
                    messages,
                    command=command,
                    args=args,
                    tool_name=forced_tool,
                ),
                timeout=timeout,
            )
        )
    except TimeoutError as e:
        logger.error(
            "MCP email batch timed out",
            extra={"phase": "mcp_email_send", "data": {"recipients": len(messages), "timeout_sec": timeout}},
        )
        raise RuntimeError(
            "MCP email batch timed out (large recipient list or slow npx/Gmail). "
            "Try SMTP, or send to fewer addresses at once."
        ) from e
    except RuntimeError:
        raise
    except Exception as e:
        detail = _describe_exception(e)
        logger.error(
            "MCP email batch failed: %s",
            detail,
            exc_info=True,
            extra={"phase": "mcp_email_send"},
        )
        raise RuntimeError(f"MCP email failed: {detail}") from e


def send_email_via_mcp(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> None:
    """
    Send one email via MCP (delegates to :func:`send_emails_via_mcp_batch`).

    Raises ``RuntimeError`` with the underlying reason on failure (surfaced in API 502 detail).

    Env config:
    - EMAIL_MCP_COMMAND: default "npx"
    - EMAIL_MCP_ARGS: default "-y @gongrzhe/server-gmail-autoauth-mcp"
    - EMAIL_MCP_TOOL: optional explicit tool name
    """
    if not to_email.strip():
        raise RuntimeError("Empty recipient email for MCP send")
    send_emails_via_mcp_batch([(to_email, subject, text_body, html_body)])
