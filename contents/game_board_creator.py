"""
Game Board Creator Module for Avirta

This module handles the creation and management of game boards for Avirta games.
It provides functions for creating game boards, selecting questions, and managing
answered questions.

This implementation follows PRJ-012 from the Avirta Rule Book, which requires
centralized game board creation with support for configurable number of questions
per category and multiple questions with the same point value.
"""

import random


def least_used_first(questions):
    """Least-used questions first. Among questions with the same count, ones
    played most recently go last and the rest come in random order, so boards
    do not repeat the same questions game after game."""
    try:
        from questionmanagement.usage_ledger import recently_played
        recent = recently_played()
    except Exception:
        recent = {}
    shuffled = list(questions)
    random.shuffle(shuffled)
    return sorted(shuffled, key=lambda q: (int(q.get("use_count", 0) or 0), recent.get(q.get("id"), -1)))


def create_board(categories, question_uploader, questions_per_category=10, point_values=None, question_types=None):
    """
    Create a game board with questions for each category.
    Implements sophisticated question selection algorithm as per issue requirements.

    Args:
        categories (list): List of category IDs to include in the board
        question_uploader (QuestionUploader): Instance of QuestionUploader to get questions
        questions_per_category (int, optional): Number of questions per category. Defaults to 10.
        point_values (list, optional): List of point values to use for questions (for speed mode).
                                      If None, uses default values. Defaults to None.
        question_types (list, optional): List of question types to include (e.g., ["multiple_choice", "true_false"]).
                                        If None, includes all question types. Defaults to None.

    Returns:
        tuple: (board, answered_questions, enough_questions, error_details) where:
            - board (dict): Game board with questions organized by category and point value
            - answered_questions (set): Empty set to track answered questions
            - enough_questions (bool): True if enough questions were found that match the criteria
            - error_details (dict): Detailed information about lacking categories and criteria
    """
    # Return empty board and answered_questions if no categories provided
    if not categories:
        return {}, set(), False, {'lacking_categories': categories, 'message': 'No categories provided'}

    # Initialize board, answered_questions, and comprehensive error tracking
    board = {}
    answered_questions = set()
    enough_questions = True
    comprehensive_error_details = {
        'lacking_categories': [],
        'category_details': {},
        'total_categories': len(categories),
        'successful_categories': 0,
        'failed_categories': 0,
        'overall_message': ''
    }

    # Process each category
    for category_id in categories:
        # Get all questions for this category
        all_questions = question_uploader.get_questions_by_category(category_id)

        # Handle categories with no questions
        if not all_questions:
            comprehensive_error_details['lacking_categories'].append(category_id)
            comprehensive_error_details['category_details'][category_id] = {
                'error': 'No questions available in this category',
                'total_available': 0,
                'total_needed': questions_per_category,
                'selected_count': 0
            }
            comprehensive_error_details['failed_categories'] += 1
            enough_questions = False
            continue

        # Choose the appropriate builder function based on whether point_values is provided
        # If point_values is provided, use build_custom_points_board
        # Otherwise, use build_standard_board (for standard mode)
        if point_values:
            category_board, category_enough_questions = build_custom_points_board(all_questions, point_values, questions_per_category, question_types)
            category_error_details = None  # Custom points board doesn't return error details yet
        else:
            category_board, category_enough_questions, category_error_details = build_standard_board(all_questions, None, questions_per_category, question_types)

        # Add category to board
        board[category_id] = category_board

        # Track category-specific results
        if category_enough_questions:
            comprehensive_error_details['successful_categories'] += 1
            comprehensive_error_details['category_details'][category_id] = {
                'status': 'success',
                'selected_count': questions_per_category,
                'total_available': len(all_questions)
            }
        else:
            comprehensive_error_details['failed_categories'] += 1
            comprehensive_error_details['lacking_categories'].append(category_id)

            # Add detailed error information for standard board
            if category_error_details:
                comprehensive_error_details['category_details'][category_id] = category_error_details
                comprehensive_error_details['category_details'][category_id]['status'] = 'insufficient'
            else:
                comprehensive_error_details['category_details'][category_id] = {
                    'status': 'insufficient',
                    'error': 'Not enough questions matching the selected criteria',
                    'total_available': len(all_questions),
                    'total_needed': questions_per_category
                }

            enough_questions = False

    # Generate overall message
    if comprehensive_error_details['failed_categories'] > 0:
        lacking_categories_names = comprehensive_error_details['lacking_categories']
        if len(lacking_categories_names) == 1:
            comprehensive_error_details['overall_message'] = f"The following category lacks sufficient questions of the selected criteria:\n• {lacking_categories_names[0]}\nPlease try to add more questions or select different categories and question types."
        else:
            categories_bullet_list = "\n".join([f"• {category}" for category in lacking_categories_names])
            comprehensive_error_details['overall_message'] = f"The following categories lack sufficient questions of the selected criteria:\n{categories_bullet_list}\nPlease try to add more questions or select different categories and question types."
    else:
        comprehensive_error_details['overall_message'] = "All categories have sufficient questions."

    return board, answered_questions, enough_questions, comprehensive_error_details

