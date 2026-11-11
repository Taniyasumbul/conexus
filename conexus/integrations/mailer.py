"""Transactional e-mail (verification, password reset).

Uses SMTP from the environment (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
optional SMTP_FROM). For Gmail: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587 and an
App Password. When SMTP is not configured, send() returns False and nothing leaves
the machine; the API can then show the link on screen, but only if
CONEXUS_DEV_EMAIL_LINKS=1 (never enable that on a public server).
"""
from __future__ import annotations

import html
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("conexus.mailer")


def configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))


def dev_links_enabled() -> bool:
    return os.getenv("CONEXUS_DEV_EMAIL_LINKS", "0").lower() in ("1", "true", "yes")


def _html(title: str, intro: str, button: str, link: str, footer: str) -> str:
    e = html.escape
    return f"""<!doctype html><html><body style="margin:0;background:#f3f8fa;font-family:Inter,Segoe UI,Arial,sans-serif;color:#0b1d26">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" style="max-width:520px;background:#ffffff;border-radius:18px;padding:32px" cellpadding="0" cellspacing="0">
<tr><td style="font-weight:800;font-size:20px;padding-bottom:20px"><span style="color:#0891b2">&#9679;</span> CoNexus</td></tr>
<tr><td style="font-weight:800;font-size:22px;padding-bottom:10px">{e(title)}</td></tr>
<tr><td style="font-size:15px;line-height:1.6;color:#46606c;padding-bottom:24px">{e(intro)}</td></tr>
<tr><td><a href="{e(link)}" style="display:inline-block;background:#0891b2;color:#ffffff;text-decoration:none;font-weight:700;padding:13px 22px;border-radius:999px">{e(button)}</a></td></tr>
<tr><td style="font-size:12px;color:#7f949e;padding-top:24px;line-height:1.6">{e(footer)}<br>Or paste this link into your browser:<br><span style="word-break:break-all">{e(link)}</span></td></tr>
</table></td></tr></table></body></html>"""


def send(to: str, subject: str, title: str, intro: str, button: str, link: str, footer: str) -> bool:
    """Send a single-button e-mail. Returns True if handed to the SMTP server."""
    if not configured():
        log.info("SMTP not configured; not sending %r to %s", subject, to)
        return False
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM") or os.environ["SMTP_USER"]
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(f"{title}\n\n{intro}\n\n{button}: {link}\n\n{footer}")
    msg.add_alternative(_html(title, intro, button, link, footer), subtype="html")
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=20) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        log.warning("e-mail to %s failed: %s", to, e)
        return False
