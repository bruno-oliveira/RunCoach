"""Shared Jinja2 template configuration.

Provides a pre-configured Jinja2Templates instance with cache-busting
static_url() global and common filters registered.
"""

import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.infrastructure.config import settings
from app.utils import format_pace


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


def create_templates(directory: str = "app/web/templates") -> Jinja2Templates:
    """Create a Jinja2Templates instance with common globals and filters."""
    tpl = Jinja2Templates(directory=directory)
    tpl.env.globals["static_url"] = static_url
    tpl.env.filters["format_pace"] = format_pace
    return tpl
