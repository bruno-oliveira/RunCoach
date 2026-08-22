"""Shared PDF infrastructure: the on-disk render cache.

Rendering a plan sheet is CPU-bound and deterministic, so identical requests
are served from a short-lived cache keyed by the plan's content rather than
re-rendered per download.
"""

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class PDFBase:
    CACHE_TTL_SECONDS = 3600

    def __init__(self, cache_dir: str | None = None):
        if cache_dir is None:
            base = Path(os.environ.get("DATA_DIR", tempfile.gettempdir()))
            cache_dir = str(base / "pdf_cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(mode=0o700, exist_ok=True)

    def _evict_stale_cache(self) -> None:
        cutoff = time.time() - self.CACHE_TTL_SECONDS
        try:
            for entry in self.cache_dir.iterdir():
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink(missing_ok=True)
        except OSError:
            pass

    def _cache_key_from_hash(self, prefix: str, plan_id: Any, content: Any) -> str:
        if not isinstance(content, str):
            content = json.dumps(content, sort_keys=True, default=str)
        content_hash = hashlib.md5(content.encode()).hexdigest()
        return f"{prefix}{plan_id}_{content_hash}.pdf"

    def _generate_with_cache(
        self, cache_key: str, filename: str, build_fn: Callable[[str], None]
    ) -> str:
        """Return a cached render, or call ``build_fn(path)`` to produce one."""
        self._evict_stale_cache()
        cache_path = self.cache_dir / cache_key

        if cache_path.exists():
            logger.info(f"Using cached PDF: {cache_key}")
            return str(cache_path)

        logger.info(f"Generating new PDF: {cache_key}")
        temp_dir = tempfile.mkdtemp()
        try:
            pdf_path = os.path.join(temp_dir, filename)
            build_fn(pdf_path)
            shutil.move(pdf_path, cache_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return str(cache_path)