def build_custom_points_board(all_questions, selected_point_values, questions_per_category, question_types=None):
    """
    Build a game board with questions organized by custom point values.
    Only includes questions that match the selected point values and question types.

    Args:
        all_questions (list): List of all questions for a category
        selected_point_values (list): List of point values to use for questions
        questions_per_category (int): Number of questions per category
        question_types (list, optional): List of question types to include (e.g., ["multiple_choice", "true_false"]).
                                        If None, includes all question types. Defaults to None.

    Returns:
        tuple: (board_category, enough_questions) where:
            - board_category (dict): Dictionary of questions organized by point value
            - enough_questions (bool): True if enough questions were found that match the criteria,
                                      False otherwise
    """
    # Initialize variables
    used_ids = set()
    selected_questions = []

    # Sort questions by use_count to prioritize less-used questions
    sorted_questions = least_used_first(all_questions)

    # Select questions that match the selected point values and question types
    for question in sorted_questions:
        # Break if we have enough questions
        if len(selected_questions) >= questions_per_category:
            break

        # Get question ID, points, and type
        question_id = question.get("id")
        points = question.get("points")
        question_type = question.get("type")

        # Skip if already used or points is not an integer
        if question_id in used_ids or not isinstance(points, int):
            continue

        # Skip if question type doesn't match any of the selected types
        if question_types and question_type not in question_types:
            continue

        # If points match one of the selected point values, add the question
        if points in selected_point_values:
            used_ids.add(question_id)
            selected_questions.append((points, question.copy()))

    # Check if we have enough questions
    enough_questions = len(selected_questions) >= questions_per_category

    # Organize questions by point value
    board_category = organize_board(selected_questions)

    return board_category, enough_questions

