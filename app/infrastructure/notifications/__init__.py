"""Outbound notification adapters."""

from app.infrastructure.notifications.mailer import (
    NullMailer,
    SmtpMailer,
    get_mailer,
)

__all__ = ["NullMailer", "SmtpMailer", "get_mailer"]
