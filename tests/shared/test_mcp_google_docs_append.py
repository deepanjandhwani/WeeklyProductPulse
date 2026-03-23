"""Unit tests for MCP Google Docs helper (no live npx)."""

from types import SimpleNamespace

from shared.mcp_google_docs_append import _pick_append_markdown_tool


def test_pick_preferred_tool_name():
    tools = [
        SimpleNamespace(name="readDocument"),
        SimpleNamespace(name="appendMarkdownToGoogleDoc"),
    ]
    assert _pick_append_markdown_tool(tools) == "appendMarkdownToGoogleDoc"


def test_pick_fallback_contains_markdown():
    tools = [SimpleNamespace(name="fooAppendMarkdownBar")]
    assert _pick_append_markdown_tool(tools) == "fooAppendMarkdownBar"
