"""Guards for the single design system (light + dark mode, no colour themes)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_old_theme_files_are_gone():
    assert not os.path.exists(os.path.join(ROOT, "static", "css", "themes"))
    assert not os.path.exists(os.path.join(ROOT, "static", "css", "custom.css"))
    assert not os.path.exists(os.path.join(ROOT, "static", "css", "ai.css"))


def test_stylesheet_has_light_and_dark_tokens_and_no_shadows():
    css = re.sub(r"/\*.*?\*/", "", _read("static", "css", "style.css"), flags=re.S)
    assert ':root[data-theme="dark"]' in css
    for token in ("--bg:", "--surface:", "--raised:", "--accent-1:", "--on-accent:"):
        assert token in css
    for banned in ("box-shadow", "text-shadow", "drop-shadow"):
        assert banned not in css, banned


def test_base_templates_boot_the_mode_before_paint():
    for name in ("base.html", "gamebase.html"):
        html = _read("templates", name)
        assert '{% include "_theme_boot.html" %}' in html
        assert "custom.css" not in html
        assert html.index("_theme_boot.html") < html.index("css/style.css")
    boot = _read("templates", "_theme_boot.html")
    assert "prefers-color-scheme: dark" in boot and "avirta-theme" in boot


def test_legacy_look_settings_are_ignored_on_load():
    from contents.admin_controls.admin_setup import AdminSetup, is_legacy_look_setting

    setup = AdminSetup.__new__(AdminSetup)
    setup.game_settings = {"default_time_limit": 30}
    setup._apply_loaded_settings({
        "default_time_limit": 20,
        "primary_color": "#123456",
        "bg_color_dark": "#000000",
        "box_shadow": "0 2px 5px black",
        "selected_theme": "dark_purple_theme",
        "spacing_md": "15px",
    })
    assert setup.game_settings == {"default_time_limit": 20}
    assert is_legacy_look_setting("text_color_light")
    assert not is_legacy_look_setting("max_players_per_room")


def test_admin_look_and_feel_offers_modes_not_themes(client):
    with client.session_transaction() as sess:
        sess["admin_authenticated"] = True
    resp = client.get("/admin")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-mode="light"' in body and 'data-mode="dark"' in body
    assert "apply_theme" not in body
    assert "Apply Selected Theme" not in body
    assert 'name="primary_color"' not in body
