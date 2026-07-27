"""The gate on every scheduler-driven endpoint.

These endpoints are the app's only unattended surfaces: nothing about them
involves a browser, a session, or a user. What they share is a shared secret in
a header and one rule — **be invisible until deliberately switched on.**

Kept here rather than in a router because there is now more than one of them
(the outbound-nudge run and the ambient sync sweep), and a second copy of an
auth check is how one of them ends up subtly weaker than the other.
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Header, HTTPException

from app.infrastructure.config import settings


def require_cron_secret(x_cron_secret: Optional[str] = Header(default=None)) -> None:
    """Reject anything that isn't the configured scheduler.

    404 rather than 401 when ``CRON_SECRET`` is unset: these endpoints mail real
    people and mutate real plans, so an unconfigured deploy should not advertise
    their existence to someone probing for them. ``compare_digest`` because the
    secret is long-lived and a timing oracle on it is worth avoiding.
    """
    if not settings.cron_secret:
        raise HTTPException(status_code=404, detail="Not found")
    if not x_cron_secret or not hmac.compare_digest(
        x_cron_secret, settings.cron_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid cron secret")
