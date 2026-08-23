"""Paints a :class:`~app.infrastructure.export.runna.sheet.Sheet` onto a canvas.

Drawing happens on a bare ReportLab canvas rather than through Platypus: the
sheet is a fixed grid whose positions all derive from measured constants, and a
flowable engine would fight those positions rather than help. Every coordinate
here is expressed as a distance from the *top* of the page (``_y`` flips it) so
the code reads in the same direction as the design.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from reportlab.lib.colors import Color
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from app.infrastructure.export.runna import theme as t
from app.infrastructure.export.runna.sheet import (
    Chip,
    DayCard,
    DetailSection,
    PhaseBlock,
    Sheet,
    WeekRow,
)

_ELLIPSIS = "…"


def _y(from_top: float) -> float:
    """Convert a from-the-top coordinate into ReportLab's bottom-up space."""
    return t.PAGE_H - from_top


def _width(text: str, font: str, size: float, tracking: float = 0.0) -> float:
    if not text:
        return 0.0
    return stringWidth(text, font, size) + tracking * (len(text) - 1)


def _shrink_to_fit(
    text: str, font: str, size: float, max_width: float, min_size: float
) -> Tuple[str, float]:
    """Reduce the size, then ellipsize, until ``text`` fits ``max_width``."""
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 0.25
    if stringWidth(text, font, size) <= max_width:
        return text, size
    while text and stringWidth(text + _ELLIPSIS, font, size) > max_width:
        text = text[:-1]
    return text.rstrip() + _ELLIPSIS, size


def _wrap(text: str, font: str, size: float, max_width: float) -> List[str]:
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _fit_lines(
    text: str, font: str, size: float, max_width: float, min_size: float, max_lines: int
) -> Tuple[List[str], float]:
    """Wrap ``text`` into at most ``max_lines``, shrinking before it truncates.

    Session names are the one string on the sheet whose length the layout does
    not control, so they get room to wrap and a smaller size before an ellipsis
    is allowed to eat the end of a name.
    """
    if not text:
        return [], size
    while True:
        lines = _wrap(text, font, size, max_width)
        if len(lines) <= max_lines and all(
            stringWidth(line, font, size) <= max_width for line in lines
        ):
            return lines, size
        if size <= min_size:
            break
        size -= 0.25
    lines = _wrap(text, font, size, max_width)
    kept = lines[:max_lines]
    # Fold the overflow back onto the last kept line so the ellipsis marks the
    # truncation rather than the name simply stopping mid-phrase.
    kept[-1] = " ".join([kept[-1], *lines[max_lines:]])
    kept[-1], _ = _shrink_to_fit(kept[-1], font, size, max_width, size)
    return kept, size


