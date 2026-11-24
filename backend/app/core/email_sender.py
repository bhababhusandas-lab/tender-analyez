"""SMTP email sender. Falls back to stdout logging if SMTP not configured."""
import os
import smtplib
import ssl
import threading
import logging
from email.message import EmailMessage
from email.utils import formatdate

log = logging.getLogger("email")

# Config from env
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))   # 465 SSL, 587 STARTTLS
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "Unique Type <admin@example.com>")
USE_STARTTLS = SMTP_PORT == 587


def _send_sync(to: str, subject: str, html: str, text: str | None = None, cc: list[str] | None = None) -> None:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        # Not configured — log instead of sending. Signup still succeeds.
        log.warning(f"[EMAIL_NOT_SENT] to={to} subject={subject!r} (SMTP not configured)")
        print(f"[email] NO SMTP — would send to {to}: {subject}")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(text or _html_to_text(html))
    msg.add_alternative(html, subtype="html")

    try:
        if USE_STARTTLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30) as s:
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        print(f"[email] sent to {to}: {subject}")
    except Exception as e:
        log.error(f"[EMAIL_SEND_FAIL] to={to} subject={subject!r} error={e}")
        print(f"[email] FAILED to send to {to}: {e}")


def send_email(to: str, subject: str, html: str, text: str | None = None, cc: list[str] | None = None) -> None:
    """Fire-and-forget email send (runs in a background thread so signup isn't slowed)."""
    threading.Thread(target=_send_sync, args=(to, subject, html, text, cc), daemon=True).start()


def _html_to_text(html: str) -> str:
    import re
    txt = re.sub(r"<br\s*/?>", "\n", html)
    txt = re.sub(r"</p>", "\n\n", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    return txt.strip()
