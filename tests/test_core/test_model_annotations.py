"""Every model attribute must be either a mapped column or a relationship.

`TrainingPlan` used to set `__allow_unmapped__ = True` so it could carry three
view-only attributes (`status_label`, `target_distance_display`,
`experience_level`) written per request by a decorator. That flag is gone: the
display fields now live in a `PlanStatus` view model
(`app.contexts.plan.plan_status`), so the ORM class is all columns and
relationships, and SQLAlchemy rejects an un-`Mapped` annotation outright.

The flag was a real hole while it existed — with it on, a future *column*
annotation that forgets its `Mapped[]` silently becomes a plain attribute instead
of raising. Nothing else would catch it, because the suite builds its schema from
Alembic migrations rather than from the model metadata, so a column that exists
in the database but is not mapped would just never be written to.

These tests keep both directions honest: no annotated attribute that is neither a
column nor a relationship, and no `Mapped[]` annotation without a backing column.
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

# Un-`Mapped` annotations allowed on a model. It is empty on purpose: the only
# three that ever existed were `TrainingPlan`'s view-only display fields, and
# those moved to the `PlanStatus` view model. Adding an entry here is a
# deliberate act; forgetting `Mapped[]` on a column is not.
VIEW_ONLY_ATTRIBUTES: dict[str, str] = {}

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
def test_no_model_has_an_unmapped_annotation(model):
    undeclared = _unmapped_annotations(model) - set(VIEW_ONLY_ATTRIBUTES)

    assert not undeclared, (
        f"{model.__name__} has annotated attribute(s) that are neither "
        f"`Mapped[...]` columns nor documented extras: {sorted(undeclared)}. "
        f"Add `Mapped[...]` (and a migration) if it is a column; view state "
        f"belongs in a view model (see app.contexts.plan.plan_status), not on "
        f"the ORM class."
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


def test_the_allow_list_is_empty():
    """The only exemption that ever existed was for the view fields; both are gone."""
    assert VIEW_ONLY_ATTRIBUTES == {}
    assert not _unmapped_annotations(TrainingPlan)


def test_training_plan_carries_no_view_state():
    """Display fields belong to the PlanStatus view model, not to the ORM class."""
    plan = TrainingPlan(id="x", user_id="u")

    for field in ("status_label", "target_distance_display", "experience_level"):
        assert not hasattr(plan, field), (
            f"TrainingPlan.{field} is view state again — read it from "
            f"app.contexts.plan.plan_status.plan_status(plan, today) instead"
        )

    # And the opt-in that made room for it is gone with it.
    assert not getattr(TrainingPlan, "__allow_unmapped__", False)
