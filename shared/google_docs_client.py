"""
Optional append to a Google Doc via the **Google Docs REST API** (service account).

Used when ``GOOGLE_DOCS_APPEND_TRANSPORT=direct`` (default).

* Enable: ``GOOGLE_DOCS_APPEND_ENABLED=true`` and ``GOOGLE_DOCS_DOCUMENT_ID``.
* Auth: ``GOOGLE_APPLICATION_CREDENTIALS`` → service-account JSON key.
* Share the target Doc with the service account email (Editor).

For **Pipeline → MCP → Google Docs** (spawn ``@a-bonus/google-docs-mcp``), use
``GOOGLE_DOCS_APPEND_TRANSPORT=mcp`` and ``shared/mcp_google_docs_append.py``.
See ``docs/GOOGLE_DOCS.md``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("weekly_pulse")

SCOPES = ("https://www.googleapis.com/auth/documents",)


def _build_docs_service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            "google-api-python-client and google-auth are required for Google Docs append. "
            "Install: pip install google-api-python-client google-auth"
        ) from e

    import os

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not creds_path:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is not set")

    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=SCOPES,
    )
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def _document_end_index(service: Any, document_id: str) -> int:
    doc = service.documents().get(documentId=document_id).execute()
    content = doc.get("body", {}).get("content") or []
    if not content:
        return 1
    end = content[-1].get("endIndex", 2)
    # Insert before the final newline of the document body
    return max(1, int(end) - 1)


def append_text_to_document(document_id: str, text: str) -> None:
    """Append plain text to the end of the document."""
    service = _build_docs_service()
    idx = _document_end_index(service, document_id)
    body = {
        "requests": [
            {
                "insertText": {
                    "location": {"index": idx},
                    "text": text,
                }
            }
        ]
    }
    service.documents().batchUpdate(documentId=document_id, body=body).execute()
    logger.info(
        "google_doc_appended",
        extra={
            "phase": "google_docs_client",
            "data": {"document_id": document_id, "chars": len(text)},
        },
    )


def try_append_payload(document_id: str, formatted_section: str) -> bool:
    """
    Append formatted section; return True on success, False if skipped or failed
    (logs error; callers should not treat Phase 4 as failed).
    """
    if not document_id or not formatted_section:
        return False
    try:
        # Leading newlines separate weekly runs
        append_text_to_document(document_id, "\n\n" + formatted_section)
        return True
    except Exception as e:
        logger.error(f"Google Docs append failed: {e}", exc_info=True)
        return False
