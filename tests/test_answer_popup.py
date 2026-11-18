"""Knowledge Columns: the answer result is a popup on the board, not a page."""
import re

import pytest

import app as app_module
from contents.game_room.game_room import GameRoom

ROOM = "room_popup_test"
QUESTION = {
    "id": "QTEST1", "category_id": "cars", "points": 100,
    "question": "Which company makes the Miata?", "correct_answer": "Mazda",
    "explanation": "The MX-5 Miata is built by Mazda.",
}


@pytest.fixture()
def room(client, monkeypatch):
    # Keep the test from writing event logs or use counts.
    monkeypatch.setattr(app_module, "add_game_event", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "increment_use_count", lambda *a, **k: None)
    r = GameRoom(ROOM, "Popup test", "Host")
    r.add_player("Sam")
    app_module.game_rooms[ROOM] = r
    with client.session_transaction() as s:
        s["room_id"], s["player_name"], s["current_question"] = ROOM, "Host", dict(QUESTION)
    yield r
    app_module.game_rooms.pop(ROOM, None)


def token(client):
    body = client.get("/").get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([0-9a-f]{64})"', body).group(1)


def evaluate(client, verdict):
    return client.post("/evaluate_answer", data={"evaluation": verdict},
                       headers={"X-CSRFToken": token(client)})


def test_answer_goes_back_to_the_board_and_passes_the_turn(client, room):
    assert room.current_player == "Host"
    resp = evaluate(client, "correct")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/game_room/{ROOM}")
    assert room.current_player == "Sam"


def test_popup_shows_once_without_scores(client, room):
    evaluate(client, "wrong")
    body = client.get(f"/game_room/{ROOM}").get_data(as_text=True)
    assert 'id="answer-popup"' in body
    assert "Sorry, Host." in body and "Mazda" in body and "built by Mazda" in body
    assert "leaderboard-table" not in body and "Current Scores" not in body
    # A reload doesn't show it again, and the turn doesn't move again.
    again = client.get(f"/game_room/{ROOM}").get_data(as_text=True)
    assert 'id="answer-popup"' not in again
    assert room.current_player == "Sam"


def test_old_result_address_returns_to_the_board(client, room):
    resp = client.get(f"/result/{ROOM}?is_correct=True")
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/game_room/{ROOM}")
