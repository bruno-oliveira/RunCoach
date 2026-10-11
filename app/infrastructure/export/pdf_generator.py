"""Entry point for the downloadable training-plan PDF.

The document itself is the Runna-style landscape sheet in
``app.infrastructure.export.runna``; this module only decides *when* to render
one, keying the cache on everything the render actually reads.
"""

import logging
from typing import Any, Dict, List

from reportlab.pdfgen.canvas import Canvas

from app.core.i18n import DEFAULT_LANGUAGE, normalize_language
from app.infrastructure.export.pdf_base import PDFBase
from app.infrastructure.export.plan_export_dto import PlanExportDTO
from app.infrastructure.export.runna import (
    build_sheet,
    localize_sheet,
    render_sheet,
    theme,
)
from app.infrastructure.export.runna.sections import build_sections
from app.infrastructure.i18n import localizer, translate

logger = logging.getLogger(__name__)

#: Bumped whenever the layout changes, so a redesign invalidates cached renders
#: instead of serving the previous design until the TTL expires.
LAYOUT_VERSION = "runna-3"


class PDFGenerator(PDFBase):
    def generate_pdf(
        self,
        plan_data: List[Dict[str, Any]],
        training_plan: PlanExportDTO,
        language: str | None = None,
    ) -> str:
        """Render the plan sheet and return the path to the PDF.

        ``training_plan`` is a :class:`PlanExportDTO`. Callers convert from the
        SQLAlchemy ``TrainingPlan`` model via ``PlanExportDTO.from_orm(plan)``.
        ``language`` is the one the runner is reading the app in; the sheet is
        built in English and translated before it is painted.
        """
        code = normalize_language(language) or DEFAULT_LANGUAGE
        cache_key = self._cache_key_from_hash(
            # The language is part of the document, so it is part of the key:
            # without it the first reader's language would be everyone's.
            f"{LAYOUT_VERSION}_{code}_",
            training_plan.id,
            {
                "plan": plan_data,
                "weeks": training_plan.weeks_duration,
                "target_km": training_plan.target_distance_km,
                "current_km": training_plan.current_weekly_km,
                "vdot": training_plan.vdot,
                "trail": training_plan.is_trail,
                "loops": training_plan.backyard_target_loops,
                "nutrition": training_plan.nutrition_plan_data,
            },
        )

        def build(path: str) -> None:
            sheet = build_sheet(
                training_plan, plan_data, build_sections(training_plan, plan_data)
            )
            sheet = localize_sheet(sheet, localizer(code))
            canvas = Canvas(path, pagesize=(theme.PAGE_W, theme.PAGE_H))
            canvas.setTitle(" ".join(sheet.cover.title_lines))
            canvas.setAuthor("RunCoach")
            canvas.setSubject(translate("Training plan", code))
            render_sheet(canvas, sheet)
            canvas.save()

        return self._generate_with_cache(
            cache_key, f"running_plan_{training_plan.id}.pdf", build
        )
