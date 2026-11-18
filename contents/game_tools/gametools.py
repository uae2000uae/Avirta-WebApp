"""
Game Tools Module for Avirta

This module handles the game tools functionality for Avirta games, including:
- Double Points: Doubles the points for the next question
- Change Question: Changes the current question to a new one
- Extend Time: Adds 15 seconds to the current question's timer
- Pull Question: Lets another player take over the current question

These tools can be used by players during the game to enhance their gameplay experience.
"""

class GameTools:
    """
    A class to manage game tools for Avirta games.

    This class provides methods for initializing, using, and checking the availability of game tools.
    It is designed to be used by the GameRoom class to handle game tools functionality.
    """

    @staticmethod
    def initialize_tools():
        """
        Initialize default player tools.

        Returns:
            dict: A dictionary containing the default tools and their states
        """
        return {
            "double_points": {"has": True, "available": True, "active": False},
            "change_question": {"has": True, "available": True, "active": False},
            "extend_time": {"has": True, "available": True, "active": False},
            "pull_question": {"has": True, "available": True, "active": False}
        }

    # Seconds added to the question timer by the Extend Time tool.
    EXTEND_TIME_SECONDS = 15

    @staticmethod
    def _tool(player_tools, player, tool_name):
        """Return a player's state for one tool, adding it (available) if the
        player's tools predate that tool, e.g. a room restored from disk."""
        tools = player_tools.setdefault(player, {})
        if tool_name not in tools:
            tools[tool_name] = {"has": True, "available": True, "active": False}
        return tools[tool_name]

    @staticmethod
    def use_extend_time(player_tools, effective_player, current_player, question_active):
        """
        Use the "Extend Time" tool: the player whose turn it is gets
        EXTEND_TIME_SECONDS more on the current question. Once per game.

        Returns:
            dict: {"success": True, "seconds": n} or {"success": False, ...}
        """
        tool = GameTools._tool(player_tools, effective_player, "extend_time")
        if not tool.get("available", False):
            return {"success": False, "error": "tool_not_available", "message": "Extend Time has already been used."}
        if not question_active:
            return {"success": False, "error": "question_not_active", "message": "No question is currently active."}
        if effective_player != current_player:
            return {"success": False, "error": "not_player_turn", "message": "Only the player whose turn it is can extend the time."}
        tool["available"] = False
        return {"success": True, "seconds": GameTools.EXTEND_TIME_SECONDS}

    @staticmethod
    def use_pull_question(player_tools, puller, current_player, players, question_active, already_pulled_by=None):
        """
        Use the "Pull the Question" tool: a player other than the one whose
        turn it is takes over the current question (and its points).
        Once per player per game; a question can only be pulled once.

        Returns:
            dict: {"success": True} or {"success": False, ...}
        """
        if puller not in players:
            return {"success": False, "error": "player_not_found", "message": "Player not found in this room."}
        if puller == current_player:
            return {"success": False, "error": "own_question", "message": "You can't pull your own question."}
        if not question_active:
            return {"success": False, "error": "question_not_active", "message": "No question is currently active."}
        if already_pulled_by:
            return {"success": False, "error": "already_pulled", "message": f"{already_pulled_by} already pulled this question."}
        tool = GameTools._tool(player_tools, puller, "pull_question")
        if not tool.get("available", False):
            return {"success": False, "error": "tool_not_available", "message": f"{puller} has already used Pull the Question."}
        tool["available"] = False
        return {"success": True}

    @staticmethod
    def use_double_points(player_tools, effective_player, question_active):
        """
        Activate the "Double the Points" tool for a player.
        This tool doubles the points for the next question the player selects.
        Can be used at any time, but only once per player.

        Args:
            player_tools (dict): Dictionary of player tools
            effective_player (str): Name of the player using the tool
            question_active (bool): Whether a question is currently active (not used anymore)

        Returns:
            bool: True if the tool was used successfully, False otherwise
        """
        # Retrieve player's tool info efficiently
        tool_data = player_tools.setdefault(effective_player, {}).get("double_points", {})

        # Ensure tool availability (only check if it's been used before)
        if not tool_data.get("available", False):
            return False

        # Activate the tool and mark it as used
        tool_data["active"] = True
        tool_data["available"] = False

        return True

    @staticmethod
    def use_change_question(player_tools, effective_player, current_player, question_active, board, 
                           answered_questions, category_id, current_points, question_uploader=None):
        """
        Activate the "Change the Question" tool for a player.
        This tool allows the player to swap the current question for another one
        from the same category with equal or close points value.

        According to PRJ-007:
        - Can only be used when a question is active
        - Can only be used when it's the player's turn
        - Must replace the current question with another from the same category
        - The new question must be from the same category with equal or close points value
        - Each player gets one use per game

        Args:
            player_tools (dict): Dictionary of player tools
            effective_player (str): Name of the player using the tool
            current_player (str): Name of the player whose turn it is
            question_active (bool): Whether a question is currently active
            board (dict): Game board with questions organized by category and point value
            answered_questions (set): Set of question IDs that have been answered
            category_id (str): ID of the category
            current_points (int): Point value of the current question
            question_uploader (QuestionUploader, optional): Instance of QuestionUploader to get questions.

        Returns:
            dict: The new question if successful, or a dict with error info if the tool couldn't be used
        """
        # PRJ-007: Check if effective player has the tool available
        if not player_tools.get(effective_player, {}).get("change_question", {}).get("available", False):
            return {"success": False, "error": "tool_not_available", "message": "This tool has already been used or is not available."}

        # PRJ-007: Can only be used when a question is active
        if not question_active:
            return {"success": False, "error": "question_not_active", "message": "No question is currently active."}

        # PRJ-007: Can only be used when it's the player's turn
        if effective_player != current_player:
            return {"success": False, "error": "not_player_turn", "message": "It's not your turn to use this tool."}

        # Check if category exists in board
        if category_id not in board:
            return {"success": False, "error": "category_not_found", "message": "Category not found on the game board."}

        # Check if the point value exists in the category
        if current_points not in board[category_id]:
            return {"success": False, "error": "points_not_found", "message": "Point value not found in this category."}

        # Get the list of questions for this point value
        questions_list = board[category_id][current_points]

        # Since question_active is True, we know there's a current question being asked
        # We don't need to find a specific "unanswered" question on the board
        # The current_points parameter tells us the point value of the current question
        current_points_value = current_points

        # If question_uploader is not provided, try to get it from the app context
        if not question_uploader:
            try:
                from flask import current_app
                question_uploader = current_app.config.get('question_uploader')
            except (ImportError, RuntimeError):
                # Flask app context not available or Flask not installed
                pass

        if not question_uploader:
            # No question_uploader available
            return {"success": False, "error": "no_question_uploader", "message": "Question database is not available."}

        # Get all questions for this category
        category_questions = question_uploader.get_questions_by_category(category_id)

        # Skip if no questions available
        if not category_questions:
            return {"success": False, "error": "no_category_questions", "message": "No questions available in this category."}

        # Get all question IDs currently on the board
        board_question_ids = set()
        for cat_id, points_dict in board.items():
            for points, questions_list in points_dict.items():
                for question in questions_list:
                    board_question_ids.add(question.get('id', ''))

        # Filter out questions that are already on the board or have been answered
        available_questions = [q for q in category_questions
                               if q.get('id') not in board_question_ids
                               and q.get('id') not in answered_questions]

        if not available_questions:
            # If no available questions, return error
            return {"success": False, "error": "no_available_questions", "message": "No alternative questions available for this category."}

        # Ensure current_points_value is an integer
        if isinstance(current_points_value, str):
            try:
                current_points_value = int(current_points_value)
            except ValueError:
                current_points_value = current_points

        # PRJ-007: Find questions with equal or close points value
        # First try to find questions with exactly matching points
        matching_questions = [q for q in available_questions 
                             if q.get('points') == current_points_value]

        # If no exact matches, look for questions with close points (within 100 points)
        if not matching_questions:
            point_range = 100
            matching_questions = [q for q in available_questions 
                                 if abs(int(q.get('points', 0)) - current_points_value) <= point_range]

        # If still no matches, return error
        if not matching_questions:
            return {"success": False, "error": "no_matching_questions", "message": "No questions with similar point values are available."}

        # Sort by usage count (least used first) to prioritize fresh questions
        matching_questions.sort(key=lambda q: q.get("use_count", 0))

        # Select the least used question
        new_question = matching_questions[0]

        # Create a copy of the new question and set its point value to match the current question
        new_question_copy = new_question.copy()
        new_question_copy["points"] = current_points_value

        # Mark the tool as used (disable it)
        player_tools[effective_player]["change_question"]["available"] = False

        # Return the new question - the calling code will handle updating the game state
        return new_question_copy

    @staticmethod
    def has_tool_available(player_tools, player_name, tool_name):
        """
        Check if a player has a specific tool available.

        Args:
            player_tools (dict): Dictionary of player tools
            player_name (str): Name of the player
            tool_name (str): Name of the tool to check ("double_points" or "change_question")

        Returns:
            bool: True if the player has the tool available, False otherwise
        """
        return player_tools.get(player_name, {}).get(tool_name, {}).get("available", False)

    @staticmethod
    def get_player_tools(player_tools, player_name):
        """
        Get all tools available for a player.

        Args:
            player_tools (dict): Dictionary of player tools
            player_name (str): Name of the player

        Returns:
            dict: Dictionary of tool names and their availability status
        """
        tools = player_tools.get(player_name, {})
        # Return a simplified version for backward compatibility.
        # Tools the player's state predates count as unused.
        simplified_tools = {name: True for name in GameTools.initialize_tools()} if player_name in player_tools else {}
        for tool_name, status in tools.items():
            simplified_tools[tool_name] = status.get("available", False)
        return simplified_tools
