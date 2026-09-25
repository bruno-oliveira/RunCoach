"""Recipe pages and search API: slugs, redirects, filtering and counts."""

from fastapi.testclient import TestClient


def test_detail_page_renders_steps_tip_and_related(client: TestClient):
    resp = client.get("/recipes/shakshuka-with-chickpeas")
    assert resp.status_code == 200
    html = resp.text
    assert "Shakshuka with Chickpeas" in html
    assert 'class="rd-steps"' in html
    assert "Runner&#39;s note" in html or "Runner's note" in html
    assert "More like this" in html
    # The page script must land in a block base.html actually renders.
    assert "saveBtn" in html and "navigator.share" in html


def test_legacy_slug_redirects_to_canonical(client: TestClient):
    resp = client.get("/recipes/salmon-ni%C3%A7oise-salad", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/recipes/salmon-nicoise-salad"


def test_unknown_recipe_is_404(client: TestClient):
    assert client.get("/recipes/definitely-not-a-recipe").status_code == 404


def test_search_matches_ingredients_and_reports_category_counts(client: TestClient):
    data = client.get("/api/recipes", params={"query": "tahini"}).json()
    names = {r["name"] for r in data["recipes"]}
    assert "Quinoa Power Bowl" in names  # tahini is only in its ingredients
    assert sum(data["counts"].values()) == data["total"]


def test_counts_ignore_the_selected_meal_type(client: TestClient):
    everything = client.get("/api/recipes").json()
    trail = client.get("/api/recipes", params={"meal_type": "trail"}).json()
    assert trail["counts"] == everything["counts"]
    assert trail["total"] == everything["counts"]["trail"]
    assert all(r["meal_type"] == "trail" for r in trail["recipes"])


def test_tag_filter_requires_every_tag(client: TestClient):
    data = client.get(
        "/api/recipes", params={"dietary_tags": "vegan,gluten_free", "page_size": 200}
    ).json()
    assert data["total"] > 0
    for recipe in data["recipes"]:
        assert {"vegan", "gluten_free"} <= set(recipe["dietary_tags"])


def test_recipes_carry_slug_and_steps(client: TestClient):
    recipe = client.get("/api/recipes", params={"page_size": 1}).json()["recipes"][0]
    assert recipe["slug"]
    assert recipe["steps"]
    assert recipe["instructions"] == " ".join(recipe["steps"])


def test_tips_page_links_every_fuel_idea_to_a_recipe(client: TestClient):
    html = client.get("/tips").text
    assert html.count('class="trail-fuel-recipe-link"') >= 20
