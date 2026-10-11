"""Shared Jinja2 template configuration.

Provides ``templates``, the one pre-configured Jinja2Templates instance every
router renders through, with the cache-busting static_url() global and the
common filters registered.

One instance, not one per router: each ``Jinja2Templates`` owns its own
environment and therefore its own compiled-template cache, so a layout or
component shared between routers was compiled once per router that rendered
it — on a machine that scales to zero and pays that again on each wake.
"""

import hashlib
import json
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.contexts.nutrition.meal_database import meal_type_label, recipe_slug
from app.core.formatting import format_km, format_pace, format_pace_bare
from app.core.training.periodization.plan_calendar import next_monday
from app.core.training.profiles.road_profile import race_name
from app.core.training.workouts.workout_steps.presentation import session_view
from app.infrastructure.config import settings
from app.infrastructure.i18n import browser_manifest


def _build_static_hashes(static_dir: str = "app/web/static") -> dict[str, str]:
    """Build a mapping of static file paths to content hashes for cache busting."""
    hashes: dict[str, str] = {}
    static_path = Path(static_dir)
    if not static_path.exists():
        return hashes
    for file_path in static_path.rglob("*"):
        if file_path.is_file():
            short_hash = hashlib.md5(file_path.read_bytes()).hexdigest()[:8]
            hashes[str(file_path.relative_to(static_path))] = short_hash
    return hashes


_static_hashes = _build_static_hashes()


def static_url(path: str) -> str:
    """Return a static file URL with a content-hash query param for cache busting."""
    if settings.debug:
        import time

        return f"/static/{path}?t={int(time.time())}"
    h = _static_hashes.get(path, "")
    return f"/static/{path}?h={h}" if h else f"/static/{path}"


def phrase_manifest() -> str:
    """The phrase-catalogue URLs for ``i18n.js``, as the JSON it reads."""
    if settings.debug:
        # Catalogue files are edited far more often than the server restarts.
        browser_manifest.cache_clear()
    return json.dumps(browser_manifest(), separators=(",", ":"))


def create_templates(directory: str = "app/web/templates") -> Jinja2Templates:
    """Create a Jinja2Templates instance with common globals and filters."""
    tpl = Jinja2Templates(directory=directory)
    tpl.env.globals["static_url"] = static_url
    tpl.env.globals["phrase_manifest"] = phrase_manifest
    # Exposed as a global (not per-route context) because the plan form is
    # rendered from several places — the home route and every validation-error
    # re-render — and each of them needs the same default start date.
    tpl.env.globals["next_monday"] = next_monday
    tpl.env.filters["format_pace"] = format_pace
    tpl.env.filters["format_pace_bare"] = format_pace_bare
    tpl.env.filters["format_km"] = format_km
    tpl.env.filters["race_name"] = race_name
    # Grouped steps + effort profile, shared with the watch export so every
    # screen shows the structure the watch will run.
    tpl.env.filters["session_view"] = session_view
    # Recipe links from plan snapshots and the Tips page, which store names
    # rather than slugs.
    tpl.env.filters["recipe_slug"] = recipe_slug
    tpl.env.filters["meal_type_label"] = meal_type_label
    return tpl


templates = create_templates()
