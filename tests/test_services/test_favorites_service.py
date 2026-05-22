"""Tests for FavoritesService (E1)."""

import pytest
from sqlalchemy.orm import Session

from app.contexts.nutrition.favorites_service import FavoritesService
from app.models import User


@pytest.fixture
def user(test_db: Session) -> User:
    u = User(id="fav-user-1", email="fav@example.com", name="Fav", google_id="g-fav-1")
    test_db.add(u)
    test_db.commit()
    return u


@pytest.fixture
def service() -> FavoritesService:
    return FavoritesService()


def _recipe(name="Oatmeal", meal_type="breakfast"):
    return {"name": name, "meal_type": meal_type, "calories": 300, "protein": 12}


def test_add_then_list(service, user, test_db):
    result = service.add_favorite(user.id, _recipe(), test_db)
    assert "id" in result and "already_exists" not in result

    favorites = service.list_favorites(user.id, test_db)
    assert len(favorites) == 1
    assert favorites[0]["name"] == "Oatmeal"
    # favorite_id is injected for client-side removal
    assert favorites[0]["favorite_id"] == result["id"]


def test_add_is_deduplicated_by_name(service, user, test_db):
    service.add_favorite(user.id, _recipe(), test_db)
    second = service.add_favorite(user.id, _recipe(), test_db)
    assert second["already_exists"] is True
    assert len(service.list_favorites(user.id, test_db)) == 1


def test_favorite_id_for(service, user, test_db):
    assert service.favorite_id_for(user.id, "Oatmeal", test_db) is None
    added = service.add_favorite(user.id, _recipe(), test_db)
    assert service.favorite_id_for(user.id, "Oatmeal", test_db) == added["id"]


def test_remove_favorite(service, user, test_db):
    added = service.add_favorite(user.id, _recipe(), test_db)
    assert service.remove_favorite(added["id"], user.id, test_db) is True
    assert service.list_favorites(user.id, test_db) == []


def test_remove_missing_returns_false(service, user, test_db):
    assert service.remove_favorite("does-not-exist", user.id, test_db) is False


def test_remove_other_users_favorite_is_denied(service, user, test_db):
    added = service.add_favorite(user.id, _recipe(), test_db)
    other = User(id="other", email="o@e.com", name="O", google_id="g-o")
    test_db.add(other)
    test_db.commit()
    # Another user cannot remove someone else's favorite.
    assert service.remove_favorite(added["id"], other.id, test_db) is False
    assert len(service.list_favorites(user.id, test_db)) == 1
