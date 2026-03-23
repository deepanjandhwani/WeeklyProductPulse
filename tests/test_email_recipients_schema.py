"""Email send request parsing / validation."""

import pytest
from pydantic import ValidationError

from web.recipients_schema import EmailSendRequest


def test_recipients_comma_string():
    r = EmailSendRequest(recipients="one@a.com, two@b.com")
    assert [str(x) for x in (r.recipients or [])] == ["one@a.com", "two@b.com"]


def test_recipients_list():
    r = EmailSendRequest(recipients=["x@y.com"])
    assert len(r.recipients or []) == 1


def test_recipients_newlines():
    r = EmailSendRequest(recipients="a@b.com\n c@d.com ")
    assert len(r.recipients or []) == 2


def test_invalid_email_rejected():
    with pytest.raises(ValidationError):
        EmailSendRequest(recipients=["not-an-email"])


def test_empty_recipients_none():
    r = EmailSendRequest(recipients="   ")
    assert r.recipients is None
