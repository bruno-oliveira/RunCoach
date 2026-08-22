"""Runna-style landscape plan sheet — the shipped training-plan PDF.

The document is a single visual system: a cover, a week-by-week calendar grid
grouped into training phases, and reference pages that reuse the same cards and
chips. ``build_sheet`` turns plan data into a pure layout model; ``render_sheet``
paints that model onto a ReportLab canvas.
"""

from app.infrastructure.export.runna.render import render_sheet
from app.infrastructure.export.runna.sheet import build_sheet

__all__ = ["build_sheet", "render_sheet"]
