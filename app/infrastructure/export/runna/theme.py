"""Measured design tokens for the Runna-style plan sheet.

Every number here was taken off the reference sheet the design follows, so the
grid, type sizes and palette line up with it rather than drifting toward
ReportLab defaults. Keep them in one place: the renderer positions everything
relative to these, and a stray literal in the drawing code is how a layout
starts to slide.
"""

from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.colors import Color, HexColor

# --- Page -----------------------------------------------------------------
# A4 landscape. The sheet is horizontal because a training week is seven
# columns wide; portrait forces the cards below a legible size.
PAGE_W = 841.89
PAGE_H = 595.28

MARGIN_L = 34.0
MARGIN_R = 34.0

# The week label sits in a gutter to the left of the seven day columns.
GRID_LEFT = 96.2
GRID_RIGHT = PAGE_W - MARGIN_R

COL_GAP = 6.4
COL_W = (GRID_RIGHT - GRID_LEFT - 6 * COL_GAP) / 7
COL_PITCH = COL_W + COL_GAP

CARD_H = 51.0
ROW_GAP = 5.8
ROW_PITCH = CARD_H + ROW_GAP
CARD_RADIUS = 4.5
CARD_PAD_X = 6.0

# Distance from the card's top edge down to each text baseline.
CARD_HEADLINE_BASELINE = 22.2
CARD_LABEL_BASELINE = 34.5
# Named sessions ("Alternating Marathon-Pace Long") do not fit a 96pt column on
# one line, so the label may run to a second. The first baseline stays put
# either way — labels lining up across a week matters more than centring the
# block inside a card that happens to have two lines.
CARD_LABEL_LEADING = 8.2
CARD_LABEL_LINES = 2

# --- Vertical rhythm of a calendar page -----------------------------------
DAY_HEADER_BASELINE = 54.3  # from page top
FIRST_RULE_TOP = 72.6
RULE_WIDTH = 1.4

# Offsets below a phase rule.
PHASE_EYEBROW_BASELINE = 19.7
PHASE_TITLE_BASELINE = 39.3
PHASE_SUBTITLE_BASELINE = 54.3
PHASE_FIRST_ROW_TOP = 71.4

# Gap between the last card of a phase and the rule that opens the next one.
PHASE_SEPARATION = 15.4

CONTENT_BOTTOM = 555.0  # cards may not extend past this (from page top)
FOOTER_BASELINE = 576.0

# --- Cover ----------------------------------------------------------------
COVER_LEFT = 91.0
COVER_EYEBROW_BASELINE = 136.8
COVER_TITLE_BASELINE = 240.2  # baseline of the LAST title line
COVER_TITLE_LEADING = 43.8
COVER_DESC_BASELINE = 277.0
COVER_DESC_LEADING = 20.0
COVER_STAT_TOP = 329.9
COVER_STAT_H = 51.1
COVER_STAT_GAP = 17.0
COVER_STAT_PAD_X = 22.0
COVER_LEGEND_TOP = 409.7
COVER_LEGEND_H = 26.2
COVER_LEGEND_PITCH = 37.4
COVER_LEGEND_GAP = 11.8
COVER_LEGEND_PAD_X = 28.0
CHIP_RADIUS = 6.0

# --- Type -----------------------------------------------------------------
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

SIZE_DAY_HEADER = 7.5
SIZE_PHASE_EYEBROW = 8.0
SIZE_PHASE_TITLE = 16.0
SIZE_PHASE_SUBTITLE = 9.0
SIZE_WEEK_LABEL = 7.0
SIZE_WEEK_NUMBER = 12.0
SIZE_CARD_HEADLINE = 9.0
SIZE_CARD_LABEL = 7.0
SIZE_REST = 8.0
SIZE_FOOTER = 7.5
SIZE_COVER_EYEBROW = 11.0
SIZE_COVER_TITLE = 40.0
SIZE_COVER_DESC = 12.5
SIZE_STAT_CHIP = 9.0
SIZE_LEGEND_CHIP = 8.0

TRACK_DAY_HEADER = 1.2
TRACK_EYEBROW = 0.5
TRACK_WEEK_LABEL = 0.4
TRACK_FOOTER = 0.8
TRACK_COVER_EYEBROW = 1.3
TRACK_STAT_CHIP = 0.5

# --- Palette --------------------------------------------------------------
INK = HexColor("#1A1A1A")
BODY = HexColor("#555555")
MUTED = HexColor("#777777")
FAINT = HexColor("#999999")
FOOTER_GREY = HexColor("#A9A9A9")
BRAND = HexColor("#9B59B6")
ACCENT = HexColor("#C8372E")

REST_BG = HexColor("#FAFAFA")
REST_BORDER = HexColor("#DEDEDE")
REST_TEXT = HexColor("#C4C4C4")


@dataclass(frozen=True)
class Accent:
    """A background/foreground pair shared by a card, a chip and a legend pill."""

    bg: Color
    fg: Color


EASY = Accent(HexColor("#DCEEFB"), HexColor("#1B6FA8"))
LONG = Accent(HexColor("#E1F5E3"), HexColor("#238C4D"))
QUALITY = Accent(HexColor("#EEE0F9"), HexColor("#7B3FA0"))
STRENGTH = Accent(HexColor("#FDEEDB"), HexColor("#C1780F"))
RECOVERY = Accent(HexColor("#D8F5F1"), HexColor("#12907E"))
RACE = Accent(HexColor("#FCE8E8"), HexColor("#C8372E"))
NEUTRAL = Accent(HexColor("#F1F1F1"), HexColor("#555555"))

#: Card kinds, in the order they appear in the cover legend.
ACCENTS: dict[str, Accent] = {
    "easy": EASY,
    "long": LONG,
    "quality": QUALITY,
    "recovery": RECOVERY,
    "strength": STRENGTH,
    "race": RACE,
    "neutral": NEUTRAL,
}

DAY_HEADERS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def accent_for(kind: str) -> Accent:
    return ACCENTS.get(kind, NEUTRAL)
