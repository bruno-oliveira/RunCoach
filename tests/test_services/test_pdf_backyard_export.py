"""A backyard plan reaches the exported sheet as a loop count, not a projection.

The plan is stored as a trail plan over a *clamped* distance, so every export
surface that reads ``target_distance_km`` would print a race the runner never
entered ("163 km Trail" on the cover of a 48-loop plan). These tests force a
real render so a broken cover or an unencodable glyph fails loudly.
"""

import datetime

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.backyard_profile import classify_backyard
from app.infrastructure.export.pdf_generator import PDFGenerator
from app.infrastructure.export.plan_export_dto import PlanExportDTO
from app.infrastructure.export.runna.sheet import _race_name


@pytest.fixture(scope="module")
def backyard_plan():
    profile = classify_backyard(24)
    plan = TrainingPlanGenerator().generate_plan(
        70.0,
        profile.equivalent_distance_km,
        20,
        max_runs_per_week=5,
        vdot=45.0,
        backyard_profile=profile,
    )
    return profile, plan


def _dto(profile, plan_data, plan_id="backyard-test") -> PlanExportDTO:
    return PlanExportDTO(
        id=plan_id,
        plan_type="distance",
        target_distance=str(profile.equivalent_distance_km),
        target_distance_km=profile.equivalent_distance_km,
        weeks_duration=len(plan_data),
        current_weekly_km=70.0,
        created_at=datetime.datetime(2026, 8, 23),
        plan_data=plan_data,
        vdot=45.0,
        is_trail=True,
        target_elevation_gain_m=0.0,
        is_backyard=True,
        backyard_target_loops=profile.target_loops,
    )


class TestCoverName:
    def test_the_cover_names_the_loop_count(self, backyard_plan):
        profile, plan_data = backyard_plan
        assert _race_name(_dto(profile, plan_data)) == "24-Loop Backyard"

    def test_two_goals_that_clamp_alike_still_get_different_covers(self, backyard_plan):
        _, plan_data = backyard_plan
        a = classify_backyard(36)
        b = classify_backyard(48)
        assert a.equivalent_distance_km == b.equivalent_distance_km
        assert _race_name(_dto(a, plan_data)) != _race_name(_dto(b, plan_data))

    def test_a_trail_plan_is_unaffected(self, backyard_plan):
        _, plan_data = backyard_plan
        dto = _dto(classify_backyard(24), plan_data)
        dto.is_backyard = False
        dto.backyard_target_loops = None
        assert "Loop" not in _race_name(dto)


class TestRender:
    def test_a_backyard_plan_renders_to_a_pdf(self, backyard_plan, tmp_path):
        profile, plan_data = backyard_plan
        path = PDFGenerator().generate_pdf(
            plan_data, _dto(profile, plan_data, plan_id="backyard-render")
        )
        assert path.endswith(".pdf")
        with open(path, "rb") as fh:
            content = fh.read()
        assert content.startswith(b"%PDF")
        assert len(content) > 5000

    def test_the_loop_count_is_part_of_the_render_cache_key(self, backyard_plan):
        """Otherwise a 36- and a 48-loop plan would serve each other's sheet."""
        profile, plan_data = backyard_plan
        gen = PDFGenerator()
        a = _dto(classify_backyard(36), plan_data, plan_id="same-id")
        b = _dto(classify_backyard(48), plan_data, plan_id="same-id")
        assert gen.generate_pdf(plan_data, a) != gen.generate_pdf(plan_data, b)
