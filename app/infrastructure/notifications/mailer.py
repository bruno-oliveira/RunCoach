"""SMTP adapter for the outbound-notification port.

stdlib ``smtplib`` on purpose: no new dependency, and it works against a Gmail
app password, a transactional provider's SMTP endpoint, or a local relay
without any of them being baked in.

The important behaviour here is the *refusal*. With no ``SMTP_HOST`` configured
:func:`get_mailer` returns :class:`NullMailer`, which logs and returns ``False``
— so an unconfigured deploy (and every test run) sends nothing and, crucially,
records nothing as sent. See :mod:`app.domain.notifications` for why that
boolean has to be honest.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage as MimeMessage
from typing import Optional

from app.domain.notifications import EmailMessage, Mailer
from app.infrastructure.config import Settings
from app.infrastructure.config import settings as default_settings

logger = logging.getLogger(__name__)

# The conventional implicit-TLS port. Anything else is treated as plain SMTP
# with an optional STARTTLS upgrade.
_SMTPS_PORT = 465


class NullMailer:
    """Delivers nothing and says so.

    Used whenever SMTP is unconfigured. Logs at WARNING rather than DEBUG: a
    scheduled job that silently mails nobody is exactly the kind of failure
    that goes unnoticed for months.
    """

    def send(self, message: EmailMessage) -> bool:
        logger.warning(
            "SMTP not configured — not sending %r to %s",
            message.subject,
            message.to,
        )
        return False


class SmtpMailer:
    """Sends via SMTP, with STARTTLS unless the port implies implicit TLS."""

    def __init__(self, config: Optional[Settings] = None) -> None:
        self._settings = config or default_settings

    def send(self, message: EmailMessage) -> bool:
        cfg = self._settings
        mime = MimeMessage()
        mime["From"] = cfg.smtp_from or cfg.smtp_username
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")

        try:
            with self._connect() as server:
                if cfg.smtp_username:
                    server.login(cfg.smtp_username, cfg.smtp_password)
                server.send_message(mime)
        except (OSError, smtplib.SMTPException):
            # Never re-raise: one bad address must not abort a batch that has
            # other runners waiting in it.
            logger.exception("Failed to send %r to %s", message.subject, message.to)
            return False

        logger.info("Sent %r to %s", message.subject, message.to)
        return True

    def _connect(self) -> smtplib.SMTP:
        cfg = self._settings
        if cfg.smtp_port == _SMTPS_PORT:
            return smtplib.SMTP_SSL(
                cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds
            )
        server = smtplib.SMTP(
            cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds
        )
        if cfg.smtp_starttls:
            server.starttls()
        return server


def get_mailer(config: Optional[Settings] = None) -> Mailer:
    """The configured mailer, or :class:`NullMailer` when SMTP is unset."""
    cfg = config or default_settings
    if not cfg.smtp_host:
        return NullMailer()
    return SmtpMailer(cfg)
