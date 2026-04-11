"""PDF training plan generator — orchestrator that delegates to page mixins."""

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer

from app.models import TrainingPlan

from .pdf_nutrition_pages import NutritionPagesMixin
from .pdf_plan_pages import PlanPagesMixin
from .pdf_supplementary_pages import SupplementaryPagesMixin

logger = logging.getLogger(__name__)


class PDFGenerator(PlanPagesMixin, NutritionPagesMixin, SupplementaryPagesMixin):
    CACHE_TTL_SECONDS = 3600

    def __init__(self, cache_dir: str = "/tmp/pdf_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _evict_stale_cache(self) -> None:
        cutoff = time.time() - self.CACHE_TTL_SECONDS
        try:
            for entry in self.cache_dir.iterdir():
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink(missing_ok=True)
        except OSError:
            pass

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

    def _get_cache_key(self, plan_data: list, training_plan) -> str:
        plan_str = json.dumps(plan_data, sort_keys=True)
        content_hash = hashlib.md5(plan_str.encode()).hexdigest()
        return f"{training_plan.id}_{content_hash}.pdf"

    def generate_pdf(self, plan_data: List[Dict[str, Any]], training_plan: TrainingPlan) -> str:
        """Generate a professional PDF training plan.

        Returns path to generated PDF file.
        """
        self._evict_stale_cache()

        cache_key = self._get_cache_key(plan_data, training_plan)
        cache_path = self.cache_dir / cache_key

        if cache_path.exists():
            logger.info(f"Using cached PDF: {cache_key}")
            return str(cache_path)

        logger.info(f"Generating new PDF: {cache_key}")

        temp_dir = tempfile.mkdtemp()
        pdf_path = os.path.join(temp_dir, f"running_plan_{training_plan.id}.pdf")

        doc = SimpleDocTemplate(
            pdf_path, pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )

        story = []
        is_performance = getattr(training_plan, 'plan_type', 'distance') == 'performance'

        self._add_title_page(story, training_plan, plan_data)
        self._add_plan_summary(story, training_plan, plan_data)

        if is_performance:
            self._build_performance_story(story, training_plan, plan_data)
        else:
            self._build_distance_story(story, training_plan, plan_data)

        self._add_footer(story)

        doc.build(story)

        shutil.move(pdf_path, cache_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

        return str(cache_path)

    def _build_performance_story(self, story, training_plan, plan_data):
        story.append(Spacer(1, 0.5 * cm))
        self._add_performance_philosophy(story)

        story.append(PageBreak())
        self._add_training_zones_page(story, training_plan)
        self._add_pace_improvement_summary(story, training_plan)

        for week in plan_data:
            story.append(PageBreak())
            self._add_performance_weekly_plan(story, week)

        if training_plan.nutrition_plan_data:
            story.append(PageBreak())
            self._add_personalized_nutrition_plan(story, training_plan)

        story.append(PageBreak())
        self._add_nutrition_guidance(story)

    def _build_distance_story(self, story, training_plan, plan_data):
        story.append(PageBreak())

        for week in plan_data:
            self._add_weekly_plan(story, week)
            story.append(PageBreak())

        if story and isinstance(story[-1], PageBreak):
            story.pop()

        if training_plan.nutrition_plan_data:
            story.append(PageBreak())
            self._add_personalized_nutrition_plan(story, training_plan)

        story.append(PageBreak())
        self._add_nutrition_guidance(story)

        story.append(PageBreak())
        self._add_injury_prevention(story)
