"""The custom-plan builder's endpoints, and creating a custom plan."""

import json
from datetime import date
from types import SimpleNamespace

from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_service import PlanService
from app.contexts.plan.plan_status import plan_status
from app.core.training.custom_plan import default_spec
from app.models import TrainingPlan, User
from app.schemas import PlanRequest
from app.web.templating import create_templates

ORIGIN = {"Origin": "http://testserver"}


def _basics(**over):
    body = {
        "current_km": 35,
        "target_distance": 21.1,
        "weeks": 14,
        "max_runs_per_week": 4,
    }
    body.update(over)
    return body


def _spec(runs=4, dist=21.1):
    return default_spec(runs, target_distance=dist).to_json()


def test_builder_page_renders(client):
    response = client.get("/plans/custom/new")
    assert response.status_code == 200
    assert "Build your own plan" in response.text


def test_signed_in_navbar_links_to_the_builder():
    template = create_templates().env.from_string(
        '{% from "components/nav.html" import render as nav %}'
        "{{ nav(user=user, current_page='custom_plan') }}"
    )
    user = SimpleNamespace(id="u1", name="Nav", intervals_athlete_id=None)
    html = template.render(user=user)
    assert 'href="/plans/custom/new" class="nav-link is-active"' in html
    assert 'data-i18n="nav.custom_plan"' in html


def test_options_follow_the_frequency(client):
    four = client.get(
        "/api/custom-plans/options",
        params={"target_distance": 21.1, "max_runs_per_week": 4},
    ).json()
    five = client.get(
        "/api/custom-plans/options",
        params={"target_distance": 21.1, "max_runs_per_week": 5},
    ).json()
    assert {(c["phase"], c["slot"]) for c in four["cells"]} == {
        ("base", "long"),
        ("build", "long"),
        ("build", "quality"),
        ("peak", "long"),
        ("peak", "quality"),
    }
    assert ("peak", "threshold") in {(c["phase"], c["slot"]) for c in five["cells"]}
    assert all(c["options"] for c in five["cells"])
    assert five["defaults"]["menus"]["build"]["speed"]


def test_options_refuse_fewer_than_three_runs(client):
    response = client.get(
        "/api/custom-plans/options",
        params={"target_distance": 10, "max_runs_per_week": 2},
    )
    assert response.status_code == 422


def test_preview_is_the_generated_plan(client):
    response = client.post(
        "/api/custom-plans/preview",
        json=_basics(custom_spec=_spec()),
        headers=ORIGIN,
    )
    assert response.status_code == 200
    weeks = response.json()["weeks"]
    assert len(weeks) == 14
    names = {d["name"] for w in weeks for d in w["days"] if d["name"]}
    assert "Negative Split" in names or "Steady Long Run" in names


def test_preview_points_at_the_cell_at_fault(client):
    spec = _spec()
    spec["menus"]["build"]["quality"] = []
    response = client.post(
        "/api/custom-plans/preview",
        json=_basics(custom_spec=spec),
        headers=ORIGIN,
    )
    assert response.status_code == 422
    problems = response.json()["problems"]
    assert {"key": "empty_cell", "phase": "build", "slot": "quality"}.items() <= (
        problems[0].items()
    )


def test_preview_needs_choices(client):
    response = client.post("/api/custom-plans/preview", json=_basics(), headers=ORIGIN)
    assert response.status_code == 422


def test_generate_plan_stores_the_choices(client, test_db):
    response = client.post(
        "/generate-plan",
        data={
            "current_km": "35",
            "target_distance": "21.1",
            "weeks": "14",
            "max_runs_per_week": "4",
            "custom_spec": json.dumps(_spec()),
        },
        headers=ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text[:500]
    plan = test_db.query(TrainingPlan).one()
    assert plan.custom_spec == _spec()
    assert plan.custom_index == 1


def test_generate_plan_rejects_unreadable_choices(client, test_db):
    response = client.post(
        "/generate-plan",
        data={
            "current_km": "35",
            "target_distance": "21.1",
            "weeks": "14",
            "max_runs_per_week": "4",
            "custom_spec": "{not json",
        },
        headers=ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code != 303
    assert test_db.query(TrainingPlan).count() == 0


# --- the service: numbering and identity ------------------------------------


def _service():
    return PlanService()


def _create(test_db, user, **over):
    request = PlanRequest(**_basics(**over))
    plan, _ = _service().create_plan(
        request, user, test_db, TrainingPlanGenerator(), NutritionEngine(random_seed=1)
    )
    return plan


def test_custom_plans_are_numbered_and_titled(test_db):
    user = User()
    test_db.add(user)
    test_db.flush()
    first = _create(test_db, user, custom_spec=_spec())
    second_spec = _spec(5)
    second = _create(test_db, user, max_runs_per_week=5, custom_spec=second_spec)
    assert (first.custom_index, second.custom_index) == (1, 2)
    status = plan_status(second, today=date(2026, 10, 15))
    assert status.custom_title == "Custom Plan 2 · Half Marathon"


def test_identity_includes_the_choices(test_db):
    user = User()
    test_db.add(user)
    test_db.flush()
    generated = _create(test_db, user)
    custom = _create(test_db, user, custom_spec=_spec())
    again = _create(test_db, user, custom_spec=_spec())
    assert custom.id != generated.id
    assert again.id == custom.id
    assert generated.custom_spec is None and generated.custom_index is None
