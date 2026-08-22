"""Trail fuelling reaches the exported plan sheet.

The web Nutrition tab and the downloadable PDF should stay in parity for trail
plans, and the fuel names are full of ampersands and en dashes ("PB & honey",
"50–70 g/h"). These tests force a real render so an unencodable glyph or a
missing block surfaces as a failure rather than a silently broken PDF.
"""

import datetime

import pytest

from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.infrastructure.export.pdf_generator import PDFGenerator
from app.infrastructure.export.plan_export_dto import PlanExportDTO
from app.infrastructure.export.runna.sections import build_sections


@pytest.fixture(scope="module")
def trail_plan_data() -> list:
    return TrainingPlanGenerator().generate_plan(
        25.0, 30.0, 10, max_runs_per_week=5, vdot=42.0, terrain="hilly"
    )


def _blueprint(is_trail: bool) -> dict:
    return NutritionEngine(42).generate_weekly_meal_plan(
        weekly_km=40.0,
        target_distance=50.0 if is_trail else 42.2,
        body_weight=70,
        is_trail=is_trail,
        target_elevation_gain_m=1500.0 if is_trail else None,
    )


def _dto(plan_data: list, nutrition: dict | None, is_trail: bool) -> PlanExportDTO:
    return PlanExportDTO(
        id="trail-test",
        plan_type="distance",
        target_distance="50",
        target_distance_km=50.0,
        weeks_duration=len(plan_data),
        current_weekly_km=40.0,
        created_at=datetime.datetime(2026, 8, 22),
        plan_data=plan_data,
        nutrition_plan_data=nutrition,
        vdot=42.0,
        is_trail=is_trail,
    )


def _section(sections, title):
    return next((s for s in sections if s.title == title), None)


def test_trail_fuelling_section_carries_all_three_blocks(trail_plan_data):
    sections = build_sections(
        _dto(trail_plan_data, _blueprint(True), True), trail_plan_data
    )
    trail = _section(sections, "Trail race fuelling")
    assert trail is not None

    leads = " | ".join(row.lead for row in trail.rows)
    bodies = " ".join(row.body for row in trail.rows)
    assert "In-race fuelling" in leads
    assert "Fuel ideas · Before" in leads
    assert "Fuel ideas · During" in leads
    assert "Fuel ideas · After" in leads
    assert "Rehearse it" in leads
    assert bodies.strip()


def test_road_plan_has_no_trail_fuelling_section(trail_plan_data):
    sections = build_sections(
        _dto(trail_plan_data, _blueprint(False), False), trail_plan_data
    )
    assert _section(sections, "Trail race fuelling") is None
    # The generic fuelling page is always present.
    assert _section(sections, "Fuelling") is not None


def test_trail_plan_renders_a_real_pdf(tmp_path, trail_plan_data):
    generator = PDFGenerator(cache_dir=str(tmp_path / "cache"))
    path = generator.generate_pdf(
        trail_plan_data, _dto(trail_plan_data, _blueprint(True), True)
    )
    assert path.endswith(".pdf")
    with open(path, "rb") as handle:
        assert handle.read(5) == b"%PDF-"
