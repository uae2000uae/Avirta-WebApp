---
apply: always
---

# Avirta AI Rules & Specifications

This document defines the core specifications, design guidelines, and system coding standards for the Avirta codebase. All code modifications, new features, and bug fixes must strictly adhere to these rules.

---

## 📋 Table of Contents

1. [General System & Styling Rules](#1-general-system--styling-rules)
   - [GEN-001: Modular Design with Standalone Functions](#gen-001-modular-design-with-standalone-functions)
   - [GEN-002: Concise and Efficient Web App Design](#gen-002-concise-and-efficient-web-app-design)
2. [Question Database & Bank Rules](#2-question-database--bank-rules)
   - [PRJ-001: Question ID Format](#prj-001-question-id-format)
   - [PRJ-002: Question Points and Difficulty Levels](#prj-002-question-points-and-difficulty-levels)
   - [PRJ-003: Dynamic Category Management](#prj-003-dynamic-category-management)
3. [Game Board & Question Selection Rules](#3-game-board--question-selection-rules)
   - [PRJ-004: Game Room Question Card Points](#prj-004-game-room-question-card-points)
   - [PRJ-005: Game Room Question Allocation and Display](#prj-005-game-room-question-allocation-and-display)
   - [PRJ-012: Centralized Game Board Creation](#prj-012-centralized-game-board-creation)
   - [PRJ-014: Sophisticated Question Selection Algorithm for Regular Game](#prj-014-sophisticated-question-selection-algorithm-for-regular-game)
4. [Game Play, Room & State Rules](#4-game-play-room--state-rules)
   - [PRJ-006: Centralized Game Status Management](#prj-006-centralized-game-status-management)
   - [PRJ-007: Player Tools Functionality](#prj-007-player-tools-functionality)
   - [PRJ-011: Game Room Persistence Across Instances](#prj-011-game-room-persistence-across-instances)
   - [PRJ-013: Who is the Fastest Game Mode](#prj-013-who-is-the-fastest-game-mode)
5. [Frontend Polling, Navigation & UI Rules](#5-frontend-polling-navigation--ui-rules)
   - [PRJ-008: Guest Player Navigation Restrictions](#prj-008-guest-player-navigation-restrictions)
   - [PRJ-009: Dynamic Game Board Updates](#prj-009-dynamic-game-board-updates)
   - [PRJ-010: Real-time Polling Mechanisms](#prj-010-real-time-polling-mechanisms)
   - [PRJ-015: Modal Handling and User Interface Messaging](#prj-015-modal-handling-and-user-interface-messaging)
6. [Version Control & GitHub Integration Rules](#6-version-control--github-integration-rules)
   - [PRJ-016: GitHub Integration & Auto-Sync of Question Data](#prj-016-github-integration--auto-sync-of-question-data)
   - [PRJ-017: GitHub Data Is Live in Every Session](#prj-017-github-data-is-live-in-every-session)

---

## 1. General System & Styling Rules

### GEN-001: Modular Design with Standalone Functions

* **Rule**: Avirta is divided into distinct modules for flexibility and scalability. It uses standalone functions to keep each module independent, making debugging, updating, and expanding much easier.
* **Examples**:
  * **Valid**: Creating a new module `category_manager.py` with standalone functions like `get_categories()`, `add_category()`, etc.
  * **Valid**: Adding utility functions to `utils.py` that don't depend on other modules.
  * **Valid**: Implementing a new feature as a separate module with well-defined interfaces.
  * **Invalid**: Creating tightly coupled modules that directly access each other's internal variables.
  * **Invalid**: Using global state that is shared across multiple modules.
  * **Invalid**: Implementing a new feature by modifying multiple existing modules instead of creating a new one.
* **Implementation Requirements**:
  1. Each module should focus on a specific functionality or domain.
  2. Modules should communicate through well-defined interfaces (function parameters and return values).
  3. Functions should be designed to be standalone and reusable.
  4. Minimize dependencies between modules.
  5. Use function parameters instead of global variables for data exchange.
  6. Document module interfaces clearly.
* **Rationale**:
  * Modular design improves code maintainability by isolating changes to specific modules.
  * Standalone functions make testing easier by reducing dependencies.
  * Independent modules can be developed, tested, and deployed separately.
  * Clear module boundaries make the codebase easier to understand for new developers.
  * Flexibility in design allows for easier future enhancements and refactoring.

### GEN-002: Concise and Efficient Web App Design

* **Rule**: Web app design must be concise and efficient. All styles must be stored separately in `style.css`, and the system must prioritize reusing existing styles rather than creating new ones for different elements. Style class naming should be generic and intuitive, making it easy for developers to choose appropriate styles while coding.
* **Examples**:
  * **Valid**: Using existing utility classes like `.text-center` or `.mt-20` for common styling needs.
  * **Valid**: Creating a new generic class `.card` that can be reused across different components.
  * **Valid**: Using CSS variables (e.g., `var(--primary-color)`) for consistent theming.
  * **Invalid**: Adding inline styles directly to HTML elements (e.g., `style="margin-top: 20px;"`).
  * **Invalid**: Creating component-specific styles when generic ones could be used (e.g., `.question-card-margin` instead of using `.mb-20`).
  * **Invalid**: Duplicating style definitions in multiple places or in `<style>` tags within HTML templates.
* **Implementation Requirements**:
  1. All styles must be defined in the `style.css` file, not inline or in `<style>` tags within HTML templates.
  2. Use CSS variables for colors, spacing, and other repeated values.
  3. Create generic, reusable classes for common styling patterns (layout, spacing, typography, etc.).
  4. Use descriptive, purpose-based naming for classes (e.g., `.card`, `.badge`, `.alert`) rather than visual descriptions (e.g., `.blue-box`, `.large-text`).
  5. Document style classes with comments in the CSS file to make their purpose clear.
  6. Regularly review the CSS for duplicate or similar styles that could be consolidated.
* **Rationale**:
  * Centralized styles in `style.css` improve maintainability and make updates easier.
  * Reusing existing styles reduces CSS bloat and ensures consistency across the application.
  * Generic class names make the styling system more intuitive and easier to learn.
  * Descriptive, purpose-based naming helps developers choose the right styles for their components.
  * Avoiding inline styles and style duplication makes the codebase cleaner and more maintainable.

---

## 2. Question Database & Bank Rules

### PRJ-001: Question ID Format

* **Rule**: Question IDs must always be in the format `Q#######` (uppercase `Q` followed by 7 digits), and there must never be any duplications.
* **Examples**:
  * **Valid**: `Q0000001`, `Q0012345`, `Q9999999`
  * **Invalid**: `q0000001` (lowercase `q`), `Q00001` (only 6 digits), `Q_0000001` (contains underscore), `q_59f7a070aca7` (uses UUID format).
* **Implementation Requirements**:
  1. All question ID generation methods must use the format `Q#######` (uppercase `Q` followed by 7 digits).
  2. IDs should be sequential, incrementing from the highest existing ID.
  3. Duplicate IDs must be prevented through validation checks.
  4. Existing questions with non-compliant IDs should be migrated to the correct format when encountered.
* **Rationale**:
  * Consistent ID format improves readability and maintainability.
  * Sequential numbering makes it easier to track and reference questions.
  * The format allows for up to 10 million unique questions (0000000-9999999).

### PRJ-002: Question Points and Difficulty Levels

* **Rule**: The difficulty level and points of a question are the same thing and must not both exist in the same question. Use only the `points` field to represent difficulty level.
* **Examples**:
  * **Valid**: `"points": 100` (easiest difficulty)
  * **Valid**: `"points": 200` (easy difficulty)
  * **Valid**: `"points": 300` (medium difficulty)
  * **Valid**: `"points": 400` (hard difficulty)
  * **Valid**: `"points": 500` (hardest difficulty)
  * **Invalid**: Having both `"points": 300` and `"difficulty": "medium"` in the same question.
* **Implementation Requirements**:
  1. Questions must only have a `points` field and not a separate `difficulty` field.
  2. The system must recognize these 5 points values (`100`, `200`, `300`, `400`, `500`) as difficulty levels.
  3. When displaying difficulty level, use the points value.
  4. When filtering by difficulty, filter by points value.
  5. Existing questions with both fields should have the `difficulty` field removed.
* **Rationale**:
  * Eliminates redundancy and potential inconsistency between points and difficulty.
  * Simplifies the question data model.
  * Provides a clear mapping between numeric values and conceptual difficulty levels.

### PRJ-003: Dynamic Category Management

* **Rule**: Categories are defined using the questions database. No categories are stored in the system with no questions. Whenever a category is recorded within a question, the category appears. Categories are a dynamic list that is derived directly from the database as live data, not stored anywhere in the system but within the questions database.
* **Examples**:
  * **Valid**: A category "Science" exists because there are questions with `category_id` "science".
  * **Invalid**: A category "Sports" exists in the system but there are no questions with `category_id` "sports".
* **Implementation Requirements**:
  1. Categories must be dynamically derived from questions in the database.
  2. No static list of categories should be maintained.
  3. When displaying categories, only include categories that have at least one question.
  4. When a new question is added with a new category, that category should automatically appear in the system.
  5. When all questions in a category are deleted, that category should no longer appear in the system.
* **Rationale**:
  * Ensures that categories accurately reflect the content in the question database.
  * Eliminates the need to manually maintain a list of categories.
  * Prevents empty categories from appearing in the system.
  * Simplifies category management by deriving it directly from question data.

---

## 3. Game Board & Question Selection Rules

### PRJ-004: Game Room Question Card Points

* **Rule**: The points in game room question cards are derived from the points of each question the system selected from the database. Having all points randomly is recommended, but if no question with the required points exists, the system can select another question. However, the points displayed on each question card must always match the points of the question given from the database.
* **Examples**:
  * **Valid**: A question with 300 points in the database is displayed with 300 points on the game board.
  * **Valid**: A question with 200 points in the database is selected for a 100-point position on the board, but still displays 200 points.
* **Rationale**:
  * Ensures that players receive the correct number of points for answering questions.
  * Maintains consistency between the question database and the game board.
  * Provides accurate difficulty indication to players.
  * Allows for more varied and interesting game boards.

### PRJ-005: Game Room Question Allocation and Display

* **Rule**: In the game room, the system will always try to allocate questions that were the least used to guarantee newness of the questions within each category. Also, the question cards will be listed from most difficult to the least within the category in the grid. And for the category heading title, use the actual category name, not the category ID (which means use a space between words, not an underscore).
* **Examples**:
  * **Valid**: A question that has never been used is selected before a question that has been used multiple times.
  * **Valid**: Questions within a category are displayed in order from 500 points (hardest) to 100 points (easiest).
  * **Valid**: A category with ID "general_knowledge" is displayed as "General Knowledge".
  * **Invalid**: Questions are selected randomly without considering how many times they've been used.
  * **Invalid**: Questions are displayed in ascending order of difficulty (easiest to hardest).
  * **Invalid**: A category with ID "general_knowledge" is displayed as "general_knowledge".
* **Implementation Requirements**:
  1. Track how many times each question has been used across game sessions (`use_count`).
  2. When creating the game board, prioritize questions that have been used the least.
  3. Sort questions within each category from most difficult (highest points) to least difficult (lowest points).
  4. Display category names with spaces instead of underscores and proper title case.
  5. Ensure the tracking mechanism persists across game sessions.
* **Rationale**:
  * Ensures players see a variety of questions rather than the same ones repeatedly.
  * Provides a consistent and intuitive difficulty progression within each category.
  * Improves readability of category names for players.
  * Enhances the overall user experience by keeping content fresh and well-organized.

### PRJ-012: Centralized Game Board Creation

* **Rule**: Game board creation must be centralized in the `game_board_creator.py` module, which provides functions for creating game boards, selecting questions, and managing answered questions. This module must support a configurable number of questions per category and allow multiple questions with the same point value.
* **Examples**:
  * **Valid**: Using `create_board` function from `game_board_creator.py` to create a game board.
  * **Valid**: Creating a board with 10 questions per category (configurable via admin settings).
  * **Valid**: Having multiple questions with the same point value in a category.
  * **Valid**: Using `select_question` function to get a question from the board.
  * **Invalid**: Implementing game board creation logic directly in the `GameRoom` or `SpeedGameRoom` classes.
  * **Invalid**: Limiting the number of questions per category to a fixed value.
  * **Invalid**: Preventing multiple questions with the same point value.
* **Implementation Requirements**:
  1. All game board creation logic must be in the `game_board_creator.py` module.
  2. The module must provide these core functions:
     * `create_board`: Creates a game board with questions for each category.
     * `build_speed_board`: Creates a board for speed mode games with specific point values.
     * `build_standard_board`: Creates a board for standard mode games with default point values.
     * `organize_board`: Organizes selected questions by point value.
     * `select_question`: Selects a question from the board based on category and point value.
     * `get_available_questions`: Gets all available questions on the board, marking answered ones.
     * `is_board_completed`: Checks if all questions on the board have been answered.
     * `is_id_on_board`: Checks if a question ID exists on the board.
  3. The `GameRoom` and `SpeedGameRoom` classes must use these functions instead of implementing their own logic.
  4. The number of questions per category must be configurable via admin settings (default: 10).
  5. The board structure must support multiple questions with the same point value by storing questions in lists for each point value.
  6. Questions must be selected based on use count, prioritizing less-used questions.
  7. The board creation process must use a two-pass selection approach:
     * **First pass**: Select questions matching the desired point values.
     * **Second pass**: Fill remaining slots with any available questions, mapping them to the closest point value.
  8. For Speed mode, the system must use the point values specified by the host.
  9. For Standard mode, the system must use the default point values `[500, 400, 300, 200, 100]`.
  10. The UI must dynamically create and update question elements based on the board data.
* **Rationale**:
  * Centralizing game board creation improves maintainability by isolating this logic in a single module.
  * Supporting configurable number of questions per category provides flexibility for different game scenarios.
  * Allowing multiple questions with the same point value increases the variety of questions available.
  * Prioritizing less-used questions ensures players see a variety of questions rather than the same ones repeatedly.
  * The two-pass selection approach ensures we get enough questions even if there aren't enough matching the desired point values.
  * Dynamic UI updates ensure all questions are displayed correctly, regardless of their point values.

### PRJ-014: Sophisticated Question Selection Algorithm for Regular Game

* **Rule**: In the regular game, when creating a room, the system must implement a sophisticated question selection algorithm that prioritizes least used questions, ensures proper question distribution, and provides detailed error reporting when insufficient questions are available. The first 5 questions collected must fill all point values, then additional passes go from least point value to most.
* **Examples**:
  * **Valid**: System selects exactly one question for each point value (100, 200, 300, 400, 500) for the first 5 questions.
  * **Valid**: System prioritizes questions with `use_count` of 0 over questions with `use_count` of 5.
  * **Valid**: For questions beyond the first 5, system goes from least point value (100) to most (500) repeatedly.
  * **Valid**: System falls back to other question types in the same category if not enough questions of selected types.
  * **Valid**: System falls back to other point values in the same category if not enough questions of needed point values.
  * **Valid**: System provides detailed error message: "Category 'Science' lacks sufficient questions of the selected criteria."
  * **Invalid**: System randomly selects questions without considering `use_count`.
  * **Invalid**: System fails to implement the first-5-questions rule for filling all point values.
  * **Invalid**: System doesn't follow the least-to-most point value order for additional questions.
  * **Invalid**: System provides generic error message without specifying which categories lack questions.
* **Implementation Requirements**:
  1. **Primary Selection Process**:
     * Look for the specified number of questions per category in the system settings.
     * Filter questions by selected categories and question types during the `create_room` dialog.
     * For each category, sort the filtered list by least used questions to most used questions (`use_count` ascending).
     * **First Pass**: Select exactly one question for each point value (100, 200, 300, 400, 500) to get the first 5 questions.
     * **Additional Passes**: If more than 5 questions are needed, go from least point value (100) to most (500) repeatedly until enough questions are collected.
  2. **Fallback Passes** (if not enough questions are available in any category):
     * **Fallback Pass**: Find questions of other point values and map them to the closest standard point value.
     * **Final Pass**: If still not enough, issue a detailed message to the user stating what category/categories lack questions of the selected criteria.
  3. **Error Reporting**:
     * Provide specific category names that lack sufficient questions.
     * Include details about available question types and point values in each category.
     * Generate user-friendly messages that guide users on how to resolve the issue.
     * Return comprehensive error details for debugging and user feedback.
  4. **Question Distribution Logic**:
     * **First 5 Questions**: Must fill all point values (100, 200, 300, 400, 500) — one question per point value.
     * **Additional Questions**: Go from least point value (100) to most (500) repeatedly: 100, 200, 300, 400, 500, 100, 200, 300, 400, 500, etc.
     * Always prioritize least used questions (lowest `use_count`) within each point value.
  5. **Integration Requirements**:
     * The `build_standard_board` function must implement this algorithm.
     * The `create_board` function must collect and aggregate error details from all categories.
     * The `GameRoom.create_board` method must return error details along with success/failure status.
     * The `app.py` routes must display detailed error messages to users.
* **Rationale**:
  * Ensures players see the least used questions first, maintaining content freshness.
  * Guarantees that all difficulty levels (point values) are represented in the first 5 questions.
  * Provides balanced difficulty progression for additional questions by cycling from easiest to hardest.
  * Implements robust fallback mechanisms to maximize question availability.
  * Offers detailed error reporting to help users understand and resolve issues.
  * Maintains backward compatibility while significantly improving question selection quality.
  * Enhances user experience by providing specific guidance when insufficient questions are available.

---

## 4. Game Play, Room & State Rules

### PRJ-006: Centralized Game Status Management

* **Rule**: All game status updates and events must be managed through a centralized system. The `GameStatusManager` class serves as the single source of truth for all game events, ensuring consistent information across all pages and components. The game status must track and record all events including but not limited to: game start, whose turn it is, what question they selected, what was the result and score change, turn switching, activation of tools, who is joining or leaving the room, etc.
* **Examples**:
  * **Valid**: Adding a game event through the centralized `add_game_event()` function that uses `GameStatusManager`.
  * **Valid**: Retrieving game events from the `/api/game_updates/<room_id>` endpoint.
  * **Invalid**: Storing game events in page-specific variables or local storage.
  * **Invalid**: Creating separate event tracking systems for different pages.
* **Implementation Requirements**:
  1. All game events must be added through the centralized `add_game_event()` function.
  2. The `GameStatusManager` class must be used to store and retrieve all game events.
  3. Events must include a timestamp, event type, and relevant data.
  4. The system must track and record all key game events including: game start, turn changes, question selection, answer results, score changes, tool activation, players joining/leaving, and game end.
  5. The API must provide a single endpoint for retrieving all game updates.
  6. Frontend pages must poll this endpoint to get the latest game status.
  7. No page should maintain its own separate event tracking system.
* **Rationale**:
  * Ensures all pages display consistent information about game events.
  * Prevents duplication of event data and potential inconsistencies.
  * Simplifies event management by centralizing it in one place.
  * Makes it easier to add new event types or modify existing ones.
  * Improves maintainability by having a single system to update.

### PRJ-007: Player Tools Functionality

* **Rule**: The game provides three tools for players: **Double Points**, **Change Question**, and **Steal Question**. Each player gets one of each tool per game. Tools must be implemented consistently across all pages and follow specific rules for when they can be used.
* **Examples**:
  * **Valid**: A player uses Double Points before selecting a question to double its point value, but only when the host is on the game room page.
  * **Valid**: The current player uses Change Question during the question timer to get a different question, but only when the host is on the question page.
  * **Valid**: A player uses Steal Question to take a question from another player, but only when the host is on the question page and it's not the player's turn.
  * **Invalid**: A player using a tool they've already used in the current game.
  * **Invalid**: A player using Double Points when the host is on the question page.
  * **Invalid**: A player using Change Question when the host is not on the question page or when it's not the player's turn.
  * **Invalid**: A player using Steal Question when the host is not on the question page or during the player's turn.
* **Implementation Requirements**:
  1. Each player must start with one of each tool per game.
  2. **Double Points**: Must be used before a question is selected and doubles the points for the next question.
     * Can only be used when the host is in the game room page, not in the question page.
  3. **Change Question**: Must only be available when a question is active and must replace the current question with another from the same category.
     * Can only be used when the host is in the question page and it's the player's turn.
     * The new question must be from the same category with equal or close points value.
  4. **Steal Question**: Must allow a player to take another player's question before it's answered.
     * Can only be used when the host is in the question page and it's NOT the player's turn.
     * This will trigger the system to switch the active player to the one who clicked on the tool.
     * This will not make the player lose their turn, they will only steal the score.
  5. Tools must be tracked in the `GameRoom` class using the `player_tools` attribute.
  6. Tool usage must be communicated to all players through the game status system.
  7. Tool buttons must be enabled/disabled appropriately based on availability and context.
* **Rationale**:
  * Provides strategic gameplay options for players.
  * Ensures fair and consistent tool usage across all games.
  * Prevents tool abuse by limiting each to one use per game.
  * Creates interesting gameplay dynamics through strategic tool usage.
  * Enhances player engagement through additional gameplay mechanics.
  * Restricts tool usage to appropriate game states to maintain game balance.

### PRJ-011: Game Room Persistence Across Instances

* **Rule**: Game rooms must be persisted to disk to ensure they are accessible across different application instances. The `GameStatusManager` is responsible for persisting and loading game rooms, similar to how it handles game events.
* **Examples**:
  * **Valid**: Creating a game room and persisting it to disk using `game_status_manager.persist_game_room()`.
  * **Valid**: Loading a game room from disk when it's not found in memory using `game_status_manager.load_game_room()`.
  * **Valid**: Updating the persisted game room when players join or leave.
  * **Invalid**: Storing game rooms only in memory without persistence.
  * **Invalid**: Creating separate persistence mechanisms for game rooms outside of `GameStatusManager`.
* **Implementation Requirements**:
  1. Game rooms must be persisted to disk whenever they are created or updated.
  2. When a game room is not found in memory, the system must attempt to load it from disk.
  3. The `GameStatusManager` class must provide methods for persisting and loading game rooms.
  4. Game room persistence must include all relevant state: players, board, answered questions, etc.
  5. The persistence mechanism must handle serialization of complex data structures like sets and dictionaries.
  6. All endpoints that access game rooms must check for persisted rooms if not found in memory.
* **Rationale**:
  * Ensures game rooms are accessible across different application instances in cloud environments.
  * Prevents "room not found" errors when requests are routed to different instances.
  * Maintains game continuity even if the application is restarted or scaled.
  * Leverages the existing persistence infrastructure in `GameStatusManager`.
  * Provides a consistent approach to state management across the application.

### PRJ-013: Who is the Fastest Game Mode

* **Rule**: The "Who is the fastest" game mode allows players to compete to answer questions the fastest. The host creates a game board, reveals questions one by one, and awards points to the player who answers correctly first.
* **Examples**:
  * **Valid**: Host creates a game with selected categories and point values.
  * **Valid**: Host reveals a question, starts the timer, and waits for players to answer.
  * **Valid**: Host awards points to the player who answers correctly first.
  * **Valid**: Host moves to the next question after awarding points or if no one answers correctly.
  * **Invalid**: Players revealing questions or answers.
  * **Invalid**: Players awarding points to themselves.
  * **Invalid**: Host moving to the next question before revealing the current question and answer.
* **Implementation Requirements**:
  1. The game must use the `FastestGameRoom` class which extends `GameRoom`.
  2. The game must support the following flow:
     * Host creates a game board with selected categories and point values.
     * Host reveals a question and the timer starts.
     * Host reveals the answer when ready.
     * Host awards points to the player who answered correctly first.
     * Host moves to the next question.
  3. The game must track and display:
     * Current question number and total questions.
     * Question category and point value.
     * Timer for each question.
     * Player scores in a leaderboard.
  4. Only the host can reveal questions, reveal answers, award points, and move to the next question.
  5. The game must persist game state to disk to ensure continuity across sessions.
  6. The game must use the existing game board creation and question selection mechanisms.
* **Rationale**:
  * Provides a new game mode that emphasizes speed and competition.
  * Leverages existing game infrastructure for consistency and maintainability.
  * Gives the host control over the game flow to ensure fair play.
  * Tracks player scores to determine the winner.
  * Persists game state to ensure continuity across sessions.

---

## 5. Frontend Polling, Navigation & UI Rules

### PRJ-008: Guest Player Navigation Restrictions

* **Rule**: Guest players in `joined_room` must not be able to navigate away from the page until the game ends or they click the "Leave Game" button. This prevents accidental navigation that would disrupt the game flow.
* **Examples**:
  * **Valid**: A guest player is prevented from using the browser's back button during an active game.
  * **Valid**: A guest player can navigate away after clicking the "Leave Game" button.
  * **Valid**: A guest player can navigate away after the game has ended.
  * **Invalid**: A guest player navigating away from the game by clicking a link or using browser navigation.
  * **Invalid**: Preventing the host from navigating between game pages.
* **Implementation Requirements**:
  1. Use the `beforeunload` event to prevent navigation for guest players.
  2. Set a `window.gameEnded` flag when the game ends to allow navigation.
  3. Add a click handler to the "Leave Game" button to allow navigation.
  4. Only apply these restrictions to guest players, not the host.
  5. Ensure AJAX is used for all in-game actions to prevent page reloads.
  6. Display appropriate messages to users when navigation is prevented.
* **Rationale**:
  * Prevents accidental game abandonment by guest players.
  * Ensures game continuity for all participants.
  * Provides clear exit paths through the "Leave Game" button.
  * Allows normal navigation after the game has ended.
  * Improves user experience by preventing accidental data loss.

### PRJ-009: Dynamic Game Board Updates

* **Rule**: The game board must update dynamically without full page refreshes. When changes occur (such as questions being answered or tools being used), only the affected parts of the UI should update.
* **Examples**:
  * **Valid**: The game board updates to show a question as answered without refreshing the page.
  * **Valid**: Double Points activation updates the point values displayed without a page refresh.
  * **Valid**: The leaderboard updates when scores change without refreshing the page.
  * **Invalid**: Refreshing the entire page when a question is answered.
  * **Invalid**: Requiring manual refresh to see updated game state.
* **Implementation Requirements**:
  1. Use AJAX to fetch updated game state from the server.
  2. Implement a dedicated `updateGameBoard()` function to refresh the question grid.
  3. Only update DOM elements that have changed since the last update.
  4. Track the last state to avoid unnecessary updates and prevent flickering.
  5. Handle tool usage (especially Double Points) by updating the UI dynamically.
  6. Ensure all updates maintain visual consistency and don't disrupt user interaction.
* **Rationale**:
  * Provides a smoother, more responsive user experience.
  * Reduces server load by avoiding full page reloads.
  * Prevents disruption to the user's current focus or interaction.
  * Maintains game flow without interruptions.
  * Improves performance, especially on slower connections.

### PRJ-010: Real-time Polling Mechanisms

* **Rule**: All game pages must implement polling mechanisms to receive real-time updates from the server. These mechanisms must be consistent across pages and handle all types of game events.
* **Examples**:
  * **Valid**: Polling the `/api/game_updates/<room_id>` endpoint every 1 second for updates.
  * **Valid**: Processing events based on their type (player_joined, question_selected, etc.).
  * **Valid**: Updating the UI based on received events without page refreshes.
  * **Invalid**: Using different polling endpoints for different types of updates.
  * **Invalid**: Implementing inconsistent polling frequencies across pages.
* **Implementation Requirements**:
  1. All pages must poll the `/api/game_updates/<room_id>` endpoint at a consistent frequency (1 second).
  2. Polling must start when the page loads and continue until the page is unloaded.
  3. Each page must track the last event timestamp to avoid processing duplicate events.
  4. Event processing must be type-specific, with appropriate UI updates for each event type.
  5. Polling must handle network errors gracefully with appropriate error logging.
  6. Clean up polling intervals when pages are unloaded to prevent memory leaks.
* **Rationale**:
  * Ensures all players have up-to-date information about the game state.
  * Provides a consistent experience across all game pages.
  * Enables real-time interaction between players.
  * Reduces server load compared to WebSocket connections for this use case.
  * Simplifies implementation while still providing near-real-time updates.

### PRJ-015: Modal Handling and User Interface Messaging

* **Rule**: All modal dialogs in the system must use a centralized modal queue system to prevent overlapping, implement proper HTML rendering for organized messages, and follow consistent patterns for error display. Modals must not auto-close and should only be dismissed through user interaction (clicking overlay or pressing Escape).
* **Examples**:
  * **Valid**: Using `showModal('Error message')` which automatically queues if another modal is active.
  * **Valid**: Displaying organized error messages with bullet points: `"The following categories lack sufficient questions:\n\n• science\n• history\n\nPlease try to add more questions."`
  * **Valid**: Using `{{ session.pop("error_modal")|safe }}` in templates to render HTML breaks properly.
  * **Valid**: Replacing `alert()` calls with `showModal()` for consistent user experience.
  * **Invalid**: Creating multiple overlapping modals simultaneously.
  * **Invalid**: Using literal `<br>` tags in modal text without the `|safe` filter.
  * **Invalid**: Using `alert()` for error messages instead of the modal system.
  * **Invalid**: Implementing auto-close timers that dismiss modals without user interaction.
* **Implementation Requirements**:
  1. **Modal Queue System**:
     * All modals must use the centralized `showModal(message, callback)` function.
     * The system must maintain a `modalQueue` array and `isModalActive` flag to prevent overlapping.
     * When a modal is active, new modal requests must be queued and displayed sequentially.
     * The `processModalQueue()` function must automatically display the next modal when the current one closes.
  2. **Message Formatting and HTML Rendering**:
     * Backend error messages with newlines (`\n`) must be converted to HTML breaks (`<br>`) before setting `session['error_modal']`.
     * Templates must use the `|safe` filter when displaying modal content: `{{ session.pop("error_modal")|safe }}`.
     * JavaScript modal display must use `innerHTML` instead of `textContent` to render HTML breaks properly.
     * Organized messages should use bullet points (`•`) with proper spacing for better readability.
  3. **Consistent Error Display Patterns**:
     * Replace all `alert()` calls with `showModal()` calls that include fallback: `if (typeof showModal === 'function') { showModal(message); } else { alert(message); }`
     * Backend routes must convert newlines to HTML breaks: `detailed_message_html = detailed_message.replace('\n', '<br>')`
     * Error messages should be organized with clear structure: introduction, bullet-pointed list, helpful guidance.
  4. **Template Safety and Loading**:
     * Use timing checks in templates to ensure `showModal` function is available before calling it.
     * Implement retry mechanism with `setTimeout` if the function is not immediately available.
     * Apply `|safe` filter only to controlled backend-generated content, never to user input.
  5. **User Interaction Requirements**:
     * Modals must not auto-close after any time duration.
     * Modals must close when users click on the dark overlay background.
     * Modals must close when users press the Escape key.
     * Modals must support optional callback functions that execute after closing.
  6. **State Management**:
     * Track current modal with `currentModal` variable for proper cleanup.
     * Reset modal state (`isModalActive = false`, `currentModal = null`) when modals close.
     * Process the next queued modal automatically after the current modal closes.
     * Use fade-out animations (300ms) for smooth modal transitions.
* **Rationale**:
  * The modal queue system prevents visual conflicts and ensures users see one clear message at a time.
  * Proper HTML rendering allows for organized, readable error messages with bullet points and proper spacing.
  * Consistent error display patterns improve user experience and reduce confusion between different message types.
  * Removing auto-close functionality gives users full control over when they dismiss messages.
  * Template safety measures prevent JavaScript errors while maintaining security.
  * Centralized modal handling reduces code duplication and ensures consistent behavior across the application.
  * Sequential modal display maintains user focus and prevents information overload.

---

## 6. Version Control & GitHub Integration Rules

### PRJ-016: GitHub Integration & Auto-Sync of Question Data

* **Rule**: Persisting question-bank content back to the GitHub repository must go through the self-contained `contents/admin_controls/github_integration.py` module, which uses the GitHub REST API (token-based) and is independent of the local `git` binary, git credentials, SSH keys, and any other module. It must be callable from anywhere in the app (Flask routes, background threads, or the CLI) and must degrade gracefully (never crash a request) when `GITHUB_TOKEN` is missing. Full source-code pushes (all changed files) are a separate concern handled by `contents/admin_controls/git_push_helper.py` (native git) and must not be conflated with question sync.
* **Public interface** (import from `contents.admin_controls.github_integration`):
  * `push_all_amended_questions_async(commit_message=None, detach=True)` — push all `contents/questions/*.json` via the API. Fire-and-forget when `detach=True`.
  * `push_files_async(rel_paths, commit_message=None, detach=True)` — push an explicit list of files.
  * `push_reports_async(commit_message=None, detach=True, include_questions=True)` — push all `questionmanagement/reported_questions/*.json` (plus the question files carrying the `reported` flag).
  * `push_usage_ledger_async(commit_message=None, detach=True)` — push ONLY this instance's usage-count ledger (`datastore/usage/usage_<INSTANCE_ID>.json`). Conflict-free; used by end/reset game.
  * `push_to_github(commit_message=None, detach=False)` — one-call convenience helper.
  * `GitHubIntegration` — client class; always check `.token` before pushing.
  * `get_push_progress()` — thread-safe progress dict used for status polling.
* **Configuration** (resolved by `secret_loader.get_secret` from env var or Google Secret Manager):
  * `GITHUB_TOKEN` (required) — PAT with `repo` / contents:write scope.
  * `GITHUB_REPO` — `owner/repo` (defaults to `.git/config` origin, else `uae2000uae/Avirta-1`).
  * `GITHUB_BRANCH` — target branch (defaults to `.git/HEAD`, else `Avirta-1`).
  * `GITHUB_API_URL` — API base for GitHub Enterprise (defaults to `https://api.github.com`).
* **Trigger Map** (every place the integration fires — keep this in sync when routes change):

  | Type | Route | Function | When |
  |------|-------|----------|------|
  | Auto | `/end_game/<room_id>` | `end_game` | a host ends a game — pushes the **usage-count ledger only** (`push_usage_ledger_async`) |
  | Auto | `/reset_game` | `reset_game` | starting a new game — pushes the **usage-count ledger only** (`push_usage_ledger_async`) |
  | Auto | `/edit_category/<id>` | `edit_category` | category ID changed |
  | Auto | `/edit_category/<id>` | `edit_category` | category updated |
  | Auto | `/question_bank/delete/<id>` | `delete_question` | a question deleted |
  | Auto | `/question_bank/delete_category_questions/<id>` | `delete_category_questions` | all questions in a category deleted |
  | Auto | `/question_bank/add` | `add_question_page` | question added or edited |
  | Auto | `/bulk_import` | `bulk_import_page` | questions bulk-imported |
  | Auto | `/save_ai_questions` | `save_ai_questions` | AI-generated questions saved (guarded by `GitHubIntegration().token`) |
  | Auto | `/save_processed_files_to_database` | `save_processed_files_to_database` | AI-validated files saved |
  | Auto | `/report_question` | `report_question` | a player reports a question (pushes the report record + the `reported` flag) |
  | Manual | `/admin/git_push` | `admin_git_push` | "Sync Questions to GitHub" button |
  | Status | `/admin/git_push_status` | `admin_git_push_status` | modal polls question-sync progress |
  | CLI/Code | — | `python -m contents.admin_controls.github_integration` or direct import | scripts, schedulers, other modules |

* **Related (native git, NOT this module)**:
  * `/admin/git_push_all` → `admin_git_push_all` — "Push All Source Files" button (all changed files via `git_push_helper.py`).
  * `/admin/git_push_all_status` → `admin_git_push_all_status` — progress for the full source push.
* **Implementation Requirements**:
  1. All question-data pushes must call the `github_integration` module — never shell out to `git` for question sync.
  2. Auto-push hooks must be best-effort: wrapped in `try/except` so a failed or missing-token push never breaks the originating request.
  3. Commits are attributed to `Copilot <223556219+Copilot@users.noreply.github.com>` and land as a single atomic commit (blobs → tree → commit → ref); unchanged files must produce no commit.
  4. Question-sync and full-source pushes must keep separate progress state and separate status endpoints.
  5. This Trigger Map must be updated whenever a call site is added or removed.
  6. Every commit this module makes carries a `[skip ci]` token so question-data syncs never trigger a Cloud Run redeploy — defense-in-depth alongside the Cloud Build `ignoredFiles` filter for `contents/questions/**`. The native full-source push (`git_push_helper.py`) intentionally omits it so code pushes still deploy.
  7. `use_count` is NOT stored via whole-file replace. It lives in per-instance grow-only ledgers under `datastore/usage/` (`usage_<INSTANCE_ID>.json`); each instance writes only its own file (conflict-free), and effective `use_count` = file base + sum of all ledgers (applied in memory by `QuestionBank.load_questions`). Increments go through `usage_ledger.increment()`; question files no longer churn on play. `datastore/usage/**` is in the trigger `ignoredFiles`. An optional single-writer `usage_ledger.rollup_into_question_files()` folds ledgers back into the question files and compacts them.
  8. Pushing is only half of the sync: because data commits carry `[skip ci]`, a running server never gets them by redeploy. Reading them back is required by [PRJ-017](#prj-017-github-data-is-live-in-every-session).
* **Rationale**:
  * The token-based REST API works on Cloud Run, where the `git` binary and credentials are unavailable.
  * A single, independent module keeps the integration testable and callable from anywhere in the app.
  * Best-effort auto-sync keeps the repository current without risking the user-facing request path.
  * Note: game end/reset (first two rows) fire on the normal game flow, so question files sync frequently on a live instance — restrict to admin/editing routes if that volume is undesirable.

### PRJ-017: GitHub Data Is Live in Every Session

* **Rule**: GitHub is the permanent store of Avirta's runtime data. Any data update committed to GitHub — by the app's own sync, by another server, or by a person editing the repository — must take effect in every ongoing session and every new session without a redeploy or restart. A server must never select questions from data older than what GitHub holds. The deploy-time copy of the data files is only a starting point, never the source of truth.
* **Problem this prevents**: A Cloud Run container starts from the files as they were when it was deployed. Data syncs are committed with `[skip ci]`, so they never redeploy. Without a pull, a container that restarts (instance recycling, a crash, a new revision) falls back to the deploy-time usage ledgers and question files: questions played since then look unplayed and are dealt again in the next game, and edits made on GitHub never reach players. (Seen in `datastore/usage/`: two ledgers from the same revision, e.g. `usage_avirta-01197-rfs_*`, each counting plays the other could not see.)
* **Examples**:
  * **Valid**: A question edited on GitHub during a game is used by the next board created on the live server.
  * **Valid**: After a container restart, the questions played before the restart are still counted as played (other ledgers are pulled from GitHub at startup).
  * **Valid**: A usage ledger that changed both here and on GitHub is merged by keeping the larger count per question.
  * **Invalid**: Reading question data or use counts only from the files shipped with the deploy.
  * **Invalid**: Caching question data in memory across games without reloading it through `load_questions()`.
  * **Invalid**: Overwriting a newer GitHub copy with this server's older, untouched copy (the sync pushes only files changed here since they last matched GitHub).
* **Implementation Requirements**:
  1. `contents/admin_controls/github_pull.py` → `refresh()` brings GitHub's data into the server. It covers `contents/questions/*.json`, `datastore/usage/*.json`, `questionmanagement/reported_questions/*.json` and `contents/category_tags.json` (`PULL_GLOBS`). Add new runtime data that the app reads to `PULL_GLOBS` as well as to `SYNC_GLOBS` in `github_sync.py`.
  2. `refresh()` runs at the start of every `QuestionUploader.load_questions()` and `QuestionBank.load_questions()` — so at startup and before every new board in every game mode. Any new code path that selects questions must load them through `load_questions()` first.
  3. Per file: same as GitHub → nothing; usage ledger → grow-only merge (max per question); unchanged here since it last matched GitHub → replace with GitHub's copy; changed here and on GitHub → keep ours (the next sync pushes it) and log `GITHUB_PULL_CONFLICT`. A file deleted on this server is not brought back. Files are written atomically.
  4. `github_sync` keeps, per file, the last version known to match GitHub (`known_remote_sha` / `remember_remote_sha`). A pull and a successful push both move it forward. A sync pushes only files that differ from it.
  5. It must never break or noticeably slow a request: it never raises, uses an 8-second timeout per GitHub call, checks GitHub at most once every `GITHUB_PULL_INTERVAL` seconds (default 20), and costs one API call when the branch has not moved.
  6. Switch: `GITHUB_PULL=1/0`. Default on when running on Cloud Run (`K_SERVICE` set), off elsewhere so local checkouts and tests are never rewritten.
  7. Tests: `tests/test_github_pull.py`.
* **Rationale**:
  * Players must not see the same questions again just because the server restarted.
  * Edits made on GitHub are the admin's intent and must reach live games immediately.
  * Grow-only ledgers make the merge lossless, so pulling and pushing can run at any time without losing a play.
