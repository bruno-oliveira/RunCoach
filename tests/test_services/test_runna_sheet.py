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
from app.infrastructure.export.runna.sections import (
    _key_session_rows,
    build_sections,
)
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
    """An unnamed long run still says what kind of long run it is."""
    card = _card(
        {
            "day": 6,
            "type": "long",
            "distance": 16.8,
            "structure": "16.8km progressive, last 5km at marathon pace",
        }
    )
    assert card.headline == "16.8K progressive"
    assert card.label == "Long Run"


def test_named_session_is_titled_on_the_card():
    """The card carries the same title the app shows, so it looks itself up."""
    card = _card(
        {
            "day": 4,
            "type": "tempo",
            "distance": 6.9,
            "key_workout_name": "Threshold Over-Unders",
            "structure": "2 x (1 km at threshold pace / 1 km easy float)",
        }
    )
    assert card.label == "Threshold Over-Unders"
    assert card.headline == "6.9K · 2×1km"


def test_a_named_card_drops_the_flavour_the_name_already_carries():
    card = _card(
        {
            "day": 6,
            "type": "long",
            "distance": 16.8,
            "key_workout_name": "Fast-Finish Long Run",
            "structure": "16.8km with last 3km at threshold pace",
        }
    )
    assert card.headline == "16.8K"
    assert card.label == "Fast-Finish Long Run"


def test_race_day_keeps_its_generic_shout():
    """The cover already names the race; the card wants the short word."""
    card = _card(
        {
            "day": 7,
            "type": "race",
            "distance": 21.1,
            "key_workout_name": "Half Marathon Race Day",
        }
    )
    assert card.label == "RACE DAY"


def test_every_named_session_is_both_titled_and_described(half_plan):
    """The gap this closes: a card the reference page cannot be reached from."""
    dto = _dto(half_plan)
    sheet = build_sheet(dto, half_plan, build_sections(dto, half_plan))
    named = {
        str(day["key_workout_name"])
        for week in half_plan
        for day in week["daily_workouts"]
        if day.get("key_workout_name")
        and day.get("structure")
        and day.get("type") != "race"
    }
    titled = {
        card.label
        for phase in sheet.phases
        for week in phase.weeks
        for card in week.cards
    }
    section = next(s for s in sheet.sections if s.title == "Key sessions")
    described = {row.lead.split(" · ")[0] for row in section.rows}
    assert named
    assert named <= titled, named - titled
    assert named <= described, named - described


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
    # Every generated plan now ends on its goal race, so "race" is a kind the
    # sheet really uses — the legend has always had a slot for it (last in the
    # ordering below), it just had nothing to put there.
    assert "race" in kinds
    assert kinds == sorted(
        kinds, key=["easy", "long", "quality", "recovery", "strength", "race"].index
    )


def test_legend_omits_kinds_the_plan_does_not_use():
    """The legend is derived from the plan, not a fixed list."""
    plan = [
        {
            "week": 1,
            "phase": "base",
            "total_km": 10,
            "daily_workouts": [{"day": 1, "type": "easy", "distance": 10.0}],
        }
    ]
    kinds = [chip.kind for chip in build_sheet(_dto(plan), plan).cover.legend]
    assert kinds == ["easy"]


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


# --- key sessions reference ------------------------------------------------


def test_key_sessions_say_which_weeks_they_land_in():
    plan = [
        {
            "week": 3,
            "phase": "build",
            "total_km": 30,
            "daily_workouts": [
                {
                    "day": 4,
                    "type": "tempo",
                    "distance": 8.0,
                    "key_workout_name": "Cruise Intervals",
                    "structure": "4 x 1km at threshold",
                }
            ],
        }
    ]
    row = _key_session_rows(plan)[0]
    assert row.lead == "Cruise Intervals · Week 3"
    assert row.body == "4 x 1km at threshold"


def test_a_session_that_grows_lists_every_shape_it_takes():
    """Deduping on the name alone used to misdescribe every later week."""
    plan = [
        {
            "week": week,
            "phase": "build",
            "total_km": 30,
            "daily_workouts": [
                {
                    "day": 6,
                    "type": "long",
                    "distance": km,
                    "key_workout_name": "Alternating Marathon-Pace Long",
                    "structure": f"{km}km alternating 2km easy / 2km marathon pace",
                }
            ],
        }
        for week, km in ((5, 14.5), (10, 19.1))
    ]
    row = _key_session_rows(plan)[0]
    assert row.lead == "Alternating Marathon-Pace Long · Weeks 5, 10"
    assert "Week 5: 14.5km" in row.body
    assert "Week 10: 19.1km" in row.body
    assert row.kind == "long"


def test_consecutive_weeks_collapse_into_a_range():
    plan = [
        {
            "week": week,
            "phase": "base",
            "total_km": 30,
            "daily_workouts": [
                {
                    "day": 4,
                    "type": "tempo",
                    "distance": 8.0,
                    "key_workout_name": "Threshold Run",
                    "structure": "20 min at threshold",
                }
            ],
        }
        for week in (2, 3, 4, 5, 9)
    ]
    assert _key_session_rows(plan)[0].lead == "Threshold Run · Weeks 2–5, 9"


def test_a_named_session_without_a_structure_is_left_off():
    """Race day is named but has nothing to describe."""
    plan = [
        {
            "week": 1,
            "phase": "taper",
            "total_km": 20,
            "daily_workouts": [
                {
                    "day": 7,
                    "type": "race",
                    "distance": 21.1,
                    "key_workout_name": "Half Marathon Race Day",
                    "structure": "",
                }
            ],
        }
    ]
    assert _key_session_rows(plan) == []
