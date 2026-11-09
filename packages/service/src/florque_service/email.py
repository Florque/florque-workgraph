"""Transactional email: Resend in production, a console sender for development and tests."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx

log = logging.getLogger("florque.email")

RESEND_URL = "https://api.resend.com/emails"


class EmailError(RuntimeError):
    """The provider refused or could not be reached."""


class EmailSender(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class ResendSender:
    """Sends through the Resend HTTP API (https://resend.com/docs/api-reference/emails)."""

    def __init__(
        self,
        api_key: str,
        sender: str,
        http: httpx.Client | None = None,
        url: str = RESEND_URL,
    ) -> None:
        self.sender = sender
        self.url = url
        self.http = http or httpx.Client(timeout=15.0)
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def send(self, to: str, subject: str, text: str) -> None:
        body = {"from": self.sender, "to": [to], "subject": subject, "text": text}
        try:
            r = self.http.post(self.url, json=body, headers=self.headers)
        except httpx.HTTPError as e:
            raise EmailError(f"email provider unreachable: {e}") from e
        if r.status_code >= 300:
            raise EmailError(f"email provider returned {r.status_code}: {r.text[:200]}")
        log.info("email sent", extra={"status": r.status_code})


@dataclass
class ConsoleSender:
    """Development sender: logs the message instead of sending it and keeps an outbox."""

    outbox: list[dict[str, str]] = field(default_factory=list)

    def send(self, to: str, subject: str, text: str) -> None:
        self.outbox.append({"to": to, "subject": subject, "text": text})
        log.warning(
            f"email not configured (RESEND_API_KEY unset); message to {to}: {subject}\n{text}"
        )


def sender_from_env() -> EmailSender:
    key = os.environ.get("RESEND_API_KEY")
    if key:
        sender = os.environ.get("FLORQUE_EMAIL_FROM")
        if not sender:
            raise RuntimeError("FLORQUE_EMAIL_FROM must be set with RESEND_API_KEY")
        return ResendSender(key, sender)
    if os.environ.get("FLORQUE_ENV") == "production":
        raise RuntimeError("RESEND_API_KEY is required when FLORQUE_ENV=production")
    return ConsoleSender()


# ---------------------------------------------------------------- messages


def invite_email(
    code: str,
    api_url: str,
    email: str,
    tenant_name: str | None,
    cli_install: str = "uv tool install florque-cli",
) -> tuple[str, str]:
    where = f"the {tenant_name} workspace" if tenant_name else "Florque Workgraph"
    subject = "Your Florque Workgraph invite"
    text = (
        f"You are invited to {where}.\n\n"
        f"Invite code: {code}\n\n"
        "Install the CLI and register:\n\n"
        f"  {cli_install}\n"
        f"  fwg register --api-url {api_url} --invite {code} --email {email} --name 'Your Name'\n\n"
        "The code works once and expires in 14 days.\n"
    )
    return subject, text


def login_email(code: str) -> tuple[str, str]:
    subject = f"Your Florque login code: {code}"
    text = (
        f"Your login code is {code}\n\n"
        "It expires in 10 minutes. If you did not ask for it, ignore this email.\n"
    )
    return subject, text