def build_standard_board(all_questions, point_values, questions_per_category, question_types=None):
    """
    Build a standard game board with questions organized by point value.
    Implements sophisticated question selection algorithm as per issue requirements:
    1. First 5 questions collected fill all point values (500, 400, 300, 200, 100)
    2. Additional passes from least point value (100) to most (500) if more questions needed
    3. Sort filtered list by least used questions to most used
    4. Implement fallback passes for insufficient questions
    5. Provide detailed error messages about lacking categories

    Args:
        all_questions (list): List of all questions for a category
        point_values (list): List of point values to use for questions (ignored in standard mode)
        questions_per_category (int): Number of questions per category
        question_types (list, optional): List of question types to include (e.g., ["multiple_choice", "true_false"]).
                                        If None, includes all question types. Defaults to None.

    Returns:
        tuple: (board_category, enough_questions, error_details) where:
            - board_category (dict): Dictionary of questions organized by point value
            - enough_questions (bool): True if enough questions were found that match the criteria
            - error_details (dict): Details about what categories/criteria are lacking questions
    """
    # Initialize variables
    used_ids = set()
    selected_questions = []
    error_details = {
        'lacking_categories': [],
        'insufficient_types': [],
        'insufficient_points': [],
        'total_available': len(all_questions),
        'total_needed': questions_per_category
    }

    # Standard point values for regular game
    standard_point_values = [500, 400, 300, 200, 100]

    # Step 1: Filter questions by selected question types
    filtered_questions = []
    for question in all_questions:
        question_type = question.get("type")
        # Skip if question type doesn't match any of the selected types
        if question_types and question_type not in question_types:
            continue
        # Skip if points is not an integer
        points = question.get("points")
        if not isinstance(points, int):
            continue
        filtered_questions.append(question)

    # Step 2: Sort filtered list by least used questions to most used
    sorted_questions = least_used_first(filtered_questions)

    # Step 3: First pass - collect first 5 questions to fill all point values
    # One question per point value: 100, 200, 300, 400, 500 (from lowest to highest)
    first_pass_order = [100, 200, 300, 400, 500]
    for point_value in first_pass_order:
        if len(selected_questions) >= questions_per_category:
            break

        # Find the least used question that matches this point value exactly
        for question in sorted_questions:
            question_id = question.get("id")
            question_points = question.get("points")

            if (question_id not in used_ids and question_points == point_value):
                used_ids.add(question_id)
                selected_questions.append((point_value, question.copy()))
                break

    # Step 4: Additional passes if more than 5 questions are needed
    # Go from least point value (100) to most (500) repeatedly
    if len(selected_questions) < questions_per_category:
        remaining_needed = questions_per_category - len(selected_questions)

        # Reverse the point values to go from least (100) to most (500)
        additional_pass_order = [100, 200, 300, 400, 500]

        # Keep making passes until we have enough questions or no more questions available
        while remaining_needed > 0:
            questions_added_this_pass = 0

            # Go through each point value from least to most
            for point_value in additional_pass_order:
                if remaining_needed <= 0:
                    break

                # Find the next least used question that matches this point value exactly
                for question in sorted_questions:
                    question_id = question.get("id")
                    question_points = question.get("points")

                    if (question_id not in used_ids and question_points == point_value):
                        used_ids.add(question_id)
                        selected_questions.append((point_value, question.copy()))
                        remaining_needed -= 1
                        questions_added_this_pass += 1
                        break

            # If no questions were added in this pass, break to avoid infinite loop
            if questions_added_this_pass == 0:
                break

    # Step 5: Fallback passes for insufficient questions (if still not enough)
    if len(selected_questions) < questions_per_category:
        remaining_needed = questions_per_category - len(selected_questions)

        # Fallback Pass 1: Find questions of other point values and map to closest standard value
        for question in sorted_questions:
            if remaining_needed <= 0:
                break

            question_id = question.get("id")
            question_points = question.get("points")

            if question_id not in used_ids:
                # Use the closest standard point value
                closest_point_value = min(standard_point_values, 
                                        key=lambda x: abs(x - question_points))
                used_ids.add(question_id)
                selected_questions.append((closest_point_value, question.copy()))
                remaining_needed -= 1

    # Step 6: Check if we have enough questions and prepare error details
    enough_questions = len(selected_questions) >= questions_per_category

    if not enough_questions:
        # Analyze what's lacking
        available_by_type = {}
        available_by_points = {}

        for question in filtered_questions:
            q_type = question.get("type", "unknown")
            q_points = question.get("points", 0)

            if q_type not in available_by_type:
                available_by_type[q_type] = 0
            available_by_type[q_type] += 1

            if q_points not in available_by_points:
                available_by_points[q_points] = 0
            available_by_points[q_points] += 1

        error_details.update({
            'available_by_type': available_by_type,
            'available_by_points': available_by_points,
            'selected_count': len(selected_questions),
            'missing_count': questions_per_category - len(selected_questions)
        })

    # Organize questions by point value
    board_category = organize_board(selected_questions)

    return board_category, enough_questions, error_details

def organize_board(selected_questions):
    """
    Organize selected questions by point value.

    Args:
        selected_questions (list): List of (point_value, question) tuples

    Returns:
        dict: Dictionary of questions organized by point value
    """
    board_category = {}

    # Group questions by point value
    for point_value, question in selected_questions:
        # Set the point value in the question
        question["points"] = point_value

        # Add the question to the appropriate list in the board
        if point_value not in board_category:
            board_category[point_value] = []

        board_category[point_value].append(question)

    return board_category

