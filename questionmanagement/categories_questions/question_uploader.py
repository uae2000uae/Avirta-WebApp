"""
Question Uploader Module for Avirta

This module handles the uploading and management of individual questions,
including validation, categorization, and storage.
"""

import json
import os
from datetime import datetime

class QuestionUploader:
    """
    A class to handle uploading and managing Avirta questions.

    Attributes:
        questions (dict): Dictionary of questions indexed by ID
        storage_path (str): Path to store question data
        question_types (list): List of valid question types
        required_fields (dict): Dictionary of required fields for each question type
    """

    def __init__(self, storage_path="questions"):
        """
        Initialize a new question uploader.

        Args:
            storage_path (str, optional): Path to store question data. Defaults to "questions".
        """
        self.questions = {}
        self.storage_path = storage_path
        self.question_types = ["multiple_choice", "true_false", "text"]
        self.required_fields = {
            "multiple_choice": ["question", "options", "correct_answer"],
            "true_false": ["question", "correct_answer"],
            "text": ["question", "correct_answer"]
        }

        # Create storage directory if it doesn't exist
        os.makedirs(storage_path, exist_ok=True)

    def add_question(self, question_data, category_id="general"):
        """
        Add a new question.

        Args:
            question_data (dict): Question data
            category_id (str, optional): Category ID. Defaults to "general".

        Returns:
            tuple: (success, message or question_id)
        """
        # Validate question data
        validation_result = self._validate_question(question_data)
        if not validation_result[0]:
            return validation_result

        # Check if question already has an ID
        if "id" in question_data and question_data["id"]:
            question_id = question_data["id"]
            # Check if a question with this ID already exists
            if question_id in self.questions:
                # Update the existing question instead of creating a new one
                return self.update_question(question_id, {**question_data, "category_id": category_id})
        else:
            # Generate a unique ID for the question
            question_id = self._generate_question_id()
            # Add metadata
            question_data["id"] = question_id
            question_data["created_at"] = datetime.now().isoformat()
            question_data["updated_at"] = question_data["created_at"]
            question_data["active"] = True

        # Set or update category_id
        question_data["category_id"] = category_id

        # Store the question
        self.questions[question_id] = question_data

        # Save to file
        self._save_question(question_id, question_data)

        return True, question_id

    def update_question(self, question_id, updated_data):
        """
        Update an existing question.

        Args:
            question_id (str): ID of the question to update
            updated_data (dict): Updated question data

        Returns:
            tuple: (success, message)
        """
        if question_id not in self.questions:
            return False, "Question not found"

        # Get the current question data
        current_data = self.questions[question_id]

        # Validate the updated data
        if "type" in updated_data and updated_data["type"] != current_data["type"]:
            # If changing question type, validate all required fields
            validation_result = self._validate_question(updated_data)
            if not validation_result[0]:
                return validation_result
        else:
            # If not changing type, just validate the provided fields
            question_type = current_data["type"]
            for field in self.required_fields[question_type]:
                if field in updated_data and not updated_data[field]:
                    return False, f"Field '{field}' cannot be empty"

        # Update the question data
        for key, value in updated_data.items():
            current_data[key] = value

        # Update metadata
        current_data["updated_at"] = datetime.now().isoformat()

        # Save to file
        self._save_question(question_id, current_data)

        return True, "Question updated successfully"

    def delete_question(self, question_id):
        """
        Delete a question.

        Args:
            question_id (str): ID of the question to delete

        Returns:
            bool: True if question was deleted successfully, False otherwise
        """
        if question_id not in self.questions:
            return False

        # Get the category of the question
        category_id = self.questions[question_id].get("category_id", "general")

        # Remove from memory
        del self.questions[question_id]

        # Remove from storage (category file)
        file_path = os.path.join(self.storage_path, f"{category_id}.json")
        if os.path.exists(file_path):
            try:
                # Load the category file
                with open(file_path, "r", encoding="utf-8") as f:
                    category_questions = json.load(f)

                # Remove the question from the list
                category_questions = [q for q in category_questions if q.get("id") != question_id]

                # Save the updated list back to the file
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(category_questions, f, indent=2)

                return True
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error updating category file {file_path}: {e}")
                return False

        return True

    def delete_questions_by_category(self, category_id):
        """
        Delete all questions in a category.

        Args:
            category_id (str): ID of the category

        Returns:
            tuple: (success, count) where count is the number of questions deleted
        """
        # Get all questions in the category
        questions_to_delete = self.get_questions_by_category(category_id)

        if not questions_to_delete:
            return False, 0

        # Count the questions to delete
        count = len(questions_to_delete)

        # Remove questions from memory
        for question in questions_to_delete:
            question_id = question.get("id")
            if question_id in self.questions:
                del self.questions[question_id]

        # Remove the category file
        file_path = os.path.join(self.storage_path, f"{category_id}.json")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except IOError as e:
                print(f"Error deleting category file {file_path}: {e}")
                return False, 0

        return True, count

    def get_question(self, question_id):
        """
        Get a question by ID.

        Args:
            question_id (str): ID of the question

        Returns:
            dict: Question data or None if not found
        """
        return self.questions.get(question_id)

    def get_questions_by_category(self, category_id):
        """
        Get all questions in a category.

        Args:
            category_id (str): ID of the category

        Returns:
            list: List of questions in the category
        """
        return [q for q in self.questions.values() if q.get("category_id") == category_id]

    def load_questions(self):
        """
        Load all questions from storage.

        Returns:
            int: Number of questions loaded
        """
        count = 0
        # Clear existing questions to ensure a clean load
        self.questions = {}

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

                            # Process each question in the category file
                            for question_data in category_questions:
                                question_id = question_data.get("id")

                                if question_id:
                                    # Ensure category_id is set correctly in the question data
                                    question_data["category_id"] = category_id

                                    # Store the question
                                    self.questions[question_id] = question_data
                                    count += 1
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"Error loading questions from {filename}: {e}")

        # Add the plays recorded in the usage ledgers. The question files hold
        # only a base count and are not rewritten on each play, so without this
        # the boards would always see the same "least used" questions.
        try:
            from questionmanagement.usage_ledger import get_totals
            totals = get_totals()
            self._ledger_extra = {}
            for question_id, question in self.questions.items():
                extra = totals.get(question_id)
                if extra:
                    question["use_count"] = int(question.get("use_count", 0) or 0) + int(extra)
                    self._ledger_extra[question_id] = int(extra)
        except Exception as e:
            print(f"usage ledger overlay skipped: {e}")

        return count

    def remove_duplicate_questions(self):
        """
        Identify and remove duplicate questions based on their content.

        A question is considered a duplicate if it has the same question text,
        type, and category_id as another question.

        Returns:
            int: Number of duplicate questions removed
        """
        # Create a dictionary to track unique questions
        unique_questions = {}
        duplicates = []

        # Identify duplicates
        for question_id, question_data in self.questions.items():
            # Create a key based on question content
            content_key = (
                question_data.get("question", ""),
                question_data.get("type", ""),
                question_data.get("category_id", "")
            )

            if content_key in unique_questions:
                # This is a duplicate
                # Keep the older question (based on created_at timestamp)
                existing_id = unique_questions[content_key]
                existing_question = self.questions[existing_id]

                # Compare timestamps to determine which to keep
                existing_time = existing_question.get("created_at", "")
                current_time = question_data.get("created_at", "")

                if current_time < existing_time:
                    # Current question is older, keep it instead
                    duplicates.append(existing_id)
                    unique_questions[content_key] = question_id
                else:
                    # Existing question is older, keep it
                    duplicates.append(question_id)
            else:
                # This is a unique question
                unique_questions[content_key] = question_id

        # Remove duplicates
        for duplicate_id in duplicates:
            self.delete_question(duplicate_id)

        return len(duplicates)

    def _validate_question(self, question_data):
        """
        Validate question data.

        Args:
            question_data (dict): Question data to validate

        Returns:
            tuple: (success, message)
        """
        # Check question type
        question_type = question_data.get("type")
        if not question_type:
            return False, "Question type is required"

        if question_type not in self.question_types:
            return False, f"Invalid question type. Must be one of: {', '.join(self.question_types)}"

        # Check required fields
        for field in self.required_fields[question_type]:
            if field not in question_data or not question_data[field]:
                return False, f"Field '{field}' is required for {question_type} questions"

        # Validate specific question types
        if question_type == "multiple_choice":
            options = question_data.get("options", [])
            if not isinstance(options, list) or len(options) < 2:
                return False, "Multiple choice questions must have at least 2 options"

            correct_answer = question_data.get("correct_answer")
            if correct_answer not in options:
                return False, "Correct answer must be one of the options"

        elif question_type == "true_false":
            correct_answer = question_data.get("correct_answer", "").lower()
            if correct_answer not in ["true", "false"]:
                return False, "Correct answer for true/false questions must be 'true' or 'false'"

        return True, "Question is valid"

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


def _without_ledger_uses(question_data, extra):
    """Copy of the question for writing to its file: the plays counted in the
    usage ledgers are taken off again, so the file keeps only its base count."""
    if not extra:
        return question_data
    data = dict(question_data)
    data["use_count"] = max(0, int(data.get("use_count", 0) or 0) - int(extra))
    return data
