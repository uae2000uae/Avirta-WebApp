"""Live rooms are saved to a store and come back after a restart."""
import time

import pytest

from contents.game_room import room_store
from contents.game_room.game_room import GameRoom
from contents.game_room.room_store import PersistentRooms
from contents.thehive.hex_game_room import HexGameRoom
from questionmanagement.question_manager import QuestionManager


class FakeStore:
    def __init__(self):
        self.docs, self.puts = {}, 0

    def get(self, room_id):
        return self.docs.get(room_id)

    def put(self, room_id, data, kind):
        self.puts += 1
        self.docs[room_id] = {"data": data, "kind": kind, "updated_at": time.time()}

    def delete(self, room_id):
        self.docs.pop(room_id, None)


def restart(rooms):
    """What a new revision sees: same store, empty memory."""
    return PersistentRooms(rooms.backend)


def columns_room():
    room = GameRoom("room_1", "Friday quiz", "Sara", ["science"], question_types=["text"])
    room.add_player("Omar")
    room.board = {"science": {100: [{"id": "Q1", "points": 100}], 300: [{"id": "Q3", "points": 300}]}}
    room.answered_questions = {"Q1"}
    room.question_manager = QuestionManager()
    room.question_manager.scores = {"Sara": 100}
    return room


def test_plain_dict_without_a_store():
    rooms = PersistentRooms(None)
    rooms["a"] = 1
    assert "a" in rooms and rooms["a"] == 1 and "b" not in rooms
    del rooms["a"]
    assert "a" not in rooms


def test_columns_room_survives_a_restart_with_all_its_state():
    rooms = PersistentRooms(FakeStore())
    rooms["room_1"] = columns_room()

    again = restart(rooms)
    assert "room_1" in again
    room = again["room_1"]
    assert type(room) is GameRoom
    assert room.players == ["Sara", "Omar"]
    assert room.answered_questions == {"Q1"}
    assert list(room.board["science"].keys()) == [100, 300]  # integer score keys kept
    assert isinstance(room.question_manager, QuestionManager)
    assert room.question_manager.scores == {"Sara": 100}


def test_changes_made_during_a_request_are_saved_once():
    store = FakeStore()
    rooms = PersistentRooms(store)
    rooms["room_1"] = columns_room()
    assert store.puts == 1

    rooms.begin_request()
    rooms["room_1"].question_manager.scores["Omar"] = 300
    rooms.end_request()
    assert store.puts == 2
    assert restart(rooms)["room_1"].question_manager.scores == {"Sara": 100, "Omar": 300}

    rooms.begin_request()
    _ = rooms["room_1"].players  # read only: nothing to write
    rooms.end_request()
    assert store.puts == 2


def test_hive_room_keeps_its_class():
    rooms = PersistentRooms(FakeStore())
    hive = HexGameRoom("hex_1", "Blue vs Red", "Blue", "Red")
    hive.grid = [{"id": i, "points": 100, "state": "neutral", "question": None, "asked": False} for i in range(25)]
    hive.grid[3]["state"] = "Blue"
    rooms["hex_1"] = hive
    back = restart(rooms)["hex_1"]
    assert type(back) is HexGameRoom and back.grid[3]["state"] == "Blue"
    assert back.find_winner() is None


def test_ended_and_stale_rooms_are_gone():
    store = FakeStore()
    rooms = PersistentRooms(store)
    rooms["room_1"] = columns_room()
    del rooms["room_1"]
    assert "room_1" not in restart(rooms) and store.docs == {}

    rooms["room_2"] = columns_room()
    store.docs["room_2"]["updated_at"] -= room_store.MAX_AGE_SECONDS + 1
    assert "room_2" not in restart(rooms)


def test_store_failures_never_break_a_game():
    class Broken(FakeStore):
        def put(self, *a):
            raise RuntimeError("store down")

        def get(self, *a):
            raise RuntimeError("store down")

    rooms = PersistentRooms(Broken())
    rooms["room_1"] = columns_room()
    assert rooms["room_1"].players == ["Sara", "Omar"]
    assert "other" not in rooms


def test_unknown_classes_are_neither_written_nor_rebuilt():
    with pytest.raises(TypeError):
        room_store.encode(object())
    with pytest.raises(TypeError):
        room_store.decode({"__obj__": "os:system", "state": {}})


def test_game_continues_after_a_restart_through_the_app(app, client, monkeypatch):
    import app as app_module

    rooms = PersistentRooms(FakeStore())
    monkeypatch.setattr(app_module, "game_rooms", rooms)
    rooms["room_9"] = columns_room()
    rooms["room_9"].room_id = "room_9"
    with client.session_transaction() as s:
        s["player_name"], s["room_id"] = "Sara", "room_9"

    dict.clear(rooms)  # the instance restarts: memory is empty, the store is not
    rooms._digests.clear()
    resp = client.get("/game_room/room_9")
    assert resp.status_code == 200, resp.headers.get("Location")
    assert dict.__contains__(rooms, "room_9")
