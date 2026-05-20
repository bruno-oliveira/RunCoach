"""PDF training plan generator — orchestrator that delegates to page mixins."""

import json
import logging
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle

from .pdf_base import PDFBase
from .pdf_nutrition_pages import NutritionPagesMixin
from .pdf_plan_pages import PlanPagesMixin
from .pdf_plan_renderers import get_renderer_for_plan
from .pdf_supplementary_pages import SupplementaryPagesMixin
from .plan_export_dto import PlanExportDTO

logger = logging.getLogger(__name__)


class PDFGenerator(PDFBase, PlanPagesMixin, NutritionPagesMixin, SupplementaryPagesMixin):

    def __init__(self, cache_dir: str | None = None):
        super().__init__(cache_dir)
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        self.title_style = ParagraphStyle(
            'CustomTitle', parent=self.styles['Heading1'],
            fontSize=24, spaceAfter=30,
            textColor=colors.HexColor('#667eea'), alignment=TA_CENTER,
        )
        self.subtitle_style = ParagraphStyle(
            'CustomSubtitle', parent=self.styles['Heading2'],
            fontSize=16, spaceAfter=20,
            textColor=colors.HexColor('#764ba2'), alignment=TA_CENTER,
        )
        self.section_style = ParagraphStyle(
            'SectionHeader', parent=self.styles['Heading3'],
            fontSize=14, spaceAfter=12, spaceBefore=20,
            textColor=colors.HexColor('#667eea'), alignment=TA_LEFT,
        )
        self.normal_style = ParagraphStyle(
            'CustomNormal', parent=self.styles['Normal'],
            fontSize=10, spaceAfter=6, leading=14,
        )
        self.small_style = ParagraphStyle(
            'CustomSmall', parent=self.styles['Normal'],
            fontSize=8, spaceAfter=3, leading=10,
        )
        self.table_cell_style = ParagraphStyle(
            'TableCell', parent=self.styles['Normal'],
            fontSize=8, leading=10, wordWrap='CJK',
        )
        self.table_header_style = ParagraphStyle(
            'TableHeader', parent=self.styles['Normal'],
            fontSize=9, leading=11, wordWrap='CJK', alignment=TA_CENTER,
        )

    def generate_pdf(
        self, plan_data: List[Dict[str, Any]], training_plan: PlanExportDTO
    ) -> str:
        """Generate a professional PDF training plan.

        ``training_plan`` is a :class:`PlanExportDTO`. Callers convert from the
        SQLAlchemy ORM model via ``PlanExportDTO.from_orm(plan)``.

        Returns path to generated PDF file.
        """
        plan_str = json.dumps(plan_data, sort_keys=True)
        cache_key = self._cache_key_from_hash("", training_plan.id, plan_str)
        renderer = get_renderer_for_plan(training_plan)

        def build(doc, story):
            self._add_title_page(story, training_plan, plan_data, renderer)
            self._add_plan_summary(story, training_plan, plan_data, renderer)
            renderer.build_body(self, story, training_plan, plan_data)
            self._add_footer(story)

        return self._generate_with_cache(
            cache_key, f"running_plan_{training_plan.id}.pdf", build
        )
