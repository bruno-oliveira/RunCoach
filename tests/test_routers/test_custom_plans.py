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


def test_the_builder_sits_under_plan_in_the_navbar():
    template = create_templates().env.from_string(
        '{% from "components/nav.html" import render as nav %}'
        "{{ nav(user=user, path='/plans/custom/new') }}"
    )
    user = SimpleNamespace(id="u1", name="Nav", intervals_athlete_id=None)
    html = template.render(user=user)
    assert 'href="/plan" class="nav-link is-active"' in html


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


def test_options_bound_each_cell_by_the_plan_length(client):
    def limits(weeks):
        data = client.get(
            "/api/custom-plans/options",
            params={"target_distance": 42.2, "max_runs_per_week": 4, "weeks": weeks},
        ).json()
        for cell in data["cells"]:
            assert (
                len(data["defaults"]["menus"][cell["phase"]][cell["slot"]])
                <= (cell["limit"])
            )
        return {(c["phase"], c["slot"]): c["limit"] for c in data["cells"]}

    long_plan, short_plan = limits(24), limits(8)
    assert long_plan[("build", "long")] == 5
    assert short_plan[("build", "long")] < 5


def test_options_lay_out_the_phases_the_limits_come_from(client):
    data = client.get(
        "/api/custom-plans/options",
        params={"target_distance": 42.2, "max_runs_per_week": 4, "weeks": 14},
    ).json()
    shape = data["shape"]
    assert [s["phase"] for s in shape] == ["base", "build", "peak", "taper"]
    assert sum(s["weeks"] for s in shape) == 14
    assert shape[-1]["training_weeks"] == 0
    training = {s["phase"]: s["training_weeks"] for s in shape}
    for cell in data["cells"]:
        assert cell["training_weeks"] == training[cell["phase"]]
        assert cell["limit"] == min(5, training[cell["phase"]])


def test_options_follow_the_frequency_the_base_can_carry(client):
    # 12 km over 5 runs is under 2.5 km a run: the generator plans 4, so the
    # builder offers the 4-run grid and says why.
    data = client.get(
        "/api/custom-plans/options",
        params={
            "target_distance": 5.0,
            "max_runs_per_week": 5,
            "weeks": 10,
            "current_km": 12,
        },
    ).json()
    assert data["requested_runs_per_week"] == 5
    assert data["runs_per_week"] == 4
    assert ("build", "quality") in {(c["phase"], c["slot"]) for c in data["cells"]}
    assert data["blocker"] is None


def test_options_say_when_the_basics_cannot_make_a_plan(client):
    data = client.get(
        "/api/custom-plans/options",
        params={
            "target_distance": 21.1,
            "max_runs_per_week": 4,
            "weeks": 14,
            "current_km": 10,
        },
    ).json()
    assert "below the recommended minimum" in data["blocker"]["message"]
    assert data["blocker"]["suggestion"]


def test_preview_validates_against_the_frequency_the_plan_runs(client):
    body = _basics(
        current_km=12,
        target_distance=5.0,
        weeks=10,
        max_runs_per_week=5,
        custom_spec=_spec(runs=4, dist=5.0),
    )
    response = client.post("/api/custom-plans/preview", json=body, headers=ORIGIN)
    assert response.status_code == 200, response.json()
    # A spec for the 5-run grid fills cells the 4-run plan never reads.
    body["custom_spec"] = _spec(runs=5, dist=5.0)
    response = client.post("/api/custom-plans/preview", json=body, headers=ORIGIN)
    assert response.status_code == 422


def test_preview_names_the_strength_sessions(client):
    spec = _spec()
    spec["strength"] = {"sessions_per_week": 2, "template": "climb_descent"}
    weeks = client.post(
        "/api/custom-plans/preview",
        json=_basics(custom_spec=spec),
        headers=ORIGIN,
    ).json()["weeks"]
    labels = {d["strength"] for w in weeks for d in w["days"] if d["strength"]}
    assert labels == {"Climb", "Descent"}


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
