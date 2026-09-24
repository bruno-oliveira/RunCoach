"""The mobile app shell: the web-app manifest and the bottom tab bar.

These two pieces are what turn a phone browser into something that behaves
like an installed app. If the manifest stops being served with the right
content type the app is no longer installable, and if the tab bar stops
rendering there is no primary navigation on a phone at all.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.template_helpers import create_templates

STATIC_ROOT = Path(__file__).resolve().parents[2] / "app" / "web" / "static"

ICON_192 = "/static/icons/icon-192.png"
ICON_512 = "/static/icons/icon-512.png"
ICON_MASKABLE = "/static/icons/icon-maskable-512.png"


def _render_tab_bar(*, user=None, path="/"):
    """Render just the tab bar macro, so the assertions can't be satisfied by
    unrelated markup elsewhere on the page."""
    env = create_templates().env
    template = env.from_string(
        '{% from "components/tab_bar.html" import render as tab_bar %}'
        "{{ tab_bar(user=user, path=path) }}"
    )
    # Collapse the template's attribute wrapping so links can be matched as
    # one string.
    return re.sub(r"\s+", " ", template.render(user=user, path=path))


@pytest.fixture
def signed_in_user():
    """The tab bar only reads truthiness off the user, so no session needed."""
    return SimpleNamespace(id="tab-user-1", name="Tab Tester")


class TestWebManifest:
    def test_served_with_the_manifest_content_type(self, client):
        resp = client.get("/manifest.webmanifest")

        assert resp.status_code == 200
        # nosniff is set app-wide, so a guessed content type would make the
        # browser refuse the manifest outright.
        assert resp.headers["content-type"].startswith("application/manifest+json")

    def test_declares_an_installable_standalone_app(self, client):
        data = client.get("/manifest.webmanifest").json()

        assert data["name"] == "RunCoach"
        assert data["short_name"] == "RunCoach"
        assert data["display"] == "standalone"
        # The installed app opens on the plan in progress (see /today).
        assert data["start_url"] == "/today"
        assert data["scope"] == "/"
        assert data["theme_color"]

    def test_declares_the_icons_the_app_shell_links(self, client):
        icons = client.get("/manifest.webmanifest").json()["icons"]
        srcs = {icon["src"] for icon in icons}

        assert {ICON_192, ICON_512, ICON_MASKABLE} <= srcs
        assert any(icon.get("purpose") == "maskable" for icon in icons)
        assert any(icon["sizes"] == "192x192" for icon in icons)
        assert any(icon["sizes"] == "512x512" for icon in icons)

    def test_every_declared_icon_exists_on_disk(self, client):
        for icon in client.get("/manifest.webmanifest").json()["icons"]:
            assert icon["src"].startswith("/static/"), icon["src"]
            on_disk = STATIC_ROOT / icon["src"].removeprefix("/static/")
            assert on_disk.is_file(), f"missing icon: {on_disk}"


class TestAppShellMarkup:
    def test_home_page_links_the_manifest_and_home_screen_icons(self, client):
        html = client.get("/").text

        assert 'rel="manifest" href="/manifest.webmanifest"' in html
        assert 'rel="apple-touch-icon"' in html
        assert 'rel="icon"' in html
        assert 'name="apple-mobile-web-app-capable"' in html
        assert 'name="theme-color"' in html
        # Without viewport-fit=cover the safe-area insets collapse to zero and
        # the tab bar sits under the home indicator.
        assert "viewport-fit=cover" in html

    def test_mobile_app_stylesheet_is_shipped_and_linked(self, client):
        assert (STATIC_ROOT / "css" / "mobile-app.css").is_file()
        assert "/static/css/mobile-app.css" in client.get("/").text

    def test_tab_bar_renders_for_anonymous_visitors(self, client):
        html = client.get("/").text

        assert 'class="tab-bar"' in html
        assert 'data-i18n="nav.home"' in html

    def test_anonymous_tab_bar_offers_only_public_surfaces(self):
        bar = _render_tab_bar(path="/")

        assert 'href="/recipes"' in bar
        assert 'href="/tips"' in bar
        assert 'data-i18n="tab.sign_in"' in bar
        # No account-only surfaces, and nothing to expand into.
        assert 'data-i18n="tab.more"' not in bar
        assert 'href="/my-plans"' not in bar
        assert 'href="/analytics"' not in bar

    def test_signed_in_tab_bar_carries_the_daily_surfaces(self, signed_in_user):
        bar = _render_tab_bar(user=signed_in_user, path="/")

        assert 'href="/my-plans"' in bar
        assert 'href="/analytics"' in bar
        assert 'href="/recipes"' in bar
        assert 'data-i18n="tab.more"' in bar
        # Signed in, so there is nothing to sign into.
        assert 'data-i18n="tab.sign_in"' not in bar

    def test_home_tab_is_current_on_the_landing_page(self, signed_in_user):
        bar = _render_tab_bar(user=signed_in_user, path="/")

        assert 'class="tab-item is-active" href="/" aria-current="page"' in bar

    @pytest.mark.parametrize(
        "path",
        ["/my-plans", "/plan/42"],
    )
    def test_plan_surfaces_highlight_the_plans_tab(self, signed_in_user, path):
        bar = _render_tab_bar(user=signed_in_user, path=path)

        assert 'class="tab-item is-active" href="/my-plans" aria-current="page"' in bar

    def test_anonymous_visitor_on_a_public_page_highlights_that_tab(self):
        bar = _render_tab_bar(path="/recipes")

        assert 'class="tab-item is-active" href="/recipes" aria-current="page"' in bar
