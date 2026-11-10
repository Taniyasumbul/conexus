"""Outbound channels and e-signature.

Console/File channels are used in simulation. Slack (incoming webhook) and SMTP
email are real, env-configured. DocuSign is a stub that writes the envelope
payload to disk - plug in the DocuSign eSignature REST API (JWT grant) for a
live deployment.
"""
from __future__ import annotations

import json
import os
import smtplib
import urllib.request
import uuid
from email.message import EmailMessage
from pathlib import Path


class Channel:
    def send(self, to: str, subject: str, body: str) -> None:
        raise NotImplementedError


class ConsoleChannel(Channel):
    def __init__(self, quiet: bool = False):
        self.quiet = quiet

    def send(self, to, subject, body):
        if not self.quiet:
            print(f"\n--- to {to} | {subject} ---\n{body}\n")


class SlackChannel(Channel):
    """Used for human escalations (posts to an internal channel)."""

    def __init__(self, webhook_url: str | None = None):
        self.url = webhook_url or os.environ["SLACK_WEBHOOK_URL"]

    def send(self, to, subject, body):
        data = json.dumps({"text": f"*{subject}*\n{body}"}).encode()
        req = urllib.request.Request(self.url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()


class EmailChannel(Channel):
    def __init__(self):
        self.host = os.environ["SMTP_HOST"]
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.environ["SMTP_USER"]
        self.password = os.environ["SMTP_PASSWORD"]

    def send(self, to, subject, body):
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.user, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port) as s:
            s.starttls()
            s.login(self.user, self.password)
            s.send_message(msg)


class ESignStub:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)

    def send_for_signature(self, contract_id: str, payload: dict) -> str:
        envelope_id = f"env-{uuid.uuid4().hex[:10]}"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / f"{contract_id}_{envelope_id}.json").write_text(json.dumps(payload, indent=2, default=str))
        return envelope_id
