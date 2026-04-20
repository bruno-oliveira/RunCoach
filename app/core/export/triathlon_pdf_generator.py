"""PDF generation for triathlon training plans."""

import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.triathlon_plan import TriathlonPlan

logger = logging.getLogger(__name__)

# Discipline colours (RGB tuples 0-1)
_SWIM_COL  = colors.HexColor("#2563eb")
_BIKE_COL  = colors.HexColor("#16a34a")
_RUN_COL   = colors.HexColor("#ea580c")
_BRICK_COL = colors.HexColor("#7c3aed")

_PHASE_COLOURS = {
    "base":  colors.HexColor("#0891b2"),
    "build": colors.HexColor("#d97706"),
    "peak":  colors.HexColor("#dc2626"),
    "taper": colors.HexColor("#7c3aed"),
}

_DISTANCE_LABELS = {
    "sprint":       "Sprint Triathlon",
    "olympic":      "Olympic Triathlon",
    "half_ironman": "Half Ironman (70.3)",
}

_DISTANCE_SPECS = {
    "sprint":       ("750m", "20km", "5km"),
    "olympic":      ("1.5km", "40km", "10km"),
    "half_ironman": ("1.9km", "90km", "21.1km"),
}

_SESSION_COLOURS = {
    "swim":  _SWIM_COL,
    "bike":  _BIKE_COL,
    "run":   _RUN_COL,
    "brick": _BRICK_COL,
}


