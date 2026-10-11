"""Persisting in-place edits to JSON columns."""

from sqlalchemy.orm.attributes import flag_modified


def persist_json(instance, attr_name: str) -> None:
    # SQLAlchemy's default JSON column type doesn't observe in-place
    # mutations, and reassigning the same Python reference doesn't flag the
    # column dirty either — so any nested dict/list edit (e.g. mutating
    # plan_data[w]["daily_workouts"][i]["distance"]) is silently dropped at
    # commit. Call this after such mutations to force a write.
    flag_modified(instance, attr_name)
