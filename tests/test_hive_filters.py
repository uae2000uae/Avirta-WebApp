"""The Hive create form: point values and tags. Questions are always multiple
choice and come from every category the chosen tags allow."""
import json

from contents.thehive.hex_game_room import HexGameRoom
from questionmanagement.category_tags import categories_matching_tags


def q(i, type_="multiple_choice", cat="cars", points=100):
    base = {"id": f"q{i}", "type": type_, "question": f"Question {i}?", "points": points,
            "category_id": cat, "correct_answer": "A"}
    if type_ == "multiple_choice":
        base["options"] = ["A", "B", "C", "D"]
    return base


class FakeUploader:
    def __init__(self, questions):
        self.questions = {x["id"]: x for x in questions}


def pool(room, questions):
    return room._get_filtered_questions(FakeUploader(questions))


def test_only_multiple_choice_reaches_the_board():
    room = HexGameRoom("h", "T", "Blue", "Red", point_values=[100])
    got = pool(room, [q(1), q(2, "true_false"), q(3, "text")])
    assert [x["id"] for x in got] == ["q1"]


def test_categories_limit_the_pool_and_empty_means_all():
    qs = [q(1, cat="cars"), q(2, cat="science"), q(3, cat="sports")]
    some = HexGameRoom("h", "T", "Blue", "Red", point_values=[100], categories=["cars", "sports"])
    assert {x["id"] for x in pool(some, qs)} == {"q1", "q3"}
    every = HexGameRoom("h", "T", "Blue", "Red", point_values=[100])
    assert len(pool(every, qs)) == 3


def test_old_saved_rooms_without_categories_still_work():
    room = HexGameRoom("h", "T", "Blue", "Red", point_values=[100])
    del room.categories
    assert len(pool(room, [q(1), q(2)])) == 2


def test_tags_widen_within_a_group_and_narrow_across_groups(tmp_path):
    p = tmp_path / "tags.json"
    p.write_text(json.dumps({
        "tags": {"english": {"en": "English", "ar": "a", "group": "language"},
                 "arabic": {"en": "Arabic", "ar": "b", "group": "language"},
                 "cars": {"en": "Cars", "ar": "c", "group": "topic"},
                 "sports": {"en": "Sports", "ar": "d", "group": "topic"}},
        "categories": {"a": ["english", "cars"], "b": ["arabic", "sports"], "c": ["english", "sports"]}}),
        encoding="utf-8")
    ids = ["a", "b", "c"]
    assert categories_matching_tags(ids, [], path=str(p)) == ids
    assert categories_matching_tags(ids, ["english"], path=str(p)) == ["a", "c"]
    assert categories_matching_tags(ids, ["cars", "sports"], path=str(p)) == ["a", "b", "c"]
    assert categories_matching_tags(ids, ["english", "sports"], path=str(p)) == ["c"]
    assert categories_matching_tags(ids, ["arabic", "cars"], path=str(p)) == []


def test_create_form_has_points_and_tags_only(client):
    html = client.get("/hex/create_room").get_data(as_text=True)
    assert 'name="point_values"' in html and 'name="tags"' in html
    assert 'name="question_types"' not in html
    assert 'name="categories"' not in html


def test_pool_counts_questions_for_the_chosen_tags(client):
    every = client.get("/api/hex/pool?point_values=100,200,300,400,500").get_json()
    english = client.get("/api/hex/pool?point_values=100,200,300,400,500&tags=english").get_json()
    assert every["board_cells"] == 25 and every["enough"]
    assert 0 < english["categories"] < every["categories"]
    assert english["count"] < every["count"]
    none = client.get("/api/hex/pool?point_values=").get_json()
    assert none["count"] == 0 and not none["enough"]