class SheetPainter:
    """Low-level drawing primitives shared by every page of the sheet."""

    def __init__(self, canvas: Canvas, footer: str):
        self.canvas = canvas
        self._footer = footer

    # --- text -------------------------------------------------------------

    def text(
        self,
        x: float,
        baseline_from_top: float,
        text: str,
        font: str,
        size: float,
        color: Color,
        tracking: float = 0.0,
    ) -> None:
        if not text:
            return
        # Letter-spacing only exists on a text object, so every string goes
        # through one rather than splitting into two drawing paths.
        cursor = self.canvas.beginText(x, _y(baseline_from_top))
        cursor.setFont(font, size)
        cursor.setFillColor(color)
        # Tc lives in the PDF graphics state, not the text object, so it has to
        # be written every time — otherwise one tracked heading spaces out the
        # rest of the document.
        cursor.setCharSpace(tracking)
        cursor.textOut(text)
        self.canvas.drawText(cursor)

    def text_centered(
        self,
        center_x: float,
        baseline_from_top: float,
        text: str,
        font: str,
        size: float,
        color: Color,
        tracking: float = 0.0,
    ) -> None:
        width = _width(text, font, size, tracking)
        self.text(
            center_x - width / 2, baseline_from_top, text, font, size, color, tracking
        )

    # --- shapes -----------------------------------------------------------

    def rule(
        self, from_top: float, x0: float = t.MARGIN_L, x1: float = t.GRID_RIGHT
    ) -> None:
        canvas = self.canvas
        canvas.setStrokeColor(t.INK)
        canvas.setLineWidth(t.RULE_WIDTH)
        canvas.setDash()
        canvas.line(x0, _y(from_top), x1, _y(from_top))

    def filled_round_rect(
        self,
        x: float,
        top: float,
        width: float,
        height: float,
        color: Color,
        radius: float,
    ) -> None:
        canvas = self.canvas
        canvas.setFillColor(color)
        canvas.setDash()
        canvas.roundRect(x, _y(top + height), width, height, radius, stroke=0, fill=1)

    def dashed_round_rect(
        self, x: float, top: float, width: float, height: float, radius: float
    ) -> None:
        canvas = self.canvas
        canvas.setFillColor(t.REST_BG)
        canvas.setStrokeColor(t.REST_BORDER)
        canvas.setLineWidth(0.8)
        canvas.setDash(2, 2)
        canvas.roundRect(x, _y(top + height), width, height, radius, stroke=1, fill=1)
        canvas.setDash()

    # --- composites -------------------------------------------------------

    def day_card(self, x: float, top: float, card: DayCard) -> None:
        if card.kind == "rest":
            self.dashed_round_rect(x, top, t.COL_W, t.CARD_H, t.CARD_RADIUS)
            self.text_centered(
                x + t.COL_W / 2,
                top + t.CARD_H / 2 + t.SIZE_REST * 0.36,
                "Rest",
                t.FONT,
                t.SIZE_REST,
                t.REST_TEXT,
            )
            return

        accent = t.accent_for(card.kind)
        self.filled_round_rect(x, top, t.COL_W, t.CARD_H, accent.bg, t.CARD_RADIUS)

        inner = t.COL_W - 2 * t.CARD_PAD_X
        headline, headline_size = _shrink_to_fit(
            card.headline, t.FONT_BOLD, t.SIZE_CARD_HEADLINE, inner, 6.5
        )
        self.text(
            x + t.CARD_PAD_X,
            top + t.CARD_HEADLINE_BASELINE,
            headline,
            t.FONT_BOLD,
            headline_size,
            accent.fg,
        )
        label_lines, label_size = _fit_lines(
            card.label, t.FONT_BOLD, t.SIZE_CARD_LABEL, inner, 5.5, t.CARD_LABEL_LINES
        )
        for offset, line in enumerate(label_lines):
            self.text(
                x + t.CARD_PAD_X,
                top + t.CARD_LABEL_BASELINE + offset * t.CARD_LABEL_LEADING,
                line,
                t.FONT_BOLD,
                label_size,
                accent.fg,
            )
        if card.strength:
            # A strength session rides along with a run rather than owning a
            # day, so it is marked on the card instead of taking a column.
            canvas = self.canvas
            canvas.setFillColor(t.STRENGTH.fg)
            canvas.circle(x + t.COL_W - 8.0, _y(top + 8.0), 2.4, stroke=0, fill=1)

    def chip(
        self,
        x: float,
        top: float,
        height: float,
        text: str,
        kind: str,
        size: float,
        pad_x: float,
        tracking: float = 0.0,
    ) -> float:
        """Draw a pill and return its width."""
        accent = t.accent_for(kind)
        width = _width(text, t.FONT_BOLD, size, tracking) + 2 * pad_x
        self.filled_round_rect(x, top, width, height, accent.bg, t.CHIP_RADIUS)
        self.text_centered(
            x + width / 2,
            top + height / 2 + size * 0.36,
            text,
            t.FONT_BOLD,
            size,
            accent.fg,
            tracking,
        )
        return width

    def page_footer(self) -> None:
        self.text_centered(
            t.PAGE_W / 2,
            t.FOOTER_BASELINE,
            self._footer,
            t.FONT,
            t.SIZE_FOOTER,
            t.FOOTER_GREY,
            t.TRACK_FOOTER,
        )

    def day_headers(self) -> None:
        for index, name in enumerate(t.DAY_HEADERS):
            center = t.GRID_LEFT + index * t.COL_PITCH + t.COL_W / 2
            self.text_centered(
                center,
                t.DAY_HEADER_BASELINE,
                name,
                t.FONT_BOLD,
                t.SIZE_DAY_HEADER,
                t.FAINT,
                t.TRACK_DAY_HEADER,
            )

    def phase_header(self, rule_top: float, phase: PhaseBlock) -> None:
        self.text(
            t.MARGIN_L,
            rule_top + t.PHASE_EYEBROW_BASELINE,
            phase.eyebrow,
            t.FONT_BOLD,
            t.SIZE_PHASE_EYEBROW,
            t.ACCENT,
            t.TRACK_EYEBROW,
        )
        self.text(
            t.MARGIN_L,
            rule_top + t.PHASE_TITLE_BASELINE,
            phase.title,
            t.FONT_BOLD,
            t.SIZE_PHASE_TITLE,
            t.INK,
        )
        subtitle, size = _shrink_to_fit(
            phase.subtitle,
            t.FONT,
            t.SIZE_PHASE_SUBTITLE,
            t.GRID_RIGHT - t.MARGIN_L,
            7.0,
        )
        self.text(
            t.MARGIN_L,
            rule_top + t.PHASE_SUBTITLE_BASELINE,
            subtitle,
            t.FONT,
            size,
            t.MUTED,
        )

    def week_row(self, top: float, week: WeekRow) -> None:
        self.text(
            t.MARGIN_L,
            top + 15.7,
            "WEEK",
            t.FONT_BOLD,
            t.SIZE_WEEK_LABEL,
            t.FAINT,
            t.TRACK_WEEK_LABEL,
        )
        number_baseline = top + (35.0 if week.tag else t.PHASE_TITLE_BASELINE)
        self.text(
            t.MARGIN_L,
            number_baseline,
            str(week.number),
            t.FONT_BOLD,
            t.SIZE_WEEK_NUMBER,
            t.INK,
        )
        if week.tag:
            self.text(
                t.MARGIN_L,
                top + 46.5,
                week.tag,
                t.FONT_BOLD,
                6.5,
                t.ACCENT if week.tag == "(RACE)" else t.FAINT,
                0.3,
            )
        for index, card in enumerate(week.cards):
            self.day_card(t.GRID_LEFT + index * t.COL_PITCH, top, card)


