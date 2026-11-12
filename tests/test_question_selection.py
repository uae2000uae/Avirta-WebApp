"""Question picking: least-used first using real play counts, varied ties, no repeats in a game."""
import json
import os
import random

from contents import game_board_creator as gbc
from contents.thehive.hex_game_room import HexGameRoom
from questionmanagement import usage_ledger
from questionmanagement.categories_questions.question_uploader import QuestionUploader


def q(i, points=100, uses=0, qtype="multiple_choice"):
    return {"id": f"Q{i:04d}", "type": qtype, "question": f"Question {i}?", "correct_answer": "A",
            "options": ["A", "B", "C", "D"], "points": points, "use_count": uses}


def write_category(folder, name, questions):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as fh:
        json.dump(questions, fh)


def test_loader_adds_the_plays_from_the_usage_ledgers(tmp_path, monkeypatch):
    folder = str(tmp_path / "questions")
    write_category(folder, "geo", [q(1, uses=2), q(2)])
    monkeypatch.setattr(usage_ledger, "get_totals", lambda: {"Q0001": 5})
    up = QuestionUploader(folder)
    up.load_questions()
    assert up.questions["Q0001"]["use_count"] == 7      # 2 in the file + 5 played
    assert up.questions["Q0002"]["use_count"] == 0


def test_editing_a_question_keeps_only_the_base_count_in_its_file(tmp_path, monkeypatch):
    folder = str(tmp_path / "questions")
    write_category(folder, "geo", [q(1, uses=2)])
    monkeypatch.setattr(usage_ledger, "get_totals", lambda: {"Q0001": 5})
    up = QuestionUploader(folder)
    up.load_questions()
    ok, _ = up.update_question("Q0001", {"question": "Edited?"})
    assert ok
    saved = json.load(open(os.path.join(folder, "geo.json"), encoding="utf-8"))[0]
    assert saved["question"] == "Edited?" and saved["use_count"] == 2   # not 7: plays stay in the ledger


def test_least_used_first_and_ties_are_shuffled():
    pool = [q(i, uses=0) for i in range(30)] + [q(100, uses=3), q(101, uses=1)]
    orders = {tuple(x["id"] for x in gbc.least_used_first(pool)[:30]) for _ in range(5)}
    assert len(orders) > 1                                   # ties come out in different orders
    ranked = gbc.least_used_first(pool)
    assert [x["use_count"] for x in ranked] == sorted(x["use_count"] for x in ranked)


def test_consecutive_boards_differ_when_many_questions_are_equally_fresh():
    random.seed(7)
    questions = [q(i, points=p) for i, p in enumerate([100, 200, 300, 400, 500] * 8)]
    first, _, _ = gbc.build_standard_board(questions, None, 10, None)
    second, _, _ = gbc.build_standard_board(questions, None, 10, None)
    ids = lambda board: {x["id"] for items in board.values() for x in items}
    assert ids(first) != ids(second)


class FakeUploader:
    def __init__(self, questions):
        self.questions = {x["id"]: x for x in questions}


def test_hive_never_repeats_a_question_in_one_game():
    room = HexGameRoom("h1", "Test", "Blue", "Red", point_values=[100])
    room.grid = [{"id": i, "points": 100, "state": "neutral", "question": None, "asked": False} for i in range(25)]
    uploader = FakeUploader([q(i) for i in range(12)])
    seen = []
    for cell in range(12):                     # open 12 cells; each is answered wrong and reset
        res = room.select_cell(cell, uploader)
        seen.append(res["cell"]["question"]["id"])
    assert len(set(seen)) == 12                # twelve different questions
    # Pool exhausted: the game still gets a question rather than an empty cell.
    assert room.select_cell(12, uploader)["success"]
