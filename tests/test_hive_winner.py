"""The Hive: a team wins when its answered cells connect its two board edges."""
from contents.thehive.hex_game_room import HexGameRoom


def room_with(owned_a=(), owned_b=()):
    room = HexGameRoom("r1", "Test", "Blue", "Red")
    room.grid = [{"id": i, "points": 100, "state": "neutral", "question": None, "asked": False} for i in range(25)]
    for i in owned_a:
        room.grid[i]["state"] = "Blue"
    for i in owned_b:
        room.grid[i]["state"] = "Red"
    return room


def idx(r, c):
    return r * 5 + c


def test_neighbors_follow_the_offset_rows():
    room = room_with()
    # Even row: up-left/up/down-left/down; odd row: up/up-right/down/down-right.
    assert sorted(room.neighbors(idx(2, 2))) == sorted([idx(2, 1), idx(2, 3), idx(1, 1), idx(1, 2), idx(3, 1), idx(3, 2)])
    assert sorted(room.neighbors(idx(1, 2))) == sorted([idx(1, 1), idx(1, 3), idx(0, 2), idx(0, 3), idx(2, 2), idx(2, 3)])
    assert sorted(room.neighbors(0)) == sorted([1, idx(1, 0)])


def test_team_a_wins_top_to_bottom():
    # A straight column zig-zags correctly in offset rows: (0,2)(1,1)(2,2)(3,1)(4,2) is connected.
    path = [idx(0, 2), idx(1, 1), idx(2, 2), idx(3, 1), idx(4, 2)]
    w = room_with(owned_a=path).find_winner()
    assert w and w["team"] == "Blue" and w["edges"] == "top-bottom"
    assert w["path"][0] // 5 == 0 and w["path"][-1] // 5 == 4 and len(w["path"]) == 5


def test_team_b_wins_left_to_right_and_path_is_connected():
    cells = [idx(2, 0), idx(2, 1), idx(1, 1), idx(1, 2), idx(2, 3), idx(2, 4)]
    room = room_with(owned_b=cells)
    w = room.find_winner()
    assert w and w["team"] == "Red" and w["edges"] == "left-right"
    for a, b in zip(w["path"], w["path"][1:]):
        assert b in room.neighbors(a)


def test_no_winner_with_a_gap_or_wrong_edges():
    # Team A owns a full left-to-right row: that is not its edges, so no win.
    assert room_with(owned_a=[idx(2, c) for c in range(5)]).find_winner() is None
    # A column missing one link.
    assert room_with(owned_a=[idx(0, 2), idx(1, 1), idx(3, 1), idx(4, 2)]).find_winner() is None


def test_answer_reports_the_winner_and_board_locks(monkeypatch):
    import contents.thehive.hex_game_room as hgr
    monkeypatch.setattr(hgr, "increment_use_count", lambda *_a, **_k: None)  # no usage writes
    room = room_with(owned_a=[idx(0, 2), idx(1, 1), idx(2, 2), idx(3, 1)])
    target = idx(4, 2)
    room.grid[target]["question"] = {"id": "Q1", "question": "?", "correct_answer": "Yes", "options": ["Yes", "No"]}
    room.current_cell_index = target
    res = room.submit_answer("Blue", "Yes")
    assert res["correct"] and res["winner"]["team"] == "Blue"
    assert room.get_board_state()["winner"]["team"] == "Blue"
    blocked = room.select_cell(idx(0, 0), question_uploader=None)
    assert not blocked["success"] and blocked["winner"]