# --- page composition -----------------------------------------------------


def _render_cover(painter: SheetPainter, sheet: Sheet) -> None:
    cover = sheet.cover
    painter.text(
        t.COVER_LEFT,
        t.COVER_EYEBROW_BASELINE,
        cover.eyebrow,
        t.FONT_BOLD,
        t.SIZE_COVER_EYEBROW,
        t.BRAND,
        t.TRACK_COVER_EYEBROW,
    )

    available = t.PAGE_W - t.COVER_LEFT - t.MARGIN_R
    lines = list(cover.title_lines)
    first_baseline = t.COVER_TITLE_BASELINE - (len(lines) - 1) * t.COVER_TITLE_LEADING
    for index, line in enumerate(lines):
        fitted, size = _shrink_to_fit(
            line, t.FONT_BOLD, t.SIZE_COVER_TITLE, available, 22.0
        )
        painter.text(
            t.COVER_LEFT,
            first_baseline + index * t.COVER_TITLE_LEADING,
            fitted,
            t.FONT_BOLD,
            size,
            t.INK,
        )

    description_width = 520.0
    for index, line in enumerate(
        _wrap(cover.description, t.FONT, t.SIZE_COVER_DESC, description_width)
    ):
        painter.text(
            t.COVER_LEFT,
            t.COVER_DESC_BASELINE + index * t.COVER_DESC_LEADING,
            line,
            t.FONT,
            t.SIZE_COVER_DESC,
            t.BODY,
        )

    x = t.COVER_LEFT
    for chip in cover.stats:
        width = painter.chip(
            x,
            t.COVER_STAT_TOP,
            t.COVER_STAT_H,
            chip.text,
            chip.kind,
            t.SIZE_STAT_CHIP,
            t.COVER_STAT_PAD_X,
            t.TRACK_STAT_CHIP,
        )
        x += width + t.COVER_STAT_GAP

    _render_legend(painter, cover.legend)
    painter.page_footer()


def _render_legend(painter: SheetPainter, legend: Sequence[Chip]) -> None:
    x = t.COVER_LEFT
    top = t.COVER_LEGEND_TOP
    right_edge = t.PAGE_W - t.MARGIN_R
    for chip in legend:
        width = (
            _width(chip.text, t.FONT_BOLD, t.SIZE_LEGEND_CHIP)
            + 2 * t.COVER_LEGEND_PAD_X
        )
        if x + width > right_edge:
            x = t.COVER_LEFT
            top += t.COVER_LEGEND_PITCH
        painter.chip(
            x,
            top,
            t.COVER_LEGEND_H,
            chip.text,
            chip.kind,
            t.SIZE_LEGEND_CHIP,
            t.COVER_LEGEND_PAD_X,
        )
        x += width + t.COVER_LEGEND_GAP


class _Pager:
    """Starts calendar pages and keeps the repeated furniture consistent."""

    def __init__(self, painter: SheetPainter):
        self._painter = painter
        self._started = False

    def new_page(self) -> float:
        if self._started:
            self._painter.page_footer()
            self._painter.canvas.showPage()
        self._started = True
        self._painter.day_headers()
        return t.FIRST_RULE_TOP

    def close(self) -> None:
        if self._started:
            self._painter.page_footer()
            self._painter.canvas.showPage()
            self._started = False


