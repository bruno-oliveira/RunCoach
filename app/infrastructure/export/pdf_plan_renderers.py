"""Plan-type renderer registry for the PDF generator.

Encapsulates the per-plan-type branches that previously lived inline in
``pdf_generator.py`` and ``pdf_plan_pages.py``. Each renderer owns:

- the title / subtitle strings,
- the target-display string,
- the stats table on the title page,
- the summary chart (header columns + per-week rows),
- the body story (zones page, weekly pages, etc.).

PDFGenerator picks the matching renderer for a plan and delegates rendering
to it; new plan types are added by writing one subclass and prepending to
``PLAN_PDF_RENDERERS``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Spacer, Table, TableStyle

from app.core.training.trail_profile import TRAIL_SENTINEL_KM
from app.infrastructure.export.plan_export_dto import PlanExportDTO

if TYPE_CHECKING:
    from app.infrastructure.export.pdf_generator import PDFGenerator


class PdfPlanRenderer(ABC):
    """Per-plan-type PDF rendering behavior."""

    @abstractmethod
    def matches(self, dto: PlanExportDTO) -> bool: ...

    # --- Title page ---

    @abstractmethod
    def title_text(self) -> str: ...

    @abstractmethod
    def subtitle_text(self, dto: PlanExportDTO) -> str: ...

    @abstractmethod
    def target_display(self, dto: PlanExportDTO) -> str: ...

    @abstractmethod
    def stats_table_rows(
        self, pdf: "PDFGenerator", dto: PlanExportDTO, plan_data: List[Dict[str, Any]]
    ) -> List[List[str]]: ...

    # --- Summary chart ---

    @abstractmethod
    def summary_chart(
        self, pdf: "PDFGenerator", plan_data: List[Dict[str, Any]]
    ) -> Table: ...

    # --- Body ---

    @abstractmethod
    def build_body(
        self,
        pdf: "PDFGenerator",
        story: List,
        dto: PlanExportDTO,
        plan_data: List[Dict[str, Any]],
    ) -> None: ...


def _summary_table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#667eea")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
        ]
    )


class PerformancePdfRenderer(PdfPlanRenderer):
    def matches(self, dto: PlanExportDTO) -> bool:
        return dto.plan_type == "performance"

    def title_text(self) -> str:
        return "⚡ Performance Training Plan"

    def subtitle_text(self, dto: PlanExportDTO) -> str:
        return f"Target: {dto.target_distance}km Race | {dto.weeks_duration} Weeks"

    def target_display(self, dto: PlanExportDTO) -> str:
        return f"{dto.target_distance} km"

    def stats_table_rows(
        self, pdf: "PDFGenerator", dto: PlanExportDTO, plan_data: List[Dict[str, Any]]
    ) -> List[List[str]]:
        target = self.target_display(dto)
        if dto.current_pace and dto.goal_pace:
            improvement = ((dto.current_pace - dto.goal_pace) / dto.current_pace) * 100
            return [
                ["Target Distance", target],
                ["Current Pace", pdf._format_pace(dto.current_pace)],
                ["Goal Pace", pdf._format_pace(dto.goal_pace)],
                ["Target Improvement", f"{improvement:.1f}%"],
                ["Training Duration", f"{dto.weeks_duration} weeks"],
                ["Weekly Mileage", f"{dto.current_weekly_km:.1f} km"],
            ]
        return _default_stats_rows(dto, plan_data, target)

    def summary_chart(
        self, pdf: "PDFGenerator", plan_data: List[Dict[str, Any]]
    ) -> Table:
        return _phase_summary_chart(pdf, plan_data)

    def build_body(
        self,
        pdf: "PDFGenerator",
        story: List,
        dto: PlanExportDTO,
        plan_data: List[Dict[str, Any]],
    ) -> None:
        story.append(Spacer(1, 0.5 * cm))
        pdf._add_performance_philosophy(story)

        story.append(PageBreak())
        pdf._add_training_zones_page(story, dto)
        pdf._add_pace_improvement_summary(story, dto)

        for week in plan_data:
            story.append(PageBreak())
            pdf._add_performance_weekly_plan(story, week)

        if dto.nutrition_plan_data:
            story.append(PageBreak())
            pdf._add_personalized_nutrition_plan(story, dto)

        story.append(PageBreak())
        pdf._add_nutrition_guidance(story)


class FitnessPdfRenderer(PdfPlanRenderer):
    def matches(self, dto: PlanExportDTO) -> bool:
        return dto.plan_type == "fitness"

    def title_text(self) -> str:
        return "💪 Fitness Training Plan"

    def subtitle_text(self, dto: PlanExportDTO) -> str:
        focus = self._focus(dto)
        return f"Focus: {focus} | {dto.weeks_duration} Weeks"

    def target_display(self, dto: PlanExportDTO) -> str:
        return self._focus(dto)

    @staticmethod
    def _focus(dto: PlanExportDTO) -> str:
        return dto.target_distance.replace("fitness_", "").replace("_", " ").title()

    def stats_table_rows(
        self, pdf: "PDFGenerator", dto: PlanExportDTO, plan_data: List[Dict[str, Any]]
    ) -> List[List[str]]:
        return _default_stats_rows(dto, plan_data, self.target_display(dto))

    def summary_chart(
        self, pdf: "PDFGenerator", plan_data: List[Dict[str, Any]]
    ) -> Table:
        return _phase_summary_chart(pdf, plan_data)

    def build_body(
        self,
        pdf: "PDFGenerator",
        story: List,
        dto: PlanExportDTO,
        plan_data: List[Dict[str, Any]],
    ) -> None:
        _distance_body(pdf, story, dto, plan_data)


class DistancePdfRenderer(PdfPlanRenderer):
    """Fallback renderer for traditional distance-based plans."""

    def matches(self, dto: PlanExportDTO) -> bool:
        return True

    def title_text(self) -> str:
        return "🏃‍♂️ Personalized Running Training Plan"

    def subtitle_text(self, dto: PlanExportDTO) -> str:
        return f"Target: {dto.target_distance}km Race | {dto.weeks_duration} Weeks"

    def target_display(self, dto: PlanExportDTO) -> str:
        target_km = dto.target_distance_km
        if dto.is_trail:
            display = f"{target_km:g} km Trail"
            if dto.target_elevation_gain_m is not None:
                display += f" · {int(dto.target_elevation_gain_m)} m vert"
            return display
        if target_km == TRAIL_SENTINEL_KM:
            return "Trail Running"
        return f"{dto.target_distance} km"

    def stats_table_rows(
        self, pdf: "PDFGenerator", dto: PlanExportDTO, plan_data: List[Dict[str, Any]]
    ) -> List[List[str]]:
        return _default_stats_rows(dto, plan_data, self.target_display(dto))

    def summary_chart(
        self, pdf: "PDFGenerator", plan_data: List[Dict[str, Any]]
    ) -> Table:
        max_mileage = max(week["total_km"] for week in plan_data)
        chart_data: List[List[str]] = [["Week", "Mileage (km)", "Progress"]]
        for week in plan_data:
            progress = pdf._create_progress_bar(week["total_km"], max_mileage)
            chart_data.append(
                [f"Week {week['week']}", f"{week['total_km']:.1f}", progress]
            )
        table = Table(chart_data, colWidths=[2 * cm, 2 * cm, 6 * cm])
        table.setStyle(_summary_table_style())
        return table

    def build_body(
        self,
        pdf: "PDFGenerator",
        story: List,
        dto: PlanExportDTO,
        plan_data: List[Dict[str, Any]],
    ) -> None:
        _distance_body(pdf, story, dto, plan_data)


def _default_stats_rows(
    dto: PlanExportDTO, plan_data: List[Dict[str, Any]], target_display: str
) -> List[List[str]]:
    return [
        ["Current Weekly Mileage", f"{dto.current_weekly_km} km"],
        ["Target Distance", target_display],
        ["Training Duration", f"{dto.weeks_duration} weeks"],
        ["Peak Week Mileage", f"{max(week['total_km'] for week in plan_data):.1f} km"],
    ]


def _phase_summary_chart(pdf: "PDFGenerator", plan_data: List[Dict[str, Any]]) -> Table:
    max_mileage = max(week["total_km"] for week in plan_data)
    chart_data: List[List[str]] = [["Week", "Phase", "Mileage (km)", "Progress"]]
    for week in plan_data:
        progress = pdf._create_progress_bar(week["total_km"], max_mileage)
        phase = week.get("phase", "").title()
        chart_data.append(
            [f"Week {week['week']}", phase, f"{week['total_km']:.1f}", progress]
        )
    table = Table(chart_data, colWidths=[2 * cm, 2 * cm, 2 * cm, 5 * cm])
    table.setStyle(_summary_table_style())
    return table


def _distance_body(
    pdf: "PDFGenerator",
    story: List,
    dto: PlanExportDTO,
    plan_data: List[Dict[str, Any]],
) -> None:
    story.append(PageBreak())

    for week in plan_data:
        pdf._add_weekly_plan(story, week)
        story.append(PageBreak())

    if story and isinstance(story[-1], PageBreak):
        story.pop()

    if dto.nutrition_plan_data:
        story.append(PageBreak())
        pdf._add_personalized_nutrition_plan(story, dto)

    story.append(PageBreak())
    pdf._add_nutrition_guidance(story)

    story.append(PageBreak())
    pdf._add_injury_prevention(story)


PLAN_PDF_RENDERERS: List[PdfPlanRenderer] = [
    PerformancePdfRenderer(),
    FitnessPdfRenderer(),
    DistancePdfRenderer(),
]


def get_renderer_for_plan(dto: PlanExportDTO) -> PdfPlanRenderer:
    for renderer in PLAN_PDF_RENDERERS:
        if renderer.matches(dto):
            return renderer
    raise ValueError(f"No PDF renderer matched plan_type={dto.plan_type!r}")
