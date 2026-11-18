"""Knowledge Columns player tools: Extend Time and Pull the Question."""

from contents.game_room.game_room import GameRoom


def make_room():
    room = GameRoom("r1", "Room", "Host")
    room.add_player("P2")
    room.add_player("P3")
    room.current_player = "P2"
    room.question_active = True
    return room


def test_new_players_start_with_both_tools():
    tools = make_room().get_player_tools("P3")
    assert tools["extend_time"] is True
    assert tools["pull_question"] is True


def test_extend_time_once_for_current_player():
    room = make_room()
    first = room.use_extend_time("P2")
    assert first == {"success": True, "seconds": 15}
    assert room.use_extend_time("P2")["success"] is False
    assert room.get_player_tools("P2")["extend_time"] is False


def test_extend_time_host_acts_for_current_player():
    room = make_room()
    assert room.use_extend_time("Host", acting_player="P2")["success"] is True
    assert room.get_player_tools("P2")["extend_time"] is False
    assert room.get_player_tools("Host")["extend_time"] is True


def test_extend_time_refused_when_not_your_turn_or_no_question():
    room = make_room()
    assert room.use_extend_time("P3")["success"] is False
    room.question_active = False
    assert room.use_extend_time("P2")["success"] is False
    assert room.get_player_tools("P2")["extend_time"] is True


def test_pull_question_once_per_player():
    room = make_room()
    assert room.use_pull_question("Host", "P3")["success"] is True
    assert room.get_player_tools("P3")["pull_question"] is False
    # Same player can't pull again later in the game.
    assert room.use_pull_question("Host", "P3")["success"] is False
    # Another player still can.
    assert room.use_pull_question("Host", "Host")["success"] is True


def test_pull_question_rules():
    room = make_room()
    # Can't pull your own question.
    assert room.use_pull_question("Host", "P2")["success"] is False
    # A question can only be pulled once.
    assert room.use_pull_question("Host", "P3", already_pulled_by="Host")["success"] is False
    # Only the host or the current player's screen may pull.
    assert room.use_pull_question("P3", "Host")["success"] is False
    assert room.use_pull_question("P2", "P3")["success"] is True
    # Unknown player.
    assert room.use_pull_question("Host", "Nobody")["success"] is False


def test_tools_missing_from_restored_room_count_as_unused():
    room = make_room()
    # Rooms saved before these tools existed only have the original two.
    room.player_tools["P2"] = {
        "double_points": {"has": True, "available": True, "active": False},
        "change_question": {"has": True, "available": False, "active": False},
    }
    tools = room.get_player_tools("P2")
    assert tools["extend_time"] is True and tools["change_question"] is False
    assert room.use_extend_time("P2")["success"] is True
    assert room.get_player_tools("P2")["extend_time"] is False
