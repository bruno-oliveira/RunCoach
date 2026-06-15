"""PDF export of the trail/ultra fuelling section.

The web Nutrition tab and the downloadable PDF should stay in parity for
trail plans. These tests exercise the ReportLab flowables directly and force
a real document build so that unescaped markup (the fuel names are full of
ampersands like "PB & honey") surfaces as a failure rather than a silent
broken PDF.
"""

from reportlab.platypus import Paragraph, SimpleDocTemplate

from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.infrastructure.export.pdf_generator import PDFGenerator


def _trail_blueprint() -> dict:
    return NutritionEngine(42).generate_weekly_meal_plan(
        weekly_km=40.0,
        target_distance=50.0,
        body_weight=70,
        is_trail=True,
        target_elevation_gain_m=1500.0,
    )


def _paragraph_texts(story) -> str:
    return "\n".join(
        f.text for f in story if isinstance(f, Paragraph) and getattr(f, "text", None)
    )


def test_trail_fuelling_appends_all_three_blocks():
    pdf = PDFGenerator()
    story: list = []
    pdf._add_trail_fuelling(story, _trail_blueprint())

    text = _paragraph_texts(story)
    assert "Trail Race Fuelling" in text
    assert "In-Race Fuelling" in text
    assert "Trail-Ready Fuel" in text
    assert "Trail Fuelling Tips" in text
    # Phase headers from the grouped fuel ideas.
    assert "Before" in text
    assert "During" in text
    assert "After" in text


def test_trail_fuelling_builds_real_pdf_without_markup_errors(tmp_path):
    pdf = PDFGenerator()
    story: list = []
    pdf._add_trail_fuelling(story, _trail_blueprint())
    assert story

    out = tmp_path / "trail.pdf"
    # doc.build parses every Paragraph; an unescaped "&" would raise here.
    SimpleDocTemplate(str(out)).build(story)
    assert out.exists() and out.stat().st_size > 0


def test_trail_fuelling_noop_without_trail_keys():
    pdf = PDFGenerator()
    story: list = []
    # A road blueprint carries no in_race_fueling / trail_* keys.
    road = NutritionEngine(42).generate_weekly_meal_plan(
        weekly_km=40.0, target_distance=42.2, body_weight=70
    )
    pdf._add_trail_fuelling(story, road)
    assert story == []