class TriathlonPDFGenerator:
    """Generates a PDF training guide from a TriathlonPlan model."""

    def __init__(self, cache_dir: str = "./pdf_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_pdf(self, plan: TriathlonPlan) -> str:
        """Generate (or return cached) PDF for a triathlon plan.

        Returns:
            Absolute path to the PDF file.
        """
        weeks: list[dict] = plan.plan_data
        cache_key = self._cache_key(plan)
        cache_path = self.cache_dir / cache_key

        if cache_path.exists():
            return str(cache_path)

        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, f"triathlon_{plan.id}.pdf")

        doc = SimpleDocTemplate(
            tmp_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        story: list[Any] = []
        self._title_page(story, plan, weeks)
        self._volume_overview(story, weeks)

        for week in weeks:
            story.append(PageBreak())
            self._week_page(story, week)

        self._footer(story)
        doc.build(story)

        shutil.move(tmp_path, cache_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return str(cache_path)

    # ------------------------------------------------------------------
    # Style setup
    # ------------------------------------------------------------------

    def _setup_styles(self) -> None:
        self.title_style = ParagraphStyle(
            "TriTitle",
            parent=self.styles["Heading1"],
            fontSize=22,
            spaceAfter=12,
            textColor=colors.HexColor("#1e3a5f"),
            alignment=TA_CENTER,
        )
        self.subtitle_style = ParagraphStyle(
            "TriSubtitle",
            parent=self.styles["Heading2"],
            fontSize=13,
            spaceAfter=6,
            textColor=colors.HexColor("#2563eb"),
            alignment=TA_CENTER,
        )
        self.section_style = ParagraphStyle(
            "TriSection",
            parent=self.styles["Heading3"],
            fontSize=12,
            spaceBefore=14,
            spaceAfter=6,
            textColor=colors.HexColor("#1e3a5f"),
            alignment=TA_LEFT,
        )
        self.normal_style = ParagraphStyle(
            "TriNormal",
            parent=self.styles["Normal"],
            fontSize=9,
            spaceAfter=4,
            leading=13,
        )
        self.small_style = ParagraphStyle(
            "TriSmall",
            parent=self.styles["Normal"],
            fontSize=8,
            spaceAfter=3,
            leading=11,
        )
        self.cell_style = ParagraphStyle(
            "TriCell",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=10,
            wordWrap="CJK",
        )
        self.header_cell_style = ParagraphStyle(
            "TriHeaderCell",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=11,
            alignment=TA_CENTER,
        )

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _title_page(self, story: list, plan: TriathlonPlan, weeks: list[dict]) -> None:
        label = _DISTANCE_LABELS.get(plan.distance, plan.distance)
        swim, bike, run = _DISTANCE_SPECS.get(plan.distance, ("?", "?", "?"))

        story.append(Paragraph("Triathlon Training Plan", self.title_style))
        story.append(Paragraph(label, self.subtitle_style))
        story.append(Spacer(1, 0.4 * cm))

        created = plan.created_at.strftime("%B %d, %Y")
        story.append(Paragraph(f"Generated on {created}", self.normal_style))
        story.append(Spacer(1, 1 * cm))

        # Stats table
        stats = [
            ["Swim", swim],
            ["Bike", bike],
            ["Run", run],
            ["Duration", f"{plan.weeks_duration} weeks"],
        ]
        t = Table(stats, colWidths=[4 * cm, 4 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f4ff")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d2fe")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 0.8 * cm))

        # Phase legend
        phases_seen: list[str] = []
        for w in weeks:
            if w["phase"] not in phases_seen:
                phases_seen.append(w["phase"])

        story.append(Paragraph("Training Phases", self.section_style))
        phase_descriptions = {
            "base":  "Build aerobic foundation and technique across all three disciplines.",
            "build": "Increase intensity with threshold and lactate work; longer bricks.",
            "peak":  "Highest volume / race-specific effort; final long sessions.",
            "taper": "Reduce volume while maintaining sharpness. Arrive fresh on race day.",
        }
        for ph in phases_seen:
            col = _PHASE_COLOURS.get(ph, colors.gray)
            hex_col = col.hexval() if hasattr(col, "hexval") else "#888888"
            desc = phase_descriptions.get(ph, "")
            story.append(
                Paragraph(
                    f'<font color="{hex_col}"><b>{ph.title()} Phase</b></font>  —  {desc}',
                    self.normal_style,
                )
            )

        story.append(Spacer(1, 0.4 * cm))

    def _volume_overview(self, story: list, weeks: list[dict]) -> None:
        story.append(Paragraph("Weekly Volume Overview", self.section_style))

        header = ["Week", "Phase", "Swim", "Bike", "Run", "Total hrs"]
        table_data = [
            [Paragraph(h, self.header_cell_style) for h in header]
        ]
        for w in weeks:
            ph = w["phase"]
            ph_col = _PHASE_COLOURS.get(ph, colors.gray)
            hex_ph = ph_col.hexval() if hasattr(ph_col, "hexval") else "#888888"
            recovery_marker = " *" if w.get("is_recovery") else ""
            table_data.append(
                [
                    Paragraph(str(w["week"]), self.cell_style),
                    Paragraph(
                        f'<font color="{hex_ph}">{ph.title()}{recovery_marker}</font>',
                        self.cell_style,
                    ),
                    Paragraph(w["swim_volume"], self.cell_style),
                    Paragraph(w["bike_volume"], self.cell_style),
                    Paragraph(w["run_volume"], self.cell_style),
                    Paragraph(f'~{w["total_hours"]}', self.cell_style),
                ]
            )

        t = Table(
            table_data,
            colWidths=[1.4 * cm, 2.2 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm, 2 * cm],
        )
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(t)
        story.append(
            Paragraph("* Recovery week", self.small_style)
        )
        story.append(Spacer(1, 0.4 * cm))

    def _week_page(self, story: list, week: dict) -> None:
        ph = week["phase"]
        ph_col = _PHASE_COLOURS.get(ph, colors.gray)
        hex_ph = ph_col.hexval() if hasattr(ph_col, "hexval") else "#888888"
        recovery = " — Recovery" if week.get("is_recovery") else ""

        story.append(
            Paragraph(
                f'Week {week["week"]}  '
                f'<font color="{hex_ph}">[ {ph.title()} Phase{recovery} ]</font>',
                self.section_style,
            )
        )

        # Volume row
        vol_data = [
            [
                Paragraph("Swim", self.header_cell_style),
                Paragraph("Bike", self.header_cell_style),
                Paragraph("Run", self.header_cell_style),
                Paragraph("Total", self.header_cell_style),
            ],
            [
                Paragraph(week["swim_volume"], self.cell_style),
                Paragraph(week["bike_volume"], self.cell_style),
                Paragraph(week["run_volume"], self.cell_style),
                Paragraph(f'~{week["total_hours"]} hrs', self.cell_style),
            ],
        ]
        vol_t = Table(vol_data, colWidths=[3.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm])
        vol_t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), _SWIM_COL),
                    ("BACKGROUND", (1, 0), (1, 0), _BIKE_COL),
                    ("BACKGROUND", (2, 0), (2, 0), _RUN_COL),
                    ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#475569")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 1), (-1, 1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(vol_t)
        story.append(Spacer(1, 0.35 * cm))

        # Day schedule
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        abbr  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        sched = week.get("weekly_schedule", {})

        sched_header = [Paragraph(a, self.header_cell_style) for a in abbr]
        sched_row    = []
        for day in days:
            activities = sched.get(day, ["rest"])
            text = " + ".join(a.upper() for a in activities)
            sched_row.append(Paragraph(text, self.cell_style))

        sched_t = Table(
            [sched_header, sched_row],
            colWidths=[2 * cm] * 7,
        )
        sched_t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, 1), 7),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(sched_t)
        story.append(Spacer(1, 0.35 * cm))

        # Key sessions
        story.append(Paragraph("Key Sessions", self.normal_style))
        sessions_data = [
            [
                Paragraph("Type", self.header_cell_style),
                Paragraph("Name", self.header_cell_style),
                Paragraph("Description", self.header_cell_style),
            ]
        ]
        for s in week.get("key_sessions", []):
            s_type = s["type"]
            col = _SESSION_COLOURS.get(s_type, colors.HexColor("#6b7280"))
            hex_s = col.hexval() if hasattr(col, "hexval") else "#6b7280"
            sessions_data.append(
                [
                    Paragraph(
                        f'<font color="{hex_s}"><b>{s_type.upper()}</b></font>',
                        self.cell_style,
                    ),
                    Paragraph(s["name"], self.cell_style),
                    Paragraph(s["description"], self.cell_style),
                ]
            )

        sess_t = Table(
            sessions_data,
            colWidths=[1.8 * cm, 3.5 * cm, 8.7 * cm],
        )
        sess_t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(sess_t)
        story.append(Spacer(1, 0.3 * cm))

        # Coaching note
        note = week.get("coaching_note", "")
        if note:
            story.append(
                Paragraph(f"<i>Coach's Note: {note}</i>", self.small_style)
            )

    def _footer(self, story: list) -> None:
        story.append(Spacer(1, 1 * cm))
        footer_style = ParagraphStyle(
            "Footer",
            parent=self.styles["Normal"],
            fontSize=7,
            alignment=TA_CENTER,
            textColor=colors.gray,
        )
        story.append(
            Paragraph("Generated by RunCoach · Triathlon Training Plan", footer_style)
        )
        story.append(
            Paragraph(
                "Consult a sports medicine professional before starting any new training programme.",
                footer_style,
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cache_key(self, plan: TriathlonPlan) -> str:
        h = hashlib.md5(plan.plan_data.encode()).hexdigest()
        return f"tri_{plan.id}_{h}.pdf"
