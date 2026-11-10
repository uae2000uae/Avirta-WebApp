# Avirta Web Interface

This directory contains a Flask web application that provides a web interface for the Avirta game.

## Setup and Running

1. Install the dependencies (in a virtual environment):
   ```
   pip install -r requirements.txt -r requirements-dev.txt
   ```

2. From the project root, run the Flask application:
   ```
   python app.py
   ```

3. Open a web browser and go to:
   ```
   http://localhost:8080
   ```

4. Run the tests with `pytest`.

Deployment is automatic: pushing to the `Avirta-1` branch deploys to Google
Cloud Run through Cloud Build. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Features

- Create game rooms with customizable categories
- Join existing game rooms
- Interactive game board with questions of varying difficulty
- Special player tools (Double Points, Change Question, Steal Question)
- Real-time scoring and leaderboard
- Question Bank management (view, add, import, export questions)
- Bulk import/export of questions from CSV and Excel files
- Template generation for question import

## Directory Structure

- `app.py`: Main Flask application
- `templates/`: HTML templates for the web interface
  - `base.html`: Base template with common structure and styling
  - `index.html`: Home page
  - `create_room.html`: Form to create a new game room
  - `join_room.html`: Form to join an existing game room
  - `game_room.html`: Game board and player tools
  - `question.html`: Question display and answer form
  - `result.html`: Result of answering a question
  - `leaderboard.html`: Current scores of all players
  - `question_bank.html`: Question bank management interface
  - `view_questions.html`: View questions in a specific category
  - `add_question.html`: Add a new question to the question bank
  - `bulk_import.html`: Import questions in bulk from files

## How to Play

1. **Create a Game Room**:
   - Click "Create Room" on the home page
   - Enter a room name and your name (as the host)
   - Select up to 5 categories for the game
   - Click "Create Room"

2. **Join a Game Room**:
   - Click "Join Room" on the home page
   - Enter the Room ID provided by the host and your name
   - Click "Join Room"

3. **Playing the Game**:
   - Select questions from the game board based on category and point value
   - Answer questions correctly to earn points
   - Use special tools to gain an advantage:
     - **Double Points**: Double the points for your next question
     - **Change Question**: Swap your current question for a new one
     - **Steal Question**: Take a question from another player
   - The player with the most points at the end wins!

## Question Bank Management

1. **View Questions**:
   - Click "Question Bank" in the navigation menu
   - Browse categories and click "View Questions" to see questions in a category

2. **Add Questions**:
   - Click "Add New Question" on the Question Bank page
   - Fill in the question details and submit the form

3. **Bulk Import Questions**:
   - Click "Bulk Import" in the navigation menu
   - Download a template file (CSV or Excel)
   - Fill in the template with your questions
   - Upload the file and configure import options
   - Click "Import Questions"

4. **Export Questions**:
   - Go to the Question Bank page
   - Click "Export Questions" for a specific category
   - The questions will be downloaded as a CSV file

## Notes

- Each player can use each tool only once per game
- The game board is automatically created with questions from the selected categories
- Questions are randomly selected from all difficulties
- The web interface provides access to all Avirta modules, including:
  - Game room and gameplay functionality
  - Question bank management
  - Bulk import/export of questions
  - Template generation for question import
