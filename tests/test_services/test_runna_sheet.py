"""The Runna-style plan sheet: what a card says and where a week lands.

These exercise the pure layout model rather than the rendered PDF, so a wording
or grouping regression names itself instead of showing up as a diff in a binary.
"""

import datetime

import pytest

from app.contexts.plan.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.infrastructure.export.pdf_generator import PDFGenerator
from app.infrastructure.export.plan_export_dto import PlanExportDTO
from app.infrastructure.export.runna import build_sheet
from app.infrastructure.export.runna.sections import build_sections
from app.infrastructure.export.runna.sheet import DayCard, _card, _week_cards


def _dto(plan_data: list, **overrides) -> PlanExportDTO:
    base = dict(
        id="sheet-test",
        plan_type="distance",
        target_distance="21.1",
        target_distance_km=21.1,
        weeks_duration=len(plan_data),
        current_weekly_km=30.0,
        created_at=datetime.datetime(2026, 8, 22),
        plan_data=plan_data,
        vdot=45.0,
    )
    base.update(overrides)
    return PlanExportDTO(**base)


@pytest.fixture(scope="module")
def half_plan() -> list:
    return TrainingPlanGenerator().generate_plan(
        30.0, 21.1, 12, max_runs_per_week=5, vdot=45.0
    )


# --- cards ----------------------------------------------------------------


def test_rest_day_becomes_a_rest_card():
    assert _card({"day": 7, "type": "rest", "distance": 0}).kind == "rest"


def test_missing_days_are_filled_with_rest():
    cards = _week_cards({"daily_workouts": [{"day": 3, "type": "easy", "distance": 5}]})
    assert len(cards) == 7
    assert cards[2].kind == "easy"
    assert [card.kind for card in cards if card.kind != "rest"] == ["easy"]


def test_easy_run_with_strides_says_so():
    card = _card(
        {
            "day": 1,
            "type": "easy",
            "distance": 6.1,
            "steps": [{"kind": "run"}, {"kind": "strides"}],
        }
    )
    assert card == DayCard(kind="easy", headline="6.1K + strides", label="Easy Run")


def test_quality_headline_carries_the_rep_shape():
    card = _card(
        {
            "day": 4,
            "type": "tempo",
            "distance": 6.9,
            "structure": "2 x (1 km at threshold pace / 1 km easy float)",
        }
    )
    assert card.headline == "6.9K · 2×1km"
    assert card.label == "Tempo"


def test_quality_headline_falls_back_to_distance_without_a_shape():
    assert _card({"day": 4, "type": "interval", "distance": 3.9}).headline == "3.9K"


def test_long_run_headline_names_its_flavour():
    card = _card(
        {
            "day": 6,
            "type": "long",
            "distance": 16.8,
            "key_workout_name": "Fast-Finish Long Run",
            "structure": "16.8km with last 3km at threshold pace",
        }
    )
    assert card.headline == "16.8K fast finish"


def test_zero_distance_recovery_reads_as_cross_training():
    card = _card(
        {
            "day": 2,
            "type": "recovery",
            "distance": 0,
            "description": "Active recovery: Easy walking to promote blood flow",
        }
    )
    assert card.headline == "Easy walk"
    assert card.kind == "recovery"


def test_run_walk_card_is_measured_in_minutes():
    card = _card({"day": 1, "type": "run_walk", "distance": 1.0, "duration_min": 20})
    assert card.headline == "20 min"
    assert card.label == "Run / Walk"


def test_strength_session_is_marked_on_the_card():
    card = _card(
        {
            "day": 1,
            "type": "easy",
            "distance": 6.0,
            "strength_session": {"type": "core"},
        }
    )
    assert card.strength is True


# --- weeks and phases -----------------------------------------------------


def test_phases_group_consecutive_weeks(half_plan):
    sheet = build_sheet(_dto(half_plan), half_plan)
    assert [phase.title for phase in sheet.phases] == [
        "Base Building",
        "Build",
        "Peak",
        "Taper & Race",
    ]
    assert sheet.phases[0].eyebrow == "PHASE 1"
    assert sheet.phases[0].subtitle.startswith("Weeks 1–4 · ")
    numbers = [week.number for phase in sheet.phases for week in phase.weeks]
    assert numbers == list(range(1, 13))


def test_recovery_week_is_tagged_deload(half_plan):
    sheet = build_sheet(_dto(half_plan), half_plan)
    tagged = {
        week.number
        for phase in sheet.phases
        for week in phase.weeks
        if week.tag == "DELOAD"
    }
    assert tagged == {week["week"] for week in half_plan if week.get("is_recovery")}
    assert tagged


