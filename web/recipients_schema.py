"""Parse and validate recipient email lists from JSON or comma-separated strings."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


class EmailSendRequest(BaseModel):
    """
    Request body for ``POST /api/email/send``.

    * ``recipients`` — optional. If provided (non-empty), must be valid email addresses.
      You may send a JSON array ``[\"a@x.com\",\"b@y.com\"]`` or a single comma-separated string.
    * If ``recipients`` is omitted or null, the server falls back to ``EMAIL_RECIPIENTS`` in the environment.
    """

    iso_week: str | None = Field(None, description="Report week; default = latest on disk")
    recipients: list[EmailStr] | str | None = Field(
        None,
        description="Destinations for the full pulse email (plain + HTML body = entire *_pulse.md)",
    )

    @field_validator("recipients", mode="before")
    @classmethod
    def coerce_recipients(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            parts = re.split(r"[\s,;]+", v.strip())
            out = [p for p in parts if p]
            return out or None
        if isinstance(v, list):
            out = [str(x).strip() for x in v if str(x).strip()]
            return out or None
        raise ValueError("recipients must be a list of emails or a comma-separated string")
