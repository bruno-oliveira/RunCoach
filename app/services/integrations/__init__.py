"""External integration services (Strava, FIT, GPX)."""

__all__ = [
    "StravaService",
    "StravaPostSyncService",
    "FitService",
    "GpxService",
]


def __getattr__(name: str):
    if name == "StravaService":
        from app.services.integrations.strava_service import StravaService
        return StravaService
    if name == "StravaPostSyncService":
        from app.services.integrations.strava_post_sync_service import StravaPostSyncService
        return StravaPostSyncService
    if name == "FitService":
        from app.services.integrations.fit_service import FitService
        return FitService
    if name == "GpxService":
        from app.services.integrations.gpx_service import GpxService
        return GpxService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
