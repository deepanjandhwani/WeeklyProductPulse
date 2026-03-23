"""
Append to Google Docs by spawning ``@a-bonus/google-docs-mcp`` over MCP stdio.

This implements **Pipeline → MCP → Google Docs**: Phase 4 calls the MCP client in-process,
which starts ``npx -y @a-bonus/google-docs-mcp`` as a subprocess and invokes the
markdown append tool.

**Requirements**

* ``npx`` / Node.js on ``PATH`` (for the MCP server process).
* Same OAuth setup as Cursor MCP: ``GOOGLE_CLIENT_ID`` and ``GOOGLE_CLIENT_SECRET``
  in the environment, and a completed ``npx @a-bonus/google-docs-mcp auth`` so
  ``~/.config/google-docs-mcp/token.json`` exists on the machine running the pipeline.

**Config**

* ``GOOGLE_DOCS_APPEND_TRANSPORT=mcp`` (vs default ``direct`` for ``google_docs_client``).

See ``docs/GOOGLE_DOCS.md``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("weekly_pulse")

# Subprocess MCP server should finish well under this; increase on slow networks
MCP_APPEND_TIMEOUT_SEC = 180


def _pick_append_markdown_tool(tool_list: list[Any]) -> str | None:
    """Resolve tool name (package may evolve)."""
    names = [getattr(t, "name", "") for t in tool_list]
    preferred = (
        "appendMarkdownToGoogleDoc",
        "appendMarkdown",
        "appendToGoogleDoc",
    )
    for p in preferred:
        if p in names:
            return p
    for n in names:
        lower = n.lower()
        if "append" in lower and "markdown" in lower:
            return n
    return None


async def _append_markdown_async(document_id: str, markdown: str) -> bool:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = dict(os.environ)
    if not env.get("GOOGLE_CLIENT_ID") or not env.get("GOOGLE_CLIENT_SECRET"):
        raise RuntimeError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set for MCP append "
            "(same as local Cursor MCP). Run `npx -y @a-bonus/google-docs-mcp auth` once."
        )

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@a-bonus/google-docs-mcp"],
        env=env,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tool_name = _pick_append_markdown_tool(listed.tools)
            if not tool_name:
                raise RuntimeError(
                    "google-docs-mcp did not expose a known append-markdown tool; "
                    f"got: {[t.name for t in listed.tools]}"
                )

            result = await session.call_tool(
                tool_name,
                arguments={
                    "documentId": document_id,
                    "markdown": markdown,
                },
            )

            if getattr(result, "isError", False):
                err_text = ""
                for block in result.content or []:
                    if getattr(block, "type", None) == "text":
                        err_text += getattr(block, "text", "") or ""
                raise RuntimeError(err_text or "MCP tool returned isError")

            logger.info(
                "mcp_google_doc_appended",
                extra={
                    "phase": "mcp_google_docs_append",
                    "data": {
                        "document_id": document_id,
                        "tool": tool_name,
                        "chars": len(markdown),
                    },
                },
            )
            return True


def try_append_via_mcp(document_id: str, markdown: str) -> bool:
    """
    Spawn google-docs-mcp, call append markdown tool, return True on success.
    """
    if not document_id or not markdown.strip():
        return False
    try:
        asyncio.run(
            asyncio.wait_for(
                _append_markdown_async(document_id, "\n\n" + markdown),
                timeout=MCP_APPEND_TIMEOUT_SEC,
            )
        )
        return True
    except TimeoutError:
        logger.error(
            "MCP Google Docs append timed out",
            extra={"phase": "mcp_google_docs_append", "data": {"document_id": document_id}},
        )
        return False
    except Exception as e:
        logger.error(f"MCP Google Docs append failed: {e}", exc_info=True)
        return False
