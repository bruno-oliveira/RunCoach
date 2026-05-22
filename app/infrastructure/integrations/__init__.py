"""External integration services (Strava, FIT, GPX)."""

__all__ = [
    "StravaService",
    "StravaPostSyncService",
    "FitService",
    "GpxService",
]


def __getattr__(name: str):
    if name == "StravaService":
        from app.infrastructure.integrations.strava_service import StravaService

        return StravaService
    if name == "StravaPostSyncService":
        from app.infrastructure.integrations.strava_post_sync_service import (
            StravaPostSyncService,
        )

        return StravaPostSyncService
    if name == "FitService":
        from app.infrastructure.integrations.fit_service import FitService

        return FitService
    if name == "GpxService":
        from app.infrastructure.integrations.gpx_service import GpxService

        return GpxService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