def select_question(board, answered_questions, category_id, points, question_id=None):
    """
    Select a question from the board based on category and point value.

    Args:
        board (dict): Game board with questions organized by category and point value
        answered_questions (set): Set of question IDs that have been answered
        category_id (str): ID of the category
        points (int): Point value of the question

    Returns:
        dict: The selected question or None if not available
    """
    # Check if category exists in board
    if category_id not in board:
        return None

    # Check if point value exists for category
    if points not in board[category_id]:
        return None

    # Get the list of questions for this point value
    questions_list = board[category_id][points]

    # A specific question was clicked (several questions can share a score).
    if question_id:
        for question in questions_list:
            if str(question['id']) == str(question_id):
                if question['id'] in answered_questions:
                    return None
                answered_questions.add(question['id'])
                return question.copy()

    # Otherwise take the first unanswered question at this score
    for question in questions_list:
        if question['id'] not in answered_questions:
            # Mark question as answered
            answered_questions.add(question['id'])
            return question.copy()

    # If all questions have been answered, return None
    return None

def get_available_questions(board, answered_questions, current_player=None, player_tools=None, use_custom_points=False):
    """
    Get all questions on the board, marking answered ones.
    Questions are sorted from most difficult to least difficult within each category.

    Args:
        board (dict): Game board with questions organized by category and point value
        answered_questions (set): Set of question IDs that have been answered
        current_player (str, optional): Name of the current player. Defaults to None.
        player_tools (dict, optional): Dictionary of player tools. Defaults to None.
        use_custom_points (bool, optional): Whether to use custom point values. Defaults to False.

    Returns:
        dict: {category_id: {points: [question_info, ...]}}. Each score keeps a
             list because several questions can share the same score; each
             question_info is {"id", "points", "answered", "doubled"}.
    """
    available = {}

    # Process each category in the board
    for category_id, points_dict in board.items():
        available[category_id] = {}

        # Create a list of all questions with their point values
        all_questions = []
        for points, questions_list in points_dict.items():
            for question in questions_list:
                # Use the actual points value from the question
                actual_points = question.get('points', points)

                # Ensure actual_points is an integer
                if isinstance(actual_points, str):
                    try:
                        actual_points = int(actual_points)
                    except ValueError:
                        actual_points = points

                # Check if double points is active for the current player
                doubled = False
                if (current_player and player_tools and 
                    player_tools.get(current_player, {}).get("double_points", {}).get("active", False) and 
                    question['id'] not in answered_questions):
                    actual_points = actual_points * 2
                    doubled = True

                # Create an info object for this question
                question_info = {
                    "id": question['id'],
                    "points": actual_points,
                    "answered": question['id'] in answered_questions,
                    "doubled": doubled
                }

                all_questions.append((points, question_info))

        # Sort by actual points in descending order (most difficult to least difficult)
        all_questions.sort(key=lambda item: item[1]["points"], reverse=True)

        # Add questions to the available dictionary (all questions per score)
        for points, question_info in all_questions:
            available[category_id].setdefault(points, []).append(question_info)

    return available

def is_board_completed(board, answered_questions):
    """
    Check if all questions on the board have been answered.

    Args:
        board (dict): Game board with questions organized by category and point value
        answered_questions (set): Set of question IDs that have been answered

    Returns:
        bool: True if all questions have been answered, False otherwise
    """
    # Check each category
    for category_id, points_dict in board.items():
        # Check each point value
        for points, questions_list in points_dict.items():
            # Check each question
            for question in questions_list:
                # If any question is unanswered, the board is not completed
                if question['id'] not in answered_questions:
                    return False

    # If all questions have been answered, the board is completed
    return True

def is_id_on_board(board, question_id):
    """
    Check if a question ID exists in any question on the board.

    Args:
        board (dict): Game board with questions organized by category and point value
        question_id (str): ID of the question to check

    Returns:
        bool: True if the ID exists on the board, False otherwise
    """
    # Check each category
    for category_id, points_dict in board.items():
        # Check each point value
        for points, questions_list in points_dict.items():
            # Check each question
            for question in questions_list:
                # If the question ID matches, return True
                if question.get('id') == question_id:
                    return True

    # If the question ID was not found, return False
    return False