def _render_calendar(painter: SheetPainter, phases: Sequence[PhaseBlock]) -> None:
    pager = _Pager(painter)
    cursor = pager.new_page()
    page_top = cursor

    for phase in phases:
        needed = t.PHASE_FIRST_ROW_TOP + t.CARD_H
        gap = 0.0 if cursor <= page_top else t.PHASE_SEPARATION
        if cursor + gap + needed > t.CONTENT_BOTTOM:
            cursor = page_top = pager.new_page()
            gap = 0.0
        cursor += gap

        painter.rule(cursor)
        painter.phase_header(cursor, phase)
        row_top = cursor + t.PHASE_FIRST_ROW_TOP

        for week in phase.weeks:
            if row_top + t.CARD_H > t.CONTENT_BOTTOM:
                row_top = page_top = pager.new_page()
            painter.week_row(row_top, week)
            row_top += t.ROW_PITCH

        cursor = row_top - t.ROW_GAP

    pager.close()


SECTION_LEAD_SIZE = 9.5
SECTION_BODY_SIZE = 8.5
SECTION_BODY_LEADING = 11.0
SECTION_LEAD_GAP = 13.0
SECTION_ROW_GAP = 9.0
SECTION_BODY_TOP = 140.0
SECTION_GUTTER = 26.0


def _section_header(painter: SheetPainter, section: DetailSection) -> None:
    painter.text(
        t.MARGIN_L,
        60.0,
        section.eyebrow,
        t.FONT_BOLD,
        t.SIZE_PHASE_EYEBROW,
        t.ACCENT,
        t.TRACK_EYEBROW,
    )
    painter.text(t.MARGIN_L, 86.0, section.title, t.FONT_BOLD, 22.0, t.INK)
    subtitle, size = _shrink_to_fit(
        section.subtitle, t.FONT, t.SIZE_PHASE_SUBTITLE, t.GRID_RIGHT - t.MARGIN_L, 7.0
    )
    painter.text(t.MARGIN_L, 104.0, subtitle, t.FONT, size, t.MUTED)
    painter.rule(118.0)


def _render_sections(painter: SheetPainter, sections: Sequence[DetailSection]) -> None:
    for section in sections:
        _flow_section(painter, section)


def _flow_section(painter: SheetPainter, section: DetailSection) -> None:
    """Fill columns top-to-bottom, left-to-right, spilling onto further pages."""
    columns = max(1, section.columns)
    column_width = (
        t.GRID_RIGHT - t.MARGIN_L - (columns - 1) * SECTION_GUTTER
    ) / columns
    available = t.CONTENT_BOTTOM - SECTION_BODY_TOP

    rows = [
        (row, _wrap(row.body, t.FONT, SECTION_BODY_SIZE, column_width))
        for row in section.rows
    ]
    heights = [
        SECTION_LEAD_GAP + len(lines) * SECTION_BODY_LEADING for _, lines in rows
    ]

    index = 0
    while True:
        _section_header(painter, section)
        # A section that fits on one page is balanced across its columns rather
        # than filling the first one and leaving the rest blank.
        remaining = sum(heights[index:]) + SECTION_ROW_GAP * max(
            0, len(heights) - index - 1
        )
        target = (
            min(available, remaining / columns)
            if columns > 1 and remaining <= available * columns
            else available
        )

        column = 0
        cursor = SECTION_BODY_TOP
        while index < len(rows):
            row, lines = rows[index]
            # ``target`` is a height; the cursor is a from-page-top coordinate.
            limit = (
                t.CONTENT_BOTTOM if column == columns - 1 else SECTION_BODY_TOP + target
            )
            if cursor > SECTION_BODY_TOP and cursor + heights[index] > limit:
                column += 1
                if column >= columns:
                    break
                cursor = SECTION_BODY_TOP
                continue
            x = t.MARGIN_L + column * (column_width + SECTION_GUTTER)
            lead, lead_size = _shrink_to_fit(
                row.lead, t.FONT_BOLD, SECTION_LEAD_SIZE, column_width, 7.5
            )
            painter.text(
                x, cursor, lead, t.FONT_BOLD, lead_size, t.accent_for(row.kind).fg
            )
            for offset, line in enumerate(lines):
                painter.text(
                    x,
                    cursor + SECTION_LEAD_GAP + offset * SECTION_BODY_LEADING,
                    line,
                    t.FONT,
                    SECTION_BODY_SIZE,
                    t.BODY,
                )
            cursor += heights[index] + SECTION_ROW_GAP
            index += 1
        painter.page_footer()
        painter.canvas.showPage()
        if index >= len(rows):
            return


def render_sheet(canvas: Canvas, sheet: Sheet) -> None:
    """Paint the whole document. Leaves the canvas ready for ``save()``."""
    painter = SheetPainter(canvas, sheet.footer)
    _render_cover(painter, sheet)
    canvas.showPage()
    _render_calendar(painter, sheet.phases)
    _render_sections(painter, sheet.sections)
