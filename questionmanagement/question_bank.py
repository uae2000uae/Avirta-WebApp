"""
Question Bank Module for Question Management

This module provides a standalone function for managing questions,
including categorization by topic, points assignment, and
prevention of repeated questions.
"""

import random
import os
import json
from datetime import datetime

class QuestionBank:
    """
    A class to manage a bank of questions for games.

    This class stores questions categorized by topic, assigns points,
    and prevents repeated questions from appearing unless no more questions exist
    in the category.

    Attributes:
        questions (dict): Dictionary of all questions indexed by ID
        categories (dict): Dictionary of categories, each containing a list of question IDs
        used_questions (dict): Dictionary tracking which questions have been used, by category
        storage_path (str): Path to store question data
    """

    # Class variable to store the singleton instance
    _instance = None

    def __init__(self, storage_path=None):
        """
        Initialize a new question bank.

        Args:
            storage_path (str, optional): Path to store question data. If None, defaults to "contents/questions".
        """
        self.questions = {}
        self.categories = {}
        self.used_questions = {}

        # Set default path if none provided
        if storage_path is None:
            storage_path = os.path.join("contents", "questions")

        # Convert to absolute path if it's a relative path
        if not os.path.isabs(storage_path):
            # Get the absolute path relative to the current script location
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.storage_path = os.path.join(base_dir, storage_path)
        else:
            self.storage_path = storage_path

        # Create storage directory if it doesn't exist
        os.makedirs(self.storage_path, exist_ok=True)

        # Load existing questions if any
        self.load_questions()

        # Update the singleton instance if this is a new instance with a custom path
        # or if no instance exists yet
        if QuestionBank._instance is None:
            QuestionBank._instance = self

    def add_question(self, question_data, category_id="general", points=300):
        """
        Add a new question to the bank.

        Args:
            question_data (dict): Question data
            category_id (str, optional): Category ID. Defaults to "general".
            points (int, optional): Points value for the question. Defaults to 30.

        Returns:
            tuple: (success, message or question_id)
        """
        # Generate a unique ID for the question
        question_id = self._generate_question_id()

        # Add metadata
        question_data["id"] = question_id
        question_data["category_id"] = category_id
        question_data["points"] = points
        question_data["created_at"] = datetime.now().isoformat()
        question_data["updated_at"] = question_data["created_at"]
        question_data["active"] = True
        question_data["use_count"] = 0

        # Store the question
        self.questions[question_id] = question_data

        # Add to category
        if category_id not in self.categories:
            self.categories[category_id] = []
        self.categories[category_id].append(question_id)

        # Initialize used_questions tracking for this category if not exists
        if category_id not in self.used_questions:
            self.used_questions[category_id] = set()

        # Save to file
        self._save_question(question_id, question_data)

        return True, question_id

    def get_question(self, category_id, points=None, prevent_repeats=True):
        """
        Get a question from the specified category and points value.

        This function prevents repeated questions from appearing unless no more
        questions exist in the category.

        Args:
            category_id (str): Category ID
            points (int, optional): Points value. If None, any points value is selected.
            prevent_repeats (bool, optional): Whether to prevent repeated questions. Defaults to True.

        Returns:
            dict: Question data or None if no questions available
        """
        # Check if category exists
        if category_id not in self.categories:
            return None

        # Get all question IDs for this category
        question_ids = self.categories[category_id]

        # Filter by points if specified
        if points:
            question_ids = [q_id for q_id in question_ids if self.questions[q_id].get("points") == points]

        # If no questions available, return None
        if not question_ids:
            return None

        # If prevent_repeats is True, filter out used questions
        available_ids = []
        if prevent_repeats:
            # Get unused question IDs
            available_ids = [q_id for q_id in question_ids if q_id not in self.used_questions[category_id]]

            # If all questions have been used, reset the used_questions for this category
            if not available_ids:
                self.used_questions[category_id].clear()
                available_ids = question_ids
        else:
            available_ids = question_ids

        # Select a random question
        question_id = random.choice(available_ids)

        # Mark as used
        self.used_questions[category_id].add(question_id)

        return self.questions[question_id]

    def get_questions_by_category(self, category_id, points=None, limit=None):
        """
        Get all questions in a category, optionally filtered by points.

        Args:
            category_id (str): Category ID
            points (int, optional): Points value. If None, any points value is returned.
            limit (int, optional): Maximum number of questions to return. If None, all questions are returned.

        Returns:
            list: List of question data dictionaries
        """
        # Check if category exists
        if category_id not in self.categories:
            return []

        # Get all question IDs for this category
        question_ids = self.categories[category_id]

        # Filter by points if specified
        if points:
            question_ids = [q_id for q_id in question_ids if self.questions[q_id].get("points") == points]

        # Limit the number of questions if specified
        if limit and limit < len(question_ids):
            question_ids = random.sample(question_ids, limit)

        # Return the questions
        return [self.questions[q_id] for q_id in question_ids]

    def reset_used_questions(self, category_id=None):
        """
        Reset the used_questions tracking for a category or all categories.

        Args:
            category_id (str, optional): Category ID. If None, all categories are reset.

        Returns:
            bool: True if reset was successful, False otherwise
        """
        if category_id:
            if category_id not in self.used_questions:
                return False
            self.used_questions[category_id].clear()
        else:
            for cat_id in self.used_questions:
                self.used_questions[cat_id].clear()

        return True

    def load_questions(self):
        """
        Load all questions from storage.

        Returns:
            int: Number of questions loaded
        """
        count = 0
        # Clear existing questions and categories to prevent duplicates
        self.questions = {}
        self.categories = {}

        if os.path.exists(self.storage_path):
            for filename in os.listdir(self.storage_path):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.storage_path, filename)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            # Each file now contains an array of questions for a category
                            category_questions = json.load(f)

                            # The category ID is the filename without the .json extension
                            category_id = os.path.splitext(filename)[0]

                            # Initialize category if not exists
                            if category_id not in self.categories:
                                self.categories[category_id] = []

                            # Initialize used_questions tracking for this category if not exists
                            if category_id not in self.used_questions:
                                self.used_questions[category_id] = set()

                            # Process each question in the category file
                            for question_data in category_questions:
                                question_id = question_data.get("id")

                                # Handle questions with difficulty field (as per PRJ-002 rule)
                                if "difficulty" in question_data:
                                    # If points are not set, convert difficulty to points
                                    if "points" not in question_data:
                                        difficulty = question_data.get("difficulty", "medium")
                                        # Convert string difficulty to numeric points
                                        if isinstance(difficulty, str):
                                            difficulty_map = {
                                                "easiest": 100, 
                                                "easy": 200, 
                                                "medium": 300, 
                                                "hard": 400, 
                                                "hardest": 500
                                            }
                                            # For backward compatibility
                                            legacy_map = {"easy": 100, "medium": 300, "hard": 500}

                                            # Try the new map first, then fall back to legacy map
                                            points = difficulty_map.get(
                                                difficulty.lower(), 
                                                legacy_map.get(difficulty.lower(), 300)
                                            )
                                            question_data["points"] = points

                                    # Always remove difficulty field as per PRJ-002 rule
                                    del question_data["difficulty"]

                                if question_id:
                                    # Ensure category_id is set correctly in the question data
                                    question_data["category_id"] = category_id

                                    # Store the question
                                    self.questions[question_id] = question_data

                                    # Add to category
                                    self.categories[category_id].append(question_id)

                                    count += 1
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"Error loading questions from {filename}: {e}")

        # Apply usage-ledger totals on top of the base counts stored in the
        # question files (effective use_count = file base + sum of all
        # per-instance ledgers). The files themselves are left untouched.
        try:
            from questionmanagement.usage_ledger import get_totals
            _totals = get_totals()
            self._ledger_extra = {}
            if _totals:
                for _qid, _q in self.questions.items():
                    _add = _totals.get(_qid)
                    if _add:
                        _q["use_count"] = int(_q.get("use_count", 0) or 0) + int(_add)
                        self._ledger_extra[_qid] = int(_add)
        except Exception as _e:
            print(f"usage ledger overlay skipped: {_e}")

        return count

    def _generate_question_id(self):
        """
        Generate a unique question ID in the format Q####### (Q followed by 7 digits).
        Continues the serial system by finding the highest existing ID and incrementing it.

        Returns:
            str: Unique question ID
        """
        # Find the highest existing ID
        highest_num = 0
        for question_id in self.questions.keys():
            # Check if the ID follows the Q####### format
            if question_id.startswith('Q') and len(question_id) == 8 and question_id[1:].isdigit():
                num = int(question_id[1:])
                if num > highest_num:
                    highest_num = num

        # Increment the highest ID
        new_num = highest_num + 1

        # Format the new ID as Q#######
        return f"Q{new_num:07d}"

    def _save_question(self, question_id, question_data):
        """
        Save a question to storage.

        Args:
            question_id (str): ID of the question
            question_data (dict): Question data
        """
        category_id = question_data.get("category_id", "general")
        file_path = os.path.join(self.storage_path, f"{category_id}.json")
        # Keep only the base count in the file; ledger plays are added on load.
        from questionmanagement.categories_questions.question_uploader import _without_ledger_uses
        question_data = _without_ledger_uses(question_data, getattr(self, "_ledger_extra", {}).get(question_id, 0))

        try:
            # Load existing category file if it exists
            category_questions = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        category_questions = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Error loading category file {file_path}: {e}")
                    # If there's an error, start with an empty list
                    category_questions = []

            # Find and update the question if it exists, or add it if it doesn't
            question_found = False
            for i, question in enumerate(category_questions):
                if question.get("id") == question_id:
                    category_questions[i] = question_data
                    question_found = True
                    break

            if not question_found:
                category_questions.append(question_data)

            # Save the updated category file
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(category_questions, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving question {question_id}: {e}")

    def increment_use_count(self, question_id):
        """
        Increment the use_count of a question and save it back to storage.

        Args:
            question_id (str): ID of the question

        Returns:
            bool: True if successful, False otherwise
        """
        if question_id not in self.questions:
            return False

        question = self.questions[question_id]

        # Record the use in THIS instance's usage ledger instead of rewriting the
        # question file. Keeps use_count mergeable across sessions (each instance
        # owns its own ledger) and stops the category files from churning on every
        # play. Effective use_count = file base + sum of ledgers (applied on load).
        try:
            from questionmanagement.usage_ledger import increment as _ledger_increment
            _ledger_increment(question_id, 1)
            # Reflect the increment in the in-memory effective count for live
            # question selection (NOT written back to the question file).
            question["use_count"] = int(question.get("use_count", 0) or 0) + 1
            extra = getattr(self, "_ledger_extra", None)
            if extra is None:
                extra = self._ledger_extra = {}
            extra[question_id] = extra.get(question_id, 0) + 1
            return True
        except Exception as e:
            # Fallback to the legacy inline behavior so a use is never lost.
            print(f"usage ledger unavailable, writing use_count inline: {e}")
            if "use_count" not in question:
                question["use_count"] = 0
            question["use_count"] += 1
            question["updated_at"] = datetime.now().isoformat()
            self._save_question(question_id, question)
            return True

# Create a singleton instance
question_bank = QuestionBank()

# Function to update the singleton instance with a custom storage path
def set_question_bank_instance(instance):
    """
    Update the singleton question_bank instance.

    Args:
        instance (QuestionBank): The new QuestionBank instance to use
    """
    global question_bank
    question_bank = instance

def get_question(category_id, points=None, prevent_repeats=True):
    """
    Standalone function to get a question from the specified category and points value.

    This function prevents repeated questions from appearing unless no more
    questions exist in the category.

    Args:
        category_id (str): Category ID
        points (int, optional): Points value. If None, any points value is selected.
        prevent_repeats (bool, optional): Whether to prevent repeated questions. Defaults to True.

    Returns:
        dict: Question data or None if no questions available
    """
    return question_bank.get_question(category_id, points, prevent_repeats)

def add_question(question_data, category_id="general", points=300):
    """
    Standalone function to add a new question.

    Args:
        question_data (dict): Question data
        category_id (str, optional): Category ID. Defaults to "general".
        points (int, optional): Points value for the question. Defaults to 30.

    Returns:
        tuple: (success, message or question_id)
    """
    return question_bank.add_question(question_data, category_id, points)

def get_questions_by_category(category_id, points=None, limit=None):
    """
    Standalone function to get all questions in a category, optionally filtered by points.

    Args:
        category_id (str): Category ID
        points (int, optional): Points value. If None, any points value is returned.
        limit (int, optional): Maximum number of questions to return. If None, all questions are returned.

    Returns:
        list: List of question data dictionaries
    """
    return question_bank.get_questions_by_category(category_id, points, limit)

def reset_used_questions(category_id=None):
    """
    Standalone function to reset the used_questions tracking for a category or all categories.

    Args:
        category_id (str, optional): Category ID. If None, all categories are reset.

    Returns:
        bool: True if reset was successful, False otherwise
    """
    return question_bank.reset_used_questions(category_id)

def increment_use_count(question_id):
    """
    Standalone function to increment the use_count of a question.

    Args:
        question_id (str): ID of the question

    Returns:
        bool: True if successful, False otherwise
    """
    return question_bank.increment_use_count(question_id)
