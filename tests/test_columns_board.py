"""Knowledge Columns board: several questions can share the same score."""
from contents.game_board_creator import get_available_questions, select_question


def board():
    return {
        "science": {
            100: [{"id": "Q1", "points": 100}, {"id": "Q2", "points": 100}],
            300: [{"id": "Q3", "points": 300}],
        }
    }


def test_every_question_at_a_score_is_listed():
    avail = get_available_questions(board(), set())
    assert [q["id"] for q in avail["science"][100]] == ["Q1", "Q2"]
    assert [q["id"] for q in avail["science"][300]] == ["Q3"]
    assert list(avail["science"].keys()) == [300, 100]  # highest score first


def test_each_question_keeps_its_own_answered_state():
    avail = get_available_questions(board(), {"Q2"})
    states = {q["id"]: q["answered"] for q in avail["science"][100]}
    assert states == {"Q1": False, "Q2": True}


def test_select_a_specific_question_by_id():
    b, answered = board(), set()
    q = select_question(b, answered, "science", 100, question_id="Q2")
    assert q["id"] == "Q2" and answered == {"Q2"}
    assert select_question(b, answered, "science", 100, question_id="Q2") is None  # already used
    assert select_question(b, answered, "science", 100)["id"] == "Q1"           # no id: first unanswered
