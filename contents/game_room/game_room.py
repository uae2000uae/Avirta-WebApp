"""
Game Room Module for Avirta

This module handles the creation and management of game rooms where players can join and participate in Avirta games.
"""

from contents.game_tools import GameTools
from contents.game_board_creator import (
    create_board as create_game_board,
    select_question as select_board_question,
    get_available_questions as get_board_available_questions,
    is_board_completed as is_board_completed,
    is_id_on_board as is_id_on_board
)

class GameRoom:
    """
    A class to represent a game room for Avirta games.

    Attributes:
        room_id (str): Unique identifier for the room
        name (str): Name of the game room
        host (str): Username of the room host
        players (list): List of players in the room
        max_players (int): Maximum number of players allowed
        current_game (object): Reference to the current game session
        is_active (bool): Whether the room is currently active
        categories (list): List of selected categories for the game
        board (dict): Game board with questions organized by category and point value
        answered_questions (set): Set of question IDs that have been answered
    """

    def __init__(self, room_id, name, host, categories=None, max_players=10, question_types=None):
        """ Initialize a new game room. """
        self.room_id = room_id
        self.name = name
        self.host = host
        self.players = [host]  # Host is automatically a player
        self.max_players = max_players
        self.current_game = None
        self.is_active = True
        self.current_player = host  # Track whose turn it is, starting with the host
        self.question_active = False  # Track whether a question is currently active

        # Initialize categories (using the provided categories list)
        self.categories = categories if categories else []

        # Store question types
        self.question_types = question_types

        # Initialize game board and answered questions
        self.board = {}
        self.answered_questions = set()

        # Initialize player tools with default values
        self.player_tools = {host: self._initialize_tools()}

    @staticmethod
    def _initialize_tools():
        """ Initializes default player tools """
        return GameTools.initialize_tools()

    def add_player(self, player_name):
        """ Add a player to the game room. """
        if len(self.players) >= self.max_players or player_name in self.players:
            return False

        self.players.append(player_name)
        self.player_tools[player_name] = self._initialize_tools()
        return True

    def remove_player(self, player_name):
        """ Remove a player from the game room. """
        if player_name not in self.players:
            return False

        self.players.remove(player_name)

        # If the host leaves, reassign or close the room
        if player_name == self.host:
            self.host = self.players[0] if self.players else None
            self.is_active = bool(self.players)  # Room stays active if players remain

        return True

    def start_game(self, game_session):
        """ Start a new game in this room. """
        if not self.is_active or len(self.players) < 2:
            return False

        self.current_game = game_session

        # Reset tools for all players
        for player in self.players:
            self.player_tools[player] = self._initialize_tools()

        return True

    def end_game(self):
        """ End the current game in this room. """
        if not self.current_game:
            return False

        self.current_game = None
        self.board.clear()
        self.answered_questions.clear()
        return True

    def create_board(self, question_uploader, questions_per_category=10):
        """
        Create a game board with an exact number of questions per category,
        prioritizing unused questions and using flexible point values if needed.
        Implements sophisticated question selection algorithm as per issue requirements.

        Returns:
            tuple: (success, enough_questions, error_details) where:
                - success (bool): True if the board was created successfully, False otherwise
                - enough_questions (bool): True if enough questions were found that match the criteria
                - error_details (dict): Detailed information about lacking categories and criteria
        """
        # Use the imported create_game_board function with question_types parameter
        self.board, self.answered_questions, enough_questions, error_details = create_game_board(
            self.categories, 
            question_uploader, 
            questions_per_category,
            question_types=self.question_types
        )

        return bool(self.board), enough_questions, error_details

    def select_question(self, category_id, points, player_name, acting_player=None, question_id=None):
        """
        Select a question from the board based on category and point value.

        Args:
            category_id (str): ID of the category
            points (int): Point value of the question
            player_name (str): Name of the player selecting the question
            acting_player (str, optional): Name of the player on whose behalf the action is being taken.
                                          If provided and player_name is the host, allows the host to act for another player.

        Returns:
            dict: The selected question or None if not available
        """
        # Check if player is in the game
        if player_name not in self.players:
            return None

        # Determine the effective player (who will be credited with the action)
        effective_player = player_name

        # If acting_player is provided and player_name is the host, use acting_player
        if acting_player and self.is_host(player_name) and acting_player in self.players:
            effective_player = acting_player

        # Check if it's the effective player's turn
        if effective_player != self.current_player:
            # Allow host override
            if not (self.is_host(player_name) and acting_player == self.current_player):
                return None

        # Use the imported select_board_question function to get the question
        question = select_board_question(self.board, self.answered_questions, category_id, points, question_id)

        # If no question is available, return None
        if not question:
            return None

        # Apply double points if active for the effective player
        if self.player_tools.get(effective_player, {}).get("double_points", {}).get("active", False):
            # Ensure points is an integer before multiplying
            if isinstance(question['points'], str):
                try:
                    question['points'] = int(question['points'])
                except ValueError:
                    question['points'] = 300

            question['points'] = question['points'] * 2
            question['doubled'] = True
            # Deactivate double points for this player after use
            self.player_tools[effective_player]["double_points"]["active"] = False

        return question

    def get_available_questions(self):
        """
        Get all questions on the board, marking answered ones.
        Questions are sorted from most difficult to least difficult within each category.

        Returns:
            dict: Dictionary of questions organized by category and point value,
                 with answered questions marked as {"points": points, "answered": True}
        """
        # Use the imported get_board_available_questions function
        return get_board_available_questions(
            self.board, 
            self.answered_questions, 
            self.current_player, 
            self.player_tools
        )

    def is_board_completed(self):
        """
        Check if all questions on the board have been answered.

        Returns:
            bool: True if all questions have been answered, False otherwise
        """
        # Use the imported is_board_completed function
        return is_board_completed(self.board, self.answered_questions)

    def use_double_points(self, player_name, acting_player=None):
        """
        Activate the "Double the Points" tool for a player.
        This tool doubles the points for the next question the player selects.
        Must be used before the question is revealed.
        Can only be used when the host is in the game room page, not in the question page.

        Args:
            player_name (str): Name of the player using the tool
            acting_player (str, optional): Name of the player on whose behalf the action is being taken.
                                           If provided and player_name is the host, allows the host to act for another player.

        Returns:
            bool: True if the tool was used successfully, False otherwise
        """
        # Validate player existence
        if player_name not in self.players:
            return False

        # Determine effective player (host can act for another player)
        effective_player = acting_player if acting_player and self.is_host(
            player_name) and acting_player in self.players else player_name

        # Use the GameTools class to handle the tool usage
        return GameTools.use_double_points(self.player_tools, effective_player, self.question_active)

    def use_change_question(self, player_name, category_id, current_points, question_uploader=None, acting_player=None):
        """
        Activate the "Change the Question" tool for a player.
        This tool allows the player to swap the current question for another one
        from the same category with the same point value.
        Must be used during the answering timer.
        Can only be used when the host is in the question page and it's the player's turn.

        Args:
            player_name (str): Name of the player using the tool
            category_id (str): ID of the category
            current_points (int): Point value of the current question
            question_uploader (QuestionUploader, optional): Instance of QuestionUploader to get questions.
                                                          If not provided, will attempt to get from Flask app context.
            acting_player (str, optional): Name of the player on whose behalf the action is being taken.
                                          If provided and player_name is the host, allows the host to act for another player.

        Returns:
            dict: The new question or None if the tool couldn't be used
        """
        # Check if player is in the game
        if player_name not in self.players:
            return None

        # Determine the effective player (who will be credited with the action)
        effective_player = player_name

        # If acting_player is provided and player_name is the host, use acting_player
        if acting_player and self.is_host(player_name) and acting_player in self.players:
            effective_player = acting_player

        # Use the GameTools class to handle the tool usage
        return GameTools.use_change_question(
            self.player_tools, 
            effective_player, 
            self.current_player, 
            self.question_active, 
            self.board, 
            self.answered_questions, 
            category_id, 
            current_points, 
            question_uploader
        )


    def has_tool_available(self, player_name, tool_name):
        """
        Check if a player has a specific tool available.

        Args:
            player_name (str): Name of the player
            tool_name (str): Name of the tool to check ("double_points" or "change_question")

        Returns:
            bool: True if the player has the tool available, False otherwise
        """
        return GameTools.has_tool_available(self.player_tools, player_name, tool_name)

    def _is_id_on_board(self, question_id):
        """
        Check if a question ID exists in any question on the board.

        Args:
            question_id (str): ID of the question to check

        Returns:
            bool: True if the ID exists on the board, False otherwise
        """
        # Use the imported is_id_on_board function
        return is_id_on_board(self.board, question_id)

    def get_player_tools(self, player_name):
        """
        Get all tools available for a player.

        Args:
            player_name (str): Name of the player

        Returns:
            dict: Dictionary of tool names and their availability status
        """
        return GameTools.get_player_tools(self.player_tools, player_name)

    def is_host(self, player_name):
        """
        Check if a player is the host of this game room.

        Args:
            player_name (str): Name of the player to check

        Returns:
            bool: True if the player is the host, False otherwise
        """
        return player_name == self.host

    def advance_turn(self):
        """
        Advance to the next player's turn.

        Returns:
            str: The name of the player whose turn it is now
        """
        if not self.players:
            return None

        # Find the current player's index
        try:
            current_index = self.players.index(self.current_player)
        except ValueError:
            # If current player is not in the list, start with the first player
            self.current_player = self.players[0]
            return self.current_player

        # Move to the next player
        next_index = (current_index + 1) % len(self.players)
        self.current_player = self.players[next_index]

        return self.current_player