def test_race_week_is_tagged():
    plan = [
        {
            "week": 1,
            "phase": "taper",
            "total_km": 20,
            "daily_workouts": [{"day": 7, "type": "race", "distance": 21.1}],
        }
    ]
    sheet = build_sheet(_dto(plan), plan)
    week = sheet.phases[0].weeks[0]
    assert week.tag == "(RACE)"
    assert week.cards[6].label == "RACE DAY"
    assert week.cards[6].kind == "race"


def test_single_week_phase_reads_as_one_week():
    plan = [{"week": 1, "phase": "peak", "total_km": 20, "daily_workouts": []}]
    sheet = build_sheet(_dto(plan), plan)
    assert sheet.phases[0].subtitle.startswith("Week 1 · ")


# --- cover ----------------------------------------------------------------


def test_cover_names_the_race_and_the_block(half_plan):
    cover = build_sheet(_dto(half_plan), half_plan).cover
    assert cover.title_lines == ("Half Marathon", "12-Week Plan")
    assert any(chip.text.startswith("GOAL: HALF MARATHON") for chip in cover.stats)
    assert any(chip.text == "12 WEEKS" for chip in cover.stats)


def test_legend_only_lists_the_kinds_the_plan_uses(half_plan):
    cover = build_sheet(_dto(half_plan), half_plan).cover
    kinds = [chip.kind for chip in cover.legend]
    assert "easy" in kinds and "long" in kinds
    assert "race" not in kinds  # this plan carries no race-day workout
    assert kinds == sorted(
        kinds, key=["easy", "long", "quality", "recovery", "strength", "race"].index
    )


def test_trail_cover_names_the_distance(half_plan):
    dto = _dto(half_plan, target_distance_km=50.0, is_trail=True)
    assert build_sheet(dto, half_plan).cover.title_lines[0] == "50 km Trail"


# --- rendering ------------------------------------------------------------


def test_render_produces_a_multi_page_pdf(tmp_path, half_plan):
    dto = _dto(half_plan)
    path = PDFGenerator(cache_dir=str(tmp_path / "cache")).generate_pdf(half_plan, dto)
    data = open(path, "rb").read()
    assert data.startswith(b"%PDF-")
    assert data.count(b"/Type /Page\n") >= 6
    assert len(data) > 5000


def test_second_render_is_served_from_cache(tmp_path, half_plan):
    generator = PDFGenerator(cache_dir=str(tmp_path / "cache"))
    dto = _dto(half_plan)
    first = generator.generate_pdf(half_plan, dto)
    second = generator.generate_pdf(half_plan, dto)
    assert first == second


def test_a_different_vdot_renders_a_different_file(tmp_path, half_plan):
    generator = PDFGenerator(cache_dir=str(tmp_path / "cache"))
    assert generator.generate_pdf(
        half_plan, _dto(half_plan, vdot=45.0)
    ) != generator.generate_pdf(half_plan, _dto(half_plan, vdot=52.0))


def test_beginner_plan_renders(tmp_path):
    plan = BeginnerPlanGenerator().generate_plan(5.0, 8, 3)
    dto = _dto(plan, target_distance_km=5.0, current_weekly_km=0.0, vdot=None)
    path = PDFGenerator(cache_dir=str(tmp_path / "cache")).generate_pdf(plan, dto)
    assert open(path, "rb").read().startswith(b"%PDF-")


def test_all_sheet_text_is_renderable_by_the_base_fonts(half_plan):
    """Helvetica is WinAnsi-encoded — an unmapped glyph would print as a box."""
    dto = _dto(half_plan)
    sheet = build_sheet(dto, half_plan, build_sections(dto, half_plan))
    strings = [
        sheet.footer,
        sheet.cover.eyebrow,
        sheet.cover.description,
        *sheet.cover.title_lines,
        *(chip.text for chip in sheet.cover.stats),
        *(chip.text for chip in sheet.cover.legend),
    ]
    for phase in sheet.phases:
        strings += [phase.eyebrow, phase.title, phase.subtitle]
        for week in phase.weeks:
            strings.append(week.tag)
            strings += [card.headline for card in week.cards]
            strings += [card.label for card in week.cards]
    for section in sheet.sections:
        strings += [section.eyebrow, section.title, section.subtitle]
        for row in section.rows:
            strings += [row.lead, row.body]

    for text in strings:
        text.encode("cp1252")  # raises UnicodeEncodeError on an unmapped glyph
