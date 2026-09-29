"""Every model attribute must be either a mapped column or a documented extra.

`TrainingPlan` sets `__allow_unmapped__ = True` so it can carry three view-only
decorated attributes (`status_label`, `target_distance_display`,
`experience_level`) that `app.contexts.plan.plan_status` fills in per request.
That opt-in is necessary — SQLAlchemy's annotated-declarative form rejects a bare
annotation without it, and `ClassVar` would forbid the per-instance write.

It is also a small hole: with the flag on, a future *column* annotation that
forgets its `Mapped[]` silently becomes a plain attribute instead of raising.
Nothing else would catch it — the test suite builds its schema from Alembic
migrations rather than from the model metadata, so a column that exists in the
database but is not mapped would just never be written to.

This test closes the hole by asserting the allow-list is exactly as long as it is
supposed to be. A new bare annotation fails here, with the fix named.
"""

import typing

import pytest

from app.models import (
    DailyWorkout,
    FavoriteRecipe,
    NotificationLog,
    PlanCustomization,
    PushSubscription,
    ReadinessLog,
    RefreshToken,
    RunFeedback,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
    WellnessDay,
)

MODELS = [
    User,
    TrainingPlan,
    WeeklyPlan,
    DailyWorkout,
    RunLog,
    RunFeedback,
    ReadinessLog,
    WellnessDay,
    FavoriteRecipe,
    RefreshToken,
    NotificationLog,
    PlanCustomization,
    PushSubscription,
]

# The only attributes allowed to be un-`Mapped`, with the reason. Adding to this
# list is a deliberate act; forgetting `Mapped[]` on a column is not.
VIEW_ONLY_ATTRIBUTES: dict[str, str] = {
    "status_label": "decorated per request by plan_status.decorate_plan_status",
    "target_distance_display": "decorated per request by plan_status.decorate_plan_status",
    "experience_level": "decorated per request by plan_status.decorate_plan_status",
}

_IGNORED = {
    "__table_args__",
    "__tablename__",
    "__allow_unmapped__",
    "__mapper_args__",
    "__table__",
    "__abstract__",
}


def _unmapped_annotations(model: type) -> set[str]:
    """Annotated attributes on ``model`` that are not ``Mapped[...]``."""
    found = set()
    for name, annotation in (getattr(model, "__annotations__", {}) or {}).items():
        if name.startswith("_") or name in _IGNORED:
            continue
        text = str(annotation)
        if "Mapped[" in text or "Mapped[" in text.replace(" ", ""):
            continue
        if typing.get_origin(annotation) is typing.ClassVar:
            continue
        found.add(name)
    return found


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_only_documented_view_attributes_are_unmapped(model):
    undeclared = _unmapped_annotations(model) - set(VIEW_ONLY_ATTRIBUTES)

    assert not undeclared, (
        f"{model.__name__} has annotated attribute(s) that are neither "
        f"`Mapped[...]` columns nor documented view-only extras: "
        f"{sorted(undeclared)}. Add `Mapped[...]` (and a migration) if it is a "
        f"column, or add it to VIEW_ONLY_ATTRIBUTES with a reason if it is not."
    )


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_no_mapped_annotation_lost_its_column(model):
    """An `__allow_unmapped__` class could silently drop a column; prove it did not."""
    mapped = {
        name
        for name, annotation in (getattr(model, "__annotations__", {}) or {}).items()
        if "Mapped[" in str(annotation).replace(" ", "")
    }
    table_columns = set(model.__table__.columns.keys())
    relationships = set(model.__mapper__.relationships.keys())

    assert table_columns | relationships == mapped, (
        f"{model.__name__}: mapped annotations and the table disagree. "
        f"columns-only={sorted(table_columns - mapped)}, "
        f"annotations-without-a-column={sorted(mapped - table_columns - relationships)}"
    )


def test_the_allow_list_stays_honest():
    """Each documented extra must really exist and really be unmapped."""
    declared = _unmapped_annotations(TrainingPlan)

    assert set(VIEW_ONLY_ATTRIBUTES) <= declared, (
        "an attribute in VIEW_ONLY_ATTRIBUTES is no longer unmapped — remove it "
        "from the list rather than leaving a stale exemption"
    )


def test_view_only_attributes_default_to_none():
    """An undecorated plan must read None, not raise AttributeError."""
    plan = TrainingPlan(id="x", user_id="u")

    assert plan.status_label is None
    assert plan.target_distance_display is None
    assert plan.experience_level is None


def test_decorating_a_plan_does_not_add_columns():
    """The decorator writes instance attributes; the schema must not move."""
    columns_before = set(TrainingPlan.__table__.columns.keys())

    plan = TrainingPlan(id="x", user_id="u")
    plan.status_label = "Week 3 of 12"
    plan.target_distance_display = "10K"
    plan.experience_level = "intermediate"

    assert plan.status_label == "Week 3 of 12"
    assert set(TrainingPlan.__table__.columns.keys()) == columns_before
    # A fresh instance is unaffected — these are per-instance, not class state.
    assert TrainingPlan(id="y", user_id="u").status_label is None
