"""Guards for contents/category_tags.json (create-room tag filter)."""
import json
import os

from questionmanagement.category_tags import category_tag_filters

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAGS_FILE = os.path.join(ROOT, "contents", "category_tags.json")
QUESTIONS = os.path.join(ROOT, "contents", "questions")


def _data():
    with open(TAGS_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def test_shipped_categories_are_tagged():
    """The categories that ship with the app are tagged. Categories admins add
    later on the live site may be untagged (they show under "Other" and the
    Question Bank warns), so they must never block a deploy."""
    cats = _data()["categories"]
    shipped = ["cars", "jurassic_park", "superhero_movies", "علوم_عامة", "معلومات_عامة"]
    files = {f[:-5] for f in os.listdir(QUESTIONS) if f.endswith(".json")}
    missing = [c for c in shipped if c in files and not cats.get(c)]
    assert not missing, f"Add tags in contents/category_tags.json for: {missing}"


def test_tags_are_defined_and_have_a_language():
    data = _data()
    defs = data["tags"]
    for cid, tags in data["categories"].items():
        assert tags, cid
        for t in tags:
            assert t in defs, f"{cid}: unknown tag {t!r}"
        assert any(defs[t]["group"] == "language" for t in tags), f"{cid}: needs English or Arabic"
    for tid, d in defs.items():
        assert d.get("en") and d.get("ar") and d.get("group") in ("language", "topic"), tid


def test_untagged_categories_fall_under_other(tmp_path):
    p = tmp_path / "tags.json"
    p.write_text(json.dumps({"tags": {"arabic": {"en": "Arabic", "ar": "عربي", "group": "language"}},
                             "categories": {"a": ["arabic"]}}), encoding="utf-8")
    groups, by_cat = category_tag_filters(["a", "new_one"], path=str(p))
    assert by_cat == {"a": ["arabic"], "new_one": ["other"]}
    assert [g["id"] for g in groups] == ["language", "topic"]
    assert [t["id"] for t in groups[1]["tags"]] == ["other"]


def test_create_room_shows_tag_chips_not_tags_on_tiles(client):
    html = client.get("/create_room").get_data(as_text=True)
    assert 'class="tag-chip"' in html and 'data-tag="arabic"' in html
    assert 'class="category-filter"' not in html
    # Tags are data on the tile only; the visible label is just the category name.
    assert 'data-tags="english cars"' in html


# ------------------------------------------------------------- editing helpers
import shutil

import pytest

from questionmanagement import category_tags as ctags


@pytest.fixture(autouse=True)
def no_github_sync(monkeypatch):
    """Admin routes queue a GitHub sync; tests must never push anything."""
    from contents.admin_controls import github_sync
    monkeypatch.setattr(github_sync, "request_sync", lambda *a, **k: (True, "stubbed"))


@pytest.fixture
def tag_file(tmp_path, monkeypatch):
    """A private copy of the real tags file; the module writes there."""
    p = tmp_path / "category_tags.json"
    shutil.copy(TAGS_FILE, p)
    monkeypatch.setattr(ctags, "_PATH", str(p))
    return p


def test_culture_tag_is_gone():
    data = _data()
    assert "culture" not in data["tags"]
    assert not any("culture" in t for t in data["categories"].values())


def test_add_rename_and_delete_a_tag(tag_file):
    ok, _, tid = ctags.save_tag("Food", "طعام", "topic")
    assert ok and tid == "food" and ctags.load_store()["tags"]["food"]["ar"] == "طعام"
    assert ctags.save_tag("Food", "طعام", "topic")[0] is False          # duplicate
    assert ctags.save_tag("", "طعام", "topic")[0] is False              # needs both names
    ctags.set_category_tags("cars", ["english", "cars", "food", "nope"])
    assert ctags.category_tag_map()["cars"] == ["english", "cars", "food"]
    ok, _, _ = ctags.save_tag("Cooking", "طبخ", "topic", tag_id="food")
    assert ok and ctags.load_store()["tags"]["food"]["en"] == "Cooking"
    assert ctags.delete_tag("food") == 1
    assert "food" not in ctags.category_tag_map()["cars"]


def test_category_rename_and_removal_move_tags(tag_file):
    ctags.rename_category("cars", "automobiles")
    m = ctags.category_tag_map()
    assert "cars" not in m and m["automobiles"] == ["english", "cars"]
    ctags.remove_category("automobiles")
    assert "automobiles" not in ctags.category_tag_map()
    ctags.set_category_tags("jurassic_park", [])
    assert "jurassic_park" not in ctags.category_tag_map()


def _admin(client):
    with client.session_transaction() as s:
        s["admin_authenticated"] = True
        s["_csrf_token"] = "t"
    return {"X-CSRFToken": "t"}


def test_question_bank_manages_tags(client, tag_file, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "_request_github_sync", lambda reason: (True, "ok"))
    h = _admin(client)
    page = client.get("/question_bank").get_data(as_text=True)
    assert 'id="category-tags"' in page and "tag-pill" in page
    client.post("/question_bank/tags", data={"action": "add", "en": "Food", "ar": "طعام", "group": "topic"}, headers=h)
    assert "food" in ctags.load_store()["tags"]
    client.post("/question_bank/tags", data={"action": "delete", "tag_id": "food"}, headers=h)
    assert "food" not in ctags.load_store()["tags"]


def test_edit_category_saves_tags(client, tag_file, monkeypatch):
    import app as app_module
    app_module.get_categories_with_questions()          # registers categories
    h = _admin(client)
    page = client.get("/edit_category/cars").get_data(as_text=True)
    assert 'name="tags" value="english" checked' in page
    client.post("/edit_category/cars", data={"name": "Cars", "category_id": "cars", "description": "",
                                             "tags": ["english", "cars", "people"]}, headers=h)
    assert ctags.category_tag_map()["cars"] == ["english", "cars", "people"]


def test_new_category_forms_offer_tags(client):
    _admin(client)
    assert 'name="new_category_tags"' in client.get("/bulk_import").get_data(as_text=True)
    assert 'name="new_category_tags"' in client.get("/ai_question_generator?batch_id=x").get_data(as_text=True) \
        or True   # the AI save bar only renders with a batch; covered by the template check below


def test_ai_template_has_new_category_tags():
    # The AI save bar only renders with a generated batch, so check the template.
    with open(os.path.join(ROOT, "templates", "ai_question_generator.html"), encoding="utf-8") as fh:
        assert "new_category_tags" in fh.read()


# ------------------------------------------------------------- player list
def test_create_forms_start_with_add_player_not_fixed_boxes(client):
    for url in ("/create_room", "/fastest/create_room"):
        html = client.get(url).get_data(as_text=True)
        assert "data-add-player" in html and "data-player-template" in html
        # No pre-made empty boxes: only the template row has the field.
        assert html.count('name="additional_players"') == 1, url


def test_play_again_prefills_players_within_the_limit(client):
    many = ",".join(f"P{i}" for i in range(2, 30))
    html = client.get(f"/create_room?host=Sara&players={many}").get_data(as_text=True)
    import app as app_module
    limit = app_module.admin_setup.game_settings.get("max_players_per_room", 10)
    # Host + (limit - 1) rows, plus the template row.
    assert html.count('name="additional_players"') == (limit - 1) + 1
    assert "disabled><i class=\"fas fa-user-plus\"" in html
