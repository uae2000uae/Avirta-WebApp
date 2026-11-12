/**
 * livestatus.js - Central script for handling game status updates in Avirta
 * 
 * This script handles:
 * 1. Polling for game updates
 * 2. Updating status messages
 * 3. Updating the leaderboard
 * 4. Handling game events (player joining, leaving, answering questions, etc.)
 */

// Import gametoolsutil.js if it's not already loaded
if (!window.addStatusUpdate) {
    const script = document.createElement('script');
    script.src = '/static/js/gametoolsutil.js';
    document.head.appendChild(script);
}

// Helper function to show a flash message and redirect to home page
function showGameEndedFlashAndRedirect() {
    // Create a flash message
    const flashContainer = document.createElement('div');
    flashContainer.className = 'flash-messages';
    const flashMessage = document.createElement('div');
    flashMessage.className = 'flash-message error';
    flashMessage.textContent = 'The game has been ended by the host.';
    flashContainer.appendChild(flashMessage);

    // Insert the flash message at the top of the container
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(flashContainer, container.firstChild);
    }

    // Redirect to home page after a short delay
    setTimeout(function() {
        window.location.href = "/"; // Redirect to home page
    }, 2000);
}

document.addEventListener('DOMContentLoaded', function() {
    // Get room and player information from data attributes
    const gameRoomSection = document.querySelector('.page-section');
    if (!gameRoomSection) return;

    const roomId = gameRoomSection.dataset.roomId || '';
    const playerName = gameRoomSection.dataset.playerName || '';
    const isHost = (gameRoomSection.dataset.isHost === 'true');

    // Get DOM elements
    const statusUpdates = document.getElementById('status-updates');
    const leaderboardBody = document.getElementById('leaderboard-body');
    const currentPlayerElement = document.querySelector('.red-badge') || document.querySelector('.green-badge');
    const turnIndicator = document.querySelector('.turn-indicator');

    // State tracking variables
    let lastStatusUpdate = "";
    let lastQuestion = null;
    let lastLeaderboard = [];
    let lastEventTimestamp = null;
    let lastPlayerList = [];
    let gameEnded = false;

    // Make gameEnded accessible to window for navigation control
    window.gameEnded = false;

    // Function to poll for game updates
    function pollGameUpdates() {
        if (!roomId) return;

        fetch(`/api/game_updates/${roomId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                // Update current player
                if (currentPlayerElement) {
                    currentPlayerElement.textContent = data.current_player;
                    if (data.is_current_player_turn) {
                        currentPlayerElement.classList.add('your-turn');
                        if (turnIndicator) {
                            turnIndicator.textContent = "It's your turn!";
                        }
                    } else {
                        currentPlayerElement.classList.remove('your-turn');
                        if (turnIndicator) {
                            turnIndicator.textContent = `It's ${data.current_player}'s turn...`;
                        }
                    }
                }

                // Update player list if changed
                if (data.players && JSON.stringify(data.players) !== JSON.stringify(lastPlayerList)) {
                    lastPlayerList = data.players;
                    const playersElement = document.querySelector('.room-header p:nth-child(3)');
                    if (playersElement) {
                        playersElement.innerHTML = `<strong>Players:</strong> ${data.players.join(', ')}`;
                    }
                }

                // Update leaderboard if available and changed
                if (leaderboardBody && data.leaderboard && data.leaderboard.length > 0) {
                    if (JSON.stringify(data.leaderboard) !== JSON.stringify(lastLeaderboard)) {
                        lastLeaderboard = data.leaderboard;
                        leaderboardBody.innerHTML = '';
                        data.leaderboard.forEach((item, index) => {
                            const row = document.createElement('tr');
                            row.innerHTML = `
                                <td>${index + 1}</td>
                                <td>${item[0]}</td>
                                <td>${item[1]}</td>
                            `;
                            leaderboardBody.appendChild(row);
                        });
                    }
                }

                // Update status messages
                if (statusUpdates && data.events && data.events.length > 0) {
                    // Clear the "Waiting for game updates..." message if it's the first update
                    if (statusUpdates.querySelector('.status-message')?.textContent === 'Waiting for game updates...') {
                        statusUpdates.innerHTML = '';
                    }

                    // Add the most recent events (up to 20)
                    const recentEvents = data.events.slice(-20);
                    recentEvents.forEach(event => {
                        // Skip events we've already displayed
                        const existingMessages = Array.from(statusUpdates.querySelectorAll('.status-message')).map(el => el.dataset.timestamp);
                        if (existingMessages.includes(event.timestamp)) {
                            return;
                        }

                        // Track the latest event timestamp
                        if (!lastEventTimestamp || event.timestamp > lastEventTimestamp) {
                            lastEventTimestamp = event.timestamp;
                        }

                        const messageElement = document.createElement('p');
                        messageElement.className = 'status-message';
                        messageElement.textContent = event.data.message;
                        messageElement.dataset.timestamp = event.timestamp;

                        // Add appropriate class based on event type
                        if (event.type === 'answer_submitted') {
                            messageElement.classList.add(event.data.is_correct ? 'status-success' : 'status-error');
                        } else if (event.type === 'player_joined') {
                            messageElement.classList.add('status-info');
                        } else if (event.type === 'player_left') {
                            messageElement.classList.add('status-info');
                        } else if (event.type === 'question_selected') {
                            messageElement.classList.add('status-info');
                        } else if (event.type === 'answer_evaluated') {
                            messageElement.classList.add(event.data.is_correct ? 'status-success' : 'status-error');
                        } else if (event.type === 'turn_switch') {
                            messageElement.classList.add('status-info');
                        } else if (event.type === 'tool_used') {
                            messageElement.classList.add('status-warning');

                            // If the tool used is double_points, update the game board
                            if (event.data.tool_name === 'double_points' && typeof updateGameBoard === 'function') {
                                // Update the game board after a short delay to allow the status message to be seen
                                setTimeout(() => {
                                    updateGameBoard();
                                }, 1000);
                            }
                        } else if (event.type === 'game_ended') {
                            messageElement.classList.add('status-error');
                            // Set the gameEnded flag to allow navigation
                            window.gameEnded = true;
                            // Show a flash message and redirect to home page after a short delay
                            setTimeout(function() {
                                showGameEndedFlashAndRedirect();
                            }, 1000);
                        }

                        // Add to the top of the list
                        statusUpdates.insertBefore(messageElement, statusUpdates.firstChild);

                        // Limit the number of status updates to 20
                        while (statusUpdates.children.length > 20) {
                            statusUpdates.removeChild(statusUpdates.lastChild);
                        }
                    });
                }

                // Update player tools based on game state
                // gametoolsutil.js loads asynchronously; skip until it is ready.
                if (typeof window.updatePlayerToolsUtil === 'function') window.updatePlayerToolsUtil(data);

                // Check if the board needs to be refreshed (e.g., after a question is answered)
                if (data.current_question && data.current_question.id) {
                    if (!lastQuestion || lastQuestion.id !== data.current_question.id) {
                        lastQuestion = data.current_question;
                        // Update the board dynamically if we're on the game room page and updateGameBoard is defined
                        if (window.location.pathname.includes('/game_room/') && typeof updateGameBoard === 'function') {
                            setTimeout(() => {
                                updateGameBoard();
                            }, 5000); // Update after 5 seconds to allow time to see the question
                        }
                    }
                }

                // Always update the game board if we're on the game room page
                if (window.location.pathname.includes('/game_room/') && typeof updateGameBoard === 'function') {
                    updateGameBoard();
                }

                // Check if the game has ended via latest_events
                if (data.latest_events && data.latest_events.game_ended && !window.gameEnded) {
                    // Set the gameEnded flag to allow navigation
                    window.gameEnded = true;
                    // Show a flash message and redirect to home page after a short delay
                    setTimeout(function() {
                        showGameEndedFlashAndRedirect();
                    }, 1000);
                }
            })
            .catch(error => {
                console.error('Error fetching game updates:', error);

                // If we get a 404 error, it likely means the room has been deleted
                // This can happen when the host ends the game
                if (error.message.includes('not ok') && !window.gameEnded) {
                    // Set the gameEnded flag to allow navigation
                    window.gameEnded = true;
                    // Show a flash message and redirect to home page after a short delay
                    setTimeout(function() {
                        showGameEndedFlashAndRedirect();
                    }, 1000);
                }
            });
    }

    // Use updatePlayerTools from gametoolsutil.js

    // Poll for updates every 1 second
    pollGameUpdates(); // Initial poll
    setInterval(pollGameUpdates, 1000);

    // If this is the joined_room page, set up navigation prevention
    if (!isHost && window.location.pathname.includes('/joined_room/')) {
        // Store the original beforeunload function
        const originalBeforeUnload = window.onbeforeunload;

        // Set up the beforeunload event to prevent navigation
        window.onbeforeunload = function(e) {
            // Allow navigation when the game ends
            if (window.gameEnded) {
                return undefined;
            }

            // Get the target URL if available
            const targetUrl = e.target?.location?.href || '';

            // Allow navigation to the leave_game URL
            if (targetUrl.includes('leave_game')) {
                return undefined;
            }

            // Prevent navigation for all other cases
            e.preventDefault();
            e.returnValue = 'You cannot leave this page until the game ends or you click "Leave Game".';
            return e.returnValue;
        };

        // Add click handler to the Leave Game button to allow navigation
        const leaveGameButton = document.querySelector('a[href*="leave_game"]');
        if (leaveGameButton) {
            leaveGameButton.addEventListener('click', function() {
                // Disable the beforeunload handler temporarily
                window.onbeforeunload = null;
            });
        }
    }
});

// Once a question is picked, the board is frozen until the question page loads.
// Picking it uses up double points on the server at once, so a poll landing in
// that moment would redraw the board without its green double-points look.
let boardFrozen = false;
document.addEventListener('submit', function (e) {
    if (e.target && e.target.closest && e.target.closest('.question-box')) boardFrozen = true;
}, true);
window.addEventListener('pageshow', function (e) {
    if (e.persisted) boardFrozen = false;   // came back with the browser's Back button
});

// Game board update function (only used in game_room.html)
function updateGameBoard() {
    if (boardFrozen) return;
    const gameRoomSection = document.querySelector('.page-section');
    if (!gameRoomSection) return;

    const roomId = gameRoomSection.dataset.roomId || '';
    if (!roomId) return;

    fetch(`/api/game_updates/${roomId}`)
        .then(response => response.json())
        .then(data => {
            if (boardFrozen) return;   // a question was picked while this poll was in flight
            if (data.available_questions) {
                const gameBoardSection = document.querySelector('.game-board');
                if (!gameBoardSection) return;

                // Loop through categories and update or create them
                for (const categoryId in data.available_questions) {
                    // Find or create the category div
                    let categoryDiv = document.querySelector(`.category[data-category="${categoryId}"]`);
                    let questionList;

                    if (!categoryDiv) {
                        // Create new category div if it doesn't exist
                        categoryDiv = document.createElement('div');
                        categoryDiv.className = 'category';
                        categoryDiv.dataset.category = categoryId;

                        // Create category header
                        const categoryHeader = document.createElement('div');
                        categoryHeader.className = 'category-header-grid';
                        categoryHeader.textContent = categoryId.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());

                        // Create question list
                        questionList = document.createElement('div');
                        questionList.className = 'question-list';

                        // Assemble category div
                        categoryDiv.appendChild(categoryHeader);
                        categoryDiv.appendChild(questionList);

                        // Add to game board
                        gameBoardSection.appendChild(categoryDiv);
                    } else {
                        // Get existing question list
                        questionList = categoryDiv.querySelector('.question-list');
                    }

                    if (questionList) {
                        // Get all available questions for this category
                        const categoryQuestions = data.available_questions[categoryId];

                        // Process each score in the category. Several questions can share a
                        // score; they are shown as equal side-by-side buttons in one row.
                        for (const points in categoryQuestions) {
                            let infos = categoryQuestions[points];
                            if (!Array.isArray(infos)) infos = [infos];

                            // Check if this score row already exists
                            let questionItem = questionList.querySelector(`.question-item[data-points="${points}"]`);
                            if (!questionItem) {
                                questionItem = document.createElement('div');
                                questionItem.className = 'question-item';
                                questionItem.dataset.points = points;
                                questionList.appendChild(questionItem);
                            }
                            questionItem.classList.toggle('question-split', infos.length > 1);
                            questionItem.style.setProperty('--split', infos.length);

                            // Rebuild the buttons if the number of questions changed
                            if (questionItem.querySelectorAll('.question-button').length !== infos.length) {
                                questionItem.innerHTML = '';
                                infos.forEach((info) => {
                                    const form = document.createElement('form');
                                    form.action = '/select_question';
                                    form.method = 'post';
                                    form.className = 'question-box';
                                    const fields = { category_id: categoryId, points: points, question_id: info.id };
                                    Object.keys(fields).forEach((name) => {
                                        const input = document.createElement('input');
                                        input.type = 'hidden';
                                        input.name = name;
                                        input.value = fields[name];
                                        form.appendChild(input);
                                    });
                                    const actingPlayerInput = document.createElement('input');
                                    actingPlayerInput.type = 'hidden';
                                    actingPlayerInput.name = 'acting_player';
                                    actingPlayerInput.className = 'acting-player-input';
                                    actingPlayerInput.value = document.querySelector('.red-badge')?.textContent || '';
                                    form.appendChild(actingPlayerInput);
                                    const button = document.createElement('button');
                                    button.type = 'submit';
                                    button.className = 'question-button';
                                    button.dataset.questionId = info.id;
                                    form.appendChild(button);
                                    questionItem.appendChild(form);
                                });
                            }

                            // Update each button (whether new or existing)
                            const buttons = questionItem.querySelectorAll('.question-button');
                            infos.forEach((info, i) => {
                                const button = buttons[i];
                                if (!button) return;
                                button.innerHTML = `<strong>${info.points}${info.doubled ? '!' : ''}</strong>`;
                                button.disabled = info.answered;
                                button.style.cursor = info.answered ? 'not-allowed' : 'pointer';
                                button.classList.toggle('doubled', info.doubled);
                                button.title = info.doubled ? 'Double Points Active!' : '';
                            });
                        }
                    }
                }
            }
        })
        .catch(error => console.error('Error updating game board:', error));
}
